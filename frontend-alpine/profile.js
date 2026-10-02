// CoMesh — /profile page (alpine frontend). Edit role + model whitelist.
document.addEventListener("alpine:init", () => {
  Alpine.data("profilePage", () => ({
    role: "both",
    currentRole: "both",
    roleWarning: "",
    savingRole: false,
    lastRoleChange: "",

    availableModels: [],
    selectedModels: [],
    allowCloud: false,
    modelWarning: "",
    savingModels: false,
    lastModelChange: "",

    error: "",

    async init() {
      if (!Auth.requireLogin()) return;
      await this.loadMe();
      await this.loadAvailableModels();
    },

    async loadMe() {
      try {
        const me = await api("/v1/me", { auth: true });
        this.role = me.role || "both";
        this.currentRole = me.role || "both";
        this.selectedModels = Array.isArray(me.allowed_models) ? [...me.allowed_models] : [];
        this.allowCloud = (this.selectedModels || []).some(m => this.isCloud(m));
        // Keep the cached user object in sync
        Auth.save({ ...(Auth.currentUser() || {}), role: this.role, allowed_models: me.allowed_models }, LS.get("api_key"));
      } catch (e) {
        this.error = "Fehler beim Laden: " + e.message;
      }
    },

    async loadAvailableModels() {
      try {
        const r = await api("/v1/available-models", { auth: true });
        this.availableModels = r.models || [];
      } catch (e) {
        this.availableModels = [];
      }
    },

    isCloud(name) {
      return !!(this.availableModels.find(x => x.name === name)?.is_cloud);
    },

    toggleModel(name) {
      const i = this.selectedModels.indexOf(name);
      if (i >= 0) this.selectedModels.splice(i, 1);
      else this.selectedModels.push(name);
    },

    async saveRole() {
      this.savingRole = true;
      this.roleWarning = "";
      this.lastRoleChange = "";
      try {
        const r = await api("/v1/me/role", { method: "PUT", auth: true, body: { role: this.role } });
        this.currentRole = r.role;
        // Refresh localStorage user object so the nav updates immediately
        const u = Auth.currentUser() || {};
        Auth.save({ ...u, role: r.role }, LS.get("api_key"));
        this.lastRoleChange = `Rolle auf '${r.role}' gesetzt.`;
        if (r.warnings && r.warnings.length > 0) {
          this.roleWarning = r.warnings.join(" • ");
        }
        toast("Rolle aktualisiert", "ok");
      } catch (e) {
        this.roleWarning = e.message;
        toast("Fehler: " + e.message, "err");
      } finally {
        this.savingRole = false;
      }
    },

    async saveModels() {
      this.savingModels = true;
      this.modelWarning = "";
      this.lastModelChange = "";
      try {
        const body = {
          models: this.selectedModels.length > 0 ? this.selectedModels : null,
          allow_cloud: this.allowCloud,
        };
        const r = await api("/v1/me/allowed-models", { method: "PUT", auth: true, body });
        this.selectedModels = Array.isArray(r.allowed_models) ? [...r.allowed_models] : [];
        this.allowCloud = !!r.allow_cloud;
        const u = Auth.currentUser() || {};
        Auth.save({ ...u, allowed_models: r.allowed_models }, LS.get("api_key"));
        this.lastModelChange = "Modell-Whitelist gespeichert.";
        if (r.warnings && r.warnings.length > 0) {
          this.modelWarning = r.warnings.join(" • ");
        }
        toast("Modelle aktualisiert", "ok");
      } catch (e) {
        this.modelWarning = e.message;
        toast("Fehler: " + e.message, "err");
      } finally {
        this.savingModels = false;
      }
    },

    async resetToDefault() {
      this.selectedModels = [];
      this.allowCloud = false;
      await this.saveModels();
    },
  }));
});
