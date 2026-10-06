// CoMesh — /earnings page (alpine frontend). Per-node + per-event earnings.
document.addEventListener("alpine:init", () => {
  Alpine.data("earningsPage", () => ({
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
        this.byNode = data.by_node || [];
        this.events = data.events || [];
        this.nodeMap = Object.fromEntries(this.byNode.map(n => [n.node_id, n.name]));
      } catch (e) {
        this.error = e.message;
      }
    },
  }));
});
