// CoMesh — /admin-nodes (Admin-Sicht auf alle Geräte).
//
// Backend: GET /admin/nodes (Filter q, status, owner_id, backend) und
// GET /admin/nodes/{id} fürs Detail. Pausieren/Aktivieren läuft über
// POST /admin/users/{owner_id}/nodes/{id}/enable?enabled=true|false — der Besitzer
// kann das für fremde Nodes nicht, der Admin schon.
//
// Warum die Frische zählt: `gpu_nodes.status` ist kein Lebenszeichen. Nach einem
// Reboot stand die Spalte weiter auf "online", während der Agent seit Stunden keinen
// Herzschlag absetzte. Deshalb steht der letzte Herzschlag im Detail, nicht nur der
// Zustand in der Tabelle.
document.addEventListener("alpine:init", () => {
  Alpine.data("adminNodesPage", () => ({

    /** Netzadressen stehen standardmäßig maskiert in der Liste. */
    zeigeAdressen: false,

    /**
     * Host einer Agenten-Adresse unkenntlich machen; Schema und Port bleiben lesbar,
     * weil sie zur Diagnose reichen und nichts über den Rechner verraten.
     */
    maskiere(url) {
      if (!url) return "";
      const roh = String(url);
      try {
        const u = new URL(roh.includes("://") ? roh : "http://" + roh);
        return u.protocol + "//" + "\u2022".repeat(8) + (u.port ? ":" + u.port : "");
      } catch (e) {
        return roh.replace(/^([a-z]+:\/\/)?[^/:]+/i, function (m) {
          return (m.indexOf("//") >= 0 ? m.slice(0, m.indexOf("//") + 2) : "") + "\u2022".repeat(8);
        });
      }
    },
    q: "",
    status: "all",
    statuses: [
      { key: "all", label: "Alle" },
      { key: "online", label: "Online" },
      { key: "offline", label: "Offline" },
      { key: "busy", label: "Beschäftigt" },
      { key: "disabled", label: "Pausiert" },
    ],
    items: [],
    summary: null,
    loading: true,
    error: "",
    actionOk: "",
    actionError: "",
    detail: null,
    busyId: null,

    async init() {
      await this.load();
    },

    async load() {
      this.loading = true;
      this.error = "";
      this.actionOk = "";
      this.actionError = "";
      try {
        const p = new URLSearchParams({ limit: "100" });
        if (this.q && this.q.trim()) p.set("q", this.q.trim());
        if (this.status !== "all") p.set("status", this.status);
        const d = await api("/admin/nodes?" + p.toString(), { auth: true });
        this.items = (d && (d.nodes || d.items)) || [];
        this.summary = (d && d.summary) || null;
      } catch (e) {
        this.error = (e && e.message) || "Geräte konnten nicht geladen werden";
        this.items = [];
        this.summary = null;
      } finally {
        this.loading = false;
      }
    },

    async details(n) {
      this.busyId = n.id;
      this.actionError = "";
      try {
        this.detail = await api("/admin/nodes/" + n.id, { auth: true });
      } catch (e) {
        this.actionError = (e && e.message) || "Detail konnte nicht geladen werden";
      } finally {
        this.busyId = null;
      }
    },

    async umschalten(n) {
      const ziel = !n.is_enabled;
      if (!confirm(ziel
        ? `Gerät "${n.name}" wieder aktivieren?`
        : `Gerät "${n.name}" pausieren? Der Besitzer kann es selbst wieder einschalten.`)) return;
      this.busyId = n.id;
      this.actionError = "";
      try {
        await api(`/admin/users/${n.owner_id}/nodes/${n.id}/enable?enabled=${ziel}`,
                  { method: "POST", auth: true });
        n.is_enabled = ziel;
        this.actionOk = `${n.name}: ${ziel ? "aktiviert" : "pausiert"}.`;
        if (this.detail && this.detail.id === n.id) this.detail.is_enabled = ziel;
      } catch (e) {
        this.actionError = (e && e.message) || "Umschalten fehlgeschlagen";
      } finally {
        this.busyId = null;
      }
    },

    /** Modellfreigabe einer Node ändern (Administrationsweg).
     *
     * Die Freigabe gehört dem Provider — er pflegt sie in seiner Geräteseite.
     * Die Administration behält den Zugriff für Supportfälle, deshalb derselbe
     * Endpunkt `PUT /nodes/{id}` mit derselben Wirkung. Leeres Feld setzt die
     * Liste auf NULL zurück (= alle lokalen Modelle, keine Cloud).
     */
    async modelle(n) {
      const aktuell = Array.isArray(n.allowed_models) ? n.allowed_models.join(", ") : "";
      const eingabe = prompt(
        `Modelle, die "${n.name}" anbietet (durch Komma getrennt).\n` +
        `Leer = alle lokalen Modelle dieser Maschine, keine Cloud-Modelle.`,
        aktuell
      );
      if (eingabe === null) return;  // abgebrochen
      const liste = eingabe.split(/[,\n;]+/).map((m) => m.trim()).filter(Boolean);
      this.busyId = n.id;
      this.actionError = "";
      try {
        const body = liste.length > 0 ? { allowed_models: liste } : { clear_allowed_models: true };
        const r = await api(`/nodes/${n.id}`, { method: "PUT", auth: true, body });
        n.allowed_models = r.allowed_models;
        if (this.detail && this.detail.id === n.id) this.detail.allowed_models = r.allowed_models;
        this.actionOk = `${n.name}: ${this.modellKurz(n)}.`;
      } catch (e) {
        this.actionError = (e && e.message) || "Modelle konnten nicht gespeichert werden";
      } finally {
        this.busyId = null;
      }
    },

    /** Zustand als Pille: online grün, beschäftigt gelb, offline grau, pausiert dunkel. */
    zustandsKlasse(n) {
      if (!n.is_enabled) return "pill pill-paused";
      const z = (n.effective_status || n.status || "").toLowerCase();
      if (z === "online") return "pill pill-online";
      if (z === "busy") return "pill pill-busy";
      return "pill pill-offline";
    },

    /** Was das Gerät anbietet: leer = alle lokalen, sonst die Liste. */
    modellKurz(n) {
      const liste = n.allowed_models;
      if (liste === null || liste === undefined) return "alle lokalen";
      if (liste.length === 0) return "nichts freigegeben";
      return liste.join(", ");
    },

    herzschlagText(d) {
      const hb = d && d.last_heartbeat;
      if (!hb) return "—";
      const wann = hb.received_at || hb.created_at || hb.at;
      if (!wann) return JSON.stringify(hb).slice(0, 60);
      const sekunden = Math.max(0, (Date.now() - new Date(wann.replace(" ", "T")).getTime()) / 1000);
      if (!isFinite(sekunden)) return String(wann);
      if (sekunden < 90) return `vor ${Math.round(sekunden)} s`;
      if (sekunden < 5400) return `vor ${Math.round(sekunden / 60)} min`;
      return `vor ${Math.round(sekunden / 3600)} h (veraltet)`;
    },
  }));
});
