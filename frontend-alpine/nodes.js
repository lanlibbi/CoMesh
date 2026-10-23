// CoMesh — /nodes page (alpine frontend). Register a node + list mine.
document.addEventListener("alpine:init", () => {
  Alpine.data("nodesPage", () => ({
  myNodes: [],
  // Mirrors the backend credits flag: hides credit rates / earnings labelling.
  billing: Credits.enabled(),
  availableModels: [],
  editingId: null,
  editAllowed: [],
  selectedIds: [],          // Node-IDs der Auswahl (Bulk-Aktionen)
  bulkBusy: false,
  bulkProgress: "",
  bulkError: "",
  bulkWhitelistOpen: false,
  bulkWhitelistBusy: false,
  bulkWhitelistProgress: "",
  bulkWhitelistError: "",
  bulkWhitelistSelection: [],
  form: { name: "", gpu_type: "", vram_gb: 24, hourly_rate: 0.05, node_url: "", port: 11435, description: "" },
  formAllowed: [],  // selected model names in the register form
  msg: "",
  lastKey: null,

    async init() {
      if (!Auth.requireProviderOrRedirect()) return;
      this.billing = Credits.enabled();
      await this.loadAvailableModels();
      await this.load();
      this.billing = Credits.enabled();
    },

    // ---- Auswahl -------------------------------------------------------
    get selectedCount() {
      return this.selectedIds.length;
    },
    get allSelected() {
      return this.myNodes.length > 0 && this.selectedIds.length === this.myNodes.length;
    },
    get someSelected() {
      return this.selectedIds.length > 0 && !this.allSelected;
    },
    selectAllNodes(el) {
      this.selectedIds = el && el.checked ? this.myNodes.map(n => n.id) : [];
      this.bulkError = "";
    },
    toggleNodeSelection(nodeId) {
      const i = this.selectedIds.indexOf(nodeId);
      if (i >= 0) this.selectedIds.splice(i, 1);
      else this.selectedIds.push(nodeId);
      // Alte Fehlermeldung gilt fuer die vorige Auswahl.
      this.bulkError = "";
    },
    clearSelection() {
      this.selectedIds = [];
      this.bulkError = "";
    },
    selectedNodes() {
      return this.myNodes.filter(n => this.selectedIds.includes(n.id));
    },

    // ---- Bulk: Status umschalten ---------------------------------------
    // Pro Node wird der eigene Zustand invertiert (genau wie der Pause/Resume-
    // Knopf an der Einzelzeile). Teilfehler werden gesammelt und gemeldet.
    async bulkToggleStatus() {
      const targets = this.selectedNodes();
      if (targets.length === 0) return;

      this.bulkBusy = true;
      this.bulkError = "";
      const failed = [];
      let done = 0;
      let enabled = 0;
      for (const n of targets) {
        try {
          const next = !n.is_enabled;
          await api(`/nodes/${n.id}/enable?enabled=${next}`, { method: "POST", auth: true });
          if (next) enabled += 1;
        } catch (e) {
          failed.push({ id: n.id, name: n.name, msg: e.message });
        }
        done += 1;
        this.bulkProgress = `${done}/${targets.length}`;
      }
      this.bulkBusy = false;
      this.bulkProgress = "";
      await this.load();

      if (failed.length > 0) {
        this.selectedIds = failed.map(f => f.id);
        this.bulkError = failed.map(f => `${f.name}: ${f.msg}`).join(" · ");
        toast(I18n.t("nodes.bulk.status_ok", { ok: targets.length - failed.length, n: targets.length }), "err");
        return;
      }
      toast(I18n.t("nodes.bulk.toggled", { n: targets.length, on: enabled, off: targets.length - enabled }), "ok");
      this.clearSelection();
    },

    // ---- Bulk: Modell-Whitelist ----------------------------------------
    openBulkWhitelist() {
      if (this.selectedCount === 0) return;
      this.bulkWhitelistSelection = [];
      this.bulkWhitelistError = "";
      this.bulkWhitelistOpen = true;
    },
    closeBulkWhitelist() {
      if (this.bulkWhitelistBusy) return;
      this.bulkWhitelistOpen = false;
    },
    toggleBulkWhitelistModel(name) {
      const i = this.bulkWhitelistSelection.indexOf(name);
      if (i >= 0) this.bulkWhitelistSelection.splice(i, 1);
      else this.bulkWhitelistSelection.push(name);
    },
    selectAllBulkModels() {
      this.bulkWhitelistSelection = this.availableModels.map(m => m.name);
    },
    selectLocalBulkModels() {
      this.bulkWhitelistSelection = this.availableModels.filter(m => !m.is_cloud).map(m => m.name);
    },
    clearBulkModels() {
      this.bulkWhitelistSelection = [];
    },
    async applyBulkWhitelist() {
      const targets = this.selectedNodes();
      if (targets.length === 0) return;
      const models = [...this.bulkWhitelistSelection];
      if (models.length === 0) {
        const names = targets.map(n => n.name).join(", ");
        if (!confirm(`Keine Modelle ausgewählt — setzt die Whitelist auf I18n.t("nodes.none_allowed") für: ${names}. Fortfahren?`)) return;
      }

      this.bulkWhitelistBusy = true;
      this.bulkWhitelistError = "";
      const failed = [];
      let done = 0;
      for (const n of targets) {
        try {
          await api(`/nodes/${n.id}`, { method: "PUT", auth: true, body: { allowed_models: models } });
        } catch (e) {
          failed.push({ id: n.id, name: n.name, msg: e.message });
        }
        done += 1;
        this.bulkWhitelistProgress = `${done}/${targets.length}`;
      }
      this.bulkWhitelistBusy = false;
      this.bulkWhitelistProgress = "";
      await this.load();

      if (failed.length > 0) {
        this.selectedIds = failed.map(f => f.id);
        this.bulkWhitelistError = failed.map(f => `${f.name}: ${f.msg}`).join(" · ");
        toast(I18n.t("nodes.bulk.whitelist_ok", { ok: targets.length - failed.length, n: targets.length }), "err");
        return;
      }
      const label = models.length > 0 ? I18n.t("unit.models_count", { n: models.length }) : I18n.t("nodes.none_allowed");
      toast(I18n.t("nodes.bulk.whitelist_result", { n: targets.length, label }), "ok");
      this.bulkWhitelistOpen = false;
      this.clearSelection();
    },

    // Existing methods continue below...

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
        this.msg = I18n.t("err.generic") + e.message;
      }
      // Auswahl auf existierende Nodes begrenzen (Loeschen/Reload).
      const ids = new Set(this.myNodes.map(n => n.id));
      this.selectedIds = this.selectedIds.filter(id => ids.has(id));
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
          node_url: this.form.node_url || null,
          port: Number(this.form.port || 11435),
          description: this.form.description || null,
          // null = default (all local, no cloud). [] = allow nothing. List = whitelist.
          allowed_models: this.formAllowed.length > 0 ? this.formAllowed : null,
        };
        const n = await api("/nodes/register", { method: "POST", body, auth: true });
        this.lastKey = n.agent_api_key;
        this.msg = I18n.t("nodes.registered_hint", { id: n.id });
        toast(I18n.t("nodes.registered"), "ok");
        this.form = { name: "", gpu_type: "", vram_gb: 24, hourly_rate: 0.05, node_url: "", port: 11435, description: "" };
        this.formAllowed = [];
        await this.load();
      } catch (e) {
        this.msg = I18n.t("err.generic") + e.message;
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
    /** Betriebsart umschalten (always | partial). */
    async betriebSetzen(n, wert) {
      try {
        await api(`/nodes/${n.id}`, { method: "PUT", auth: true, body: { availability: wert } });
        n.availability = wert;
        toast(wert === "always" ? "Dauerbetrieb gespeichert" : "Zeitweise Verfügbarkeit gespeichert", "ok");
      } catch (e) {
        toast(e.message, "err");
        await this.load();
      }
    },

    /** Besitzer im Adminbereich anonymisieren oder wieder nennen. */
    async besitzerVerbergen(n, wert) {
      try {
        await api(`/nodes/${n.id}`, { method: "PUT", auth: true, body: { hide_owner: !!wert } });
        n.hide_owner = !!wert;
        toast(wert ? "Besitzer erscheint im Adminbereich als anonym" : "Besitzer wird wieder genannt", "ok");
      } catch (e) {
        toast(e.message, "err");
        await this.load();
      }
    },

    async saveEdit(n) {
      try {
        await api(`/nodes/${n.id}`, {
          method: "PUT",
          auth: true,
          body: { allowed_models: this.editAllowed.length > 0 ? this.editAllowed : [] },
        });
        toast(I18n.t("nodes.whitelist_updated"), "ok");
        this.editingId = null;
        await this.load();
      } catch (e) { toast(I18n.t("nodes.update_failed") + " " + e.message, "err"); }
    },

    async toggle(n) {
      try {
        await api(`/nodes/${n.id}/enable?enabled=${!n.is_enabled}`, { method: "POST", auth: true });
        await this.load();
      } catch (e) { toast(I18n.t("nodes.toggle_failed") + " " + e.message, "err"); }
    },

    async del(n) {
      if (!confirm(I18n.t("nodes.delete_confirm", { id: n.id, name: n.name }))) return;
      try {
        const r = await fetch(API_BASE + `/nodes/${n.id}`, { method: "DELETE", headers: { Authorization: "Bearer " + LS.get("api_key") } });
        if (!r.ok && r.status !== 204) throw new Error(`HTTP ${r.status}`);
        toast(I18n.t("nodes.deleted"), "ok");
        await this.load();
      } catch (e) { toast("Delete failed: " + e.message, "err"); }
    },

    // Status pill class is derived in the template (`'pill-' + n.status`) so
    // unknown server statuses degrade to the neutral pill instead of a missing one.
  }));
});
