// GPU-Pool — /pool page (alpine frontend). Live community pool overview.
document.addEventListener("alpine:init", () => {
  Alpine.data("poolPage", () => ({
    stats: null,
    nodes: [],
    loading: true,

    async init() {
      await this.refresh();
      setInterval(() => this.refresh(), 10000);
    },

    async refresh() {
      try {
        this.stats = await api("/nodes/stats/summary");
        this.nodes = await api("/nodes/list?only_online=true");
        this.loading = false;
      } catch (e) {
        console.error(e);
      }
    },

    utilPct(n) { return Math.round((n.current_utilization || 0) * 100); },
    vramPct(n) { return n.vram_gb ? Math.round((n.vram_used_gb / n.vram_gb) * 100) : 0; },
    rateRange() {
      if (!this.stats || this.stats.lowest_rate == null) return "—";
      return `${this.stats.lowest_rate} – ${this.stats.highest_rate}`;
    },
  }));
});
