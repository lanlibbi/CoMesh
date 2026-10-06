// CoMesh — /agent page (alpine frontend). Setup instructions.
document.addEventListener("alpine:init", () => {
  Alpine.data("agentPage", () => ({
    nodes: [],
    cmd: "",

    async init() {
      if (!Auth.requireLogin()) return;
      try {
        this.nodes = await api("/nodes/my", { auth: true });
        if (this.nodes.length) {
          const n = this.nodes[0];
          this.cmd = `docker run -d --name gpu-pool-agent \\
  --gpus all \\
  --restart unless-stopped \\
  -e PORTAL_URL=${location.origin} \\
  -e NODE_ID=${n.id} \\
  -e NODE_API_KEY=node_xxxxxxxx \\
  -e OLLAMA_URL=http://host.docker.internal:11434 \\
  -p 11435:11435 \\
  gpu-pool-node-agent`;
        } else {
          this.cmd = I18n.t("agent.comment_hint");
        }
      } catch (e) {
        console.error(e);
      }
    },
  }));
});
