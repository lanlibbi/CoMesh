// CoMesh — API base URL resolution.
//
// The frontend must never carry a hardcoded address: the same build has to work
// on a laptop, on a DHCP LAN, behind a reverse proxy and inside a tailnet.
// Resolution order (first hit wins):
//
//   1. ?api=<base>            — one-shot setup: <base> is stored and removed from
//                               the URL. This is how an operator points a static
//                               build at a portal that is not same-origin.
//   2. localStorage "api_base" — set by step 1, or manually:
//                               localStorage.setItem("api_base", "http://portal-host:8765")
//   3. window.COMESH_API_BASE — an optional runtime config file (config.js),
//                               edited after the build, no rebuild needed.
//   4. "/api"                 — same-origin default. nginx in this repo proxies
//                               /api/* to the portal, so a normal deployment
//                               needs no configuration at all.
//
// Query parameters are read with URLSearchParams and validated: only http(s)
// URLs (or same-origin paths) are accepted, so a crafted link cannot inject e.g.
// `javascript:` into fetch().
(function () {
  "use strict";

  var LS_KEY = "api_base";

  function normalize(raw) {
    if (!raw) return null;
    var value = String(raw).trim().replace(/\/+$/, "");
    if (!value) return null;
    if (value.charAt(0) === "/") return value;              // same-origin path
    if (/^https?:\/\//i.test(value)) return value;          // absolute http(s)
    // A bare "host:port" is accepted too — the browser needs a scheme, and http
    // is the only sensible guess for a self-hosted portal.
    if (/^[A-Za-z0-9._\[\]:-]+$/.test(value) && value.indexOf("://") === -1) {
      return "http://" + value.replace(/^\/+/, "");
    }
    return null;
  }

  function readParam() {
    try {
      var params = new URLSearchParams(window.location.search);
      var raw = params.get("api");
      if (!raw) return null;
      var value = normalize(raw);
      if (value) {
        try { localStorage.setItem(LS_KEY, value); } catch (e) { /* private mode */ }
        params.delete("api");
        var qs = params.toString();
        var clean = window.location.pathname + (qs ? "?" + qs : "") + window.location.hash;
        window.history.replaceState(null, "", clean);
      }
      return value;
    } catch (e) {
      return null;
    }
  }

  function stored() {
    try { return normalize(localStorage.getItem(LS_KEY)); } catch (e) { return null; }
  }

  window.ComeshApi = {
    /** Resolve the API base URL. Called once at load; see the order above. */
    resolve: function () {
      var fromQuery = readParam();
      if (fromQuery) return fromQuery;
      var fromStore = stored();
      if (fromStore) return fromStore;
      var fromConfig = normalize(window.COMESH_API_BASE);
      if (fromConfig) return fromConfig;
      return "/api";
    },
    /** Forget a stored override (used by the settings hint / troubleshooting). */
    clear: function () {
      try { localStorage.removeItem(LS_KEY); } catch (e) { /* ignore */ }
    },
    normalize: normalize,
  };

  window.API_BASE = window.ComeshApi.resolve();
})();
