// CoMesh i18n v4 — Dropdown-Switcher, EN/DE/ES/FR (KEIN PT, KEIN ZH)
// Basis: Anthrazit/Messing-Design. Default-Sprache: EN (Weisung Christian 29./30.09.)
const I18N_DICT = {
  en: {
    "nav.dashboard": "Dashboard", "nav.chat": "Chat", "nav.pool": "Pool",
    "nav.nodes": "Nodes", "nav.earnings": "Earnings", "nav.agent": "Agent",
    "nav.profile": "Profile", "nav.usage": "Usage", "nav.adminUsage": "Admin Usage",
    "nav.logout": "Logout",
    "login.title": "Sign in · CoMesh",
    "login.h1": "Contribute GPUs to the pool, use the whole pool through one OpenAI-compatible API — free and powered by your community.",
    "login.intro": "One pool of machines with a free GPU, one OpenAI-compatible entry point. Free, carried by the community — no subscription, no per-token billing.",
    "login.sub": "Sign in to manage your nodes, API keys and usage.",
    "login.email": "E-mail", "login.password": "Password",
    "login.submit": "Sign in", "login.submitting": "Signing in…",
    "login.emailPh": "name@example.com", "login.error": "Sign-in failed",
    "login.welcome": "Welcome back",
    "reg.title": "Register · CoMesh",
    "reg.sub": "Create an account and join in.",
    "reg.submit": "Create account", "reg.submitting": "Creating…",
    "idx.keyTitle": "Save your API key now",
    "idx.copy": "Copy", "idx.saved": "I've saved it",
    "idx.overview": "Overview",
    "idx.overviewSub": "Balance, API access and recent calls at a glance.",
    "idx.balance": "Credit balance", "idx.openChat": "Open chat",
    "idx.refresh": "Refresh", "idx.registered": "Registered",
    "idx.usage": "Usage", "idx.usageSub": "Tokens used per day.",
    "idx.stats": "Stats", "idx.apiCalls": "API calls",
    "idx.tokensUsed": "Tokens used", "idx.models": "Models",
    "idx.creditsUsed": "Credits spent", "idx.lastActivity": "Last activity",
    "idx.apiKey": "API key", "idx.regenerate": "Regenerate",
    "idx.recent": "Recent calls"
  },
  de: {
    "nav.dashboard": "Dashboard", "nav.chat": "Chat", "nav.pool": "Pool",
    "nav.nodes": "Nodes", "nav.earnings": "Einnahmen", "nav.agent": "Agent",
    "nav.profile": "Profil", "nav.usage": "Statistik", "nav.adminUsage": "Admin-Statistik",
    "nav.logout": "Logout",
    "login.title": "Anmelden · CoMesh",
    "login.h1": "Stelle GPUs für den Pool bereit und nutze den ganzen Pool über eine einzige OpenAI-kompatible API — kostenlos und von deiner Community getragen.",
    "login.intro": "Ein Pool aus Rechnern mit freier GPU, ein einziger OpenAI-kompatibler Zugang. Kostenlos, getragen von der Community — kein Abo, keine Abrechnung pro Token.",
    "login.sub": "Melde dich an, um Nodes, API-Keys und Nutzung zu verwalten.",
    "login.email": "E-Mail", "login.password": "Passwort",
    "login.submit": "Anmelden", "login.submitting": "Anmeldung läuft…",
    "login.emailPh": "name@beispiel.de", "login.error": "Anmeldung fehlgeschlagen",
    "login.welcome": "Willkommen zurück",
    "reg.title": "Registrieren · CoMesh",
    "reg.sub": "Konto anlegen und mitmachen.",
    "reg.submit": "Konto anlegen", "reg.submitting": "Wird angelegt…",
    "idx.keyTitle": "API-Key jetzt sichern",
    "idx.copy": "Kopieren", "idx.saved": "Habe ich gesichert",
    "idx.overview": "Übersicht",
    "idx.overviewSub": "Guthaben, API-Zugang und die letzten Aufrufe auf einen Blick.",
    "idx.balance": "Credit-Guthaben", "idx.openChat": "Chat öffnen",
    "idx.refresh": "Aktualisieren", "idx.registered": "Registriert",
    "idx.usage": "Verbrauch", "idx.usageSub": "Pro Tag verbrauchte Token.",
    "idx.stats": "Kennzahlen", "idx.apiCalls": "API-Aufrufe",
    "idx.tokensUsed": "Token verbraucht", "idx.models": "Modelle",
    "idx.creditsUsed": "Credits verbraucht", "idx.lastActivity": "Letzte Aktivität",
    "idx.apiKey": "API-Key", "idx.regenerate": "Neu ausstellen",
    "idx.recent": "Protokoll"
  },
  es: {
    "nav.dashboard": "Panel", "nav.chat": "Chat", "nav.pool": "Pool",
    "nav.nodes": "Nodos", "nav.earnings": "Ingresos", "nav.agent": "Agente",
    "nav.profile": "Perfil", "nav.usage": "Uso", "nav.adminUsage": "Uso admin",
    "nav.logout": "Salir",
    "login.title": "Iniciar sesión · CoMesh",
    "login.h1": "Aporta GPUs al pool y usa todo el pool a través de una única API compatible con OpenAI: gratis y sostenido por tu comunidad.",
    "login.intro": "Un pool de máquinas con GPU libre, un único acceso compatible con OpenAI. Gratis y sostenido por la comunidad: sin suscripción ni facturación por Token.",
    "login.sub": "Inicia sesión para gestionar tus nodes, API keys y consumo.",
    "login.email": "Correo", "login.password": "Contraseña",
    "login.submit": "Entrar", "login.submitting": "Entrando…",
    "login.emailPh": "nombre@ejemplo.com", "login.error": "Error al entrar",
    "login.welcome": "Bienvenido de nuevo",
    "reg.title": "Registro · CoMesh",
    "reg.sub": "Crea una cuenta y participa.",
    "reg.submit": "Crear cuenta", "reg.submitting": "Creando…",
    "idx.keyTitle": "Guarda tu clave API ahora",
    "idx.copy": "Copiar", "idx.saved": "Ya la guardé",
    "idx.overview": "Resumen",
    "idx.overviewSub": "Saldo, acceso API y últimas llamadas de un vistazo.",
    "idx.balance": "Saldo de créditos", "idx.openChat": "Abrir chat",
    "idx.refresh": "Actualizar", "idx.registered": "Registrado",
    "idx.usage": "Uso", "idx.usageSub": "Tokens usados por día.",
    "idx.stats": "Estadísticas", "idx.apiCalls": "Llamadas API",
    "idx.tokensUsed": "Tokens usados", "idx.models": "Modelos",
    "idx.creditsUsed": "Créditos gastados", "idx.lastActivity": "Última actividad",
    "idx.apiKey": "Clave API", "idx.regenerate": "Regenerar",
    "idx.recent": "Registro"
  },
  fr: {
    "nav.dashboard": "Tableau de bord", "nav.chat": "Chat", "nav.pool": "Pool",
    "nav.nodes": "Nœuds", "nav.earnings": "Revenus", "nav.agent": "Agent",
    "nav.profile": "Profil", "nav.usage": "Utilisation", "nav.adminUsage": "Utilisation admin",
    "nav.logout": "Déconnexion",
    "login.title": "Connexion · CoMesh",
    "login.h1": "Apportez des GPU au pool et utilisez tout le pool via une seule API compatible OpenAI — gratuit et porté par votre communauté.",
    "login.intro": "Un pool de machines avec un GPU libre, un seul accès compatible OpenAI. Gratuit et porté par la communauté — sans abonnement, sans facturation par Token.",
    "login.sub": "Connectez-vous pour gérer vos nodes, clés API et consommation.",
    "login.email": "E-mail", "login.password": "Mot de passe",
    "login.submit": "Connexion", "login.submitting": "Connexion…",
    "login.emailPh": "nom@exemple.fr", "login.error": "Échec de connexion",
    "login.welcome": "Bon retour",
    "reg.title": "Inscription · CoMesh",
    "reg.sub": "Créez un compte et participez.",
    "reg.submit": "Créer le compte", "reg.submitting": "Création…",
    "idx.keyTitle": "Sauvegardez votre clé API maintenant",
    "idx.copy": "Copier", "idx.saved": "C'est noté",
    "idx.overview": "Aperçu",
    "idx.overviewSub": "Solde, accès API et derniers appels d'un coup d'œil.",
    "idx.balance": "Solde de crédits", "idx.openChat": "Ouvrir le chat",
    "idx.refresh": "Actualiser", "idx.registered": "Inscrit",
    "idx.usage": "Utilisation", "idx.usageSub": "Tokens utilisés par jour.",
    "idx.stats": "Statistiques", "idx.apiCalls": "Appels API",
    "idx.tokensUsed": "Tokens utilisés", "idx.models": "Modèles",
    "idx.creditsUsed": "Crédits dépensés", "idx.lastActivity": "Dernière activité",
    "idx.apiKey": "Clé API", "idx.regenerate": "Régénérer",
    "idx.recent": "Journal"
  }
};

