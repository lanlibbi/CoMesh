// CoMesh — /admin-usage page (alpine frontend).
// Per-user token/credit consumption across ALL users. Backend: GET /admin/usage
// (role-gated, see usage_stats.py build_admin_usage) — one aggregated payload per
// window change, no polling.
//
// The page is only reachable for role == "admin"; the server enforces the same
// rule, so a non-admin who guesses the URL gets a clean 403 instead of data.
document.addEventListener("alpine:init", () => {
  Alpine.data("adminUsagePage", () => ({
    window: "7d",
    windows: [
      { key: "24h", label: I18n.t("usage.window.24h") },
      { key: "7d", label: I18n.t("dash.window.7d") },
      { key: "30d", label: I18n.t("dash.window.30d") },
      { key: "all", label: I18n.t("usage.window.all") },
    ],
    includeInactive: true,
    limit: 50,
    data: null,
    loading: true,
    error: "",
    /** null while unknown; false once the 403 came back. */
    denied: false,

    async init() {
      if (!Auth.requireLogin()) return;
      await this.load();
      await this.loadSettings();
    },

    settings: { credits_enabled: false },
    settingsLoaded: false,

    async loadSettings() {
      try {
        const r = await api("/admin/settings", { auth: true });
        this.settings = r; this.settingsLoaded = true;
      } catch (e) { /* non-admin or error -> banner stays hidden */ }
    },
    async toggleCredits() {
      try {
        const neu = !this.settings.credits_enabled;
        if (!confirm(I18n.t("admin.credits_confirm_" + (neu ? "on" : "off")))) return;
        const r = await api("/admin/settings", { method: "PUT", body: { credits_enabled: neu }, auth: true });
        this.settings = r;
      } catch (e) { alert(e.message || String(e)); }
    },
    async setQuota(u, mode) {
      try {
        await api(`/admin/users/${u.id}/quota`, { method: "PATCH", body: { quota_mode: mode }, auth: true });
        u.quota_mode = mode;
      } catch (e) { alert(e.message || String(e)); }
    },
    quotaLabel(mode) {
      return I18n.t("admin.quota." + (mode || "unlimited"));
    },
    isAdmin() {
      const u = Auth.currentUser() || {};
      return (u.role || "").toLowerCase() === "admin";
    },

    async setWindow(key) {
      if (this.window === key) return;
      this.window = key;
      await this.load();
    },

    async toggleInactive() {
      this.includeInactive = !this.includeInactive;
      await this.load();
    },

    async load() {
      this.loading = true;
      this.error = "";
      try {
        const qs = new URLSearchParams({
          window: this.window,
          limit: String(this.limit),
          include_inactive: String(this.includeInactive),
        });
        this.data = await api(`/admin/usage?${qs}`, { auth: true });
        this.denied = false;
      } catch (e) {
        const msg = e.message || "Laden fehlgeschlagen";
        // 403 = authenticated but not an admin; that is a state, not an error.
        this.denied = /admin role required/i.test(msg) || /403/.test(msg);
        this.error = this.denied ? "" : msg;
        this.data = null;
      } finally {
        this.loading = false;
      }
    },

    get users() { return (this.data && this.data.users) || []; },
    get totals() { return (this.data && this.data.totals) || {}; },

    /** Heaviest user's token count — the bar scale for the user rows. */
    get maxTokens() {
      const vals = this.users.map((u) => Number(u.total_tokens) || 0);
      return Math.max(1, ...vals);
    },

    barPct(u) {
      return Math.max(1, (Number(u.total_tokens) || 0) / this.maxTokens * 100);
    },

    /** Share of the whole-window total across every listed user. */
    sharePct(u) {
      const total = Number(this.totals.total_tokens) || 0;
      if (!total) return "—";
      return ((Number(u.total_tokens) || 0) / total * 100).toFixed(1) + " %";
    },

    /** Compact per-model summary: I18n.t("fmt.model_tokens") joined, top 3 + count. */
    modelSummary(u) {
      const ms = u.models || [];
      if (!ms.length) return "—";
      const head = ms.slice(0, 3)
        .map((m) => `${m.model} (${this.fmtCompact(m.total_tokens)})`)
        .join(" · ");
      return ms.length > 3 ? head + I18n.t("fmt.plus_more", { n: ms.length - 3 }) : head;
    },

    fmtTokens(n) { return fmtNumber(n == null ? 0 : n); },

    fmtCompact(n) {
      const v = Number(n) || 0;
      if (v >= 1e9) return (v / 1e9).toFixed(1) + " Mrd";
      if (v >= 1e6) return (v / 1e6).toFixed(1) + " Mio";
      if (v >= 1e3) return (v / 1e3).toFixed(1) + "k";
      return String(v);
    },

    fmtLastUsed(s) { return s ? fmtDate(s) : "—"; },

    windowLabel() { return (this.data && this.data.window_label) || "—"; },

    rangeText() {
      if (!this.data) return "";
      if (!this.data.since) return I18n.t("usage.range.all");
      return I18n.t("fmt.range_now", { since: fmtDate(this.data.since) });
    },

    /** "12 von 34" — shows the limit actually truncated the list or not. */
    coverageText() {
      if (!this.data) return "";
      const shown = this.users.length;
      const total = this.totals.active_users;
      if (total == null) return I18n.t("unit.users", { shown });
      return shown >= total
        ? I18n.t("unit.users", { shown })
        : I18n.t("fmt.range_shown", { shown, total }) + " " + I18n.t("unit.users_limit", { limit: this.limit });
    },
  }));
});
