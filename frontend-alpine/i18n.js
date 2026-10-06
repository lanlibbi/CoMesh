// CoMesh — theme + language runtime.
//
// Two things every page needs before it paints:
//
//   1. THEME. Dark (anthracite) is the default. An explicit choice in
//      localStorage wins; otherwise the OS setting decides for first-time
//      visitors. The choice is written to <html data-theme> by the *inline*
//      boot script in each page head (before the first paint), so switching
//      cannot flash the wrong palette. This file re-applies it and owns the
//      toggle.
//
//   2. LANGUAGE. Four locales — EN (default), DE, ES, FR — persisted in
//      localStorage. PT and ZH are deliberately NOT implemented (LANA-65);
//      adding one means re-making that decision, not just adding a column, so
//      the catalog build check in i18n/build_catalog.py gates the count. Every
//      visitor-facing string lives in i18n-catalog.js and is applied to the
//      static markup through data-i18n* attributes, so a page that never runs
//      JS is still fully translated.
//
// Neither palettes nor words live here: style.css owns the colours, the catalog
// owns the strings.

const PREF = { THEME: "gp_theme", LANG: "gp_lang" };
const THEMES = ["dark", "light"];
const DEFAULT_THEME = "dark"; // anthracite is the product default
const FALLBACK_LANG = "en";   // product default language

/** Raw (not JSON) so the inline head script can read the same value cheaply. */
function prefGet(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}
function prefSet(key, value) {
  try { localStorage.setItem(key, value); } catch { /* private mode */ }
}

/** Theme to apply now: explicit choice, else the OS, else dark. */
function resolveTheme() {
  const stored = prefGet(PREF.THEME);
  if (THEMES.includes(stored)) return stored;
  try {
    if (window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches) {
      return "light";
    }
  } catch { /* no matchMedia: stay dark */ }
  return DEFAULT_THEME;
}

const Theme = {
  current() {
    return document.documentElement.getAttribute("data-theme") || resolveTheme();
  },
  apply(name, { persist = true } = {}) {
    const theme = THEMES.includes(name) ? name : DEFAULT_THEME;
    document.documentElement.setAttribute("data-theme", theme);
    if (persist) prefSet(PREF.THEME, theme);
    if (typeof window.redrawCharts === "function") window.redrawCharts();
    document.dispatchEvent(new CustomEvent("theme:changed", { detail: { theme } }));
    return theme;
  },
  toggle() {
    return this.apply(this.current() === "dark" ? "light" : "dark");
  },
  /** True while the visitor has never chosen — then we follow the OS live. */
  isFollowingOS() {
    return !THEMES.includes(prefGet(PREF.THEME));
  },
};

try {
  if (window.matchMedia) {
    const mq = window.matchMedia("(prefers-color-scheme: light)");
    const onChange = () => {
      if (Theme.isFollowingOS()) Theme.apply(resolveTheme(), { persist: false });
    };
    if (mq.addEventListener) mq.addEventListener("change", onChange);
    else if (mq.addListener) mq.addListener(onChange);
  }
} catch { /* ignore */ }

// ------------------------------------------------------------------- i18n
const DATA = window.GP_I18N || { locales: [], meta: [], catalog: {} };

