// CoMesh — Admin: Registrierungen freigeben und Rollen verwalten.
//
// Backend (alles rollen-geprüft, nur role == "admin"):
//   GET   /admin/registrations?status=pending|approved|rejected&q=&limit=&offset=
//   POST  /admin/registrations/{id}/approve
//   POST  /admin/registrations/{id}/reject
//   PATCH /admin/users/{id}          { role?, is_active?, name? }
//   GET   /admin/users?role=admin    (nur zum Zählen der Admins)
//
// Der letzte Admin lässt sich hier nicht degradieren — sonst wäre der Bereich
// für alle Zeiten zu. Der Server prüft das (noch) nicht, deshalb steht der
// Riegel in der Oberfläche und wird gegen die echte Admin-Zahl geprüft.
document.addEventListener("alpine:init", () => {
  Alpine.data("registrationAdminPage", () => ({
    q: "",
    status: "pending",
    statuses: [
      { key: "pending", label: "Ausstehend" },
      { key: "approved", label: "Freigegeben" },
      { key: "rejected", label: "Abgelehnt" },
      { key: "", label: "Alle" },
    ],
    roles: [
      { key: "both", label: "both — Consumer + Provider" },
      { key: "consumer", label: "consumer" },
      { key: "provider", label: "provider" },
      { key: "admin", label: "admin — darf verwalten" },
    ],
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
    denied: false,
    busyId: null,

    async init() {
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
      if (this.status) p.set("status", this.status);
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

    /** Vier billige Zählabfragen (limit=1) — nur die total-Felder werden genutzt. */
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
        /* Zähler sind Beiwerk — die Tabelle bleibt brauchbar. */
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
      } catch (e) {
        this._err(e, "Freigabe fehlgeschlagen");
      } finally {
        this.busyId = null;
      }
    },

    async reject(id) {
      if (!confirm("Diese Registrierung ablehnen? Die Schlüssel des Kontos werden deaktiviert.")) return;
      this.busyId = id;
      try {
        await api(`/admin/registrations/${id}/reject`, { method: "POST", auth: true });
        this._ok("Abgelehnt.");
        await this.reload();
      } catch (e) {
        this._err(e, "Ablehnung fehlgeschlagen");
      } finally {
        this.busyId = null;
      }
    },

    /** Admin ernennen oder entziehen — mit Riegel gegen den letzten Admin. */
    async setRole(item, role) {
      if (!role || role === item.role) return;
      const warAdmin = (item.role || "") === "admin";
      const wirdAdmin = role === "admin";
      if (wirdAdmin && !confirm(`${item.email} zum Admin machen? Admins sehen alle Konten und können Rechte ändern.`)) {
        await this.load();
        return;
      }
      if (warAdmin && !wirdAdmin) {
        if (this.adminCount != null && this.adminCount <= 1) {
          this._err(null, "Das ist der letzte Admin. Erst ein weiteres Konto zum Admin machen, dann entziehen.");
          await this.load();
          return;
        }
        if (!confirm(`${item.email} die Admin-Rolle entziehen?`)) {
          await this.load();
          return;
        }
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
      } finally {
        this.busyId = null;
      }
    },

    async toggleActive(item) {
      const neu = !item.is_active;
      if (!neu && !confirm(`${item.email} deaktivieren? Die API-Schlüssel werden ungültig.`)) return;
      this.busyId = item.id;
      try {
        const r = await api(`/admin/users/${item.id}`, { method: "PATCH", auth: true, body: { is_active: neu } });
        item.is_active = r && r.is_active != null ? r.is_active : neu;
        this._ok(`${item.email} ist jetzt ${item.is_active ? "aktiv" : "inaktiv"}.`);
      } catch (e) {
        this._err(e, "Aktivierung fehlgeschlagen");
      } finally {
        this.busyId = null;
      }
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
    next() {
      if (this.offset + this.limit < this.total) { this.offset += this.limit; this.load(); }
    },
    prev() {
      if (this.offset > 0) { this.offset = Math.max(0, this.offset - this.limit); this.load(); }
    },
  }));
});
