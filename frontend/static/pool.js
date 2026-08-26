/* GPU-Pool — /pool page: live community pool overview. */
(async function() {
  renderWho();

  async function refresh() {
    try {
      const stats = await API.get("/nodes/stats/summary");
      document.getElementById("stat-nodes").textContent = `${stats.online_nodes} / ${stats.total_nodes}`;
      document.getElementById("stat-vram").textContent = `${stats.total_vram_gb}`;
      document.getElementById("stat-avail").textContent = `${stats.available_vram_gb}`;
      document.getElementById("stat-util").textContent = `${(stats.avg_utilization * 100).toFixed(0)}%`;
      document.getElementById("stat-rate").textContent =
        stats.lowest_rate != null ? `${stats.lowest_rate} – ${stats.highest_rate}` : "—";

      const nodes = await API.get("/nodes/list?only_online=true");
      const target = document.getElementById("nodes");
      if (!nodes.length) {
        target.innerHTML = "<div class='empty'>Keine Nodes gerade online. Schau später wieder rein!</div>";
        return;
      }
      target.innerHTML = nodes.map(n => {
        const utilPct = Math.round((n.current_utilization || 0) * 100);
        const vramUsedPct = n.vram_gb ? Math.round((n.vram_used_gb / n.vram_gb) * 100) : 0;
        return `
          <div class="node-card">
            <h4>${n.name} <span class="pill pill-${n.status}">${n.status}</span></h4>
            <div class="meta">${n.gpu_type} · ${n.vram_gb} GB VRAM</div>
            <div class="meta">Stundensatz: ${n.hourly_rate} Credits</div>
            <div class="meta">VRAM: ${n.vram_used_gb} / ${n.vram_gb} GB (${vramUsedPct}%)</div>
            <div class="util-bar"><div style="width:${utilPct}%;"></div></div>
            <div class="meta">Auslastung: ${utilPct}%</div>
            ${n.description ? `<div class="meta" style="margin-top:6px;">${n.description}</div>` : ""}
          </div>`;
      }).join("");
    } catch (e) {
      console.error(e);
    }
  }

  await refresh();
  setInterval(refresh, 10000);
})();
