// GPU-Pool — shared client (Alpine frontend)
// Vanilla JS + Alpine.js. Talks to the backend at /api/* (proxied by nginx).
//
// This file also owns the app-wide chrome: the animated background field is
// injected here, so every view gets the identical effect and it can never
// drift between pages.

const API_BASE = "/api"; // same-origin; nginx strips the /api prefix before proxying

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
      toast("Der Provider-Bereich braucht die Rolle „Provider" + "“ oder „beides" + "“ — im Profil umstellbar.", "err");
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
const NAV_ITEMS = [
  { key: "dashboard", href: "index.html", label: "Dashboard" },
  { key: "chat", href: "chat.html", label: "Chat" },
  { key: "usage", href: "usage.html", label: "Usage" },
  { key: "pool", href: "pool.html", label: "Pool" },
  { key: "nodes", href: "nodes.html", label: "Nodes", providerOnly: true },
  { key: "earnings", href: "earnings.html", label: "Earnings", providerOnly: true },
  { key: "agent", href: "agent.html", label: "Agent" },
  { key: "profile", href: "profile.html", label: "Profil" },
];

function navHTML(active) {
  const user = Auth.currentUser() || {};
  const isProvider = Auth.hasRole("provider");
  const links = NAV_ITEMS
    .filter((i) => !i.providerOnly || isProvider)
    .map((i) => `<a href="${i.href}" class="nav-link${active === i.key ? " active" : ""}">${i.label}</a>`)
    .join("");

  return `
    <header class="topbar">
      <div class="shell topbar-inner">
        <a href="index.html" class="brand">
          <span class="brand-mark" aria-hidden="true">
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                 stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
              <path d="M13 2 4.5 13.5H11l-1 8.5 8.5-11.5H12l1-8.5Z"/>
            </svg>
          </span>
          <span class="brand-text">
            <strong>GPU-Pool</strong>
            <span>Community Compute</span>
          </span>
        </a>
        <nav class="nav" aria-label="Hauptnavigation">${links}</nav>
        <div class="topbar-right">
          <span class="who">
            <b>${user.email || ""}</b>
            <em>${user.role || "both"}</em>
          </span>
          <button type="button" class="btn-ghost btn-sm" onclick="Auth.logout()">Logout</button>
        </div>
      </div>
    </header>
  `;
}

function footerHTML() {
  return `
    <footer class="site-foot">
      <span>GPU-Pool · selbstgehosteter Community-Compute-Pool</span>
      <span class="mono">Owner 70 % · Platform 20 % · Treasury 10 %</span>
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
    ctx.fillText("noch keine Nutzung erfasst", W / 2, H / 2);
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
