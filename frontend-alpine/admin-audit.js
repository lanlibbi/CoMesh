// CoMesh — Admin-Protokoll: wer hat wann was geändert.
//
// Backend: GET /admin/audit?action=&admin_user_id=&target_id=&limit=&offset=
// Die Tabelle admin_audit_log wurde bisher nur geschrieben; dieser Endpunkt
// macht sie lesbar. Passwörter und Schlüsselwerte stehen nicht drin.
document.addEventListener("alpine:init", () => {
  Alpine.data("auditPage", () => ({
    aktion: "",
    aktionen: [
      { key: "", label: "Alle Aktionen" },
      { key: "user.create", label: "Konto angelegt" },
      { key: "user.update", label: "Konto geändert" },
      { key: "user.topup", label: "Credits gebucht" },
      { key: "node.enable", label: "Gerät freigegeben" },
    ],
    limit: 50,
    offset: 0,
    total: 0,
    events: [],
    loading: false,
    error: "",
    denied: false,

    async init() {
      if (!Auth.requireLogin()) return;
      await this.load();
    },

    isAdmin() {
      const u = Auth.currentUser() || {};
      return (u.role || "").toLowerCase() === "admin";
    },

    async load() {
      this.loading = true;
      this.error = "";
      try {
        const p = new URLSearchParams();
        if (this.aktion) p.set("action", this.aktion);
        p.set("limit", String(this.limit));
        p.set("offset", String(this.offset));
        const d = await api(`/admin/audit?${p}`, { auth: true });
        this.events = (d && (d.events || d.items)) || [];
        this.total = (d && d.total) || this.events.length;
        this.denied = false;
      } catch (e) {
        const msg = e.message || "Laden fehlgeschlagen";
        this.denied = /admin role required/i.test(msg) || /403/.test(msg);
        this.error = this.denied ? "" : msg;
        this.events = [];
      } finally {
        this.loading = false;
      }
    },

    filter() { this.offset = 0; this.load(); },
    next() { if (this.offset + this.limit < this.total) { this.offset += this.limit; this.load(); } },
    prev() { if (this.offset > 0) { this.offset = Math.max(0, this.offset - this.limit); this.load(); } },

    aktionLabel(a) {
      return ({
        "user.create": "Konto angelegt",
        "user.update": "Konto geändert",
        "user.topup": "Credits gebucht",
        "node.enable": "Gerät freigegeben",
        "user.key.rotate": "Schlüssel erneuert",
        "user.key.revoke": "Schlüssel entzogen",
        "node.disable": "Gerät gesperrt",
      })[a] || a;
    },

    /** Änderungen lesbar machen: {role: {from, to}} -> "role: both → admin" */
    aenderung(e) {
      const c = e.changed;
      if (!c || typeof c !== "object") return "—";
      return Object.keys(c).map((k) => {
        const v = c[k] || {};
        if (v.changed === true) return `${k}: geändert`;
        if (v.from !== undefined || v.to !== undefined) return `${k}: ${v.from} → ${v.to}`;
        return `${k}: ${JSON.stringify(v)}`;
      }).join(" · ");
    },
  }));
});