const I18n = {
  get lang() {
    const stored = prefGet(PREF.LANG);
    return DATA.locales.includes(stored) ? stored : FALLBACK_LANG;
  },
  get locales() { return DATA.locales; },
  get localeList() { return DATA.meta; },

  /** Key -> active language, then fallback language, then the key itself. */
  t(key, params) {
    if (key == null) return "";
    const entry = DATA.catalog[key];
    let value = entry
      ? (entry[this.lang] ?? entry[FALLBACK_LANG] ?? entry.de ?? key)
      : key;
    if (params) {
      value = String(value).replace(/\{(\w+)\}/g, (m, name) =>
        Object.prototype.hasOwnProperty.call(params, name) ? params[name] : m);
    }
    return value;
  },

  /**
   * Translate the static markup of this document.
   *
   * data-i18n           element text -> textContent
   * data-i18n-html      element body -> innerHTML (the value carries its markup)
   * data-i18n-<attr>    attribute    -> setAttribute
   *
   * Conservative on purpose: an element is skipped while it still contains
   * individually keyed children, otherwise we would flatten them.
   */
  apply(root) {
    const scope = root || document;

    scope.querySelectorAll("[data-i18n-html]").forEach((el) => {
      el.innerHTML = this.t(el.getAttribute("data-i18n-html"));
    });

    ["placeholder", "title", "aria-label"].forEach((attr) => {
      scope.querySelectorAll(`[data-i18n-${attr}]`).forEach((el) => {
        el.setAttribute(attr, this.t(el.getAttribute(`data-i18n-${attr}`)));
      });
    });

    scope.querySelectorAll("[data-i18n]").forEach((el) => {
      let node = el;
      if (node.hasAttribute("data-i18n-html")) return;
      if (node.querySelector("[data-i18n]")) return;
      el.textContent = this.t(el.getAttribute("data-i18n"));
    });

    document.documentElement.setAttribute("lang", this.lang);
    const title = document.querySelector("title[data-i18n]");
    if (title) document.title = this.t(title.getAttribute("data-i18n"));
  },

  /** Persist, re-render markup and let the page refresh its Alpine strings. */
  set(lang) {
    if (!DATA.locales.includes(lang)) return this.lang;
    prefSet(PREF.LANG, lang);
    syncAlpineStore();
    this.apply();
    mountChrome();
    // The store drives bound markup (the nav); the explicit event covers any
    // page that binds its own strings.
    document.dispatchEvent(new CustomEvent("lang:changed", { detail: { lang } }));
    return lang;
  },
};

/**
 * Alpine bridge.
 *
 * `$store.lang` is the DOM-side view of the active language, so bound markup
 * (the nav) re-renders from the same source of truth as the static markup.
 * Alpine is a `defer` script and therefore executes *after* this file; its own
 * start (on DOMContentLoaded) dispatches `alpine:init` immediately followed by
 * the first render of `x-data` components. Registering the store on that event
 * is the only reliable moment: it is after Alpine exists and before anything
 * that reads the store is evaluated.
 */
function mountAlpineStore() {
  if (!window.Alpine || typeof window.Alpine.store !== "function") return false;
  try {
    window.Alpine.store("lang", { code: I18n.lang });
    return true;
  } catch { return false; }
}

function syncAlpineStore() {
  try {
    const store = window.Alpine && window.Alpine.store ? window.Alpine.store("lang") : null;
    if (store) store.code = I18n.lang;
  } catch { /* no Alpine on this page */ }
}

document.addEventListener("alpine:init", () => {
  mountAlpineStore();
  // The store is only knowable at this point, so the first render of the nav
  // waits for it instead of painting an empty topbar.
  I18n.apply();
  mountChrome();
});

/** BCP-47 tag for Intl formatting, keyed off the active language. */
function localeTag() {
  return { en: "en-GB", de: "de-DE", es: "es-ES", fr: "fr-FR" }[I18n.lang] || "en-GB";
}

