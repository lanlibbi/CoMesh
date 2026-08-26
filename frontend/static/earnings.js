/* GPU-Pool — /earnings page: per-node + per-event earnings. */
(async function() {
  const me = API.getUser();
  if (!me || !me.email) {
    document.getElementById("needs-login").style.display = "";
    document.getElementById("app").style.display = "none";
    return;
  }
  document.getElementById("app").style.display = "";
  renderWho();

  try {
    const data = await API.get("/pool/earnings/mine");
    document.getElementById("total").textContent = data.total.toFixed(4);
    document.getElementById("nodes-count").textContent = data.by_node.length;

    const nodeMap = {};
    data.by_node.forEach(n => nodeMap[n.node_id] = n.name);
    const tb = document.querySelector("#by-node tbody");
    tb.innerHTML = data.by_node.length
      ? data.by_node.map(n => `<tr><td>${n.name}</td><td>${n.earnings_total.toFixed(4)}</td></tr>`).join("")
      : `<tr><td colspan="2" class="muted">Noch keine Nodes.</td></tr>`;

    const et = document.querySelector("#events tbody");
    et.innerHTML = data.events.length
      ? data.events.map(e => `
          <tr>
            <td>${new Date(e.created_at).toLocaleString()}</td>
            <td>${nodeMap[e.node_id] || "#" + e.node_id}</td>
            <td>${e.job_cost.toFixed(6)}</td>
            <td>${e.owner_share.toFixed(6)}</td>
            <td>${e.platform_share.toFixed(6)}</td>
            <td>${e.treasury_share.toFixed(6)}</td>
          </tr>`).join("")
      : `<tr><td colspan="6" class="muted">Noch keine Job-Earnings.</td></tr>`;
  } catch (e) {
    document.querySelector("#events tbody").innerHTML =
      `<tr><td colspan="6" style="color:#f87171">Fehler: ${e.message}</td></tr>`;
  }
})();
