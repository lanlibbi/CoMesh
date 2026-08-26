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
