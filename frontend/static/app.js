/* GPU-Pool POC — shared client side helpers
 * Stores the API key in localStorage. Every fetch automatically attaches
 * `Authorization: Bearer <key>`. Also exposes a thin .get/.post wrapper.
 */
const API = (() => {
  const KEY_LS = "gpu_pool_key";
  const USER_LS = "gpu_pool_user";

  const getKey = () => localStorage.getItem(KEY_LS) || "";
  const setKey = (k) => localStorage.setItem(KEY_LS, k);
  const getUser = () => JSON.parse(localStorage.getItem(USER_LS) || "null");
  const setUser = (u) => localStorage.setItem(USER_LS, JSON.stringify(u));
  const clear = () => { localStorage.removeItem(KEY_LS); localStorage.removeItem(USER_LS); };

  async function call(method, path, body) {
    const headers = { "Content-Type": "application/json" };
    const k = getKey();
    if (k) headers["Authorization"] = `Bearer ${k}`;
    const resp = await fetch(path, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });
    const text = await resp.text();
    let data;
    try { data = text ? JSON.parse(text) : {}; } catch { data = { detail: text }; }
    if (!resp.ok) {
      const msg = data.detail || data.message || resp.statusText;
      if (resp.status === 401) clear();
      throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
    }
    return data;
  }

  return {
    get: (p) => call("GET", p),
    post: (p, body) => call("POST", p, body),
    setKey, setUser, getUser, clear,
    refreshMe: async () => {
      try {
        const me = await call("GET", "/v1/me");
        setUser(me);
        renderWho();
        return me;
      } catch (e) { console.warn("refreshMe failed", e); }
    },
  };
})();

async function renderWho() {
  const el = document.getElementById("who");
  if (!el) return;
  const me = API.getUser();
  if (me && me.email) {
    el.innerHTML = `👤 <b>${me.email}</b> · <span class="muted">${Number(me.credits).toFixed(2)} credits</span> · <a href="#" onclick="API.clear(); location.href='/'; return false;">logout</a>`;
  } else {
    el.innerHTML = `<a href="/">Login</a>`;
  }
}

// WS chat (LANA-112): prefer WebSocket transport (CF-tunnel-safe), fall back
// to HTTP /v1/chat/completions if the handshake fails. The API key rides in
// the Sec-WebSocket-Protocol subprotocol (api-key.<raw>) so it never lands in
// proxy/Cloudflare URL logs; ?api_key= stays a documented server-side fallback.
// chunk frames are progress-rendered; keepalive frames are ignored.
API.chatCompletion = async function ({ model, messages, stream = false, onChunk = null, temperature, max_tokens }) {
  const key = getKey();
  if (!key) throw new Error("Not logged in");
  const body = { model, messages, stream };
  if (temperature != null) body.temperature = temperature;
  if (max_tokens != null) body.max_tokens = max_tokens;

  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${proto}//${location.host}/ws/chat`;
  const ws = await new Promise((resolve, reject) => {
    let sock;
    try { sock = new WebSocket(wsUrl, [`api-key.${key}`]); }
    catch (e) { reject(e); return; }
    const timer = setTimeout(() => { try { sock.close(); } catch {} reject(new Error("ws handshake timeout")); }, 8000);
    sock.onopen = () => { clearTimeout(timer); resolve(sock); };
    sock.onerror = () => { clearTimeout(timer); reject(new Error("ws handshake failed")); };
  });

  try {
    return await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("ws chat timeout")), 300000);
      ws.onmessage = (ev) => {
        let f; try { f = JSON.parse(ev.data); } catch { return; }
        switch (f.type) {
          case "keepalive":
          case "hello":
          case "status":
            break;
          case "chunk":
            if (onChunk) onChunk(f.delta || "");
            break;
          case "error":
            clearTimeout(timer); ws.close();
            reject(new Error(`Upstream-Fehler (WS ${f.status})`));
            break;
          case "final":
            clearTimeout(timer); ws.close();
            resolve({ choices: [{ message: { role: "assistant", content: f.content || "" } }],
                      usage: f.usage || { total_tokens: 0 }, transport: "ws" });
            break;
          default:
            break;
        }
      };
      ws.onerror = () => { clearTimeout(timer); reject(new Error("ws connection lost")); };
      // (LANA-113 A) A clean close from an intermediary fires onclose without
      // onerror — reject immediately so the HTTP fallback kicks in instead of
      // waiting out the 300 s timer. Already-settled promises ignore this.
      ws.onclose = () => { clearTimeout(timer); reject(new Error("ws closed")); };
      ws.send(JSON.stringify({ id: `c${Date.now()}`, ...body }));
    });
  } catch (e) {
    try { ws.close(); } catch {}
    throw e;
  }
};
