/* GPU-Pool — /nodes page: register a node + list my nodes. */
(async function() {
  const me = API.getUser();
  if (!me || !me.email) {
    document.getElementById("needs-login").style.display = "";
    document.getElementById("app").style.display = "none";
    return;
  }
  document.getElementById("app").style.display = "";
  renderWho();

  const form = document.getElementById("register-form");
  const msg = document.getElementById("register-msg");

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    const body = {
      name: fd.get("name"),
      gpu_type: fd.get("gpu_type"),
      vram_gb: Number(fd.get("vram_gb")),
      hourly_rate: Number(fd.get("hourly_rate")),
      node_url: fd.get("node_url") || null,
      port: Number(fd.get("port") || 11435),
      description: fd.get("description") || null,
    };
    msg.textContent = "Registriere...";
    try {
      const node = await API.post("/nodes/register", body);
      msg.innerHTML = `✅ Node <b>#${node.id}</b> registriert. Agent-Key (jetzt kopieren!):<div class="key-box">${node.agent_api_key}</div>`;
      form.reset();
      await renderMyNodes();
    } catch (err) {
      msg.innerHTML = `<span style="color:#f87171">Fehler: ${err.message}</span>`;
    }
  });

  async function renderMyNodes() {
    const target = document.getElementById("my-nodes");
    target.innerHTML = "<p class='muted'>Lade...</p>";
    try {
      const nodes = await API.get("/nodes/my");
      if (!nodes.length) {
        target.innerHTML = "<p class='muted'>Noch keine Nodes registriert.</p>";
        return;
      }
      const rows = nodes.map(n => {
        const status = n.status || "offline";
        const last = n.last_seen ? new Date(n.last_seen).toLocaleString() : "—";
        return `
          <div class="card" style="margin-top:8px;">
            <div style="display:flex; justify-content:space-between; align-items:start;">
              <div>
                <h4>${n.name} <span class="pill pill-${status}">${status}</span></h4>
                <div class="meta">${n.gpu_type} · ${n.vram_gb} GB VRAM · ${n.node_url || "Adresse noch unbekannt"}</div>
                <div class="meta">Stundensatz: ${n.hourly_rate} Credits · Earned: ${n.earnings_total.toFixed(4)} · Last seen: ${last}</div>
              </div>
              <div>
                <button class="secondary" onclick="toggleNode(${n.id}, ${!n.is_enabled})">${n.is_enabled ? "Pause" : "Resume"}</button>
                <button class="danger" onclick="deleteNode(${n.id})">Löschen</button>
              </div>
            </div>
          </div>`;
      }).join("");
      target.innerHTML = rows;
    } catch (e) {
      target.innerHTML = `<p style="color:#f87171">Fehler beim Laden: ${e.message}</p>`;
    }
  }

  window.toggleNode = async (id, enabled) => {
    try {
      await API.post(`/nodes/${id}/enable?enabled=${enabled}`);
      await renderMyNodes();
    } catch (e) { alert("Toggle failed: " + e.message); }
  };
  window.deleteNode = async (id) => {
    if (!confirm(`Node #${id} wirklich löschen?`)) return;
    try {
      await API.post(`/nodes/${id}/delete`, {});  // fallback: try POST first
    } catch (_) {
      try { await fetch(`/nodes/${id}`, { method: "DELETE", headers: { Authorization: "Bearer " + API.getKey() } }); }
      catch (e) { alert("Delete failed: " + e.message); return; }
    }
    await renderMyNodes();
  };

  await renderMyNodes();
})();
