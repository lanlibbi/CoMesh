// GPU-Pool — /earnings page (alpine frontend). Per-node + per-event earnings.
document.addEventListener("alpine:init", () => {
  Alpine.data("earningsPage", () => ({
    billing: Credits.enabled(),
    total: 0,
    byNode: [],
    events: [],
    nodeMap: {},
    error: "",

    async init() {
      if (!Auth.requireProviderOrRedirect()) return;
      try {
        const data = await api("/pool/earnings/mine", { auth: true });
        this.total = data.total;
        this.byNode = data.by_node;
        this.events = data.events;
        this.nodeMap = Object.fromEntries(data.by_node.map(n => [n.node_id, n.name]));
      } catch (e) {
        this.error = e.message;
      }
    },
  }));
});
