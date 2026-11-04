// CoMesh — Admin: Konten freigeben, Rollen, Passwörter, Credits, Schlüssel.
//
// Backend (alles rollen-geprüft, nur role == "admin"):
//   GET   /admin/registrations?status=pending|approved|rejected&q=&limit=&offset=
//   POST  /admin/registrations/{id}/approve | /reject
//   POST  /admin/users                     { email, name, password?, role, initial_credits }
//   PATCH /admin/users/{id}                { role?, is_active?, name?, password? }
//   POST  /admin/users/{id}/topup          { amount, reason }
//   POST  /admin/users/{id}/keys           neuer Schlüssel, alte werden ungültig
//   GET   /admin/users?role=admin          nur zum Zählen der Admins
document.addEventListener("alpine:init", () => {
  Alpine.data("registrationAdminPage", () => ({
    q: "",
    status: "pending",
    statuses: [
      { key: "pending", label: "Ausstehend" },
      { key: "approved", label: "Freigegeben" },
      { key: "rejected", label: "Abgelehnt" },
      { key: "all", label: "Alle" },
    ],
    roles: [
      { key: "both", label: "both — Consumer + Provider" },
      { key: "consumer", label: "consumer" },
      { key: "provider", label: "provider" },
      { key: "admin", label: "admin — darf verwalten" },
    ],
    // SMTP-Einstellungen (in der Datenbank, nicht in der .env)
    mailOffen: false,
    mailBusy: false,
    mailMeldung: "",
    mail: {
      enabled: false, host: "", port: 587, security: "starttls", username: "",
      password: "", password_set: false, sender: "", sender_name: "CoMesh",
      notify_to: "", notify_pending: true,
    },

    limit: 25,
    offset: 0,
    total: 0,
    items: [],
    counts: { pending: null, approved: null, rejected: null, admins: null },
    adminCount: null,
    loading: false,
    error: "",
    actionError: "",
    actionOk: "",
    neuerSchluessel: "",
    // Modellfreigabe je Konto
    modellKonto: null,
    modellListe: [],
    modellAuswahl: [],
    modellAlle: true,
    modellCloud: false,
    modellBusy: false,
    modellHinweis: "",
    denied: false,
    busyId: null,
    formOffen: false,
    form: { email: "", name: "", password: "", role: "both", initial_credits: 100 },

    async ladeMail() {
      try {
        const r = await api("/admin/mail", { auth: true });
        this.mail = { ...this.mail, ...r, password: "" };
      } catch (e) {
        this.mailMeldung = "Einstellungen nicht lesbar: " + e.message;
      }
    },

    async speichereMail() {
      this.mailBusy = true;
      this.mailMeldung = "";
      try {
        const body = {
          enabled: !!this.mail.enabled, host: this.mail.host, port: Number(this.mail.port) || 587,
          security: this.mail.security, username: this.mail.username,
          sender: this.mail.sender, sender_name: this.mail.sender_name,
          notify_to: this.mail.notify_to, notify_pending: !!this.mail.notify_pending,
        };
        if (this.mail.password) body.password = this.mail.password;   // leer = gespeichertes behalten
        const r = await api("/admin/mail", { method: "PUT", auth: true, body });
        this.mail = { ...this.mail, ...r, password: "" };
        this.mailMeldung = "Gespeichert.";
      } catch (e) {
        this.mailMeldung = e.message;
      } finally {
        this.mailBusy = false;
      }
    },

    async testMail() {
      this.mailBusy = true;
      this.mailMeldung = "sende …";
      try {
        const r = await api("/admin/mail/test", { method: "POST", auth: true });
        this.mailMeldung = (r.ok ? "Testmail: " : "Fehler: ") + (r.detail || "") +
          (r.to ? " → " + r.to : "");
      } catch (e) {
        this.mailMeldung = "Fehler: " + e.message;
      } finally {
        this.mailBusy = false;
      }
    },

    async init() {
      this.ladeMail();
      if (!Auth.requireLogin()) return;
      await this.reload();
    },

    isAdmin() {
      const u = Auth.currentUser() || {};
      return (u.role || "").toLowerCase() === "admin";
    },

    qs() {
      const p = new URLSearchParams();
      if (this.q) p.set("q", this.q);
      // Nur echte Zustaende senden: "all" heisst kein Filter.
      const s = (this.status || "").toLowerCase();
      if (["pending", "approved", "rejected"].includes(s)) p.set("status", s);
      p.set("limit", String(this.limit));
      p.set("offset", String(this.offset));
      return p.toString();
    },

    async reload() {
      await this.load();
      await this.loadCounts();
    },

    async load() {
      this.loading = true;
      this.error = "";
      try {
        const data = await api(`/admin/registrations?${this.qs()}`, { auth: true });
        this.items = (data && (data.registrations || data.items || data.users)) || [];
        this.total = (data && data.total) || this.items.length;
        this.denied = false;
      } catch (e) {
        const msg = e.message || "Laden fehlgeschlagen";
        this.denied = /admin role required/i.test(msg) || /403/.test(msg);
        this.error = this.denied ? "" : msg;
        this.items = [];
      } finally {
        this.loading = false;
      }
    },

    async loadCounts() {
      try {
        const [p, a, r, adm] = await Promise.all([
          api("/admin/registrations?status=pending&limit=1", { auth: true }),
          api("/admin/registrations?status=approved&limit=1", { auth: true }),
          api("/admin/registrations?status=rejected&limit=1", { auth: true }),
          api("/admin/users?role=admin&limit=1", { auth: true }),
        ]);
        this.counts = {
          pending: p.total == null ? 0 : p.total,
          approved: a.total == null ? 0 : a.total,
          rejected: r.total == null ? 0 : r.total,
          admins: adm.total == null ? 0 : adm.total,
        };
        this.adminCount = this.counts.admins;
      } catch (e) {
        /* Zähler sind Beiwerk. */
      }
    },

    _ok(msg) { this.actionError = ""; this.actionOk = msg; },
    _err(e, fallback) { this.actionOk = ""; this.actionError = (e && e.message) || fallback; },

    async approve(id) {
      this.busyId = id;
      try {
        await api(`/admin/registrations/${id}/approve`, { method: "POST", auth: true });
        this._ok("Freigegeben.");
        await this.reload();
      } catch (e) { this._err(e, "Freigabe fehlgeschlagen"); } finally { this.busyId = null; }
    },

    async reject(id) {
      if (!confirm("Diese Registrierung ablehnen? Die Schlüssel des Kontos werden deaktiviert.")) return;
      this.busyId = id;
      try {
        await api(`/admin/registrations/${id}/reject`, { method: "POST", auth: true });
        this._ok("Abgelehnt.");
        await this.reload();
      } catch (e) { this._err(e, "Ablehnung fehlgeschlagen"); } finally { this.busyId = null; }
    },

    async setRole(item, role) {
      if (!role || role === item.role) return;
      const warAdmin = (item.role || "") === "admin";
      const wirdAdmin = role === "admin";
      if (wirdAdmin && !confirm(`${item.email} zum Admin machen? Admins sehen alle Konten und können Rechte ändern.`)) {
        await this.load(); return;
      }
      if (warAdmin && !wirdAdmin) {
        if (this.adminCount != null && this.adminCount <= 1) {
          this._err(null, "Das ist der letzte Admin. Erst ein weiteres Konto zum Admin machen, dann entziehen.");
          await this.load(); return;
        }
        if (!confirm(`${item.email} die Admin-Rolle entziehen?`)) { await this.load(); return; }
      }
      this.busyId = item.id;
      try {
        const r = await api(`/admin/users/${item.id}`, { method: "PATCH", auth: true, body: { role } });
        item.role = (r && r.role) || role;
        this._ok(`${item.email}: Rolle jetzt ${item.role}.`);
        await this.loadCounts();
      } catch (e) {
        this._err(e, "Rollenwechsel fehlgeschlagen");
        await this.load();
      } finally { this.busyId = null; }
    },

    async toggleActive(item) {
      const neu = !item.is_active;
      if (!neu && !confirm(`${item.email} deaktivieren? Die API-Schlüssel werden ungültig.`)) return;
      this.busyId = item.id;
      try {
        const r = await api(`/admin/users/${item.id}`, { method: "PATCH", auth: true, body: { is_active: neu } });
        item.is_active = r && r.is_active != null ? r.is_active : neu;
        this._ok(`${item.email} ist jetzt ${item.is_active ? "aktiv" : "inaktiv"}.`);
      } catch (e) { this._err(e, "Aktivierung fehlgeschlagen"); } finally { this.busyId = null; }
    },

    /** Ein Konto löschen — mit Sicherheitsabfrage, die den Bestand nennt.
     *
     * Die Abfrage sagt, was verschwindet und was bleibt: Schlüssel und Sitzungen
     * gehen mit, die Einnahmen einer Node nicht. Ohne diesen Hinweis ist
     * "Löschen" ein Knopf mit unbekannter Wirkung.
     */
    async loeschen(item) {
      const frage = I18n.t("admin.delete.confirm", { email: item.email });
      if (!confirm(frage)) return;
      // Zweite, bewusste Bestätigung: der Vorgang ist nicht rückgängig zu machen.
      if (!confirm(I18n.t("admin.delete.confirm2", { email: item.email }))) return;
      this.busyId = item.id;
      try {
        const r = await api(`/admin/users/${item.id}`, { method: "DELETE", auth: true });
        const teile = [];
        if (r && r.keys_removed) teile.push(I18n.t("admin.delete.keys", { n: r.keys_removed }));
        if (r && r.nodes_kept && r.nodes_kept.length) {
          teile.push(I18n.t("admin.delete.nodes_kept", { ids: r.nodes_kept.join(", ") }));
        }
        if (r && r.nodes_removed && r.nodes_removed.length) {
          teile.push(I18n.t("admin.delete.nodes_removed", { n: r.nodes_removed.length }));
        }
        this._ok(I18n.t("admin.delete.done", { email: item.email, details: teile.join(" · ") }));
        await this.reload();
        await this.loadCounts();
      } catch (e) {
        this._err(e, I18n.t("admin.delete.failed"));
      } finally {
        this.busyId = null;
      }
    },

    /** Passwort setzen — der Supportfall "Passwort vergessen". */
    async setPasswort(item) {
      const pw = prompt(`Neues Passwort für ${item.email}:`);
      if (!pw) return;
      if (pw.length < 8 && !confirm("Kürzer als 8 Zeichen. Trotzdem setzen?")) return;
      this.busyId = item.id;
      try {
        await api(`/admin/users/${item.id}`, { method: "PATCH", auth: true, body: { password: pw } });
        this._ok(`Passwort für ${item.email} gesetzt.`);
      } catch (e) { this._err(e, "Passwort konnte nicht gesetzt werden"); } finally { this.busyId = null; }
    },

    /** Credits zuschieben (negativ = abziehen). */
    /** Freigabe eines Kontos öffnen und den Modellkatalog nachladen. */
    async modelle(item) {
      this.modellKonto = item;
      this.modellHinweis = "";
      this.modellAuswahl = Array.isArray(item.allowed_models) ? [...item.allowed_models] : [];
      this.modellAlle = !Array.isArray(item.allowed_models);
      this.modellCloud = !!item.allow_cloud;
      if (this.modellListe.length === 0) {
        try {
          const r = await api("/v1/available-models", { auth: true });
          this.modellListe = r.models || [];
        } catch (e) { this._err(e, "Modellliste konnte nicht geladen werden"); }
      }
    },

    modellUmschalten(name) {
      const i = this.modellAuswahl.indexOf(name);
      if (i === -1) this.modellAuswahl.push(name); else this.modellAuswahl.splice(i, 1);
    },

    /** Alle lokalen Modelle freigeben — als ausdrückliche Liste, weil bei einem Consumer
        "keine Liste" inzwischen "nichts" bedeutet. */
    modellAlleLokalen() {
      const lokale = this.modellListe.filter((m) => !m.is_cloud).map((m) => m.name);
      this.modellAuswahl = lokale;
      this.modellAlle = false;
      this.modellHinweis = lokale.length
        ? `${lokale.length} lokale Modelle ausgewählt — jetzt speichern.`
        : "Keine lokalen Modelle gefunden.";
    },

    modellStandard() {
      this.modellAuswahl = [];
      this.modellAlle = true;
      this.modellCloud = false;
      this.modellHinweis = "";
    },

    async modellSpeichern() {
      const konto = this.modellKonto;
      if (!konto) return;
      if (!this.modellAlle && this.modellAuswahl.length === 0 && !this.modellCloud) {
        this.modellHinweis = "Ohne Auswahl und ohne Cloud darf das Konto nichts nutzen. "
          + "Für \"alle lokalen\" den Haken oben setzen.";
        return;
      }
      this.modellBusy = true;
      this.modellHinweis = "";
      try {
        const r = await api(`/admin/users/${konto.id}`, {
          method: "PATCH", auth: true,
          body: {
            allowed_models: this.modellAlle ? null : [...this.modellAuswahl],
            allow_cloud: this.modellCloud,
          },
        });
        konto.allowed_models = r.allowed_models;
        konto.allow_cloud = r.allow_cloud;
        this._ok(`${konto.email}: Freigabe gespeichert.`);
        this.modellKonto = null;
      } catch (e) {
        this._err(e, "Freigabe konnte nicht gespeichert werden");
      } finally {
        this.modellBusy = false;
      }
    },

    /** Kurzfassung für die Zeile: was darf dieses Konto? */
    freigabeKurz(item) {
      const liste = item.allowed_models;
      const teile = [];
      if (liste === null || liste === undefined) teile.push("alle lokalen");
      else if (liste.length === 0) teile.push("nichts");
      else teile.push(`${liste.length} Modell${liste.length === 1 ? "" : "e"}`);
      if (item.allow_cloud) teile.push("Cloud");
      return teile.join(" + ");
    },

    async credits(item) {
      const eingabe = prompt(`Credits für ${item.email} (negativ = abziehen):`, "10");
      if (eingabe == null || eingabe.trim() === "") return;
      const betrag = Number(eingabe.replace(",", "."));
      if (!isFinite(betrag) || betrag === 0) { this._err(null, "Bitte eine Zahl ungleich 0 angeben."); return; }
      this.busyId = item.id;
      try {
        const r = await api(`/admin/users/${item.id}/topup`, {
          method: "POST", auth: true,
          body: { amount: betrag, reason: "manuell (admin)" },
        });
        item.credits = r && r.credits != null ? r.credits : item.credits;
        this._ok(`${item.email}: ${betrag > 0 ? "+" : ""}${betrag} Credits, Stand ${item.credits}.`);
      } catch (e) { this._err(e, "Credits konnten nicht gebucht werden"); } finally { this.busyId = null; }
    },

    /** Neue API-Schlüssel ausstellen — die alten werden dabei ungültig. */
    async schluessel(item) {
      if (!confirm(`Neuen Schlüssel für ${item.email} ausstellen? Der bisherige wird sofort ungültig.`)) return;
      this.busyId = item.id;
      this.neuerSchluessel = "";
      try {
        const r = await api(`/admin/users/${item.id}/keys`, { method: "POST", auth: true });
        if (r && r.api_key) {
          this.neuerSchluessel = `${item.email}: ${r.api_key}`;
          this._ok("Neuer Schlüssel ausgestellt — er wird nur jetzt angezeigt.");
        } else {
          this._ok("Schlüssel unverändert (Wiederholung).");
        }
      } catch (e) { this._err(e, "Schlüssel konnte nicht ausgestellt werden"); } finally { this.busyId = null; }
    },

    /** Konto anlegen. Der Schlüssel erscheint genau einmal. */
    async anlegen() {
      const f = this.form;
      if (!f.email || !f.name) { this._err(null, "E-Mail und Name sind Pflicht."); return; }
      this.busyId = -1;
      this.neuerSchluessel = "";
      try {
        const body = {
          email: f.email.trim(), name: f.name.trim(), role: f.role,
          initial_credits: Number(f.initial_credits) || 0,
        };
        if (f.password) body.password = f.password;
        const r = await api("/admin/users", { method: "POST", auth: true, body });
        if (r && r.api_key) this.neuerSchluessel = `${r.email}: ${r.api_key}`;
        this._ok(`Konto ${r.email} angelegt (id ${r.user_id}).`);
        this.form = { email: "", name: "", password: "", role: "both", initial_credits: 100 };
        this.formOffen = false;
        await this.reload();
      } catch (e) { this._err(e, "Konto konnte nicht angelegt werden"); } finally { this.busyId = null; }
    },

    statusLabel(s) {
      return ({ pending: "Ausstehend", approved: "Freigegeben", rejected: "Abgelehnt" })[s] || s || "—";
    },
    statusClass(s) {
      return s === "pending" ? "pill pill-paused"
        : s === "rejected" ? "pill pill-flat"
        : "pill";
    },

    search() { this.offset = 0; this.load(); },
    next() { if (this.offset + this.limit < this.total) { this.offset += this.limit; this.load(); } },
    prev() { if (this.offset > 0) { this.offset = Math.max(0, this.offset - this.limit); this.load(); } },
  }));
});
