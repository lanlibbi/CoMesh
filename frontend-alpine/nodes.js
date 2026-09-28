// GPU-Pool — /nodes page (alpine frontend). Register a node + list mine.
document.addEventListener("alpine:init", () => {
  Alpine.data("nodesPage", () => ({
    myNodes: [],
    availableModels: [],
    editingId: null,
    editAllowed: [],
    form: { name: "", gpu_type: "", vram_gb: 24, hourly_rate: 0.05, tailscale_ip: "", port: 11435, description: "" },
    formAllowed: [],  // selected model names in the register form
    msg: "",
    lastKey: null,

    async init() {
      if (!Auth.requireProviderOrRedirect()) return;
      await this.loadAvailableModels();
      await this.load();
    },

    async loadAvailableModels() {
      try {
        const r = await api("/v1/available-models", { auth: true });
        this.availableModels = r.models || [];
      } catch (e) {
        this.availableModels = [];
      }
    },

    isCloud(m) { return !!(this.availableModels.find(x => x.name === m)?.is_cloud); },

    async load() {
      try {
        this.myNodes = await api("/nodes/my", { auth: true });
      } catch (e) {
        this.msg = "Fehler: " + e.message;
      }
    },

    toggleFormModel(name) {
      const i = this.formAllowed.indexOf(name);
      if (i >= 0) this.formAllowed.splice(i, 1);
      else this.formAllowed.push(name);
    },

    async submit() {
      this.msg = "Registriere...";
      try {
        const body = {
          name: this.form.name,
          gpu_type: this.form.gpu_type,
          vram_gb: Number(this.form.vram_gb),
          hourly_rate: Number(this.form.hourly_rate),
          tailscale_ip: this.form.tailscale_ip || null,
          port: Number(this.form.port || 11435),
          description: this.form.description || null,
          // null = default (all local, no cloud). [] = allow nothing. List = whitelist.
          allowed_models: this.formAllowed.length > 0 ? this.formAllowed : null,
        };
        const n = await api("/nodes/register", { method: "POST", body, auth: true });
        this.lastKey = n.agent_api_key;
        this.msg = `Node #${n.id} registriert. Agent-Key (jetzt kopieren!):`;
        toast("Node registriert", "ok");
        this.form = { name: "", gpu_type: "", vram_gb: 24, hourly_rate: 0.05, tailscale_ip: "", port: 11435, description: "" };
        this.formAllowed = [];
        await this.load();
      } catch (e) {
        this.msg = "Fehler: " + e.message;
      }
    },

    startEdit(n) {
      this.editingId = n.id;
      this.editAllowed = Array.isArray(n.allowed_models) ? [...n.allowed_models] : [];
    },
    cancelEdit() { this.editingId = null; this.editAllowed = []; },
    toggleEditModel(name) {
      const i = this.editAllowed.indexOf(name);
      if (i >= 0) this.editAllowed.splice(i, 1);
      else this.editAllowed.push(name);
    },
    async saveEdit(n) {
      try {
        await api(`/nodes/${n.id}`, {
          method: "PUT",
          auth: true,
          body: { allowed_models: this.editAllowed.length > 0 ? this.editAllowed : [] },
        });
        toast("Modell-Whitelist aktualisiert", "ok");
        this.editingId = null;
        await this.load();
      } catch (e) { toast("Update fehlgeschlagen: " + e.message, "err"); }
    },

    async toggle(n) {
      try {
        await api(`/nodes/${n.id}/enable?enabled=${!n.is_enabled}`, { method: "POST", auth: true });
        await this.load();
      } catch (e) { toast("Toggle failed: " + e.message, "err"); }
    },

    async del(n) {
      if (!confirm(`Node #${n.id} (${n.name}) wirklich löschen?`)) return;
      try {
        const r = await fetch(API_BASE + `/nodes/${n.id}`, { method: "DELETE", headers: { Authorization: "Bearer " + LS.get("api_key") } });
        if (!r.ok && r.status !== 204) throw new Error(`HTTP ${r.status}`);
        toast("Node gelöscht", "ok");
        await this.load();
      } catch (e) { toast("Delete failed: " + e.message, "err"); }
    },

    // Status pill class is derived in the template (`'pill-' + n.status`) so
    // unknown server statuses degrade to the neutral pill instead of a missing one.
  }));
});
