// CoMesh — shared client (Alpine frontend)
// Vanilla JS + Alpine.js. Talks to the backend at API_BASE + path.
//
// The base URL is resolved at runtime by config.js (?api= → localStorage →
// config.js global → same-origin /api); no address is baked into this file.
//
// This file also owns the app-wide chrome: the animated background field is
// injected here, so every view gets the identical effect and it can never
// drift between pages.

// Fallback only for the case where config.js was not loaded (e.g. an old cached
// HTML shell). Same-origin /api is the deployment default.
const API_BASE = (typeof window !== "undefined" && window.API_BASE) || "/api";

// ---------- LocalStorage helpers ----------
const LS = {
  get(key, fallback = null) {
    try {
      const v = localStorage.getItem(key);
      return v == null ? fallback : JSON.parse(v);
    } catch { return fallback; }
  },
  set(key, value) { localStorage.setItem(key, JSON.stringify(value)); },
  del(key) { localStorage.removeItem(key); },
};

// ---------- API client ----------
async function api(path, { method = "GET", body = null, auth = false, raw = false } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (auth) {
    const key = LS.get("api_key");
    if (!key) throw new Error(I18n.t("app.login_required"));
    headers["Authorization"] = `Bearer ${key}`;
  }
  const res = await fetch(API_BASE + path, {
    method,
    headers,
    body: body ? JSON.stringify(body) : null,
  });
  if (raw) return res;
  const text = await res.text();
  let data;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!res.ok) {
    const detail = (data && data.detail) || (typeof data === "string" ? data : `HTTP ${res.status}`);
    throw new Error(detail);
  }
  return data;
}

// ---------- Auth ----------
const Auth = {
  isLoggedIn() { return !!LS.get("api_key"); },
  currentUser() { return LS.get("user"); },
  logout() { LS.del("api_key"); LS.del("user"); window.location.href = "login.html"; },
  requireLogin() {
    if (!this.isLoggedIn()) { window.location.href = "login.html"; return false; }
    return true;
  },
  save(user, apiKey) {
    // 'role' may be missing on older callers; default to 'both' so the UI
    // treats unknown roles as fully featured.
    if (user && !user.role) user.role = "both";
    LS.set("user", user);
    LS.set("api_key", apiKey);
  },
  /**
   * Role checks. 'both' is treated as both provider and consumer.
   * @param {"provider"|"consumer"} role
   * @returns {boolean}
   */
  hasRole(role) {
    const u = this.currentUser() || {};
    const r = u.role || "both";
    if (r === "both") return true;
    return r === role;
  },
  /** Convenience: consumer-only users get bounced away from provider pages. */
  requireProviderOrRedirect(target = "chat.html") {
    if (!this.isLoggedIn()) { window.location.href = "login.html"; return false; }
    if (!this.hasRole("provider")) {
      toast(I18n.t("app.provider_required"), "err");
      window.location.href = target;
      return false;
    }
    return true;
  },
};

// ---------- Toast notifications ----------
function toast(msg, kind = "ok", timeout = 3500) {
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => { el.style.opacity = "0"; el.style.transition = "opacity 0.3s"; }, timeout - 300);
  setTimeout(() => el.remove(), timeout);
}

