/* GPU-Pool — /agent page: setup instructions + docker command with the user's first node. */
(async function() {
  const me = API.getUser();
  if (!me || !me.email) {
    document.getElementById("needs-login").style.display = "";
    document.getElementById("app").style.display = "none";
    return;
  }
  document.getElementById("app").style.display = "";
  renderWho();

  // Try to find a node the user already has and show the docker run command
  try {
    const nodes = await API.get("/nodes/my");
    const target = document.getElementById("reg-result");
    const cmd = document.getElementById("cmd");
    if (nodes.length) {
      const n = nodes[0];
      target.innerHTML = `<p>Bestehender Node: <b>${n.name}</b> (#${n.id}). Agent-Key ist nach Registrierung nicht mehr abrufbar —
      falls verloren, lösche + registriere neu.</p>`;
      cmd.textContent = `docker run -d --name gpu-pool-agent \\
  --gpus all \\
  --restart unless-stopped \\
  -e PORTAL_URL=${location.origin} \\
  -e NODE_ID=${n.id} \\
  -e NODE_API_KEY=node_xxxxxxxx \\
  -e OLLAMA_URL=http://host.docker.internal:11434 \\
  -p 11435:11435 \\
  gpu-pool-node-agent`;
    } else {
      target.innerHTML = `<p>Du hast noch keine Nodes. <a href="/nodes">Jetzt registrieren</a>, dann
      bekommst du hier den passenden <code>docker run</code>-Befehl.</p>`;
      cmd.textContent = `# Erst Node registrieren auf /nodes`;
    }
  } catch (e) {
    document.getElementById("reg-result").innerHTML =
      `<p style="color:#f87171">Fehler: ${e.message}</p>`;
  }
})();
