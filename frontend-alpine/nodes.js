// CoMesh — /nodes page (alpine frontend). Register a node + list mine.

// Der Abschnitt „Eigene Node beitragen" (nodes.html) braucht zwei Dinge, die
// nicht im Markup stehen können:
//
//   * die Adresse, unter der das Portal gerade benutzt wird (window.location)
//     und — falls abweichend — die öffentliche; beide sollen im Befehl stehen,
//     damit niemand eine URL raten muss,
//   * die Dateiliste mit Größe und SHA-256. Beides wird beim Laden aus der
//     ausgelieferten Datei gelesen (HEAD für die Größe, die `.sha256`-Datei
//     daneben für die Summe) statt hier eingetragen: eine abgetippte Summe ist
//     nach dem nächsten Release falsch, ohne dass es jemand merkt.
//
// Die öffentliche Adresse ist die einzige feste Adresse im Frontend; sie lässt
// sich über `window.COMESH_PUBLIC_ORIGIN` (config.js) überschreiben, damit ein
// anderer Aufbau nicht am Quelltext hängt.
const CONTRIBUTE_PUBLIC_ORIGIN = "https://comesh.lanlibbilab.me";

// `hasSum: false` — für die beiden Installer gibt es keine .sha256-Datei; sie
// prüfen die Summe des Binaries, das sie laden. Die Spalte sagt das dann auch.
const CONTRIBUTE_FILES = [
  { file: "install.sh", platform: "macOS / Linux", hasSum: false },
  { file: "install.ps1", platform: "Windows", hasSum: false },
  { file: "comesh-agent-linux-x86_64", platform: "Linux x86_64", hasSum: true },
  { file: "comesh-agent-windows-x86_64.exe", platform: "Windows x86_64", hasSum: true },
  { file: "comesh-agent-darwin-arm64", platform: "macOS arm64", hasSum: true },
];

// Kopier-Rückmeldung je Knopf; außerhalb der Alpine-Daten, damit ein Timer die
// Ansicht nicht neu zeichnet.
const COPY_TIMERS = {};

