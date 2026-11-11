/* Rechtstexte dieser Instanz — Admin-Formular.
 *
 * Die Werte kommen aus GET /admin/legal (Datenbank gewinnt gegen Umgebung) und
 * gehen als PUT zurück. Leeren eines Feldes löscht den Datenbank-Eintrag, dann
 * gilt wieder die Umgebungsvariable der Instanz.
 */
const LEGAL_FELDER = [
  "IMPRESSUM_FIRMA", "IMPRESSUM_STRASSE", "IMPRESSUM_PLZ_ORT", "IMPRESSUM_LAND",
  "IMPRESSUM_EMAIL", "IMPRESSUM_TELEFON", "IMPRESSUM_VERTRETEN", "IMPRESSUM_REGISTER",
  "IMPRESSUM_USTID", "DATENSCHUTZ_EMAIL", "HOSTING_ANBIETER",
];

function legalAdminPage() {
  const leeresFeld = () => ({ wert: "", quelle: "leer" });

  return {
    allowed: false,
    loading: true,
    busy: false,
    msg: "",
    error: false,
    fehlend: [],
    ausUmgebung: [],
    upstream: "",
    werte: LEGAL_FELDER.reduce((acc, name) => { acc[name] = leeresFeld(); return acc; }, {}),

    async init() {
      if (!Auth.requireLogin()) return;
      const user = Auth.currentUser() || {};
      this.allowed = String(user.role || "").toLowerCase() === "admin";
      this.loading = false;
      if (!this.allowed) return;
      await this.laden();
    },

    async laden() {
      try {
        const d = await api("/admin/legal", { auth: true });
        this.uebernehmen(d);
        this.error = false;
      } catch (e) {
        this.error = true;
        this.msg = e.message || I18n.t("laden-fehlgeschlagen");
      }
    },

    uebernehmen(d) {
      if (!d || !d.werte) return;
      LEGAL_FELDER.forEach((name) => {
        const eintrag = d.werte[name] || leeresFeld();
        this.werte[name] = { wert: eintrag.wert || "", quelle: eintrag.quelle || "leer" };
      });
      this.fehlend = d.fehlend || [];
      this.upstream = d.upstream || "";
      this.ausUmgebung = LEGAL_FELDER.filter((n) => (this.werte[n].quelle || "") === "umgebung");
    },

    async save() {
      this.busy = true;
      this.msg = "";
      this.error = false;
      try {
        const nutzlast = {};
        LEGAL_FELDER.forEach((name) => { nutzlast[name] = this.werte[name].wert || ""; });
        const d = await api("/admin/legal", { method: "PUT", body: nutzlast, auth: true });
        this.uebernehmen(d);
        this.msg = this.fehlend.length
          ? I18n.t("legal_admin.saved_open", { n: this.fehlend.length })
          : I18n.t("legal_admin.saved_ok");
      } catch (e) {
        this.error = true;
        this.msg = e.message || I18n.t("legal_admin.save_failed");
      } finally {
        this.busy = false;
      }
    },
  };
}

window.legalAdminPage = legalAdminPage;