// ---------- Format helpers ----------
function fmtCredits(n) {
  if (n == null) return "—";
  const v = Number(n);
  if (Math.abs(v) >= 1) return v.toFixed(2);
  return v.toFixed(4);
}
function fmtNumber(n) {
  if (n == null) return "—";
  return Number(n).toLocaleString("de-DE");
}
function fmtDate(s) {
  if (!s) return "—";
  try {
    return new Date(s).toLocaleString("de-DE", {
      day: "2-digit", month: "2-digit", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch { return s; }
}
function timeAgo(s) {
  if (!s) return "—";
  const diff = (Date.now() - new Date(s).getTime()) / 1000;
  if (diff < 60) return `vor ${Math.floor(diff)}s`;
  if (diff < 3600) return `vor ${Math.floor(diff / 60)}m`;
  if (diff < 86400) return `vor ${Math.floor(diff / 3600)}h`;
  return `vor ${Math.floor(diff / 86400)}d`;
}

// ---------- App-wide background field ----------
// Rendered from JS so it is guaranteed present (and identical) on every view,
// including new pages added later. CSS-only animation — see style.css.
function mountBackground() {
  if (document.querySelector(".bg-field")) return;
  const field = document.createElement("div");
  field.className = "bg-field";
  field.setAttribute("aria-hidden", "true");
  field.innerHTML = `
    <div class="bg-grid"></div>
    <div class="bg-glow"></div>
    <div class="bg-grain"></div>
  `;
  document.body.insertBefore(field, document.body.firstChild);
}

// ---------- Chrome (topbar + footer) ----------
// Labels are catalog *keys* resolved at render time, never pre-translated
// strings: this array is evaluated once at load, so a stored translation here
// would freeze the nav in whatever language was active on the first paint.
const NAV_ITEMS = [
  { key: "dashboard", href: "index.html", labelKey: "nav.dashboard" },
  { key: "chat", href: "chat.html", labelKey: "nav.chat" },
  { key: "usage", href: "usage.html", labelKey: "nav.usage", label: "Mein Verbrauch" },
  // Admin-only view of every user's consumption; the server gates /admin/usage too.
  { key: "admin-usage", href: "admin-usage.html", labelKey: "nav.admin", label: "Verbrauch (alle)", adminOnly: true },
  { key: "admin-registrations", href: "admin-registrations.html", labelKey: "nav.admin", label: "Freigaben", adminOnly: true },
  { key: "admin-audit", href: "admin-audit.html", labelKey: "nav.admin", label: "Protokoll", adminOnly: true },
  { key: "pool", href: "pool.html", labelKey: "nav.pool" },
  { key: "nodes", href: "nodes.html", labelKey: "nav.nodes", providerOnly: true },
  { key: "agent", href: "agent.html", labelKey: "nav.agent" },
  { key: "profile", href: "profile.html", labelKey: "nav.profile" },
];

function navHTML(active) {
  const user = Auth.currentUser() || {};
  const isProvider = Auth.hasRole("provider");
  // Deliberately NOT Auth.hasRole("admin"): that helper treats role "both" as
  // satisfying any role, which would show the Admin tab to every normal user.
  // Admin is a privileged role, never implied by "both".
  const isAdmin = ((user.role || "both") || "").toLowerCase() === "admin";
  const links = NAV_ITEMS
    .filter((i) => !i.providerOnly || isProvider)
    .filter((i) => !i.adminOnly || isAdmin)
    .map((i) => `<a href="${i.href}" class="nav-link${active === i.key ? " active" : ""}">${i.label || I18n.t(i.labelKey)}</a>`)
    .join("");

  return `
    <header class="topbar topbar-2row">
      <div class="shell topbar-inner">
        <a href="index.html" class="brand">
          <span class="brand-mark" aria-hidden="true">
            <!-- Marke: eine Mesh-Zelle — Sechseck mit drei verbundenen Knoten.
                 Gleiche Bildsprache wie die Animation daneben, nur als Zeichen. -->
            <svg class="brand-glyph" width="26" height="26" viewBox="0 0 24 24" fill="none"
                 stroke="currentColor" stroke-width="1.35" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 2.7 20.1 7.35v9.3L12 21.3 3.9 16.65v-9.3z"/>
              <path d="M12 7.6 16.2 15.1H7.8z" stroke-opacity="0.5"/>
              <circle cx="12" cy="7.6" r="1.55" fill="currentColor" stroke="none"/>
              <circle cx="16.2" cy="15.1" r="1.55" fill="currentColor" stroke="none"/>
              <circle cx="7.8" cy="15.1" r="1.55" fill="currentColor" stroke="none"/>
              <circle cx="12" cy="12.1" r="0.9" fill="currentColor" stroke="none" fill-opacity="0.55"/>
            </svg>
          </span>
          <span class="brand-text">
            <strong>CoMesh</strong>
            <span>${I18n.t("brand.tagline")}</span>
          </span>
        </a>
        <!-- Miniatur der Deck-Szene: Knoten, Leitungen, wandernde Pakete.
             Bewusst ausserhalb des Links, damit ein Klick nichts ausloest. -->
        <canvas id="brand-mesh" class="brand-mesh" aria-hidden="true"></canvas>
        <div class="topbar-right">
          <div class="controls"></div>
          <span class="who">
            <b>${user.email || ""}</b>
            <em>${user.role || "both"}</em>
          </span>
          <button type="button" class="btn-ghost btn-sm" onclick="Auth.logout()">${I18n.t("nav.logout.button")}</button>
        </div>
      </div>
      <div class="shell topbar-row-nav">
        <nav class="nav" aria-label="${I18n.t("nav.aria")}">${links}</nav>
      </div>
    </header>
  `;
}

function footerHTML() {
  return `
    <footer class="site-foot">
      <span>${I18n.t("foot.text")}</span>
    </footer>
  `;
}

// ---------- Inline usage chart (usage by day) ----------
function renderUsageChart(canvasId, dataPoints) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const cssW = canvas.clientWidth || 600;
  const cssH = canvas.clientHeight || 180;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = cssW * dpr;
  canvas.height = cssH * dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, cssW, cssH);

  const W = cssW, H = cssH;
  const style = getComputedStyle(document.documentElement);
  const dim = style.getPropertyValue("--text-mute").trim() || "#8d97a2";
  const brass = style.getPropertyValue("--brass").trim() || "#c9a24a";

  const hasData = dataPoints && dataPoints.some((d) => Number(d.value) > 0);
  if (!hasData) {
    ctx.fillStyle = dim;
    ctx.font = "12px 'JetBrains Mono', monospace";
    ctx.textAlign = "center";
    ctx.fillText(I18n.t("chart.no_usage"), W / 2, H / 2);
    return;
  }

  const max = Math.max(...dataPoints.map((d) => Number(d.value)), 1);
  const padL = 34, padR = 10, padT = 12, padB = 26;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;
  const slot = plotW / dataPoints.length;
  const barW = Math.max(6, slot - 12);

  // baseline + horizontal guides
  ctx.strokeStyle = "rgba(255,255,255,0.07)";
  ctx.lineWidth = 1;
  for (let g = 0; g <= 3; g++) {
    const y = padT + (plotH / 3) * g + 0.5;
    ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(W - padR, y); ctx.stroke();
    ctx.fillStyle = dim;
    ctx.font = "10px 'JetBrains Mono', monospace";
    ctx.textAlign = "right";
    ctx.fillText(fmtShort(max - (max / 3) * g), padL - 7, y + 3);
  }

  dataPoints.forEach((d, i) => {
    const v = Number(d.value) || 0;
    const barH = (v / max) * plotH;
    const x = padL + i * slot + (slot - barW) / 2;
    const y = padT + plotH - barH;
    if (barH > 0.5) {
      const grad = ctx.createLinearGradient(0, y, 0, padT + plotH);
      grad.addColorStop(0, "#e2c885");
      grad.addColorStop(1, brass);
      ctx.fillStyle = grad;
      if (ctx.roundRect) {
        ctx.beginPath();
        ctx.roundRect(x, y, barW, barH, 3);
        ctx.fill();
      } else {
        ctx.fillRect(x, y, barW, barH);
      }
    }
    ctx.fillStyle = dim;
    ctx.font = "10px 'JetBrains Mono', monospace";
    ctx.textAlign = "center";
    ctx.fillText(String(d.label || ""), x + barW / 2, H - 8);
  });
}

function fmtShort(n) {
  const v = Number(n) || 0;
  if (v >= 1e6) return (v / 1e6).toFixed(1) + "M";
  if (v >= 1e3) return (v / 1e3).toFixed(1) + "k";
  return v.toFixed(v >= 10 ? 0 : 1);
}

// ---------- Refresh user info (call after credit changes) ----------
async function refreshUser() {
  try {
    const me = await api("/v1/me", { auth: true });
    LS.set("user", me);
    return me;
  } catch (e) {
    if (String(e.message).toLowerCase().includes("api key")) {
      Auth.logout();
    }
    throw e;
  }
}

// ---------- Bootstrap: background + footer on every page ----------
mountBackground();
document.addEventListener("DOMContentLoaded", () => {
  mountBackground();
  // The footer is appended (not templated) so pages don't each need a placeholder.
  if (!document.querySelector(".site-foot")) {
    const holder = document.createElement("div");
    holder.innerHTML = footerHTML();
    document.body.appendChild(holder.firstElementChild);
  }
});

/**
 * Die Rolle kann serverseitig wechseln (ein Admin ernennt jemanden). Der
 * zwischengespeicherte Nutzer in localStorage wird nur beim Login geschrieben,
 * deshalb hier einmal pro Seitenaufbau erneuern — sonst bleibt der Admin-Tab
 * verborgen, bis man sich von Hand neu anmeldet. Ein einmaliger Reload laesst
 * Alpine die Navigation mit der neuen Rolle zeichnen.
 */
document.addEventListener("DOMContentLoaded", async () => {
  if (!Auth.isLoggedIn()) return;
  let vorher = "";
  try { vorher = ((Auth.currentUser() || {}).role || "").toLowerCase(); } catch (e) { /* egal */ }
  try {
    const me = await refreshUser();
    const nachher = ((me && me.role) || "").toLowerCase();
    if (nachher && nachher !== vorher && !sessionStorage.getItem("nav_role_reload")) {
      sessionStorage.setItem("nav_role_reload", "1");
      window.location.reload();
    } else if (nachher && nachher === vorher) {
      sessionStorage.removeItem("nav_role_reload");
    }
  } catch (e) { /* offline oder Schluessel ungueltig: zwischengespeicherten Nutzer stehen lassen */ }
});

/**
 * On narrow screens the nav becomes a horizontal scroller. Scroll the active
 * link into view so the current section is never hidden off-screen.
 * Nav markup is injected by Alpine, so watch for it instead of guessing a delay.
 */
function revealActiveNav() {
  const active = document.querySelector(".nav .nav-link.active");
  if (!active) return false;
  const nav = active.parentElement;
  // Nothing to do when every link already fits.
  if (nav.scrollWidth <= nav.clientWidth + 4) return true;
  const target = active.offsetLeft - (nav.clientWidth - active.offsetWidth) / 2;
  nav.scrollLeft = Math.max(0, Math.min(target, nav.scrollWidth - nav.clientWidth));
  return true;
}

if (typeof MutationObserver !== "undefined") {
  const mo = new MutationObserver(() => {
    if (revealActiveNav()) mo.disconnect();
  });
  const start = () => mo.observe(document.body, { childList: true, subtree: true });
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
}
window.addEventListener("resize", revealActiveNav);
window.addEventListener("load", revealActiveNav);

// Expose helpers globally
window.API = api;
window.Auth = Auth;
window.LS = LS;
window.toast = toast;
window.fmtCredits = fmtCredits;
window.fmtNumber = fmtNumber;
window.fmtDate = fmtDate;
window.timeAgo = timeAgo;
window.navHTML = navHTML;
window.footerHTML = footerHTML;
window.mountBackground = mountBackground;
window.renderUsageChart = renderUsageChart;
window.refreshUser = refreshUser;

// ---------- WS chat (LANA-112) ----------
// Prefer WebSockets for /v1-style chat (CF-tunnel-safe, no 100 s HTTP cap).
// The API key is transported in the Sec-WebSocket-Protocol subprotocol
// (api-key.<raw>) so it never lands in proxy/Cloudflare URL logs; the
// ?api_key= query param exists server-side only as a documented fallback.
// On handshake/open failure we fall back to plain HTTP automatically.
// Server frames: hello | keepalive (ignored) | status | chunk (progress
// rendering of the finished answer, not token streaming) | final | error.
async function apiChatCompletion({ model, messages, stream = false, onChunk = null, temperature, max_tokens }) {
  const key = LS.get("api_key");
  if (!key) throw new Error(I18n.t("app.login_required"));
  const body = { model, messages, stream };
  if (temperature != null) body.temperature = temperature;
  if (max_tokens != null) body.max_tokens = max_tokens;

  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${proto}//${location.host}${API_BASE ? API_BASE.replace(/\/$/, "") : ""}/ws/chat`;
  const ws = await new Promise((resolve, reject) => {
    let sock;
    try {
      sock = new WebSocket(wsUrl, [`api-key.${key}`]);
    } catch (e) { reject(e); return; }
    const timer = setTimeout(() => {
      try { sock.close(); } catch {}
      reject(new Error("ws handshake timeout"));
    }, 8000);
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
            break; // progress signals — nothing to render for status today
          case "chunk":
            if (onChunk) onChunk(f.delta || "");
            break;
          case "error":
            clearTimeout(timer);
            ws.close();
            reject(new Error(`Upstream-Fehler (WS ${f.status})`));
            break;
          case "final":
            clearTimeout(timer);
            ws.close();
            resolve({
              choices: [{ message: { role: "assistant", content: f.content || "" } }],
              usage: f.usage || { total_tokens: 0 },
              transport: "ws",
            });
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
}
window.apiChatCompletion = apiChatCompletion;