document.addEventListener("alpine:init", () => {
  Alpine.data("nodesPage", () => ({
  myNodes: [],
  // Provider-Funktionen (Registrieren, Massenaktionen) hängen an der Rolle.
  // Die Seite selbst ist für jedes Konto offen — der Abschnitt „Eigene Node
  // beitragen" ist der Weg, über den ein Konto Provider wird. Vorbelegt aus
  // dem gespeicherten Konto, damit beim ersten Aufbau nichts aufblitzt;
  // `init()` liest die Rolle danach erneut.
  isProvider: Auth.canProvide(),
  // Mirrors the backend credits flag: hides credit rates / earnings labelling.
  billing: Credits.enabled(),
  availableModels: [],
  editingId: null,
  editAllowed: [],
  // Freitextfeld: die Modelle, die WIRKLICH auf dieser Node liegen. Der
  // Katalog unten kommt vom Portal-Host und ist fuer einen Provider oft der
  // falsche — deshalb ist das Feld die fuehrende Eingabe.
  editModelsText: "",
  // Adresse und Port werden getrennt bearbeitet: nach einem Umzug oder einem
  // falsch eingetragenen Port ist das die einzige Korrektur, die man braucht.
  editUrl: "",
  editPort: 11435,
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

  // ---- Eigene Node beitragen -----------------------------------------
  originChoice: "current",   // "current" | "public"
  artifacts: [],             // Größe/Summe kommen aus loadArtifacts()
  copyState: { unix: "", windows: "" },

    async init() {
      // Kein Rollen-Riegel für die ganze Seite: ein Consumer muss den
      // Installationsweg sehen können, sonst findet er nie zum Provider.
      // Ausgeblendet werden nur die Provider-Funktionen (Markup über
      // `isProvider`), und das Server-Gate in nodes.py bleibt bestehen.
      if (!Auth.requireLogin()) return;
      this.isProvider = Auth.canProvide();
      this.billing = Credits.enabled();
      this.initContribute();
      await this.load();
      if (this.isProvider) await this.loadAvailableModels();
      this.billing = Credits.enabled();
    },

    // ---- Eigene Node beitragen -----------------------------------------
    // Die Dateiliste steht im Markup zur Verfügung, bevor die Größen da sind;
    // sie werden nachgeladen und erscheinen dann von selbst (Alpine).
    initContribute() {
      this.artifacts = CONTRIBUTE_FILES.map((a) => ({
        file: a.file,
        platform: a.platform,
        hasSum: a.hasSum,
        bytes: null,
        sizeState: "pending",
        sha: null,
        sumState: a.hasSum ? "pending" : "none",
      }));
      this.loadArtifacts();
    },

    /** Nur der Pfad ist fest — der Host kommt aus der Adresswahl. */
    downloadsBase(origin) {
      return `${String(origin).replace(/\/+$/, "")}/downloads`;
    },

    get currentOrigin() { return window.location.origin; },
    get publicOrigin() {
      return String(window.COMESH_PUBLIC_ORIGIN || CONTRIBUTE_PUBLIC_ORIGIN).replace(/\/+$/, "");
    },
    /** Die Adresswahl erscheint nur, wenn sich die beiden wirklich unterscheiden. */
    get hasTwoOrigins() { return this.publicOrigin !== this.currentOrigin; },
    get chosenOrigin() {
      return (this.originChoice === "public" && this.hasTwoOrigins)
        ? this.publicOrigin
        : this.currentOrigin;
    },

    get commandUnix() {
      return `curl -fsSL ${this.downloadsBase(this.chosenOrigin)}/install.sh | sh`;
    },
    get commandWindows() {
      // -ExecutionPolicy Bypass: auf verwalteten Rechnern ist die Skriptausfuehrung
      // gesperrt (PSSecurityException). Der Bypass gilt nur fuer diesen Aufruf.
      return `powershell -ExecutionPolicy Bypass -Command "irm ${this.downloadsBase(this.chosenOrigin)}/install.ps1 | iex"`;
    },

    /**
     * Download-Adresse. Bei Binaries mit Prüfsumme hängt die Summe als Query
     * dran — wie in install.sh: der Query ändert sich mit dem Inhalt, eine alte
     * Cloudflare-Kopie der .exe kann dann nicht mehr greifen.
     */
    artifactHref(a) {
      const pin = (a.hasSum && a.sha) ? `?sha=${a.sha.slice(0, 12)}` : "";
      return `${this.downloadsBase(this.chosenOrigin)}/${a.file}${pin}`;
    },

    async loadArtifacts() {
      const base = this.downloadsBase(this.currentOrigin);
      await Promise.all(this.artifacts.map((a) => this.loadArtifact(a, base)));
    },

    /** Größe über HEAD (kein 14-MB-Download), Summe aus der .sha256 daneben. */
    async loadArtifact(a, base) {
      const url = `${base}/${a.file}`;
      try {
        const head = await fetch(url, { method: "HEAD", cache: "no-store" });
        const len = Number(head.headers.get("content-length"));
        if (head.ok && Number.isFinite(len) && len > 0) {
          a.bytes = len;
          a.sizeState = "ok";
        } else {
          a.sizeState = "error";
        }
      } catch (e) {
        a.sizeState = "error";
      }
      if (!a.hasSum) return;
      try {
        const res = await fetch(`${url}.sha256`, { cache: "no-store" });
        const text = res.ok ? await res.text() : "";
        const first = (text.trim().split(/\s+/)[0] || "").toLowerCase();
        if (/^[0-9a-f]{64}$/.test(first)) {
          a.sha = first;
          a.sumState = "ok";
        } else {
          a.sumState = "error";
        }
      } catch (e) {
        a.sumState = "error";
      }
    },

    /**
     * Der Lesezugriff auf den Sprach-Store ist der Grund für diese Methode: ohne
     * ihn zeichnet Alpine die per x-text gesetzten Beschriftungen bei einem
     * Sprachwechsel nicht neu (das Markup mit data-i18n erledigt I18n.apply()).
     *
     * Über `Alpine.store("lang")` statt `this.$store`: die Magie `$store` gibt es
     * nur im Ausdrucks-Scope, nicht in einer Methode — dort ist sie undefined,
     * der Lesezugriff fiele aus und die Beschriftungen blieben in der alten
     * Sprache stehen (gemessen: „Laden"/„Kopieren" unter EN/ES/FR).
     */
    touchLang() {
      try {
        const store = (window.Alpine && window.Alpine.store) ? window.Alpine.store("lang") : null;
        if (store) void store.code;
      } catch (e) { /* außerhalb von Alpine */ }
    },
    sizeText(a) {
      this.touchLang();
      if (a.sizeState === "pending") return I18n.t("node.contribute.pending");
      if (a.sizeState !== "ok" || !a.bytes) return I18n.t("node.contribute.unavailable");
      return `${a.bytes.toLocaleString(localeTag())} B`;
    },
    shaText(a) {
      this.touchLang();
      if (a.sumState === "pending") return I18n.t("node.contribute.pending");
      if (a.sumState === "none") return I18n.t("node.contribute.no_checksum");
      if (a.sumState !== "ok" || !a.sha) return I18n.t("node.contribute.unavailable");
      return a.sha;
    },
    copyLabel(which) {
      this.touchLang();
      const state = this.copyState[which];
      if (state === "ok") return I18n.t("node.contribute.copied");
      if (state === "err") return I18n.t("node.contribute.copy_failed");
      return I18n.t("node.contribute.copy");
    },
    get copyLabelUnix() { return this.copyLabel("unix"); },
    get copyLabelWindows() { return this.copyLabel("windows"); },
    get downloadLabel() {
      this.touchLang();
      return I18n.t("node.contribute.download");
    },

    async copyCommand(which) {
      const text = which === "windows" ? this.commandWindows : this.commandUnix;
      const ok = await this.copyToClipboard(text);
      this.copyState[which] = ok ? "ok" : "err";
      clearTimeout(COPY_TIMERS[which]);
      COPY_TIMERS[which] = setTimeout(() => { this.copyState[which] = ""; }, 2600);
    },

    /**
     * navigator.clipboard gibt es nur im secure context. Das Portal läuft auch
     * über http im LAN (192.168.x.y:8767) — dort ist der textarea-Weg der
     * Normalfall, nicht die Ausnahme.
     */
    async copyToClipboard(text) {
      try {
        if (navigator.clipboard && window.isSecureContext) {
          await navigator.clipboard.writeText(text);
          return true;
        }
      } catch (e) { /* weiter mit dem Fallback */ }
      try {
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.setAttribute("readonly", "");
        ta.style.position = "fixed";
        ta.style.top = "-1000px";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        ta.setSelectionRange(0, text.length);
        const ok = document.execCommand("copy");
        ta.remove();
        return ok;
      } catch (e) {
        return false;
      }
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
      if (!this.isProvider || targets.length === 0) return;

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
      if (!this.isProvider || this.selectedCount === 0) return;
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
      if (!this.isProvider) return;
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
      this.editModelsText = this.editAllowed.join(", ");
      this.editUrl = n.node_url || "";
      this.editPort = n.port || 11435;
    },
    cancelEdit() {
      this.editingId = null;
      this.editAllowed = [];
      this.editModelsText = "";
      this.editUrl = "";
      this.editPort = 11435;
    },
    toggleEditModel(name) {
      const i = this.editAllowed.indexOf(name);
      if (i >= 0) this.editAllowed.splice(i, 1);
      else this.editAllowed.push(name);
      this.editModelsText = this.editAllowed.join(", ");
    },
    /** Freitext -> Liste. Komma, Semikolon und Zeilenumbrueche trennen. */
    parseModelsText(text) {
      return String(text || "")
        .split(/[,\n;]+/)
        .map((m) => m.trim())
        .filter((m) => m.length > 0);
    },
    /** Modelle aus dem Freitext in die Auswahlliste uebernehmen. */
    uebernehmeFreitext() {
      const liste = this.parseModelsText(this.editModelsText);
      const fremde = liste.filter((m) => !this.editAllowed.includes(m));
      this.editAllowed = [...this.editAllowed, ...fremde];
      toast(I18n.t("nodes.models.adopted", { n: fremde.length }), "ok");
    },
    /**
     * Modelle, die der Agent dieser Node selbst gemeldet hat (Sicht seines
     * Backends). Getrennt von `allowed_models`: die Freigabe sagt, was ANDERE
     * nutzen dürfen, diese Liste sagt, was auf der Maschine liegt.
     */
    gemeldeteModelle(n) {
      return Array.isArray(n && n.reported_models) ? n.reported_models : [];
    },
    /** Gemeldete Modelle ins Freitextfeld übernehmen — gespeichert wird später. */
    uebernehmeGemeldete(n) {
      const vorhanden = this.parseModelsText(this.editModelsText);
      const neu = this.gemeldeteModelle(n).filter((m) => !vorhanden.includes(m));
      this.editModelsText = [...vorhanden, ...neu].join(", ");
      toast(
        neu.length
          ? `${neu.length} gemeldete Modelle übernommen — noch speichern.`
          : "Alle gemeldeten Modelle stehen schon im Feld.",
        "ok",
      );
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
        // Das Freitextfeld gilt: es beschreibt die Maschine des Providers.
        // Leer heisst "alle lokalen Modelle" (NULL), nicht "nichts".
        const liste = this.parseModelsText(this.editModelsText);
        const body = liste.length > 0
          ? { allowed_models: liste }
          : { clear_allowed_models: true };
        // Adresse und Port nur mitschicken, wenn sie sich geaendert haben. Ein leeres Feld
        // heisst "nichts anfassen": der Agent meldet seine Adresse beim Heartbeat selbst.
        const url = String(this.editUrl || "").trim();
        if (url && url !== String(n.node_url || "").trim()) body.node_url = url;
        const port = Number(this.editPort);
        if (Number.isFinite(port) && port >= 1 && port <= 65535 && port !== Number(n.port)) {
          body.port = port;
        }
        await api(`/nodes/${n.id}`, { method: "PUT", auth: true, body });
        toast(body.node_url || body.port ? "Adresse gespeichert — die Node meldet sich"
                                          + " beim naechsten Heartbeat mit der neuen Adresse."
                                        : I18n.t("nodes.whitelist_updated"), "ok");
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
