// CoMesh — /pool page (alpine frontend). Live community pool overview.
document.addEventListener("alpine:init", () => {
  Alpine.data("poolPage", () => ({
    stats: null,
    nodes: [],
    loading: true,
    _timer: null,

    async init() {
      await this.refresh();
      this._timer = setInterval(() => this.refresh(), 10000);
      // Don't keep polling a tab that is not visible.
      document.addEventListener("visibilitychange", () => {
        if (document.hidden) { clearInterval(this._timer); this._timer = null; }
        else if (!this._timer) { this._timer = setInterval(() => this.refresh(), 10000); this.refresh(); }
      });
    },

    async refresh() {
      try {
        this.stats = await api("/nodes/stats/summary");
        this.nodes = await api("/nodes/list?only_online=true");
        this.loading = false;
      } catch (e) {
        console.error(e);
        this.loading = false;
      }
    },

    utilPct(n) { return Math.round((n.current_utilization || 0) * 100); },
    vramPct(n) { return n.vram_gb ? Math.round((n.vram_used_gb / n.vram_gb) * 100) : 0; },

    // Meter colour shifts with load: calm metal → amber → red.
    loadClass(pct) {
      const v = Number(pct) || 0;
      if (v >= 85) return "crit";
      if (v >= 60) return "warn";
      return "";
    },

    rateRange() {
      if (!this.stats || this.stats.lowest_rate == null) return "—";
      return `${this.stats.lowest_rate} – ${this.stats.highest_rate}`;
    },
  }));
});
