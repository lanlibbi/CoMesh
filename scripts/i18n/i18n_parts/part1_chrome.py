# LANA-63 — catalog part 1: chrome, navigation, generic strings, page titles.
# Five locales in the order the switcher shows them. EN is the product default.
#
# Fachbegriffe stay untranslated in EVERY locale: Node, Token, Model, Credits,
# API-Key, Pool, Earnings, Provider, Consumer, Owner, Treasury, VRAM, Tailscale.
# That is a product decision (Christian's brief), not an oversight.

KEYS = {
    # ---------------------------------------------------------------- chrome
    "chrome.theme":         {"en": "Theme", "de": "Design", "es": "Tema", "fr": "Thème"},
    "chrome.theme.dark":    {"en": "Dark", "de": "Dunkel", "es": "Oscuro", "fr": "Sombre"},
    "chrome.theme.light":   {"en": "Light", "de": "Hell", "es": "Claro", "fr": "Clair"},
    "chrome.theme.dark.short":  {"en": "Dark", "de": "Dunkel", "es": "Oscuro", "fr": "Sombre"},
    "chrome.theme.light.short": {"en": "Light", "de": "Hell", "es": "Claro", "fr": "Clair"},
    "chrome.language":      {"en": "Language", "de": "Sprache", "es": "Idioma", "fr": "Langue"},

    # ------------------------------------------------------------ navigation
    "nav.dashboard":        {"en": "Dashboard", "de": "Dashboard", "es": "Panel", "fr": "Tableau"},
    "nav.chat":             {"en": "Chat", "de": "Chat", "es": "Chat", "fr": "Chat"},
    "nav.usage":            {"en": "Usage", "de": "Nutzung", "es": "Consumo", "fr": "Usage"},
    "nav.admin":            {"en": "Admin", "de": "Admin", "es": "Admin", "fr": "Admin"},
    "nav.pool":             {"en": "Pool", "de": "Pool", "es": "Pool", "fr": "Pool"},
    "nav.nodes":            {"en": "Nodes", "de": "Nodes", "es": "Nodes", "fr": "Nodes"},
    "nav.earnings":         {"en": "Earnings", "de": "Einnahmen", "es": "Ingresos", "fr": "Revenus"},
    "nav.agent":            {"en": "Agent", "de": "Agent", "es": "Agente", "fr": "Agent"},
    "nav.profile":          {"en": "Profile", "de": "Profil", "es": "Perfil", "fr": "Profil"},
    "nav.logout":           {"en": "Log out", "de": "Abmelden", "es": "Cerrar sesión", "fr": "Déconnexion"},
    "nav.aria":             {"en": "Main navigation", "de": "Hauptnavigation", "es": "Navegación principal", "fr": "Navigation principale"},
    "brand.tagline": {"en": "Your compute, meshed.", "de": "Your compute, meshed.", "es": "Your compute, meshed.", "fr": "Your compute, meshed."},
    "foot.text": {"en": "CoMesh · your compute, meshed.", "de": "CoMesh · your compute, meshed.", "es": "CoMesh · your compute, meshed.", "fr": "CoMesh · your compute, meshed."},

    "nav.logout.button":    {"en": "Log out", "de": "Abmelden", "es": "Cerrar sesión", "fr": "Déconnexion"},

    # ---------------------------------------------------------------- generic
    "common.loading":       {"en": "Loading…", "de": "Lädt…", "es": "Cargando…", "fr": "Chargement…"},
    "common.refresh":       {"en": "Refresh", "de": "Aktualisieren", "es": "Actualizar", "fr": "Actualiser"},
    "common.cancel":        {"en": "Cancel", "de": "Abbrechen", "es": "Cancelar", "fr": "Annuler"},
    "common.save":          {"en": "Save", "de": "Speichern", "es": "Guardar", "fr": "Enregistrer"},
    "common.saving":        {"en": "Saving…", "de": "Speichere…", "es": "Guardando…", "fr": "Enregistrement…"},
    "common.none":          {"en": "—", "de": "—", "es": "—", "fr": "—"},
    "common.credits":       {"en": "Credits", "de": "Credits", "es": "Credits", "fr": "Credits"},
    "common.token":         {"en": "Token", "de": "Token", "es": "Token", "fr": "Token"},
    "common.period":        {"en": "Period", "de": "Zeitraum", "es": "Periodo", "fr": "Période"},
    "common.active":        {"en": "Active", "de": "Aktiv", "es": "Activo", "fr": "Actif"},
    "common.inactive":      {"en": "Inactive", "de": "Inaktiv", "es": "Inactivo", "fr": "Inactif"},
    "common.total":         {"en": "Total", "de": "Gesamt", "es": "Total", "fr": "Total"},

    # ------------------------------------------------------- shared app bits
    "app.login_required":   {"en": "Not logged in", "de": "Nicht angemeldet", "es": "Sesión no iniciada", "fr": "Non connecté"},
    "app.toast.ok":         {"en": "Copied ✓", "de": "Kopiert ✓", "es": "Copiado ✓", "fr": "Copié ✓"},
    "app.provider_required": {
        "en": "The provider area needs the role \"provider\" or \"both\" — change it in the profile.",
        "de": "Der Provider-Bereich braucht die Rolle „Provider“ oder „beides“ — im Profil umstellbar.",
        "es": "El área de proveedor requiere el rol «provider» o «both» — se cambia en el perfil.",
        "fr": "L'espace fournisseur nécessite le rôle « provider » ou « both » — modifiable dans le profil.",
        },
    "err.load":             {"en": "Loading failed:", "de": "Laden fehlgeschlagen:", "es": "Error al cargar:", "fr": "Échec du chargement :"},

    # --------------------------------------------------- dynamic compositions
    "fmt.models_in_circulation": {"en": " models in circulation", "de": " Modelle im Umlauf", "es": " modelos en circulación", "fr": " modèles en circulation"},
    "fmt.token_per_request":     {"en": " Token / request", "de": " Token / Request", "es": " Token / solicitud", "fr": " Token / requête"},
    "fmt.avg_prefix":            {"en": "avg ", "de": "Ø ", "es": "med. ", "fr": "moy. "},
    "fmt.model_tokens":          {"en": "model (tokens)", "de": "Modell (Token)", "es": "modelo (tokens)", "fr": "modèle (tokens)"},
    "fmt.range_shown":           {"en": "{shown} of {total}", "de": "{shown} von {total}", "es": "{shown} de {total}", "fr": "{shown} sur {total}"},
    "fmt.last_n_requests":       {"en": "The most recent {n} calls in this period.", "de": "Die jüngsten {n} Aufrufe in diesem Zeitraum.", "es": "Las {n} llamadas más recientes de este periodo.", "fr": "Les {n} appels les plus récents sur cette période."},
    "fmt.range_last":            {"en": "The most recent ", "de": "Die jüngsten ", "es": "Las más recientes ", "fr": "Les plus récents "},
    "unit.credits_per_hour":     {"en": "Credits/h", "de": "Credits/h", "es": "Credits/h", "fr": "Credits/h"},
    "unit.node_s":               {"en": "node(s)", "de": "Node(s)", "es": "node(s)", "fr": "node(s)"},
    "unit.models":               {"en": "model(s)", "de": "Modell(e)", "es": "modelo(s)", "fr": "modèle(s)"},

    # ---------------------------------------------------------------- charts
    "chart.no_usage":       {"en": "no usage recorded yet", "de": "noch keine Nutzung erfasst", "es": "aún no hay consumo registrado", "fr": "aucun usage enregistré"},

    # ---------------------------------------------------------------- auth
    "auth.welcome":         {"en": "Welcome back,", "de": "Willkommen zurück,", "es": "Bienvenido de nuevo,", "fr": "Bon retour,"},
    "auth.login_failed":    {"en": "Sign-in failed", "de": "Anmeldung fehlgeschlagen", "es": "Error de inicio de sesión", "fr": "Échec de la connexion"},
    "auth.registered":      {"en": "Account created — 100 Credits credited.", "de": "Konto angelegt — 100 Credits gutgeschrieben.", "es": "Cuenta creada — 100 Credits abonados.", "fr": "Compte créé — 100 Credits crédités."},
    "auth.register_failed": {"en": "Registration failed", "de": "Registrierung fehlgeschlagen", "es": "Error de registro", "fr": "Échec de l'inscription"},

    # ------------------------------------------------------------ page titles
    "title.index": {"en": "Dashboard · CoMesh", "de": "Dashboard · CoMesh", "es": "Panel · CoMesh", "fr": "Tableau · CoMesh"},
    "title.login": {"en": "Sign in · CoMesh", "de": "Anmelden · CoMesh", "es": "Iniciar sesión · CoMesh", "fr": "Connexion · CoMesh"},
    "title.register": {"en": "Register · CoMesh", "de": "Registrieren · CoMesh", "es": "Registro · CoMesh", "fr": "Inscription · CoMesh"},
    "title.chat": {"en": "Chat · CoMesh", "de": "Chat · CoMesh", "es": "Chat · CoMesh", "fr": "Chat · CoMesh"},
    "title.credits": {"en": "Credits · CoMesh", "de": "Credits · CoMesh", "es": "Credits · CoMesh", "fr": "Credits · CoMesh"},
    "title.pool": {"en": "Community pool · CoMesh", "de": "Community-Pool · CoMesh", "es": "Pool comunitario · CoMesh", "fr": "Pool communautaire · CoMesh"},
    "title.nodes": {"en": "My nodes · CoMesh", "de": "Meine Nodes · CoMesh", "es": "Mis nodes · CoMesh", "fr": "Mes nodes · CoMesh"},
    "title.earnings": {"en": "Earnings · CoMesh", "de": "Einnahmen · CoMesh", "es": "Ingresos · CoMesh", "fr": "Revenus · CoMesh"},
    "title.agent": {"en": "Node agent · CoMesh", "de": "Node-Agent · CoMesh", "es": "Agente de node · CoMesh", "fr": "Agent de node · CoMesh"},
    "title.profile": {"en": "Profile · CoMesh", "de": "Profil · CoMesh", "es": "Perfil · CoMesh", "fr": "Profil · CoMesh"},
    "title.usage": {"en": "Usage · CoMesh", "de": "Nutzung · CoMesh", "es": "Consumo · CoMesh", "fr": "Usage · CoMesh"},
    "title.admin-usage": {"en": "Admin usage · CoMesh", "de": "Admin-Nutzung · CoMesh", "es": "Consumo admin · CoMesh", "fr": "Usage admin · CoMesh"},
}
