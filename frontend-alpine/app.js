// GPU-Pool Frontend - shared logic
// Vanilla JS, Alpine.js for reactivity. Talks to backend at /api/* (proxied by nginx).

const API_BASE = "/api"; // same-origin; nginx strips /api prefix before proxying

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
    if (!key) throw new Error("Not logged in");
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
    // 'role' may or may not be present on the user object (older callers);
    // default to 'both' so the UI treats unknown roles as fully featured.
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
      toast("Provider-Bereich — wechsle deine Rolle im Profil.", "err");
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
  try { return new Date(s).toLocaleString("de-DE"); } catch { return s; }
}
function timeAgo(s) {
  if (!s) return "—";
  const diff = (Date.now() - new Date(s).getTime()) / 1000;
  if (diff < 60) return `${Math.floor(diff)}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

// ---------- Nav HTML (used on protected pages) ----------
function navHTML(active) {
  const user = Auth.currentUser() || {};
  const isProvider = Auth.hasRole("provider");
  return `
    <nav class="flex items-center justify-between px-6 py-4 max-w-6xl mx-auto">
      <a href="index.html" class="text-xl font-bold gradient-text">⚡ GPU-Pool</a>
      <div class="flex items-center gap-1">
        <a href="index.html" class="nav-link ${active === "dashboard" ? "active" : ""}">Dashboard</a>
        <a href="chat.html" class="nav-link ${active === "chat" ? "active" : ""}">Chat</a>
        
        <a href="pool.html" class="nav-link ${active === "pool" ? "active" : ""}">Pool</a>
        ${isProvider ? `<a href="nodes.html" class="nav-link ${active === "nodes" ? "active" : ""}">Nodes</a>` : ""}
        ${isProvider ? `<a href="earnings.html" class="nav-link ${active === "earnings" ? "active" : ""}">Earnings</a>` : ""}
        <a href="agent.html" class="nav-link ${active === "agent" ? "active" : ""}">Agent</a>
        <a href="profile.html" class="nav-link ${active === "profile" ? "active" : ""}">Profil</a>
      </div>
      <div class="flex items-center gap-3 text-sm">
        <span class="text-[color:var(--text-dim)]">${user.email || ""} <span class="text-xs opacity-60">(${user.role || "both"})</span></span>
        <button onclick="Auth.logout()" class="btn-ghost">Logout</button>
      </div>
    </nav>
  `;
}

// ---------- Simple inline bar chart (usage by day) ----------
function renderUsageChart(canvasId, dataPoints) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width = canvas.clientWidth * 2;
  const h = canvas.height = canvas.clientHeight * 2;
  ctx.scale(2, 2);
  const W = canvas.clientWidth;
  const H = canvas.clientHeight;
  ctx.clearRect(0, 0, W, H);

  if (!dataPoints || dataPoints.length === 0) {
    ctx.fillStyle = "#9aa3c0";
    ctx.font = "13px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("No usage yet", W / 2, H / 2);
    return;
  }

  const max = Math.max(...dataPoints.map(d => d.value), 1);
  const pad = 24;
  const barW = (W - pad * 2) / dataPoints.length - 6;
  const gradient = ctx.createLinearGradient(0, 0, 0, H);
  gradient.addColorStop(0, "#8b5cf6");
  gradient.addColorStop(1, "#6366f1");

  dataPoints.forEach((d, i) => {
    const x = pad + i * ((W - pad * 2) / dataPoints.length) + 3;
    const barH = (d.value / max) * (H - 40);
    const y = H - 20 - barH;
    ctx.fillStyle = gradient;
    ctx.beginPath();
    ctx.roundRect ? ctx.roundRect(x, y, barW, barH, 4) : ctx.fillRect(x, y, barW, barH);
    ctx.fill();
    ctx.fillStyle = "#9aa3c0";
    ctx.font = "10px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(d.label, x + barW / 2, H - 6);
  });
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
window.renderUsageChart = renderUsageChart;
window.refreshUser = refreshUser;
