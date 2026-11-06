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
    // `null` = keine Einschränkung (Server-Vorgabe), `[]` = nichts freigegeben.
    // Muss deklariert sein: das Markup liest `allowedRaw`, und ein nicht
    // deklariertes Feld ist in Alpine 3 nicht im Scope (Konsole:
    // "Uncaught ReferenceError: allowedRaw is not defined").
    allowedRaw: null,
    allowCloud: false,
    modelWarning: "",
    savingModels: false,
    lastModelChange: "",

    // ---- API-Schlüssel -------------------------------------------------
    // Das Gegenstück zur Liste aus GET /v1/me/keys: nur Präfix und Datum.
    // `newKey` hält den einzigen Zeitpunkt fest, an dem der volle Wert sichtbar
    // ist — er kommt aus der Antwort von POST /v1/me/keys und wird nirgends
    // gespeichert (kein localStorage, keine Anzeige nach dem Neuladen).
    keys: [],
    keysLoaded: false,
    keyPassword: "",
    keyError: "",
    creatingKey: false,
    newKey: "",
    meEmail: "",

    error: "",

    async init() {
      if (!Auth.requireLogin()) return;
      await this.loadMe();
      this.loadKeys();
      await this.loadAvailableModels();
    },

    async loadMe() {
      try {
        const me = await api("/v1/me", { auth: true });
        this.role = me.role || "both";
        this.currentRole = me.role || "both";
        this.meEmail = me.email || "";
        this.selectedModels = Array.isArray(me.allowed_models) ? [...me.allowed_models] : [];
        // None (Standard) und [] (nichts erlaubt) müssen unterscheidbar bleiben.
        this.allowedRaw = me.allowed_models === null || me.allowed_models === undefined
          ? null
          : [...me.allowed_models];
        // Nicht aus der Modellliste ableiten: die ist an dieser Stelle noch leer
        // (availableModels kommt erst danach), dadurch sprang der Haken immer zurück.
        this.allowCloud = me.allow_cloud === undefined ? false : !!me.allow_cloud;
        // Keep the cached user object in sync
        Auth.save({ ...(Auth.currentUser() || {}), role: this.role, allowed_models: me.allowed_models }, LS.get("api_key"));
      } catch (e) {
        this.error = I18n.t("err.load_prefix") + e.message;
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

    // ---- API-Schlüssel ---------------------------------------------------
    /** Liste mit Präfix, Datum und Zustand — mehr gibt der Server nicht her. */
    async loadKeys() {
      try {
        const r = await api("/v1/me/keys", { auth: true });
        this.keys = Array.isArray(r.keys) ? r.keys : [];
      } catch (e) {
        this.keys = [];
        this.keyError = I18n.t("profile.key.load_failed") + " " + e.message;
      } finally {
        this.keysLoaded = true;
      }
    },

    /** Datum in der aktiven Sprache, nicht fest auf de-DE. */
    keyDate(iso) {
      if (!iso) return "—";
      try {
        return new Date(iso).toLocaleString(localeTag(), {
          day: "2-digit", month: "2-digit", year: "numeric",
          hour: "2-digit", minute: "2-digit",
        });
      } catch (e) {
        return iso;
      }
    },

    /** Beschriftung des Zustands — literale Schlüssel, damit der Katalogbau sie sieht. */
    keyStatus(k) {
      return k && k.is_active
        ? I18n.t("profile.key.status.active")
        : I18n.t("profile.key.status.replaced");
    },

    /**
     * Neuen Schlüssel ausstellen. Der Server verlangt das Passwort und gibt den
     * Wert genau einmal zurück; frühere gpu_-Schlüssel werden dabei ungültig,
     * die Sitzung (sess_…) bleibt bestehen. Deshalb steht der Wert nur in
     * `newKey` und geht nicht in den Speicher.
     */
    async createKey() {
      if (this.creatingKey) return;
      this.keyError = "";
      if (!this.keyPassword) {
        this.keyError = I18n.t("profile.key.needs_password");
        return;
      }
      this.creatingKey = true;
      try {
        const r = await api("/v1/me/keys", {
          method: "POST",
          auth: true,
          body: { password: this.keyPassword },
        });
        this.newKey = r.api_key || "";
        this.keyPassword = "";
        await this.loadKeys();
        toast(I18n.t("profile.key.issued"), "ok");
      } catch (e) {
        // 401 heißt hier: Passwort falsch (der Server antwortet mit
        // "Password incorrect.") — der Rest ist eine echte Störung.
        this.keyError = /password/i.test(e.message || "")
          ? I18n.t("profile.key.password_wrong")
          : e.message;
      } finally {
        this.creatingKey = false;
      }
    },

    async copyNewKey(ev) {
      if (!this.newKey) return;
      try {
        await navigator.clipboard.writeText(this.newKey);
      } catch (e) {
        // Ohne Clipboard-Erlaubnis bleibt der Wert markierbar im <pre> stehen.
        this.keyError = e.message || String(e);
        return;
      }
      toast(I18n.t("profile.key.copied"), "ok");
      const btn = ev && ev.currentTarget;
      if (btn) {
        const before = btn.textContent;
        btn.textContent = "✓";
        setTimeout(() => { btn.textContent = before; }, 1400);
      }
    },

    /** Einmalige Anzeige schließen — der Wert ist danach weg, absichtlich. */
    dismissKey() {
      this.newKey = "";
    },

    isCloud(name) {
      return !!(this.availableModels.find(x => x.name === name)?.is_cloud);
    },

    toggleModel(name) {
      const i = this.selectedModels.indexOf(name);
      if (i >= 0) this.selectedModels.splice(i, 1);
      else this.selectedModels.push(name);
    },

    /** Admins verwalten ihre Rolle nicht selbst — sonst hebt ein Profil-Speichern die Rechte auf. */
    isAdminRole() {
      const u = Auth.currentUser() || {};
      return (u.role || "").toLowerCase() === "admin";
    },

    async saveRole() {
      if (this.isAdminRole()) {
        this.roleWarning = I18n.t("profile.admin_role_managed");
        return;
      }
      this.savingRole = true;
      this.roleWarning = "";
      this.lastRoleChange = "";
      try {
        const r = await api("/v1/me/role", { method: "PUT", auth: true, body: { role: this.role } });
        this.currentRole = r.role;
        // Refresh localStorage user object so the nav updates immediately
        const u = Auth.currentUser() || {};
        Auth.save({ ...u, role: r.role }, LS.get("api_key"));
        this.lastRoleChange = I18n.t("profile.role_set", { role: r.role });
        if (r.warnings && r.warnings.length > 0) {
          this.roleWarning = r.warnings.join(" • ");
        }
        toast(I18n.t("profile.role.updated"), "ok");
      } catch (e) {
        this.roleWarning = e.message;
        toast(I18n.t("err.generic") + e.message, "err");
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
        this.lastModelChange = I18n.t("profile.models.saved");
        if (r.warnings && r.warnings.length > 0) {
          this.modelWarning = r.warnings.join(" • ");
        }
        toast(I18n.t("profile.models.updated"), "ok");
      } catch (e) {
        this.modelWarning = e.message;
        toast(I18n.t("err.generic") + e.message, "err");
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