// --------------------------------------------------------------- chrome UI
const ICON = {
  dark: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z"/></svg>`,
  light: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>`,
};

function themeToggleHTML() {
  const dark = Theme.current() === "dark";
  const label = (t) => I18n.t(t);
  return `
    <div class="seg" role="group" aria-label="${I18n.t("chrome.theme")}">
      <button type="button" class="seg-btn" data-theme-set="dark"
              aria-pressed="${dark}" title="${label("chrome.theme.dark")}">
        ${ICON.dark}<span class="seg-lab">${label("chrome.theme.dark.short")}</span>
      </button>
      <button type="button" class="seg-btn" data-theme-set="light"
              aria-pressed="${!dark}" title="${label("chrome.theme.light")}">
        ${ICON.light}<span class="seg-lab">${label("chrome.theme.light.short")}</span>
      </button>
    </div>`;
}

function langSwitchHTML() {
  const cur = I18n.lang;
  const items = I18n.localeList.map((l) => `
      <button type="button" class="lang-item" role="menuitemradio"
              data-lang-set="${l.code}" aria-checked="${l.code === cur}">
        <span class="code">${l.code}</span>
        <span>${l.label}</span>
        ${l.code === cur ? `<span class="tick" aria-hidden="true">✓</span>` : ""}
      </button>`).join("");
  return `
    <details class="lang">
      <summary title="${I18n.t("chrome.language")}">
        ${cur.toUpperCase()}
        <svg class="chev" width="9" height="6" viewBox="0 0 10 6" fill="none" aria-hidden="true">
          <path d="M1 1l4 4 4-4" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
        </svg>
      </summary>
      <div class="lang-menu" role="menu" aria-label="${I18n.t("chrome.language")}">${items}</div>
    </details>`;
}

function controlsHTML() {
  return themeToggleHTML() + langSwitchHTML();
}

/** Put the controls into their mount point. Idempotent; safe to re-run. */
function mountChrome() {
  const topbarRight = document.querySelector(".topbar-right");
  const authWrap = document.querySelector(".auth-wrap");
  let host = null;
  if (topbarRight) {
    host = topbarRight.querySelector(".controls");
    if (!host) {
      host = document.createElement("div");
      host.className = "controls";
      topbarRight.insertBefore(host, topbarRight.firstChild);
    }
  } else if (authWrap) {
    host = authWrap.querySelector(".auth-controls");
    if (!host) {
      host = document.createElement("div");
      host.className = "auth-controls";
      authWrap.insertBefore(host, authWrap.firstChild);
    }
  } else {
    return;
  }
  host.innerHTML = controlsHTML();
}

// ------------------------------------------------------------------- boot
// `mountChrome()` renders the switcher itself, and it needs a mount point that
// Alpine only creates *after* `alpine:init` (the topbar is injected through
// `x-html="navHTML(...)"`, and Alpine re-injects it on every language change).
// So: mount what we can now, then watch for the node — the same approach
// `revealActiveNav()` in app.js uses, instead of guessing a delay. The check is
// "is it missing", never "is it stale", so the observer cannot loop.
function ensureChromeMounted() {
  const host = document.querySelector(".topbar-right") || document.querySelector(".auth-wrap");
  if (!host) return false;
  if (host.querySelector(".controls") || host.querySelector(".auth-controls")) return true;
  mountChrome();
  return true;
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => { I18n.apply(); mountChrome(); });
} else {
  I18n.apply();
  mountChrome();
}

if (typeof MutationObserver !== "undefined") {
  const mo = new MutationObserver(() => { ensureChromeMounted(); });
  const start = () => mo.observe(document.body, { childList: true, subtree: true });
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
  // A language change re-renders the nav, which throws the controls away with
  // it; re-mount them once Alpine has settled.
  document.addEventListener("lang:changed", () => {
    mountChrome();
    setTimeout(ensureChromeMounted, 0);
  });
}

// One delegated listener serves every control, wherever it was mounted.
document.addEventListener("click", (ev) => {
  const themeBtn = ev.target.closest("[data-theme-set]");
  if (themeBtn) {
    Theme.apply(themeBtn.getAttribute("data-theme-set"));
    mountChrome(); // repaint the pressed state
    return;
  }
  const langBtn = ev.target.closest("[data-lang-set]");
  if (langBtn) {
    const open = langBtn.closest("details.lang");
    if (open) open.open = false;
    I18n.set(langBtn.getAttribute("data-lang-set"));
  }
});

document.addEventListener("click", (ev) => {
  document.querySelectorAll("details.lang[open]").forEach((d) => {
    if (!d.contains(ev.target)) d.open = false;
  });
});
document.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape") {
    document.querySelectorAll("details.lang[open]").forEach((d) => { d.open = false; });
  }
});

// Canvas charts cannot inherit CSS variables; they repaint on a theme change.
const _chartRedraws = [];
window.onChartRedraw = (fn) => _chartRedraws.push(fn);
window.redrawCharts = () => _chartRedraws.forEach((fn) => { try { fn(); } catch { /* ignore */ } });

window.Theme = Theme;
window.I18n = I18n;
window.localeTag = localeTag;
window.controlsHTML = controlsHTML;
window.mountChrome = mountChrome;
