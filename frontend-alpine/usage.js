// GPU-Pool — /usage page (alpine frontend).
// Token + credit consumption per model, per window. Backend: GET /v1/me/usage
// (see usage_stats.py) — one aggregated payload per window change, no polling.
document.addEventListener("alpine:init", () => {
  Alpine.data("usagePage", () => ({
    window: "7d",
    windows: [
      { key: "24h", label: "24 h" },
      { key: "7d", label: "7 Tage" },
      { key: "30d", label: "30 Tage" },
      { key: "all", label: "Gesamt" },
    ],
    data: null,
    loading: true,
    error: "",

    async init() {
      await this.load();
    },

    async setWindow(key) {
      if (this.window === key) return;
      this.window = key;
      await this.load();
    },

    async load() {
      this.loading = true;
      this.error = "";
      try {
        this.data = await api(`/v1/me/usage?window=${encodeURIComponent(this.window)}`, { auth: true });
      } catch (e) {
        this.error = e.message || "Laden fehlgeschlagen";
        this.data = null;
      } finally {
        this.loading = false;
        // The canvas is sized from its own CSS box, so it must exist first.
        this.$nextTick(() => this.draw());
      }
    },

    draw() {
      if (!this.data) return;
      renderUsageChart("usageSeries", (this.data.series || []).map((b) => ({
        label: b.label,
        value: b.total_tokens,
      })));
    },

    get models() { return (this.data && this.data.models) || []; },
    get totals() { return (this.data && this.data.totals) || {}; },
    get recent() { return (this.data && this.data.recent) || []; },

    /** Peak token count in the window — the bar scale for the model list. */
    get maxTokens() {
      return Math.max(1, ...this.models.map((m) => Number(m.total_tokens) || 0));
    },

    /** Width (in %) of the token bar for one model. */
    barPct(m) {
      return Math.max(0.8, (Number(m.total_tokens) || 0) / this.maxTokens * 100);
    },

    /** Share of the window total, as a rendered percentage. */
    sharePct(m) {
      return ((Number(m.share) || 0) * 100).toFixed(1) + " %";
    },

    fmtTokens(n) {
      return fmtNumber(n == null ? 0 : n);
    },

    /** Compact token count for the axis-adjacent labels on small screens. */
    fmtCompact(n) {
      const v = Number(n) || 0;
      if (v >= 1e9) return (v / 1e9).toFixed(1) + " Mrd";
      if (v >= 1e6) return (v / 1e6).toFixed(1) + " Mio";
      if (v >= 1e3) return (v / 1e3).toFixed(1) + "k";
      return String(v);
    },

    fmtLatency(ms) {
      if (ms == null) return "—";
      return ms >= 1000 ? (ms / 1000).toFixed(2) + " s" : ms + " ms";
    },

    tokensPerRequest(t) {
      if (!t || !t.requests) return "—";
      return fmtNumber(Math.round(t.total_tokens / t.requests));
    },

    windowLabel() { return (this.data && this.data.window_label) || "—"; },

    /** "since" is null for the all-time window. */
    rangeText() {
      if (!this.data) return "";
      if (!this.data.since) return "gesamter Zeitraum";
      return `${fmtDate(this.data.since)} – jetzt`;
    },

    modelHue(i) {
      // Deterministic tint per model row: metallic → brass ramp, no rainbow.
      const ramp = ["var(--metal)", "var(--metal-2)", "var(--brass-soft)", "var(--brass)"];
      return ramp[i % ramp.length];
    },
  }));
});