const LANGS = ["en", "de", "es", "fr"];
const LANG_LABELS = { en: "English", de: "Deutsch", es: "Español", fr: "Français" };

const I18N = {
  lang: null,
  detect() {
    const stored = localStorage.getItem("gpupool_lang");
    if (stored && LANGS.includes(stored)) return stored;
    const nav = (navigator.language || "en").slice(0, 2).toLowerCase();
    return LANGS.includes(nav) ? nav : "en";
  },
  init() {
    this.lang = this.detect();
    document.documentElement.lang = this.lang;
    this.applyDOM();
  },
  set(lang) {
    if (!LANGS.includes(lang)) return;
    this.lang = lang;
    localStorage.setItem("gpupool_lang", lang);
    document.documentElement.lang = lang;
    this.applyDOM();
    this.refreshSlots();
    document.dispatchEvent(new CustomEvent("i18n:changed", { detail: { lang: lang } }));
  },
  t(key) {
    const d = I18N_DICT[this.lang];
    return (d && d[key]) || I18N_DICT.en[key] || key;
  },
  applyDOM() {
    document.querySelectorAll("[data-i18n]").forEach(function (el) {
      el.textContent = I18N.t(el.getAttribute("data-i18n"));
    });
    document.querySelectorAll("[data-i18n-placeholder]").forEach(function (el) {
      el.placeholder = I18N.t(el.getAttribute("data-i18n-placeholder"));
    });
  },
  switcherHTML() {
    let opts = "";
    for (const l of LANGS) {
      opts += '<option value="' + l + '"' + (l === this.lang ? " selected" : "") + ">" + LANG_LABELS[l] + "</option>";
    }
    return '<select class="lang-select" onchange="I18N.set(this.value)" aria-label="Language">' + opts + "</select>";
  },
  refreshSlots() {
    document.querySelectorAll("#langSlot, #langSlotHolder").forEach(function (slot) {
      slot.innerHTML = I18N.switcherHTML();
    });
  }
};

// --- Start: fill slots + observer for Alpine x-html navs (rendered after DOMContentLoaded) ---
I18N._observer = new MutationObserver(function () {
  if (document.querySelector("#langSlot:empty, #langSlotHolder:empty")) I18N.refreshSlots();
});
function _i18nStart() {
  I18N.init();
  I18N.refreshSlots();
  I18N._observer.observe(document.body, { childList: true, subtree: true });
  setTimeout(function () { I18N.refreshSlots(); }, 60);
  setTimeout(function () { I18N.refreshSlots(); }, 350);
  window.addEventListener("load", function () { I18N.refreshSlots(); });
}
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", _i18nStart);
} else {
  _i18nStart();
}
window.I18N = I18N;