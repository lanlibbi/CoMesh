// CoMesh — string catalog for the supported languages.
// Generated from i18n_parts/*.py; do not hand-edit here, the coverage
// checks in build_catalog.py are what keep markup and catalog in sync.
//
// Scope: exactly EN (default), DE, ES, FR. PT and ZH are deliberately NOT
// implemented (LANA-65) — do not add a locale without that decision being
// re-made and the four-locale check in build_catalog.py being updated.
//
// Fachbegriffe (Node, Token, Model, API-Key, Pool, Provider,
// Owner, Treasury, VRAM, Tailscale) are deliberately identical in every
// locale — that is the product rule, not missing translations.
window.GP_I18N = {
 "locales": [
  "en",
  "de",
  "es",
  "fr"
 ],
 "meta": [
  {
   "code": "en",
   "label": "English"
  },
  {
   "code": "de",
   "label": "Deutsch"
  },
  {
   "code": "es",
   "label": "Español"
  },
  {
   "code": "fr",
   "label": "Français"
  }
 ],
 "catalog": {
  "api_key_manage": {
   "en": "Manage keys",
   "de": "Schlüssel verwalten",
   "es": "Gestionar claves",
   "fr": "Gérer les clés"
  },
  "node.models.free_label": {
   "en": "Models on this node",
   "de": "Modelle dieser Node",
   "es": "Modelos de este nodo",
   "fr": "Modèles de ce nœud"
  },
  "node.models.free_placeholder": {
   "en": "qwen2.5-coder:7b, llama3.1:8b",
   "de": "qwen2.5-coder:7b, llama3.1:8b",
   "es": "qwen2.5-coder:7b, llama3.1:8b",
   "fr": "qwen2.5-coder:7b, llama3.1:8b"
  },
  "node.models.free_hint": {
   "en": "One model name per line or separated by commas. Empty means: all local models on this machine, no cloud models. This list is what others can use through your node.",
   "de": "Ein Modellname je Zeile oder durch Komma getrennt. Leer heißt: alle lokalen Modelle dieser Maschine, keine Cloud-Modelle. Genau diese Liste bestimmt, welche Modelle andere über deine Node nutzen können.",
   "es": "Un nombre de modelo por línea o separados por comas. Vacío significa: todos los modelos locales de esta máquina, ningún modelo en la nube. Esta lista determina qué modelos pueden usar otros a través de tu nodo.",
   "fr": "Un nom de modèle par ligne ou séparés par des virgules. Vide signifie : tous les modèles locaux de cette machine, aucun modèle cloud. C'est cette liste qui détermine ce que les autres peuvent utiliser via votre nœud."
  },
  "node.models.catalog_hint": {
   "en": "The list below is the portal host's catalog — not the models on your node. Anything that exists only on your machine goes in the field above.",
   "de": "Die Liste unten ist der Katalog des Portal-Hosts — nicht die Modelle deiner Node. Was nur auf deiner Maschine liegt, steht oben im Feld.",
   "es": "La lista de abajo es el catálogo del host del portal — no los modelos de tu nodo. Lo que solo existe en tu máquina va en el campo de arriba.",
   "fr": "La liste ci-dessous est le catalogue de l'hôte du portail — pas les modèles de votre nœud. Ce qui n'existe que sur votre machine se met dans le champ ci-dessus."
  },
  "node.models.adopt": {
   "en": "Add to the selection",
   "de": "In die Auswahl übernehmen",
   "es": "Añadir a la selección",
   "fr": "Ajouter à la sélection"
  },
  "nodes.models.adopted": {
   "en": "{n} model(s) added to the selection",
   "de": "{n} Modell(e) in die Auswahl übernommen",
   "es": "{n} modelo(s) añadido(s) a la selección",
   "fr": "{n} modèle(s) ajouté(s) à la sélection"
  },
  "admin.delete.confirm": {
   "en": "Delete the account {email}? Its API keys and sessions are removed with it.",
   "de": "Konto {email} löschen? Die API-Schlüssel und Sitzungen des Kontos verschwinden mit.",
   "es": "¿Eliminar la cuenta {email}? Sus claves de API y sesiones se eliminan también.",
   "fr": "Supprimer le compte {email} ? Ses clés d'API et sessions disparaissent avec."
  },
  "admin.delete.confirm2": {
   "en": "Really delete? Node earnings are kept so the books stay correct, but the account itself cannot be restored.",
   "de": "Wirklich löschen? Die Einnahmen der Nodes bleiben erhalten, damit die Abrechnung stimmt — das Konto selbst lässt sich nicht wiederherstellen.",
   "es": "¿Eliminar de verdad? Los ingresos de los nodos se conservan para que las cuentas cuadren, pero la cuenta en sí no se puede restaurar.",
   "fr": "Vraiment supprimer ? Les revenus des nœuds sont conservés pour que la comptabilité reste juste, mais le compte lui-même est irrécupérable."
  },
  "admin.delete.keys": {
   "en": "{n} key(s) removed",
   "de": "{n} Schlüssel entfernt",
   "es": "{n} clave(s) eliminada(s)",
   "fr": "{n} clé(s) supprimée(s)"
  },
  "admin.delete.nodes_kept": {
   "en": "nodes kept with their earnings: {ids}",
   "de": "Nodes mit Einnahmen behalten: {ids}",
   "es": "nodos conservados con sus ingresos: {ids}",
   "fr": "nœuds conservés avec leurs revenus : {ids}"
  },
  "admin.delete.nodes_removed": {
   "en": "{n} node(s) without earnings removed",
   "de": "{n} Node(s) ohne Einnahmen entfernt",
   "es": "{n} nodo(s) sin ingresos eliminado(s)",
   "fr": "{n} nœud(s) sans revenus supprimé(s)"
  },
  "admin.delete.done": {
   "en": "{email} deleted. {details}",
   "de": "{email} gelöscht. {details}",
   "es": "{email} eliminada. {details}",
   "fr": "{email} supprimé. {details}"
  },
  "admin.delete.failed": {
   "en": "The account could not be deleted",
   "de": "Konto konnte nicht gelöscht werden",
   "es": "No se pudo eliminar la cuenta",
   "fr": "Le compte n'a pas pu être supprimé"
  },
  "chrome.theme": {
   "en": "Theme",
   "de": "Design",
   "es": "Tema",
   "fr": "Thème"
  },
  "chrome.theme.dark": {
   "en": "Dark",
   "de": "Dunkel",
   "es": "Oscuro",
   "fr": "Sombre"
  },
  "chrome.theme.light": {
   "en": "Light",
   "de": "Hell",
   "es": "Claro",
   "fr": "Clair"
  },
  "chrome.theme.dark.short": {
   "en": "Dark",
   "de": "Dunkel",
   "es": "Oscuro",
   "fr": "Sombre"
  },
  "chrome.theme.light.short": {
   "en": "Light",
   "de": "Hell",
   "es": "Claro",
   "fr": "Clair"
  },
  "chrome.language": {
   "en": "Language",
   "de": "Sprache",
   "es": "Idioma",
   "fr": "Langue"
  },
  "nav.dashboard": {
   "en": "Dashboard",
   "de": "Dashboard",
   "es": "Panel",
   "fr": "Tableau"
  },
  "nav.chat": {
   "en": "Chat",
   "de": "Chat",
   "es": "Chat",
   "fr": "Chat"
  },
  "nav.usage": {
   "en": "My usage",
   "de": "Mein Verbrauch",
   "es": "Mi consumo",
   "fr": "Ma consommation"
  },
  "nav.admin": {
   "en": "Admin",
   "de": "Admin",
   "es": "Admin",
   "fr": "Admin"
  },
  "nav.admin.usage": {
   "en": "Usage (all)",
   "de": "Verbrauch (alle)",
   "es": "Consumo (todos)",
   "fr": "Consommation (tous)"
  },
  "nav.admin.accounts": {
   "en": "Accounts",
   "de": "Konten",
   "es": "Cuentas",
   "fr": "Comptes"
  },
  "nav.admin.audit": {
   "en": "Audit log",
   "de": "Protokoll",
   "es": "Registro",
   "fr": "Journal"
  },
  "nav.admin.nodes": {
   "en": "Devices",
   "de": "Geräte",
   "es": "Dispositivos",
   "fr": "Appareils"
  },
  "nav.pool": {
   "en": "Pool",
   "de": "Pool",
   "es": "Pool",
   "fr": "Pool"
  },
  "nav.nodes": {
   "en": "Nodes",
   "de": "Nodes",
   "es": "Nodes",
   "fr": "Nodes"
  },
  "nav.earnings": {
   "en": "Earnings",
   "de": "Einnahmen",
   "es": "Ingresos",
   "fr": "Revenus"
  },
  "nav.agent": {
   "en": "Agent",
   "de": "Agent",
   "es": "Agente",
   "fr": "Agent"
  },
  "nav.profile": {
   "en": "Profile",
   "de": "Profil",
   "es": "Perfil",
   "fr": "Profil"
  },
  "help.link": {
   "en": "Guide",
   "de": "Anleitung",
   "es": "Guía",
   "fr": "Guide"
  },
  "nav.logout": {
   "en": "Log out",
   "de": "Abmelden",
   "es": "Cerrar sesión",
   "fr": "Déconnexion"
  },
  "nav.aria": {
   "en": "Main navigation",
   "de": "Hauptnavigation",
   "es": "Navegación principal",
   "fr": "Navigation principale"
  },
  "brand.tagline": {
   "en": "Your compute, meshed.",
   "de": "Your compute, meshed.",
   "es": "Your compute, meshed.",
   "fr": "Your compute, meshed."
  },
  "foot.text": {
   "en": "CoMesh · your compute, meshed.",
   "de": "CoMesh · your compute, meshed.",
   "es": "CoMesh · your compute, meshed.",
   "fr": "CoMesh · your compute, meshed."
  },
  "nav.logout.button": {
   "en": "Log out",
   "de": "Abmelden",
   "es": "Cerrar sesión",
   "fr": "Déconnexion"
  },
  "common.loading": {
   "en": "Loading…",
   "de": "Lädt…",
   "es": "Cargando…",
   "fr": "Chargement…"
  },
  "common.refresh": {
   "en": "Refresh",
   "de": "Aktualisieren",
   "es": "Actualizar",
   "fr": "Actualiser"
  },
  "common.cancel": {
   "en": "Cancel",
   "de": "Abbrechen",
   "es": "Cancelar",
   "fr": "Annuler"
  },
  "common.none": {
   "en": "—",
   "de": "—",
   "es": "—",
   "fr": "—"
  },
  "common.credits": {
   "en": "Credits",
   "de": "Credits",
   "es": "Credits",
   "fr": "Credits"
  },
  "app.login_required": {
   "en": "Not logged in",
   "de": "Nicht angemeldet",
   "es": "Sesión no iniciada",
   "fr": "Non connecté"
  },
  "app.toast.ok": {
   "en": "Copied ✓",
   "de": "Kopiert ✓",
   "es": "Copiado ✓",
   "fr": "Copié ✓"
  },
  "app.provider_required": {
   "en": "The provider area needs the role \"provider\" or \"both\" — change it in the profile.",
   "de": "Der Provider-Bereich braucht die Rolle „Provider“ oder „beides“ — im Profil umstellbar.",
   "es": "El área de proveedor requiere el rol «provider» o «both» — se cambia en el perfil.",
   "fr": "L'espace fournisseur nécessite le rôle « provider » ou « both » — modifiable dans le profil."
  },
  "err.load": {
   "en": "Loading failed:",
   "de": "Laden fehlgeschlagen:",
   "es": "Error al cargar:",
   "fr": "Échec du chargement :"
  },
  "fmt.models_in_circulation": {
   "en": " models in circulation",
   "de": " Modelle im Umlauf",
   "es": " modelos en circulación",
   "fr": " modèles en circulation"
  },
  "fmt.token_per_request": {
   "en": " Token / request",
   "de": " Token / Request",
   "es": " Token / solicitud",
   "fr": " Token / requête"
  },
  "fmt.avg_prefix": {
   "en": "avg ",
   "de": "Ø ",
   "es": "med. ",
   "fr": "moy. "
  },
  "fmt.model_tokens": {
   "en": "model (tokens)",
   "de": "Modell (Token)",
   "es": "modelo (tokens)",
   "fr": "modèle (tokens)"
  },
  "fmt.range_shown": {
   "en": "{shown} of {total}",
   "de": "{shown} von {total}",
   "es": "{shown} de {total}",
   "fr": "{shown} sur {total}"
  },
  "fmt.last_n_requests": {
   "en": "The most recent {n} calls in this period.",
   "de": "Die jüngsten {n} Aufrufe in diesem Zeitraum.",
   "es": "Las {n} llamadas más recientes de este periodo.",
   "fr": "Les {n} appels les plus récents sur cette période."
  },
  "fmt.range_last": {
   "en": "The most recent ",
   "de": "Die jüngsten ",
   "es": "Las más recientes ",
   "fr": "Les plus récents "
  },
  "unit.credits_per_hour": {
   "en": "Credits/h",
   "de": "Credits/h",
   "es": "Credits/h",
   "fr": "Credits/h"
  },
  "unit.node_s": {
   "en": "node(s)",
   "de": "Node(s)",
   "es": "node(s)",
   "fr": "node(s)"
  },
  "unit.models": {
   "en": "model(s)",
   "de": "Modell(e)",
   "es": "modelo(s)",
   "fr": "modèle(s)"
  },
  "chart.no_usage": {
   "en": "no usage recorded yet",
   "de": "noch keine Nutzung erfasst",
   "es": "aún no hay consumo registrado",
   "fr": "aucun usage enregistré"
  },
  "auth.welcome": {
   "en": "Welcome back,",
   "de": "Willkommen zurück,",
   "es": "Bienvenido de nuevo,",
   "fr": "Bon retour,"
  },
  "auth.login_failed": {
   "en": "Sign-in failed",
   "de": "Anmeldung fehlgeschlagen",
   "es": "Error de inicio de sesión",
   "fr": "Échec de la connexion"
  },
  "auth.registered": {
   "en": "Account created — 100 Credits credited.",
   "de": "Konto angelegt — 100 Credits gutgeschrieben.",
   "es": "Cuenta creada — 100 Credits abonados.",
   "fr": "Compte créé — 100 Credits crédités."
  },
  "auth.register_failed": {
   "en": "Registration failed",
   "de": "Registrierung fehlgeschlagen",
   "es": "Error de registro",
   "fr": "Échec de l'inscription"
  },
  "title.index": {
   "en": "Dashboard · CoMesh",
   "de": "Dashboard · CoMesh",
   "es": "Panel · CoMesh",
   "fr": "Tableau · CoMesh"
  },
  "title.login": {
   "en": "Sign in · CoMesh",
   "de": "Anmelden · CoMesh",
   "es": "Iniciar sesión · CoMesh",
   "fr": "Connexion · CoMesh"
  },
  "title.register": {
   "en": "Register · CoMesh",
   "de": "Registrieren · CoMesh",
   "es": "Registro · CoMesh",
   "fr": "Inscription · CoMesh"
  },
  "title.chat": {
   "en": "Chat · CoMesh",
   "de": "Chat · CoMesh",
   "es": "Chat · CoMesh",
   "fr": "Chat · CoMesh"
  },
  "title.credits": {
   "en": "Credits · CoMesh",
   "de": "Credits · CoMesh",
   "es": "Credits · CoMesh",
   "fr": "Credits · CoMesh"
  },
  "title.pool": {
   "en": "Community pool · CoMesh",
   "de": "Community-Pool · CoMesh",
   "es": "Pool comunitario · CoMesh",
   "fr": "Pool communautaire · CoMesh"
  },
  "title.nodes": {
   "en": "My nodes · CoMesh",
   "de": "Meine Nodes · CoMesh",
   "es": "Mis nodes · CoMesh",
   "fr": "Mes nodes · CoMesh"
  },
  "title.earnings": {
   "en": "Earnings · CoMesh",
   "de": "Einnahmen · CoMesh",
   "es": "Ingresos · CoMesh",
   "fr": "Revenus · CoMesh"
  },
  "title.agent": {
   "en": "Node agent · CoMesh",
   "de": "Node-Agent · CoMesh",
   "es": "Agente de node · CoMesh",
   "fr": "Agent de node · CoMesh"
  },
  "title.profile": {
   "en": "Profile · CoMesh",
   "de": "Profil · CoMesh",
   "es": "Perfil · CoMesh",
   "fr": "Profil · CoMesh"
  },
  "title.usage": {
   "en": "Usage · CoMesh",
   "de": "Nutzung · CoMesh",
   "es": "Consumo · CoMesh",
   "fr": "Usage · CoMesh"
  },
  "title.admin-usage": {
   "en": "Admin usage · CoMesh",
   "de": "Admin-Nutzung · CoMesh",
   "es": "Consumo admin · CoMesh",
   "fr": "Usage admin · CoMesh"
  },
  "konto-api-zugang-und-die-letzten-aufrufe": {
   "en": "Account, API access and recent calls at a glance.",
   "de": "Konto, API-Zugang und die letzten Aufrufe auf einen Blick.",
   "es": "Cuenta, acceso a la API y las últimas llamadas de un vistazo.",
   "fr": "Compte, accès API et derniers appels en un coup d'œil."
  },
  "noch-kein-konto-a-href-register-html-class": {
   "en": "No account yet? <a href=\"register.html\" class=\"link\">Register</a> — 100 Credits to start.",
   "de": "Noch kein Konto? <a href=\"register.html\" class=\"link\">Registrieren</a> — 100 Credits zum Start.",
   "es": "¿Aún sin cuenta? <a href=\"register.html\" class=\"link\">Registrarse</a> — 100 Credits de inicio.",
   "fr": "Pas encore de compte ? <a href=\"register.html\" class=\"link\">S'inscrire</a> — 100 Credits pour commencer."
  },
  "konto-anlegen-und-mitmachen": {
   "en": "Create an account and join in.",
   "de": "Konto anlegen und mitmachen.",
   "es": "Crea una cuenta y participa.",
   "fr": "Créez un compte et participez."
  },
  "b-eigene-hardware-einbringen-b-der-node": {
   "en": "<b>Bring your own hardware.</b> The node agent runs as a container, 70 % of job cost goes to the owner.",
   "de": "<b>Eigene Hardware einbringen.</b> Der Node-Agent läuft als Container, 70 % der Job-Kosten gehen an den Owner.",
   "es": "<b>Aporta tu propio hardware.</b> El agente de node se ejecuta como contenedor; el 70 % del coste del job va al owner.",
   "fr": "<b>Apportez votre matériel.</b> L'agent de node tourne en conteneur ; 70 % du coût du job revient à l'owner."
  },
  "login.no_account": {
   "en": "No account yet? <a href=\"register.html\" class=\"link\">Register</a>.",
   "de": "Noch kein Konto? <a href=\"register.html\" class=\"link\">Registrieren</a>.",
   "es": "¿Aún sin cuenta? <a href=\"register.html\" class=\"link\">Registrarse</a>.",
   "fr": "Pas encore de compte ? <a href=\"register.html\" class=\"link\">S'inscrire</a>."
  },
  "login.point.api": {
   "en": "<b>OpenAI-compatible API.</b> Existing clients and SDKs work without changes.",
   "de": "<b>OpenAI-kompatible API.</b> Bestehende Clients und SDKs funktionieren ohne Anpassung.",
   "es": "<b>API compatible con OpenAI.</b> Los clientes y SDK existentes funcionan sin cambios.",
   "fr": "<b>API compatible OpenAI.</b> Les clients et SDK existants fonctionnent sans modification."
  },
  "login.point.hardware": {
   "en": "<b>Bring your own hardware.</b> The Node agent runs as a container and reports the GPU to the Pool.",
   "de": "<b>Eigene Hardware einbringen.</b> Der Node-Agent läuft als Container und meldet die GPU an den Pool.",
   "es": "<b>Aporta tu propio hardware.</b> El agente Node se ejecuta como contenedor y anuncia la GPU al Pool.",
   "fr": "<b>Apportez votre matériel.</b> L'agent Node tourne en conteneur et annonce le GPU au Pool."
  },
  "login.point.models": {
   "en": "<b>Models stay under control.</b> Whitelist per Node and per account, cloud models unlocked explicitly.",
   "de": "<b>Modelle bleiben kontrollierbar.</b> Pro Node und pro Konto als Whitelist steuerbar, Cloud-Modelle explizit freizuschalten.",
   "es": "<b>Los Model siguen controlables.</b> Lista blanca por Node y por cuenta, Model en la nube se habilitan explícitamente.",
   "fr": "<b>Les Model restent contrôlables.</b> Liste blanche par Node et par compte, Model cloud débloqués explicitement."
  },
  "register.role.consumer": {
   "en": "<b>Consumer.</b> Use the API, provide no hardware. For machines without a usable GPU.",
   "de": "<b>Consumer.</b> API nutzen, keine Hardware bereitstellen. Für Rechner ohne nutzbare GPU.",
   "es": "<b>Consumer.</b> Usar la API, sin aportar hardware. Para equipos sin GPU utilizable.",
   "fr": "<b>Consumer.</b> Utiliser l'API, sans fournir de matériel. Pour les machines sans GPU utilisable."
  },
  "register.role.provider": {
   "en": "<b>Provider.</b> Register Nodes and earn Credits, no own API calls.",
   "de": "<b>Provider.</b> Nodes registrieren und Credits verdienen, keine eigenen API-Calls.",
   "es": "<b>Provider.</b> Registrar Nodes y ganar Credits, sin llamadas propias a la API.",
   "fr": "<b>Provider.</b> Enregistrer des Nodes et gagner des Credits, sans appels API propres."
  },
  "register.role.both": {
   "en": "<b>Both.</b> Full access — contribute and use at the same time.",
   "de": "<b>Beides.</b> Voller Zugriff — Einbringen und Nutzen gleichzeitig.",
   "es": "<b>Ambos.</b> Acceso completo: aportar y usar a la vez.",
   "fr": "<b>Les deux.</b> Accès complet — apporter et utiliser en même temps."
  },
  "register.models_limited": {
   "en": "Limit the models",
   "de": "Modelle einschränken",
   "es": "Limitar los Model",
   "fr": "Limiter les Model"
  },
  "register.models_optional": {
   "en": "optional — empty means: all local models, no cloud",
   "de": "optional — leer bedeutet: alle lokalen Modelle, keine Cloud",
   "es": "opcional — vacío significa: todos los Model locales, sin nube",
   "fr": "facultatif — vide signifie : tous les Model locaux, sans cloud"
  },
  "register.role_hint": {
   "en": "Can be changed any time later in the <a href=\"profile.html\" class=\"link\">profile</a>.",
   "de": "Später im <a href=\"profile.html\" class=\"link\">Profil</a> jederzeit änderbar.",
   "es": "Se puede cambiar en cualquier momento en el <a href=\"profile.html\" class=\"link\">perfil</a>.",
   "fr": "Modifiable à tout moment dans le <a href=\"profile.html\" class=\"link\">profil</a>."
  },
  "login.foot.openai": {
   "en": "OpenAI-compatible API",
   "de": "OpenAI-kompatible API",
   "es": "API compatible con OpenAI",
   "fr": "API compatible OpenAI"
  },
  "api_key_no_bearer": {
   "en": "— in config files and SDKs only the key, without \"Bearer\".",
   "de": "— in Konfigurationsdateien und SDKs nur der Schlüssel, ohne „Bearer\".",
   "es": "— en archivos de configuración y SDKs solo la clave, sin \"Bearer\".",
   "fr": "— dans les fichiers de configuration et SDK, seulement la clé, sans « Bearer »."
  },
  "login.tagline": {
   "en": "Contribute GPUs to the pool, use the whole pool through one OpenAI-compatible API — free and powered by your community.",
   "de": "Stelle GPUs für den Pool bereit und nutze den ganzen Pool über eine einzige OpenAI-kompatible API — kostenlos und von deiner Community getragen.",
   "es": "Aporta GPUs al pool y usa todo el pool a través de una única API compatible con OpenAI: gratis y sostenido por tu comunidad.",
   "fr": "Apportez des GPU au pool et utilisez tout le pool via une seule API compatible OpenAI — gratuit et porté par votre communauté."
  },
  "rechner-mit-freier-gpu-stellen-ihre": {
   "en": "Machines with a free GPU offer their capacity, others use it through an OpenAI-compatible API. Billing runs on Credits — per Token, not per subscription.",
   "de": "Rechner mit freier GPU stellen ihre Leistung bereit, andere nutzen sie über eine OpenAI-kompatible API. Abrechnung läuft über Credits — pro Token, nicht pro Abo.",
   "es": "Las máquinas con GPU libre ofrecen su capacidad y otras la usan a través de una API compatible con OpenAI. La facturación va por Credits — por Token, no por suscripción.",
   "fr": "Les machines disposant d'un GPU libre mettent leur puissance à disposition, d'autres l'utilisent via une API compatible OpenAI. La facturation se fait en Credits — par Token, sans abonnement."
  },
  "b-openai-kompatible-api-b-bestehende": {
   "en": "<b>OpenAI-compatible API.</b> Existing clients and SDKs work without changes.",
   "de": "<b>OpenAI-kompatible API.</b> Bestehende Clients und SDKs funktionieren ohne Anpassung.",
   "es": "<b>API compatible con OpenAI.</b> Los clientes y SDK existentes funcionan sin cambios.",
   "fr": "<b>API compatible OpenAI.</b> Les clients et SDK existants fonctionnent sans modification."
  },
  "b-modelle-bleiben-kontrollierbar-b-pro-node": {
   "en": "<b>Models stay under control.</b> Allow-listed per node and per account; cloud models are opted into explicitly.",
   "de": "<b>Modelle bleiben kontrollierbar.</b> Pro Node und pro Konto als Whitelist steuerbar, Cloud-Modelle explizit freizuschalten.",
   "es": "<b>Los modelos siguen bajo control.</b> Lista blanca por node y por cuenta; los modelos cloud se habilitan explícitamente.",
   "fr": "<b>Les modèles restent contrôlables.</b> Liste blanche par node et par compte ; les modèles cloud s'activent explicitement."
  },
  "melde-dich-an-um-credits-nodes-und-api-keys": {
   "en": "Sign in to manage Credits, Nodes and API keys.",
   "de": "Melde dich an, um Credits, Nodes und API-Keys zu verwalten.",
   "es": "Inicia sesión para gestionar Credits, Nodes y API keys.",
   "fr": "Connectez-vous pour gérer Credits, Nodes et clés API."
  },
  "name-beispiel-de": {
   "en": "name@example.com",
   "de": "name@beispiel.de",
   "es": "nombre@ejemplo.es",
   "fr": "nom@exemple.fr"
  },
  "anmeldung-laeuft": {
   "en": "Signing in…",
   "de": "Anmeldung läuft…",
   "es": "Iniciando sesión…",
   "fr": "Connexion…"
  },
  "anmelden": {
   "en": "Sign in",
   "de": "Anmelden",
   "es": "Iniciar sesión",
   "fr": "Connexion"
  },
  "e-mail": {
   "en": "E-mail",
   "de": "E-Mail",
   "es": "Correo electrónico",
   "fr": "E-mail"
  },
  "passwort": {
   "en": "Password",
   "de": "Passwort",
   "es": "Contraseña",
   "fr": "Mot de passe"
  },
  "ein-konto-deckt-beides-ab-die-api-nutzen": {
   "en": "One account covers both: using the API and contributing your own GPUs. The role decides what is unlocked — changeable in the profile at any time.",
   "de": "Ein Konto deckt beides ab: die API nutzen und eigene GPUs bereitstellen. Die Rolle legt fest, was freigeschaltet wird — im Profil jederzeit änderbar.",
   "es": "Una cuenta cubre ambas cosas: usar la API y aportar tus propias GPUs. El rol define qué se habilita — modificable en el perfil.",
   "fr": "Un seul compte couvre les deux : utiliser l'API et fournir vos propres GPU. Le rôle détermine ce qui est débloqué — modifiable dans le profil."
  },
  "b-consumer-b-api-nutzen-keine-hardware": {
   "en": "<b>Consumer.</b> Use the API, contribute no hardware. For machines without a usable GPU.",
   "de": "<b>Consumer.</b> API nutzen, keine Hardware bereitstellen. Für Rechner ohne nutzbare GPU.",
   "es": "<b>Consumer.</b> Usar la API sin aportar hardware. Para equipos sin GPU utilizable.",
   "fr": "<b>Consumer.</b> Utiliser l'API sans fournir de matériel. Pour les machines sans GPU exploitable."
  },
  "b-provider-b-nodes-registrieren-und-credits": {
   "en": "<b>Provider.</b> Register nodes and earn Credits, no API calls of your own.",
   "de": "<b>Provider.</b> Nodes registrieren und Credits verdienen, keine eigenen API-Calls.",
   "es": "<b>Provider.</b> Registrar nodes y ganar Credits, sin llamadas API propias.",
   "fr": "<b>Provider.</b> Enregistrer des nodes et gagner des Credits, sans appels API propres."
  },
  "b-beides-b-voller-zugriff-einbringen-und": {
   "en": "<b>Both.</b> Full access — contributing and consuming at the same time.",
   "de": "<b>Beides.</b> Voller Zugriff — Einbringen und Nutzen gleichzeitig.",
   "es": "<b>Ambos.</b> Acceso completo — aportar y consumir a la vez.",
   "fr": "<b>Les deux.</b> Accès complet — apporter et consommer en même temps."
  },
  "neues-konto": {
   "en": "New account",
   "de": "Neues Konto",
   "es": "Cuenta nueva",
   "fr": "Nouveau compte"
  },
  "registrieren": {
   "en": "Register",
   "de": "Registrieren",
   "es": "Registrarse",
   "fr": "S'inscrire"
  },
  "name": {
   "en": "Name",
   "de": "Name",
   "es": "Nombre",
   "fr": "Nom"
  },
  "vor-und-nachname": {
   "en": "First and last name",
   "de": "Vor- und Nachname",
   "es": "Nombre y apellidos",
   "fr": "Prénom et nom"
  },
  "mindestens-6-zeichen": {
   "en": "at least 6 characters",
   "de": "mindestens 6 Zeichen",
   "es": "mínimo 6 caracteres",
   "fr": "au moins 6 caractères"
  },
  "eigene-gpus-teilen-keine-api-calls": {
   "en": "Share your own GPUs, no API calls.",
   "de": "Eigene GPUs teilen, keine API-Calls.",
   "es": "Compartir tus propias GPUs, sin llamadas API.",
   "fr": "Partager vos GPU, aucun appel API."
  },
  "gpus-teilen-und-api-nutzen-standard": {
   "en": "Share GPUs and use the API — default.",
   "de": "GPUs teilen und API nutzen — Standard.",
   "es": "Compartir GPUs y usar la API — por defecto.",
   "fr": "Partager des GPU et utiliser l'API — par défaut."
  },
  "modelle-einschraenken-span-class-hint": {
   "en": "Limit models <span class=\"hint\">optional — empty means: all local models, no cloud</span>",
   "de": "Modelle einschränken <span class=\"hint\">optional — leer bedeutet: alle lokalen Modelle, keine Cloud</span>",
   "es": "Limitar modelos <span class=\"hint\">opcional — vacío significa: todos los modelos locales, sin cloud</span>",
   "fr": "Limiter les modèles <span class=\"hint\">optionnel — vide signifie : tous les modèles locaux, pas de cloud</span>"
  },
  "spaeter-im-a-href-profile-html-class-link": {
   "en": "Changeable any time later in the <a href=\"profile.html\" class=\"link\">profile</a>.",
   "de": "Später im <a href=\"profile.html\" class=\"link\">Profil</a> jederzeit änderbar.",
   "es": "Modificable en cualquier momento en el <a href=\"profile.html\" class=\"link\">perfil</a>.",
   "fr": "Modifiable à tout moment dans le <a href=\"profile.html\" class=\"link\">profil</a>."
  },
  "konto-anlegen": {
   "en": "Create account",
   "de": "Konto anlegen",
   "es": "Crear cuenta",
   "fr": "Créer le compte"
  },
  "wird-angelegt": {
   "en": "Creating…",
   "de": "Wird angelegt…",
   "es": "Creando…",
   "fr": "Création…"
  },
  "schon-registriert-a-href-login-html-class": {
   "en": "Already registered? <a href=\"login.html\" class=\"link\">Sign in</a>",
   "de": "Schon registriert? <a href=\"login.html\" class=\"link\">Anmelden</a>",
   "es": "¿Ya registrado? <a href=\"login.html\" class=\"link\">Iniciar sesión</a>",
   "fr": "Déjà inscrit ? <a href=\"login.html\" class=\"link\">Connexion</a>"
  },
  "api-key-jetzt-sichern": {
   "en": "Secure the API key now",
   "de": "API-Key jetzt sichern",
   "es": "Guarda ahora la API key",
   "fr": "Sécurisez la clé API maintenant"
  },
  "dieser-schluessel-wird-nur-einmal": {
   "en": "This key is shown in full only once. It is the only way to reach the API.",
   "de": "Dieser Schlüssel wird nur einmal vollständig angezeigt. Er ist die einzige Zugangsmöglichkeit zur API.",
   "es": "Esta clave solo se muestra completa una vez. Es el único acceso a la API.",
   "fr": "Cette clé n'est affichée en entier qu'une seule fois. C'est le seul accès à l'API."
  },
  "habe-ich-gesichert": {
   "en": "I saved it",
   "de": "Habe ich gesichert",
   "es": "La he guardado",
   "fr": "Je l'ai sauvegardée"
  },
  "uebersicht": {
   "en": "Overview",
   "de": "Übersicht",
   "es": "Resumen",
   "fr": "Aperçu"
  },
  "credit-guthaben": {
   "en": "Credit balance",
   "de": "Credit-Guthaben",
   "es": "Saldo de Credits",
   "fr": "Solde de Credits"
  },
  "entspricht-ca-span-x-text-fmtnumber-math": {
   "en": "roughly <span x-text=\"fmtNumber(Math.floor((me?.credits || 0) * 1000))\"></span> Token",
   "de": "entspricht ca. <span x-text=\"fmtNumber(Math.floor((me?.credits || 0) * 1000))\"></span> Token",
   "es": "equivale a unos <span x-text=\"fmtNumber(Math.floor((me?.credits || 0) * 1000))\"></span> Token",
   "fr": "correspond à environ <span x-text=\"fmtNumber(Math.floor((me?.credits || 0) * 1000))\"></span> Token"
  },
  "chat-oeffnen": {
   "en": "Open chat",
   "de": "Chat öffnen",
   "es": "Abrir chat",
   "fr": "Ouvrir le chat"
  },
  "registriert": {
   "en": "Registered",
   "de": "Registriert",
   "es": "Registrado",
   "fr": "Inscrit"
  },
  "verbrauch": {
   "en": "Consumption",
   "de": "Verbrauch",
   "es": "Consumo",
   "fr": "Consommation"
  },
  "pro-tag-verbrauchte-token": {
   "en": "Token consumed per day.",
   "de": "Pro Tag verbrauchte Token.",
   "es": "Token consumidos por día.",
   "fr": "Token consommés par jour."
  },
  "kennzahlen": {
   "en": "Metrics",
   "de": "Kennzahlen",
   "es": "Métricas",
   "fr": "Indicateurs"
  },
  "api-aufrufe": {
   "en": "API calls",
   "de": "API-Aufrufe",
   "es": "Llamadas API",
   "fr": "Appels API"
  },
  "token-verbraucht": {
   "en": "Token consumed",
   "de": "Token verbraucht",
   "es": "Token consumidos",
   "fr": "Token consommés"
  },
  "zugang": {
   "en": "Access",
   "de": "Zugang",
   "es": "Acceso",
   "fr": "Accès"
  },
  "neu-ausstellen": {
   "en": "Issue new",
   "de": "Neu ausstellen",
   "es": "Emitir nueva",
   "fr": "Émettre une nouvelle"
  },
  "anzeigen": {
   "en": "Show",
   "de": "Anzeigen",
   "es": "Mostrar",
   "fr": "Afficher"
  },
  "verbergen": {
   "en": "Hide",
   "de": "Verbergen",
   "es": "Ocultar",
   "fr": "Masquer"
  },
  "kopieren": {
   "en": "Copy",
   "de": "Kopieren",
   "es": "Copiar",
   "fr": "Copier"
  },
  "protokoll": {
   "en": "Log",
   "de": "Protokoll",
   "es": "Registro",
   "fr": "Journal"
  },
  "letzte-api-aufrufe": {
   "en": "Recent API calls",
   "de": "Letzte API-Aufrufe",
   "es": "Últimas llamadas API",
   "fr": "Derniers appels API"
  },
  "noch-keine-aufrufe-der-chat-ist-der": {
   "en": "No calls yet. The chat is the fastest route to a first request.",
   "de": "Noch keine Aufrufe. Der Chat ist der schnellste Weg zum ersten Request.",
   "es": "Aún sin llamadas. El chat es la vía más rápida a la primera solicitud.",
   "fr": "Aucun appel pour l'instant. Le chat est le chemin le plus rapide vers une première requête."
  },
  "oder-direkt-per-curl": {
   "en": "Or directly with curl:",
   "de": "Oder direkt per curl:",
   "es": "O directamente con curl:",
   "fr": "Ou directement avec curl :"
  },
  "wann": {
   "en": "When",
   "de": "Wann",
   "es": "Cuándo",
   "fr": "Quand"
  },
  "authorization-bearer-lt-api-key-gt": {
   "en": "Authorization: Bearer &lt;api-key&gt;",
   "de": "Authorization: Bearer &lt;api-key&gt;",
   "es": "Authorization: Bearer &lt;api-key&gt;",
   "fr": "Authorization: Bearer &lt;api-key&gt;"
  },
  "direkter-testlauf-gegen-den-pool": {
   "en": "A direct test run against the pool. Billing is per Token from your balance — currently <span class=\"text-brand num\" x-text=\"fmtCredits(me?.credits)\"></span> Credits.",
   "de": "Direkter Testlauf gegen den Pool. Abgerechnet wird pro Token über dein Guthaben — aktuell <span class=\"text-brand num\" x-text=\"fmtCredits(me?.credits)\"></span> Credits.",
   "es": "Una prueba directa contra el pool. El consumo se factura por Token desde tu saldo — actualmente <span class=\"text-brand num\" x-text=\"fmtCredits(me?.credits)\"></span> Credits.",
   "fr": "Un test direct contre le pool. La facturation se fait par Token sur votre solde — actuellement <span class=\"text-brand num\" x-text=\"fmtCredits(me?.credits)\"></span> Credits."
  },
  "inference": {
   "en": "Inference",
   "de": "Inference",
   "es": "Inferencia",
   "fr": "Inférence"
  },
  "session": {
   "en": "Session",
   "de": "Session",
   "es": "Sesión",
   "fr": "Session"
  },
  "modellliste-neu-laden": {
   "en": "Reload model list",
   "de": "Modellliste neu laden",
   "es": "Recargar lista de modelos",
   "fr": "Recharger la liste des modèles"
  },
  "noch-keine-nachricht-starte-mit-einer-der": {
   "en": "No message yet. Start with one of the templates or just type.",
   "de": "Noch keine Nachricht. Starte mit einer der Vorlagen oder tippe direkt los.",
   "es": "Aún sin mensajes. Empieza con una plantilla o escribe directamente.",
   "fr": "Pas encore de message. Commencez avec un modèle ou écrivez directement."
  },
  "antwort-wird-erzeugt": {
   "en": "Generating a reply",
   "de": "Antwort wird erzeugt",
   "es": "Generando respuesta",
   "fr": "Génération de la réponse"
  },
  "letzte-antwort-span-x-text-fmtnumber": {
   "en": "Last reply: <span x-text=\"fmtNumber(lastUsage?.total_tokens)\"></span> Token · <span x-text=\"fmtCredits(lastUsage?.credits_used)\"></span> Credits",
   "de": "Letzte Antwort: <span x-text=\"fmtNumber(lastUsage?.total_tokens)\"></span> Token · <span x-text=\"fmtCredits(lastUsage?.credits_used)\"></span> Credits",
   "es": "Última respuesta: <span x-text=\"fmtNumber(lastUsage?.total_tokens)\"></span> Token · <span x-text=\"fmtCredits(lastUsage?.credits_used)\"></span> Credits",
   "fr": "Dernière réponse : <span x-text=\"fmtNumber(lastUsage?.total_tokens)\"></span> Token · <span x-text=\"fmtCredits(lastUsage?.credits_used)\"></span> Credits"
  },
  "span-x-text-messages-length-span": {
   "en": "<span x-text=\"messages.length\"></span> messages in the history",
   "de": "<span x-text=\"messages.length\"></span> Nachrichten im Verlauf",
   "es": "<span x-text=\"messages.length\"></span> mensajes en el historial",
   "fr": "<span x-text=\"messages.length\"></span> messages dans l'historique"
  },
  "senden": {
   "en": "Send",
   "de": "Senden",
   "es": "Enviar",
   "fr": "Envoyer"
  },
  "abrechnung": {
   "en": "Billing",
   "de": "Abrechnung",
   "es": "Facturación",
   "fr": "Facturation"
  },
  "credits-aufladen": {
   "en": "Top up Credits",
   "de": "Credits aufladen",
   "es": "Recargar Credits",
   "fr": "Recharger des Credits"
  },
  "aktuelles-guthaben-span-class-text-brand": {
   "en": "Current balance: <span class=\"text-brand num semibold\" x-text=\"fmtCredits(me?.credits)\"></span> Credits. Billing is per Token — no subscription and no minimum term.",
   "de": "Aktuelles Guthaben: <span class=\"text-brand num semibold\" x-text=\"fmtCredits(me?.credits)\"></span> Credits. Abgerechnet wird pro Token — es gibt kein Abo und keine Mindestlaufzeit.",
   "es": "Saldo actual: <span class=\"text-brand num semibold\" x-text=\"fmtCredits(me?.credits)\"></span> Credits. Se factura por Token — sin suscripción ni permanencia mínima.",
   "fr": "Solde actuel : <span class=\"text-brand num semibold\" x-text=\"fmtCredits(me?.credits)\"></span> Credits. Facturation par Token — sans abonnement ni engagement."
  },
  "empfohlen": {
   "en": "recommended",
   "de": "empfohlen",
   "es": "recomendado",
   "fr": "recommandé"
  },
  "kaufen": {
   "en": "Buy",
   "de": "Kaufen",
   "es": "Comprar",
   "fr": "Acheter"
  },
  "zahlung-ist-im-poc-nicht-angeschlossen": {
   "en": "Payment is not wired up in the POC",
   "de": "Zahlung ist im POC nicht angeschlossen",
   "es": "El pago no está conectado en el POC",
   "fr": "Le paiement n'est pas raccordé dans le POC"
  },
  "kaufen-legt-lediglich-einen-aufladewunsch": {
   "en": "\"Buy\" only files a top-up request that an admin confirms. Real payment processing (Stripe or similar) is not implemented yet.",
   "de": "„Kaufen\" legt lediglich einen Aufladewunsch an, den ein Admin bestätigt. Echte Zahlungsabwicklung (Stripe o. ä.) ist noch nicht implementiert.",
   "es": "«Comprar» solo crea una solicitud de recarga que un admin confirma. El procesamiento de pagos real (Stripe u otros) aún no está implementado.",
   "fr": "« Acheter » crée seulement une demande de recharge qu'un admin confirme. Le traitement des paiements réels (Stripe ou autre) n'est pas encore implémenté."
  },
  "manuell": {
   "en": "Manual",
   "de": "Manuell",
   "es": "Manual",
   "fr": "Manuel"
  },
  "aufladung-anfragen": {
   "en": "Request a top-up",
   "de": "Aufladung anfragen",
   "es": "Solicitar recarga",
   "fr": "Demander une recharge"
  },
  "betrag-und-optionalen-verwendungszweck": {
   "en": "Enter an amount and an optional note — the admin credits it.",
   "de": "Betrag und optionalen Verwendungszweck angeben — der Admin schreibt gut.",
   "es": "Indica el importe y una nota opcional — el admin lo abona.",
   "fr": "Indiquez un montant et une note facultative — l'admin crédite."
  },
  "betrag-credits": {
   "en": "Amount (Credits)",
   "de": "Betrag (Credits)",
   "es": "Importe (Credits)",
   "fr": "Montant (Credits)"
  },
  "notiz-optional": {
   "en": "Note (optional)",
   "de": "Notiz (optional)",
   "es": "Nota (opcional)",
   "fr": "Note (facultative)"
  },
  "z-b-rechnungsnummer": {
   "en": "e.g. invoice number",
   "de": "z. B. Rechnungsnummer",
   "es": "p. ej. número de factura",
   "fr": "p. ex. numéro de facture"
  },
  "anfrage-senden": {
   "en": "Send request",
   "de": "Anfrage senden",
   "es": "Enviar solicitud",
   "fr": "Envoyer la demande"
  },
  "historie": {
   "en": "History",
   "de": "Historie",
   "es": "Historial",
   "fr": "Historique"
  },
  "deine-aufladungen": {
   "en": "Your top-ups",
   "de": "Deine Aufladungen",
   "es": "Tus recargas",
   "fr": "Vos recharges"
  },
  "noch-keine-anfragen-gestellt": {
   "en": "No requests made yet.",
   "de": "Noch keine Anfragen gestellt.",
   "es": "Aún no has hecho solicitudes.",
   "fr": "Aucune demande pour l'instant."
  },
  "betrag": {
   "en": "Amount",
   "de": "Betrag",
   "es": "Importe",
   "fr": "Montant"
  },
  "status": {
   "en": "Status",
   "de": "Status",
   "es": "Estado",
   "fr": "Statut"
  },
  "notiz": {
   "en": "Note",
   "de": "Notiz",
   "es": "Nota",
   "fr": "Note"
  },
  "live": {
   "en": "Live",
   "de": "Live",
   "es": "En vivo",
   "fr": "En direct"
  },
  "community-pool": {
   "en": "Community pool",
   "de": "Community-Pool",
   "es": "Pool comunitario",
   "fr": "Pool communautaire"
  },
  "alle-beigetragenen-gpus-mit-aktueller": {
   "en": "Every contributed GPU with its current utilisation. Refreshes automatically every 10 seconds.",
   "de": "Alle beigetragenen GPUs mit aktueller Auslastung. Aktualisiert sich automatisch alle 10 Sekunden.",
   "es": "Todas las GPUs aportadas con su uso actual. Se actualiza automáticamente cada 10 segundos.",
   "fr": "Tous les GPU apportés avec leur utilisation actuelle. Actualisation automatique toutes les 10 secondes."
  },
  "nodes-online": {
   "en": "Nodes online",
   "de": "Nodes online",
   "es": "Nodes en línea",
   "fr": "Nodes en ligne"
  },
  "bereit-registriert": {
   "en": "ready / registered",
   "de": "bereit / registriert",
   "es": "listos / registrados",
   "fr": "prêts / enregistrés"
  },
  "vram-gesamt": {
   "en": "VRAM total",
   "de": "VRAM gesamt",
   "es": "VRAM total",
   "fr": "VRAM total"
  },
  "gb-im-pool": {
   "en": "GB in the pool",
   "de": "GB im Pool",
   "es": "GB en el pool",
   "fr": "GB dans le pool"
  },
  "vram-verfuegbar": {
   "en": "VRAM available",
   "de": "VRAM verfügbar",
   "es": "VRAM disponible",
   "fr": "VRAM disponible"
  },
  "gb-gerade-frei": {
   "en": "GB free right now",
   "de": "GB gerade frei",
   "es": "GB libres ahora",
   "fr": "GB libres actuellement"
  },
  "auslastung": {
   "en": "Utilisation",
   "de": "Auslastung",
   "es": "Uso",
   "fr": "Utilisation"
  },
  "hardware": {
   "en": "Hardware",
   "de": "Hardware",
   "es": "Hardware",
   "fr": "Matériel"
  },
  "verfuegbare-gpus": {
   "en": "Available GPUs",
   "de": "Verfügbare GPUs",
   "es": "GPUs disponibles",
   "fr": "GPU disponibles"
  },
  "gerade-ist-keine-node-online-schau-spaeter": {
   "en": "No node is online right now. Check back later or <a href=\"nodes.html\" class=\"link\">register your own GPU</a>.",
   "de": "Gerade ist keine Node online. Schau später wieder rein oder <a href=\"nodes.html\" class=\"link\">registriere deine eigene GPU</a>.",
   "es": "Ahora mismo no hay ningún node en línea. Vuelve más tarde o <a href=\"nodes.html\" class=\"link\">registra tu propia GPU</a>.",
   "fr": "Aucun node n'est en ligne actuellement. Revenez plus tard ou <a href=\"nodes.html\" class=\"link\">enregistrez votre propre GPU</a>."
  },
  "credits-aus-jobs-die-andere-nutzer-auf": {
   "en": "Credits from jobs other users ran on your nodes — including the split between owner, platform and treasury.",
   "de": "Credits aus Jobs, die andere Nutzer auf deinen Nodes ausgeführt haben — inklusive Aufteilung zwischen Owner, Plattform und Treasury.",
   "es": "Credits de los jobs que otros usuarios ejecutaron en tus nodes — incluido el reparto entre owner, plataforma y treasury.",
   "fr": "Credits issus des jobs exécutés par d'autres utilisateurs sur vos nodes — répartition entre owner, plateforme et trésorerie."
  },
  "gesamt-earnings": {
   "en": "Total earnings",
   "de": "Gesamt-Earnings",
   "es": "Ingresos totales",
   "fr": "Revenus totaux"
  },
  "credits-ueber-alle-nodes": {
   "en": "Credits across all nodes",
   "de": "Credits über alle Nodes",
   "es": "Credits en todos los nodes",
   "fr": "Credits sur tous les nodes"
  },
  "beitragende-nodes": {
   "en": "Contributing nodes",
   "de": "Beitragende Nodes",
   "es": "Nodes contribuyentes",
   "fr": "Nodes contributeurs"
  },
  "mit-mindestens-einem-job": {
   "en": "with at least one job",
   "de": "mit mindestens einem Job",
   "es": "con al menos un job",
   "fr": "avec au moins un job"
  },
  "aufteilung": {
   "en": "Split",
   "de": "Aufteilung",
   "es": "Reparto",
   "fr": "Répartition"
  },
  "owner-plattform-treasury": {
   "en": "Owner / platform / treasury",
   "de": "Owner / Plattform / Treasury",
   "es": "Owner / plataforma / treasury",
   "fr": "Owner / plateforme / trésorerie"
  },
  "aggregiert": {
   "en": "Aggregated",
   "de": "Aggregiert",
   "es": "Agregado",
   "fr": "Agrégé"
  },
  "pro-node": {
   "en": "Per node",
   "de": "Pro Node",
   "es": "Por node",
   "fr": "Par node"
  },
  "noch-keine-nodes": {
   "en": "No nodes yet.",
   "de": "Noch keine Nodes.",
   "es": "Aún no hay nodes.",
   "fr": "Aucun node pour l'instant."
  },
  "letzte-job-earnings": {
   "en": "Recent job earnings",
   "de": "Letzte Job-Earnings",
   "es": "Últimos ingresos por job",
   "fr": "Derniers revenus par job"
  },
  "job-kosten": {
   "en": "Job cost",
   "de": "Job-Kosten",
   "es": "Coste del job",
   "fr": "Coût du job"
  },
  "owner-70": {
   "en": "Owner 70 %",
   "de": "Owner 70 %",
   "es": "Owner 70 %",
   "fr": "Owner 70 %"
  },
  "plattform-20": {
   "en": "Platform 20 %",
   "de": "Plattform 20 %",
   "es": "Plataforma 20 %",
   "fr": "Plateforme 20 %"
  },
  "treasury-10": {
   "en": "Treasury 10 %",
   "de": "Treasury 10 %",
   "es": "Treasury 10 %",
   "fr": "Trésorerie 10 %"
  },
  "noch-keine-job-earnings": {
   "en": "No job earnings yet.",
   "de": "Noch keine Job-Earnings.",
   "es": "Aún no hay ingresos por job.",
   "fr": "Aucun revenu de job pour l'instant."
  },
  "konto": {
   "en": "Account",
   "de": "Konto",
   "es": "Cuenta",
   "fr": "Compte"
  },
  "rolle-und-modell-whitelist-aenderungen": {
   "en": "Role and model allow-list. Changes take effect immediately, without signing in again.",
   "de": "Rolle und Modell-Whitelist. Änderungen greifen sofort, ohne erneute Anmeldung.",
   "es": "Rol y lista blanca de modelos. Los cambios se aplican de inmediato, sin volver a iniciar sesión.",
   "fr": "Rôle et liste blanche des modèles. Les changements s'appliquent immédiatement, sans reconnexion."
  },
  "berechtigungen": {
   "en": "Permissions",
   "de": "Berechtigungen",
   "es": "Permisos",
   "fr": "Permissions"
  },
  "rolle": {
   "en": "Role",
   "de": "Rolle",
   "es": "Rol",
   "fr": "Rôle"
  },
  "api-nutzbar-keine-node-registrierung": {
   "en": "API usable, no node registration.",
   "de": "API nutzbar, keine Node-Registrierung.",
   "es": "API utilizable, sin registro de nodes.",
   "fr": "API utilisable, aucun node enregistré."
  },
  "nodes-registrierbar-keine-eigenen-api-calls": {
   "en": "Nodes registrable, no API calls of your own.",
   "de": "Nodes registrierbar, keine eigenen API-Calls.",
   "es": "Nodes registrables, sin llamadas API propias.",
   "fr": "Nodes enregistrables, aucun appel API propre."
  },
  "voller-zugriff": {
   "en": "Full access.",
   "de": "Voller Zugriff.",
   "es": "Acceso completo.",
   "fr": "Accès complet."
  },
  "nur-consumer": {
   "en": "Consumer only",
   "de": "Nur Consumer",
   "es": "Solo consumer",
   "fr": "Consumer uniquement"
  },
  "api-nutzen-keine-nodes-registrieren": {
   "en": "Use the API, register no nodes.",
   "de": "API nutzen, keine Nodes registrieren.",
   "es": "Usar la API, sin registrar nodes.",
   "fr": "Utiliser l'API, aucun node enregistré."
  },
  "nur-provider": {
   "en": "Provider only",
   "de": "Nur Provider",
   "es": "Solo provider",
   "fr": "Provider uniquement"
  },
  "nodes-teilen-keine-api-calls": {
   "en": "Share nodes, no API calls.",
   "de": "Nodes teilen, keine API-Calls.",
   "es": "Compartir nodes, sin llamadas API.",
   "fr": "Partager des nodes, aucun appel API."
  },
  "beides": {
   "en": "Both",
   "de": "Beides",
   "es": "Ambos",
   "fr": "Les deux"
  },
  "voller-zugriff-standard": {
   "en": "Full access — default.",
   "de": "Voller Zugriff — Standard.",
   "es": "Acceso completo — por defecto.",
   "fr": "Accès complet — par défaut."
  },
  "rolle-speichern": {
   "en": "Save role",
   "de": "Rolle speichern",
   "es": "Guardar rol",
   "fr": "Enregistrer le rôle"
  },
  "speichere": {
   "en": "Saving…",
   "de": "Speichere…",
   "es": "Guardando…",
   "fr": "Enregistrement…"
  },
  "freigegebene-modelle": {
   "en": "Allowed models",
   "de": "Freigegebene Modelle",
   "es": "Modelos permitidos",
   "fr": "Modèles autorisés"
  },
  "leer-bedeutet-alle-lokalen-modelle-keine": {
   "en": "Empty means: all local models, no cloud. Choose explicitly to restrict or to unlock cloud models.",
   "de": "Leer bedeutet: alle lokalen Modelle, keine Cloud. Explizit wählen, um einzuschränken oder Cloud freizuschalten.",
   "es": "Vacío significa: todos los modelos locales, sin cloud. Elige explícitamente para restringir o habilitar cloud.",
   "fr": "Vide signifie : tous les modèles locaux, pas de cloud. Choisissez explicitement pour restreindre ou activer le cloud."
  },
  "cloud-modelle-erlauben": {
   "en": "Allow cloud models",
   "de": "Cloud-Modelle erlauben",
   "es": "Permitir modelos cloud",
   "fr": "Autoriser les modèles cloud"
  },
  "sinnvoll-wenn-die-lokale-hardware-gerade": {
   "en": "Useful when the local hardware is not available right now.",
   "de": "Sinnvoll, wenn die lokale Hardware gerade nicht verfügbar ist.",
   "es": "Útil cuando el hardware local no está disponible en ese momento.",
   "fr": "Utile lorsque le matériel local n'est pas disponible."
  },
  "modelle-speichern": {
   "en": "Save models",
   "de": "Modelle speichern",
   "es": "Guardar modelos",
   "fr": "Enregistrer les modèles"
  },
  "auf-standard-zuruecksetzen": {
   "en": "Reset to default",
   "de": "Auf Standard zurücksetzen",
   "es": "Restablecer valores por defecto",
   "fr": "Réinitialiser"
  },
  "node-agent-einrichten": {
   "en": "Set up the node agent",
   "de": "Node-Agent einrichten",
   "es": "Configurar el agente de node",
   "fr": "Configurer l'agent de node"
  },
  "vier-schritte-node-registrieren-image-bauen": {
   "en": "Four steps: register the node, build the image, start the container, verify it in the pool. After that everything runs automatically via heartbeats.",
   "de": "Vier Schritte: Node registrieren, Image bauen, Container starten, im Pool verifizieren. Danach läuft alles über Heartbeats automatisch.",
   "es": "Cuatro pasos: registrar el node, construir la imagen, iniciar el contenedor y verificarlo en el pool. Después todo funciona automáticamente por heartbeats.",
   "fr": "Quatre étapes : enregistrer le node, construire l'image, démarrer le conteneur, vérifier dans le pool. Ensuite tout fonctionne automatiquement par heartbeats."
  },
  "image-bauen": {
   "en": "Build the image",
   "de": "Image bauen",
   "es": "Construir la imagen",
   "fr": "Construire l'image"
  },
  "repo-klonen-oder-den-ordner-code-class": {
   "en": "Clone the repo (or copy the <code class=\"inline\">node-agent/</code> folder) and build:",
   "de": "Repo klonen (oder den Ordner <code class=\"inline\">node-agent/</code> kopieren) und bauen:",
   "es": "Clona el repo (o copia la carpeta <code class=\"inline\">node-agent/</code>) y construye:",
   "fr": "Clonez le dépôt (ou copiez le dossier <code class=\"inline\">node-agent/</code>) et construisez :"
  },
  "container-starten": {
   "en": "Start the container",
   "de": "Container starten",
   "es": "Iniciar el contenedor",
   "fr": "Démarrer le conteneur"
  },
  "code-class-inline-node-id-code-und-code": {
   "en": "Replace <code class=\"inline\">NODE_ID</code> and <code class=\"inline\">NODE_API_KEY</code> with the values from step 1:",
   "de": "<code class=\"inline\">NODE_ID</code> und <code class=\"inline\">NODE_API_KEY</code> durch die Werte aus Schritt 1 ersetzen:",
   "es": "Sustituye <code class=\"inline\">NODE_ID</code> y <code class=\"inline\">NODE_API_KEY</code> por los valores del paso 1:",
   "fr": "Remplacez <code class=\"inline\">NODE_ID</code> et <code class=\"inline\">NODE_API_KEY</code> par les valeurs de l'étape 1 :"
  },
  "logs-verfolgen": {
   "en": "Follow the logs:",
   "de": "Logs verfolgen:",
   "es": "Sigue los logs:",
   "fr": "Suivre les logs :"
  },
  "health-check-der-node": {
   "en": "Health check of the node:",
   "de": "Health-Check der Node:",
   "es": "Health check del node:",
   "fr": "Health check du node :"
  },
  "verifizieren": {
   "en": "Verify",
   "de": "Verifizieren",
   "es": "Verificar",
   "fr": "Vérifier"
  },
  "sobald-die-node-im-a-href-pool-html-class": {
   "en": "As soon as the node appears in the <a href=\"pool.html\" class=\"link\">community pool</a>, it is live. Requests are routed there automatically; 70 % of job cost lands as Credits on your account.",
   "de": "Sobald die Node im <a href=\"pool.html\" class=\"link\">Community-Pool</a> auftaucht, ist sie live. Anfragen werden automatisch dorthin geroutet; 70 % der Job-Kosten landen als Credits auf deinem Konto.",
   "es": "En cuanto el node aparezca en el <a href=\"pool.html\" class=\"link\">pool comunitario</a>, estará activo. Las solicitudes se enrutan allí automáticamente; el 70 % del coste del job llega como Credits a tu cuenta.",
   "fr": "Dès que le node apparaît dans le <a href=\"pool.html\" class=\"link\">pool communautaire</a>, il est actif. Les requêtes y sont routées automatiquement ; 70 % du coût du job arrivent en Credits sur votre compte."
  },
  "pool-ansehen": {
   "en": "View pool",
   "de": "Pool ansehen",
   "es": "Ver el pool",
   "fr": "Voir le pool"
  },
  "profile.models_available_title": {
   "en": "Available models",
   "de": "Verfügbare Modelle",
   "es": "Model disponibles",
   "fr": "Model disponibles"
  },
  "profile.models_available_hint": {
   "en": "These are the models the pool currently offers. Which ones your account may use is decided by the administration; cloud models you can allow yourself below. A client (Hermes, SDK) only shows the models released for your account.",
   "de": "Diese Modelle bietet der Pool zurzeit an. Welche dein Konto nutzen darf, legt die Administration fest; Cloud-Modelle kannst du unten selbst erlauben. Im Client (Hermes, SDK) erscheinen nur die Modelle, die für dein Konto freigegeben sind.",
   "es": "Estos son los Model que el Pool ofrece ahora. La administración decide cuáles puede usar tu cuenta; los Model en la nube puedes permitirlos abajo. Un cliente (Hermes, SDK) solo muestra los Model liberados para tu cuenta.",
   "fr": "Voici les Model que le Pool propose actuellement. Seuls ceux qui apportent un Node peuvent les libérer — rôle provider ou les deux."
  },
  "api_key_session_only": {
   "en": "In the browser you work with a session, not an API key. For a program, a Hermes or an SDK issue a key here — it starts with <code class=\"inline\">gpu_</code> and is shown exactly once.",
   "de": "Im Browser arbeitest du mit einer Sitzung, nicht mit einem API-Schlüssel. Für ein Programm, einen Hermes oder ein SDK stelle hier einen Schlüssel aus — er beginnt mit <code class=\"inline\">gpu_</code> und wird genau einmal angezeigt.",
   "es": "En el navegador trabajas con una sesión, no con un API-Key. Para un programa, un Hermes o un SDK emite aquí una clave: empieza con <code class=\"inline\">gpu_</code> y se muestra una sola vez.",
   "fr": "Dans le navigateur, vous travaillez avec une session, pas avec une API-Key. Pour un programme, un Hermes ou un SDK, émettez une clé ici — elle commence par <code class=\"inline\">gpu_</code> et n'est affichée qu'une seule fois."
  },
  "profile.models_none": {
   "en": "Dir sind derzeit keine Modelle freigegeben — deshalb lehnt der Dienst jeden Aufruf ab. Ein Administrator kann das ändern.",
   "de": "Dir sind derzeit keine Modelle freigegeben — deshalb lehnt der Dienst jeden Aufruf ab. Ein Administrator kann das ändern.",
   "es": "Ahora mismo no tienes Model liberados: por eso el servicio rechaza cada llamada. Un administrador puede cambiarlo.",
   "fr": "Aucun Model ne vous est actuellement libéré — c'est pourquoi le service refuse chaque appel. Un administrateur peut le modifier."
  },
  "api_key_scope": {
   "en": "This key belongs to the signed-in account:",
   "de": "Dieser Schlüssel gilt für das angemeldete Konto:",
   "es": "Esta clave pertenece a la cuenta conectada:",
   "fr": "Cette clé appartient au compte connecté :"
  },
  "api_key_scope_hint": {
   "en": "Models and releases belong to this account — not to the one you expect.",
   "de": "Modelle und Freigaben hängen an diesem Konto — nicht an dem, das du erwartest.",
   "es": "Los Model y las liberaciones dependen de esta cuenta, no de la que esperas.",
   "fr": "Les Model et les libérations dépendent de ce compte — pas de celui que vous attendez."
  },
  "cloud_ack": {
   "en": "I am aware that this lets me use paid models and may require additional credits.",
   "de": "Ich bin mir bewusst, dass ich damit kostenpflichtige Modelle nutze und gegebenenfalls zusätzliche Credits dafür brauche.",
   "es": "Soy consciente de que así uso Model de pago y puede que necesite Credits adicionales.",
   "fr": "Je suis conscient que cela me permet d'utiliser des Model payants et peut nécessiter des Credits supplémentaires."
  },
  "chat.models_hint": {
   "en": "Only models released for your account are listed — without a restriction, all local ones. Cloud models are enabled in the profile.",
   "de": "Angezeigt werden nur Modelle, die für dein Konto freigegeben sind — ohne Einschränkung alle lokalen. Cloud-Modelle schaltest du im Profil zu.",
   "es": "Solo se muestran los Model liberados para tu cuenta; sin restricción, todos los locales. Los Model en la nube se habilitan en el perfil.",
   "fr": "Seuls les Model libérés pour votre compte sont affichés — sans restriction, tous les locaux. Les Model cloud s'autorisent dans le profil."
  },
  "register.pending": {
   "de": "Registrierung eingereicht — ein Administrator gibt das Konto frei.",
   "en": "Registration submitted — an administrator will release the account.",
   "es": "Registro enviado — un administrador liberará la cuenta.",
   "fr": "Inscription envoyée — un administrateur libérera le compte."
  },
  "profile.key.title": {
   "en": "API keys",
   "de": "API-Schlüssel",
   "es": "API keys",
   "fr": "API keys"
  },
  "profile.key.hint": {
   "en": "These keys belong to the account signed in here. A key is shown in full exactly once, when it is issued — afterwards only the prefix remains, because the portal stores a hash.",
   "de": "Diese Schlüssel gehören zu dem hier angemeldeten Konto. Ein Schlüssel wird genau einmal vollständig angezeigt — beim Ausstellen; danach bleibt nur das Präfix, weil das Portal nur einen Hash speichert.",
   "es": "Estas claves pertenecen a la cuenta conectada aquí. Una clave se muestra completa exactamente una vez, al emitirla; después solo queda el prefijo, porque el portal guarda un hash.",
   "fr": "Ces clés appartiennent au compte connecté ici. Une clé n’est affichée en entier qu’une seule fois, à son émission ; ensuite seul le préfixe reste, le portail ne conservant qu’un hash."
  },
  "profile.key.list.title": {
   "en": "Issued keys",
   "de": "Ausgestellte Schlüssel",
   "es": "Claves emitidas",
   "fr": "Clés émises"
  },
  "profile.key.col.prefix": {
   "en": "Prefix",
   "de": "Präfix",
   "es": "Prefijo",
   "fr": "Préfixe"
  },
  "profile.key.col.created": {
   "en": "Created",
   "de": "Erstellt",
   "es": "Creada",
   "fr": "Créée"
  },
  "profile.key.col.status": {
   "en": "Status",
   "de": "Status",
   "es": "Estado",
   "fr": "Statut"
  },
  "profile.key.status.active": {
   "en": "active",
   "de": "aktiv",
   "es": "activa",
   "fr": "active"
  },
  "profile.key.status.replaced": {
   "en": "replaced",
   "de": "ersetzt",
   "es": "reemplazada",
   "fr": "remplacée"
  },
  "profile.key.empty": {
   "en": "No key issued yet. The browser works with a session; create a key here as soon as a program, an SDK or the node installer needs one.",
   "de": "Noch kein Schlüssel ausgestellt. Der Browser arbeitet mit einer Sitzung; einen Schlüssel brauchst du, sobald ein Programm, ein SDK oder der Node-Installer einen verlangt.",
   "es": "Todavía no hay ninguna clave emitida. El navegador trabaja con una sesión; necesitas una clave en cuanto un programa, un SDK o el instalador del node la pida.",
   "fr": "Aucune clé émise pour l’instant. Le navigateur travaille avec une session ; une clé devient nécessaire dès qu’un programme, un SDK ou l’installeur du node en demande une."
  },
  "profile.key.new.title": {
   "en": "Create a new key",
   "de": "Neuen Schlüssel erzeugen",
   "es": "Crear una clave nueva",
   "fr": "Créer une nouvelle clé"
  },
  "profile.key.new.hint": {
   "en": "A new key replaces the previous one: the old key stops working immediately. Confirm with your password — no key is issued without it.",
   "de": "Ein neuer Schlüssel ersetzt den bisherigen: der alte funktioniert sofort nicht mehr. Bestätige mit deinem Passwort — ohne Passwort wird kein Schlüssel ausgestellt.",
   "es": "Una clave nueva sustituye a la anterior: la antigua deja de funcionar de inmediato. Confirma con tu contraseña; sin ella no se emite ninguna clave.",
   "fr": "Une nouvelle clé remplace la précédente : l’ancienne cesse immédiatement de fonctionner. Confirmez avec votre mot de passe — sans lui, aucune clé n’est émise."
  },
  "profile.key.password": {
   "en": "Password to confirm",
   "de": "Passwort zur Bestätigung",
   "es": "Contraseña para confirmar",
   "fr": "Mot de passe pour confirmer"
  },
  "profile.key.create": {
   "en": "Create key",
   "de": "Schlüssel erzeugen",
   "es": "Crear clave",
   "fr": "Créer la clé"
  },
  "profile.key.creating": {
   "en": "Creating…",
   "de": "Erzeuge…",
   "es": "Creando…",
   "fr": "Création…"
  },
  "profile.key.once.title": {
   "en": "This key is shown only now",
   "de": "Dieser Schlüssel wird nur jetzt angezeigt",
   "es": "Esta clave solo se muestra ahora",
   "fr": "Cette clé n’est affichée que maintenant"
  },
  "profile.key.once.body": {
   "en": "Copy it now and keep it somewhere safe. It cannot be displayed again — if you lose it, create a new one. Do not pass it on: it gives full access to this account, including its credits.",
   "de": "Kopiere ihn jetzt und lege ihn sicher ab. Er lässt sich nicht erneut anzeigen — ist er weg, erzeugst du einen neuen. Gib ihn nicht weiter: er öffnet den vollen Zugang zu diesem Konto, einschließlich der Credits.",
   "es": "Cópiala ahora y guárdala en un lugar seguro. No se puede volver a mostrar; si la pierdes, crea otra. No la compartas: da acceso completo a esta cuenta, incluidos sus Credits.",
   "fr": "Copiez-la maintenant et conservez-la en lieu sûr. Elle ne peut plus être réaffichée ; si vous la perdez, créez-en une nouvelle. Ne la transmettez pas : elle ouvre l’accès complet à ce compte, y compris ses Credits."
  },
  "profile.key.copy": {
   "en": "Copy key",
   "de": "Schlüssel kopieren",
   "es": "Copiar clave",
   "fr": "Copier la clé"
  },
  "profile.key.copied": {
   "en": "Key copied",
   "de": "Schlüssel kopiert",
   "es": "Clave copiada",
   "fr": "Clé copiée"
  },
  "profile.key.dismiss": {
   "en": "I have saved it — hide",
   "de": "Ich habe ihn gesichert — ausblenden",
   "es": "La he guardado — ocultar",
   "fr": "Je l’ai enregistrée — masquer"
  },
  "profile.key.for.node": {
   "en": "This is the value the node installer asks for as PORTAL_USER_KEY.",
   "de": "Das ist der Wert, den der Node-Installer als PORTAL_USER_KEY abfragt.",
   "es": "Este es el valor que el instalador del node pide como PORTAL_USER_KEY.",
   "fr": "C’est la valeur que l’installeur du node demande comme PORTAL_USER_KEY."
  },
  "profile.key.load_failed": {
   "en": "Keys could not be loaded:",
   "de": "Schlüssel konnten nicht geladen werden:",
   "es": "No se pudieron cargar las claves:",
   "fr": "Impossible de charger les clés :"
  },
  "profile.key.password_wrong": {
   "en": "Password incorrect — no key was issued.",
   "de": "Passwort falsch — es wurde kein Schlüssel ausgestellt.",
   "es": "Contraseña incorrecta: no se emitió ninguna clave.",
   "fr": "Mot de passe incorrect — aucune clé n’a été émise."
  },
  "profile.key.needs_password": {
   "en": "Enter your password to create a key.",
   "de": "Gib dein Passwort ein, um einen Schlüssel zu erzeugen.",
   "es": "Introduce tu contraseña para crear una clave.",
   "fr": "Saisissez votre mot de passe pour créer une clé."
  },
  "profile.key.issued": {
   "en": "New key created — the previous one is invalid.",
   "de": "Neuer Schlüssel erzeugt — der bisherige ist ungültig.",
   "es": "Clave nueva creada: la anterior ya no es válida.",
   "fr": "Nouvelle clé créée — la précédente est invalide."
  },
  "gpu-bereitstellen": {
   "en": "Contribute a GPU",
   "de": "GPU bereitstellen",
   "es": "Aportar una GPU",
   "fr": "Fournir un GPU"
  },
  "node-registrieren": {
   "en": "Register node",
   "de": "Node registrieren",
   "es": "Registrar node",
   "fr": "Enregistrer le node"
  },
  "node-registrieren-agent-starten-fertig-70": {
   "en": "Register the node, start the agent, done. 70 % of job cost is credited to the node owner as Credits.",
   "de": "Node registrieren, Agent starten, fertig. 70 % der Job-Kosten werden dem Node-Owner als Credits gutgeschrieben.",
   "es": "Registra el node, inicia el agente y listo. El 70 % del coste del job se abona al node owner como Credits.",
   "fr": "Enregistrez le node, démarrez l'agent, terminé. 70 % du coût du job est crédité au node owner en Credits."
  },
  "alle-nodes-auswaehlen": {
   "en": "Select all nodes",
   "de": "Alle Nodes auswählen",
   "es": "Seleccionar todos los nodes",
   "fr": "Sélectionner tous les nodes"
  },
  "alle-auswaehlen": {
   "en": "Select all",
   "de": "Alle auswählen",
   "es": "Seleccionar todo",
   "fr": "Tout sélectionner"
  },
  "whitelist-setzen": {
   "en": "Set allow-list",
   "de": "Whitelist setzen",
   "es": "Definir lista blanca",
   "fr": "Définir la liste blanche"
  },
  "auswahl-aufheben": {
   "en": "Clear selection",
   "de": "Auswahl aufheben",
   "es": "Anular selección",
   "fr": "Désélectionner"
  },
  "z-b-wohnzimmer-rtx-4090": {
   "en": "e.g. living room RTX 4090",
   "de": "z. B. Wohnzimmer RTX 4090",
   "es": "p. ej. salón RTX 4090",
   "fr": "p. ex. salon RTX 4090"
  },
  "rtx-4090": {
   "en": "RTX 4090",
   "de": "RTX 4090",
   "es": "RTX 4090",
   "fr": "RTX 4090"
  },
  "vram-gb": {
   "en": "VRAM (GB)",
   "de": "VRAM (GB)",
   "es": "VRAM (GB)",
   "fr": "VRAM (GB)"
  },
  "vram-angenommen-keine-gpu-erkannt": {
   "en": "VRAM assumed — no GPU detected: the pool will not route jobs here until NODE_VRAM_GB is set",
   "de": "VRAM angenommen — keine GPU erkannt: der Pool schickt dieser Node keinen Auftrag, bis NODE_VRAM_GB gesetzt ist",
   "es": "VRAM supuesta — no se detecta GPU: el pool no enviará trabajos a este node hasta que se defina NODE_VRAM_GB",
   "fr": "VRAM supposée — aucun GPU détecté : le pool n’enverra aucune tâche à ce node tant que NODE_VRAM_GB n’est pas défini"
  },
  "stundensatz-credits": {
   "en": "Rate (Credits)",
   "de": "Stundensatz (Credits)",
   "es": "Tarifa (Credits)",
   "fr": "Tarif (Credits)"
  },
  "adresse-leer-lassen-der-agent-meldet": {
   "en": "Leave empty: the agent reports its own address with the first heartbeat (the usual case on DHCP). Prefer a fixed address? Enter a name — DNS/mDNS such as mein-gpu.local:11435, not an IP.",
   "de": "Leer lassen: der Agent meldet seine Adresse beim ersten Heartbeat selbst (üblich in DHCP-Netzen). Feste Adresse? Dann einen Namen eintragen — DNS/mDNS wie mein-gpu.local:11435 statt einer IP.",
   "es": "Déjalo vacío: el agente comunica su dirección con el primer heartbeat (lo habitual en DHCP). ¿Prefieres una dirección fija? Usa un nombre — DNS/mDNS como mein-gpu.local:11435, no una IP.",
   "fr": "Laissez vide : l’agent annonce sa propre adresse au premier heartbeat (le cas habituel en DHCP). Adresse fixe ? Utilisez un nom — DNS/mDNS comme mein-gpu.local:11435, pas une IP."
  },
  "der-pool-routet-ausschliesslich-ueber-das": {
   "en": "The pool routes exclusively over the tailnet — publicly reachable nodes are not intended.",
   "de": "Der Pool routet ausschließlich über das Tailnet — public erreichbare Nodes sind nicht vorgesehen.",
   "es": "El pool enruta exclusivamente por el tailnet — no se contemplan nodes accesibles públicamente.",
   "fr": "Le pool route exclusivement via le tailnet — les nodes accessibles publiquement ne sont pas prévus."
  },
  "modelle-die-diese-node-teilen-darf": {
   "en": "Models this node may share",
   "de": "Modelle, die diese Node teilen darf",
   "es": "Modelos que este node puede compartir",
   "fr": "Modèles que ce node peut partager"
  },
  "leer-standard-alle-lokalen-modelle-keine": {
   "en": "Empty = default (all local models, no cloud). Choose explicitly to restrict.",
   "de": "Leer = Standard (alle lokalen Modelle, keine Cloud). Explizit auswählen, um einzuschränken.",
   "es": "Vacío = por defecto (todos los modelos locales, sin cloud). Elige explícitamente para restringir.",
   "fr": "Vide = par défaut (tous les modèles locaux, pas de cloud). Choisissez explicitement pour restreindre."
  },
  "modelle-werden-geladen": {
   "en": "Loading models…",
   "de": "Modelle werden geladen…",
   "es": "Cargando modelos…",
   "fr": "Chargement des modèles…"
  },
  "wird-nur-jetzt-angezeigt-der-node-agent": {
   "en": "Shown only now — the node agent needs it at startup.",
   "de": "Wird nur jetzt angezeigt — der Node-Agent braucht ihn beim Start.",
   "es": "Se muestra solo ahora — el agente de node lo necesita al arrancar.",
   "fr": "Affiché une seule fois — l'agent de node en a besoin au démarrage."
  },
  "was-beim-registrieren-passiert": {
   "en": "What happens on registration",
   "de": "Was beim Registrieren passiert",
   "es": "Qué ocurre al registrarse",
   "fr": "Ce qui se passe à l'enregistrement"
  },
  "node-agent-als-container-starten-mit-node": {
   "en": "Start the node agent as a container, with the node ID and API key.",
   "de": "Node-Agent als Container starten, mit Node-ID und API-Key.",
   "es": "Inicia el agente de node como contenedor, con el node ID y la API key.",
   "fr": "Démarrez l'agent de node en conteneur, avec l'ID du node et la clé API."
  },
  "der-agent-sendet-alle-30-s-einen-heartbeat": {
   "en": "The agent sends a heartbeat every 30 s — the node shows up in the community pool.",
   "de": "Der Agent sendet alle 30 s einen Heartbeat — die Node erscheint im Community-Pool.",
   "es": "El agente envía un heartbeat cada 30 s — el node aparece en el pool comunitario.",
   "fr": "L'agent envoie un heartbeat toutes les 30 s — le node apparaît dans le pool communautaire."
  },
  "anfragen-laufen-ueber-deine-gpu-70-der-job": {
   "en": "Requests run on your GPU. 70 % of job cost goes to you, 20 % to the platform, 10 % to the treasury.",
   "de": "Anfragen laufen über deine GPU. 70 % der Job-Kosten gehen an dich, 20 % an die Plattform, 10 % an die Treasury.",
   "es": "Las solicitudes se ejecutan en tu GPU. El 70 % del coste del job va a ti, 20 % a la plataforma, 10 % al treasury.",
   "fr": "Les requêtes tournent sur votre GPU. 70 % du coût du job vous revient, 20 % à la plateforme, 10 % à la trésorerie."
  },
  "zur-node-agent-anleitung": {
   "en": "Go to the node agent guide",
   "de": "Zur Node-Agent-Anleitung",
   "es": "Ir a la guía del agente de node",
   "fr": "Aller au guide de l'agent de node"
  },
  "meine-registrierten-nodes": {
   "en": "My registered nodes",
   "de": "Meine registrierten Nodes",
   "es": "Mis nodes registrados",
   "fr": "Mes nodes enregistrés"
  },
  "span-x-text-n-gpu-type-span-span-x-text-n": {
   "en": "<span x-text=\"n.gpu_type\"></span> · <span x-text=\"n.vram_gb\"></span> GB VRAM · <span class=\"mono\" x-text=\"n.node_url || '—'\"></span>",
   "de": "<span x-text=\"n.gpu_type\"></span> · <span x-text=\"n.vram_gb\"></span> GB VRAM · <span class=\"mono\" x-text=\"n.node_url || '—'\"></span>",
   "es": "<span x-text=\"n.gpu_type\"></span> · <span x-text=\"n.vram_gb\"></span> GB VRAM · <span class=\"mono\" x-text=\"n.node_url || '—'\"></span>",
   "fr": "<span x-text=\"n.gpu_type\"></span> · <span x-text=\"n.vram_gb\"></span> GB VRAM · <span class=\"mono\" x-text=\"n.node_url || '—'\"></span>"
  },
  "span-class-mono-x-text-n-hourly-rate-span": {
   "en": "<span class=\"mono\" x-text=\"n.hourly_rate\"></span> Credits/h · earned <span class=\"mono\" x-text=\"fmtCredits(n.earnings_total)\"></span> · last seen <span x-text=\"fmtDate(n.last_seen)\"></span>",
   "de": "<span class=\"mono\" x-text=\"n.hourly_rate\"></span> Credits/h · verdient <span class=\"mono\" x-text=\"fmtCredits(n.earnings_total)\"></span> · zuletzt gesehen <span x-text=\"fmtDate(n.last_seen)\"></span>",
   "es": "<span class=\"mono\" x-text=\"n.hourly_rate\"></span> Credits/h · ganado <span class=\"mono\" x-text=\"fmtCredits(n.earnings_total)\"></span> · visto por última vez <span x-text=\"fmtDate(n.last_seen)\"></span>",
   "fr": "<span class=\"mono\" x-text=\"n.hourly_rate\"></span> Credits/h · gagné <span class=\"mono\" x-text=\"fmtCredits(n.earnings_total)\"></span> · vu pour la dernière fois <span x-text=\"fmtDate(n.last_seen)\"></span>"
  },
  "standard-alle-lokal-keine-cloud": {
   "en": "Default (all local, no cloud)",
   "de": "Standard (alle lokal, keine Cloud)",
   "es": "Por defecto (todo local, sin cloud)",
   "fr": "Par défaut (tout local, pas de cloud)"
  },
  "nichts-freigegeben": {
   "en": "nothing allowed",
   "de": "nichts freigegeben",
   "es": "nada permitido",
   "fr": "rien d'autorisé"
  },
  "modell-whitelist-bearbeiten": {
   "en": "Edit model allow-list",
   "de": "Modell-Whitelist bearbeiten",
   "es": "Editar lista blanca de modelos",
   "fr": "Modifier la liste blanche"
  },
  "leere-auswahl-bedeutet-nichts-freigegeben": {
   "en": "An empty selection means: nothing allowed. \"Reset to default\" in the profile restores \"all local models\".",
   "de": "Leere Auswahl bedeutet: nichts freigegeben. Über „Auf Standard zurücksetzen\" im Profil gilt wieder „alle lokalen Modelle\".",
   "es": "Una selección vacía significa: nada permitido. «Restablecer valores por defecto» en el perfil vuelve a «todos los modelos locales».",
   "fr": "Une sélection vide signifie : rien d'autorisé. « Réinitialiser » dans le profil rétablit « tous les modèles locaux »."
  },
  "noch-keine-node-registriert-das-formular": {
   "en": "No node registered yet — the form above is the first step.",
   "de": "Noch keine Node registriert — das Formular oben ist der erste Schritt.",
   "es": "Aún no hay ningún node registrado — el formulario de arriba es el primer paso.",
   "fr": "Aucun node enregistré — le formulaire ci-dessus est la première étape."
  },
  "modell-whitelist-fuer-span-x-text": {
   "en": "Model allow-list for <span x-text=\"selectedCount\"></span> node(s)",
   "de": "Modell-Whitelist für <span x-text=\"selectedCount\"></span> Node(s)",
   "es": "Lista blanca de modelos para <span x-text=\"selectedCount\"></span> node(s)",
   "fr": "Liste blanche pour <span x-text=\"selectedCount\"></span> node(s)"
  },
  "gilt-fuer-alle-ausgewaehlten-nodes-keine": {
   "en": "Applies to all selected nodes. No selection = nodes accept no models. Resetting to \"default\" (all local models) is currently not possible through the UI — see LANA-49.",
   "de": "Gilt für alle ausgewählten Nodes. Keine Auswahl = Nodes nehmen keine Modelle an. Ein Zurücksetzen auf \"Standard\" (alle lokalen Modelle) ist über die UI derzeit nicht möglich — siehe LANA-49.",
   "es": "Se aplica a todos los nodes seleccionados. Sin selección = los nodes no aceptan modelos. Volver a \"default\" (todos los modelos locales) aún no es posible desde la UI — ver LANA-49.",
   "fr": "S'applique à tous les nodes sélectionnés. Aucune sélection = les nodes n'acceptent aucun modèle. Le retour à « par défaut » (tous les modèles locaux) n'est pas encore possible via l'UI — voir LANA-49."
  },
  "alle-lokalen": {
   "en": "All local",
   "de": "Alle lokalen",
   "es": "Todos los locales",
   "fr": "Tous les locaux"
  },
  "alle": {
   "en": "All",
   "de": "Alle",
   "es": "Todos",
   "fr": "Tous"
  },
  "keine": {
   "en": "None",
   "de": "Keine",
   "es": "Ninguno",
   "fr": "Aucun"
  },
  "lade-modelle": {
   "en": "Loading models…",
   "de": "Lade Modelle…",
   "es": "Cargando modelos…",
   "fr": "Chargement des modèles…"
  },
  "welche-modelle-du-nutzt-und-wie-viele-token": {
   "en": "Which models you use and how many Token pass through. Aggregated server-side from every <code class=\"inline\">/v1/chat/completions</code> call.",
   "de": "Welche Modelle du nutzt und wie viele Token dabei durchlaufen. Aggregiert serverseitig aus jedem <code class=\"inline\">/v1/chat/completions</code>-Aufruf.",
   "es": "Qué modelos usas y cuántos Token pasan. Agregado en el servidor a partir de cada llamada a <code class=\"inline\">/v1/chat/completions</code>.",
   "fr": "Quels modèles vous utilisez et combien de Token circulent. Agrégé côté serveur à partir de chaque appel <code class=\"inline\">/v1/chat/completions</code>."
  },
  "usage-konnte-nicht-geladen-werden": {
   "en": "Usage could not be loaded",
   "de": "Usage konnte nicht geladen werden",
   "es": "No se pudo cargar el consumo",
   "fr": "Impossible de charger l'usage"
  },
  "token-gesamt": {
   "en": "Token total",
   "de": "Token gesamt",
   "es": "Token totales",
   "fr": "Token au total"
  },
  "verschiedene-modelle-verwendet": {
   "en": "different models used",
   "de": "verschiedene Modelle verwendet",
   "es": "modelos distintos usados",
   "fr": "modèles différents utilisés"
  },
  "verteilung": {
   "en": "Distribution",
   "de": "Verteilung",
   "es": "Distribución",
   "fr": "Répartition"
  },
  "token-je-modell": {
   "en": "Token per model",
   "de": "Token je Modell",
   "es": "Token por modelo",
   "fr": "Token par modèle"
  },
  "in-diesem-zeitraum-wurde-noch-nichts": {
   "en": "Nothing consumed in this period yet.",
   "de": "In diesem Zeitraum wurde noch nichts verbraucht.",
   "es": "Aún no se ha consumido nada en este periodo.",
   "fr": "Rien n'a encore été consommé sur cette période."
  },
  "a-href-chat-html-class-link-chat-oeffnen-a": {
   "en": "<a href=\"chat.html\" class=\"link\">Open chat</a> or switch the period to \"Total\".",
   "de": "<a href=\"chat.html\" class=\"link\">Chat öffnen</a> oder den Zeitraum auf „Gesamt“ stellen.",
   "es": "<a href=\"chat.html\" class=\"link\">Abrir chat</a> o cambiar el periodo a «Total».",
   "fr": "<a href=\"chat.html\" class=\"link\">Ouvrir le chat</a> ou passer la période à « Total »."
  },
  "verlauf": {
   "en": "History",
   "de": "Verlauf",
   "es": "Evolución",
   "fr": "Historique"
  },
  "token-je-span-x-text-data-data-granularity": {
   "en": "Token per <span x-text=\"data && data.granularity === 'hour' ? 'hour' : 'day'\"></span>",
   "de": "Token je <span x-text=\"data && data.granularity === 'hour' ? 'Stunde' : 'Tag'\"></span>",
   "es": "Token por <span x-text=\"data && data.granularity === 'hour' ? 'hora' : 'día'\"></span>",
   "fr": "Token par <span x-text=\"data && data.granularity === 'hour' ? 'heure' : 'jour'\"></span>"
  },
  "leere-abschnitte-heissen-keine-anfrage": {
   "en": "Empty sections mean: no request.",
   "de": "Leere Abschnitte heißen: keine Anfrage.",
   "es": "Los tramos vacíos significan: ninguna solicitud.",
   "fr": "Les sections vides signifient : aucune requête."
  },
  "credits-verbraucht": {
   "en": "Credits consumed",
   "de": "Credits verbraucht",
   "es": "Credits consumidos",
   "fr": "Credits consommés"
  },
  "letzte-aktivitaet": {
   "en": "Last activity",
   "de": "Letzte Aktivität",
   "es": "Última actividad",
   "fr": "Dernière activité"
  },
  "letzte-requests": {
   "en": "Recent requests",
   "de": "Letzte Requests",
   "es": "Últimas solicitudes",
   "fr": "Dernières requêtes"
  },
  "keine-requests-in-diesem-zeitraum": {
   "en": "No requests in this period.",
   "de": "Keine Requests in diesem Zeitraum.",
   "es": "Sin solicitudes en este periodo.",
   "fr": "Aucune requête sur cette période."
  },
  "prompt": {
   "en": "Prompt",
   "de": "Prompt",
   "es": "Prompt",
   "fr": "Prompt"
  },
  "completion": {
   "en": "Completion",
   "de": "Completion",
   "es": "Completion",
   "fr": "Completion"
  },
  "verbrauch-aller-nutzer": {
   "en": "Consumption of all users",
   "de": "Verbrauch aller Nutzer",
   "es": "Consumo de todos los usuarios",
   "fr": "Consommation de tous les utilisateurs"
  },
  "token-und-credits-pro-nutzer-und-modell-die": {
   "en": "Token and Credits per user and model — the admin view of",
   "de": "Token und Credits pro Nutzer und Modell — die Admin-Sicht auf",
   "es": "Token y Credits por usuario y modelo — la vista de admin de",
   "fr": "Token et Credits par utilisateur et modèle — la vue admin de"
  },
  "admin-rolle-erforderlich": {
   "en": "Admin role required",
   "de": "Admin-Rolle erforderlich",
   "es": "Se requiere rol de admin",
   "fr": "Rôle admin requis"
  },
  "dieser-bereich-listet-die-nutzung-aller": {
   "en": "This area lists the usage of all accounts and is limited to <code class=\"inline\">role = admin</code>. Your role: <span class=\"mono\" x-text=\"(Auth.currentUser() || {}).role || 'both'\"></span>. Your own usage is under <a href=\"usage.html\" class=\"link\">Usage</a>.",
   "de": "Dieser Bereich listet die Nutzung aller Konten und ist auf <code class=\"inline\">role = admin</code> beschränkt. Deine Rolle: <span class=\"mono\" x-text=\"(Auth.currentUser() || {}).role || 'both'\"></span>. Die eigene Nutzung steht unter <a href=\"usage.html\" class=\"link\">Usage</a>.",
   "es": "Esta sección lista el consumo de todas las cuentas y está limitada a <code class=\"inline\">role = admin</code>. Tu rol: <span class=\"mono\" x-text=\"(Auth.currentUser() || {}).role || 'both'\"></span>. Tu propio consumo está en <a href=\"usage.html\" class=\"link\">Usage</a>.",
   "fr": "Cette section liste l'usage de tous les comptes et est réservée à <code class=\"inline\">role = admin</code>. Votre rôle : <span class=\"mono\" x-text=\"(Auth.currentUser() || {}).role || 'both'\"></span>. Votre propre usage se trouve dans <a href=\"usage.html\" class=\"link\">Usage</a>."
  },
  "verbrauch-konnte-nicht-geladen-werden": {
   "en": "Consumption could not be loaded",
   "de": "Verbrauch konnte nicht geladen werden",
   "es": "No se pudo cargar el consumo",
   "fr": "Impossible de charger la consommation"
  },
  "nutzende-konten": {
   "en": "Active accounts",
   "de": "Nutzende Konten",
   "es": "Cuentas con actividad",
   "fr": "Comptes actifs"
  },
  "verbrauch-je-nutzer": {
   "en": "Consumption per user",
   "de": "Verbrauch je Nutzer",
   "es": "Consumo por usuario",
   "fr": "Consommation par utilisateur"
  },
  "in-diesem-zeitraum-hat-niemand-verbraucht": {
   "en": "Nobody consumed anything in this period.",
   "de": "In diesem Zeitraum hat niemand verbraucht.",
   "es": "Nadie ha consumido nada en este periodo.",
   "fr": "Personne n'a consommé sur cette période."
  },
  "zeitraum-auf-gesamt-stellen-oder-inaktive": {
   "en": "Switch the period to \"Total\" or show inactive accounts.",
   "de": "Zeitraum auf „Gesamt“ stellen oder inaktive Konten einblenden.",
   "es": "Cambia el periodo a «Total» o muestra cuentas inactivas.",
   "fr": "Passez la période à « Total » ou affichez les comptes inactifs."
  },
  "nutzer": {
   "en": "User",
   "de": "Nutzer",
   "es": "Usuario",
   "fr": "Utilisateur"
  },
  "zeitraum": {
   "en": "Period",
   "de": "Zeitraum",
   "es": "Periodo",
   "fr": "Période"
  },
  "admin.credits_system": {
   "en": "Credits system",
   "de": "Credits-System",
   "es": "Sistema de créditos",
   "fr": "Système de crédits"
  },
  "admin.quota": {
   "en": "Quota",
   "de": "Quota",
   "es": "Cuota",
   "fr": "Quota"
  },
  "abbrechen": {
   "en": "Cancel",
   "de": "Abbrechen",
   "es": "Cancelar",
   "fr": "Annuler"
  },
  "ablauf": {
   "en": "Expiry",
   "de": "Ablauf",
   "es": "Caducidad",
   "fr": "Expiration"
  },
  "agent-api-key": {
   "en": "Agent API key",
   "de": "Agent-API-Key",
   "es": "Agent API key",
   "fr": "Clé API agent"
  },
  "aktualisieren": {
   "en": "Refresh",
   "de": "Aktualisieren",
   "es": "Actualizar",
   "fr": "Actualiser"
  },
  "aufschluesselung": {
   "en": "Breakdown",
   "de": "Aufschlüsselung",
   "es": "Desglose",
   "fr": "Détail"
  },
  "beschreibung": {
   "en": "Description",
   "de": "Beschreibung",
   "es": "Descripción",
   "fr": "Description"
  },
  "bestand": {
   "en": "Inventory",
   "de": "Bestand",
   "es": "Inventario",
   "fr": "Parc"
  },
  "bulk": {
   "en": "Bulk",
   "de": "Bulk",
   "es": "Bulk",
   "fr": "Bulk"
  },
  "gpu-typ": {
   "en": "GPU type",
   "de": "GPU-Typ",
   "es": "Tipo de GPU",
   "fr": "Type de GPU"
  },
  "inaktiv": {
   "en": "inactive",
   "de": "inaktiv",
   "es": "inactivo",
   "fr": "inactif"
  },
  "laedt": {
   "en": "Loading…",
   "de": "Lädt…",
   "es": "Cargando…",
   "fr": "Chargement…"
  },
  "loeschen": {
   "en": "Delete",
   "de": "Löschen",
   "es": "Eliminar",
   "fr": "Supprimer"
  },
  "neu": {
   "en": "New",
   "de": "Neu",
   "es": "Nuevo",
   "fr": "Nouveau"
  },
  "pausiert": {
   "en": "paused",
   "de": "pausiert",
   "es": "pausado",
   "fr": "en pause"
  },
  "port": {
   "en": "Port",
   "de": "Port",
   "es": "Puerto",
   "fr": "Port"
  },
  "schliessen": {
   "en": "Close",
   "de": "Schließen",
   "es": "Cerrar",
   "fr": "Fermer"
  },
  "speichern": {
   "en": "Save",
   "de": "Speichern",
   "es": "Guardar",
   "fr": "Enregistrer"
  },
  "node-adresse-optional": {
   "en": "Node address (optional)",
   "de": "Adresse der Node (optional)",
   "es": "Dirección del node (opcional)",
   "fr": "Adresse du node (facultatif)"
  },
  "automatisch-erkannt": {
   "en": "auto-detected",
   "de": "automatisch erkannt",
   "es": "detectada automáticamente",
   "fr": "détectée automatiquement"
  },
  "zuletzt": {
   "en": "Last seen",
   "de": "Zuletzt",
   "es": "Última vez",
   "fr": "Vu récemment"
  },
  "span-class-mono-x-text": {
   "en": "<span class=\"mono\" x-text=\"bulkWhitelistSelection.length\"></span> selected",
   "de": "<span class=\"mono\" x-text=\"bulkWhitelistSelection.length\"></span> gewählt",
   "es": "<span class=\"mono\" x-text=\"bulkWhitelistSelection.length\"></span> seleccionados",
   "fr": "<span class=\"mono\" x-text=\"bulkWhitelistSelection.length\"></span> sélectionnés"
  },
  "span-class-mono-x-text-selectedcount-span": {
   "en": "<span class=\"mono\" x-text=\"selectedCount\"></span> selected",
   "de": "<span class=\"mono\" x-text=\"selectedCount\"></span> ausgewählt",
   "es": "<span class=\"mono\" x-text=\"selectedCount\"></span> seleccionados",
   "fr": "<span class=\"mono\" x-text=\"selectedCount\"></span> sélectionnés"
  },
  "stundensatz-span-x-text-raterange-span": {
   "en": "Rate <span x-text=\"rateRange()\"></span>",
   "de": "Stundensatz <span x-text=\"rateRange()\"></span>",
   "es": "Tarifa <span x-text=\"rateRange()\"></span>",
   "fr": "Tarif <span x-text=\"rateRange()\"></span>"
  },
  "quelle-code-class-inline-get-admin-usage": {
   "en": "Source: <code class=\"inline\">GET /admin/usage?window=24h|7d|30d|all&amp;limit=50&amp;include_inactive=true</code> — the same shape as the user's own usage endpoint.",
   "de": "Quelle: <code class=\"inline\">GET /admin/usage?window=24h|7d|30d|all&amp;limit=50&amp;include_inactive=true</code> — dieselbe Form wie der eigene Nutzungs-Endpunkt.",
   "es": "Fuente: <code class=\"inline\">GET /admin/usage?window=24h|7d|30d|all&amp;limit=50&amp;include_inactive=true</code> — la misma forma que el endpoint de consumo propio.",
   "fr": "Source : <code class=\"inline\">GET /admin/usage?window=24h|7d|30d|all&amp;limit=50&amp;include_inactive=true</code> — même forme que l'endpoint d'usage personnel."
  },
  "auf-a-href-nodes-html-class-link-meine": {
   "en": "Fill in <a href=\"nodes.html\" class=\"link\">My nodes</a>. The response contains the <code class=\"inline\">agent_api_key</code> — shown once.",
   "de": "Auf <a href=\"nodes.html\" class=\"link\">Meine Nodes</a> ausfüllen. Die Antwort enthält den <code class=\"inline\">agent_api_key</code> — einmalig sichtbar.",
   "es": "Rellena <a href=\"nodes.html\" class=\"link\">Mis nodes</a>. La respuesta incluye el <code class=\"inline\">agent_api_key</code> — visible una sola vez.",
   "fr": "À remplir sur <a href=\"nodes.html\" class=\"link\">Mes nodes</a>. La réponse contient la <code class=\"inline\">agent_api_key</code> — affichée une seule fois."
  },
  "live-aus-code-class-inline-get-v1-me-usage": {
   "en": "Live from <code class=\"inline\">GET /v1/me/usage</code> — details and the period switcher are in the <a href=\"usage.html\" class=\"link\">Usage tab</a>.",
   "de": "Live aus <code class=\"inline\">GET /v1/me/usage</code> — Details und Zeitraum-Umschalter im <a href=\"usage.html\" class=\"link\">Usage-Tab</a>.",
   "es": "En vivo desde <code class=\"inline\">GET /v1/me/usage</code> — los detalles y el selector de periodo están en la <a href=\"usage.html\" class=\"link\">pestaña Usage</a>.",
   "fr": "En direct depuis <code class=\"inline\">GET /v1/me/usage</code> — les détails et le sélecteur de période sont dans l'<a href=\"usage.html\" class=\"link\">onglet Usage</a>."
  },
  "fuer-code-class-inline-v1-chat-completions": {
   "en": "For <code class=\"inline\">/v1/chat/completions</code> and <code class=\"inline\">/v1/models</code>.",
   "de": "Für <code class=\"inline\">/v1/chat/completions</code> und <code class=\"inline\">/v1/models</code>.",
   "es": "Para <code class=\"inline\">/v1/chat/completions</code> y <code class=\"inline\">/v1/models</code>.",
   "fr": "Pour <code class=\"inline\">/v1/chat/completions</code> et <code class=\"inline\">/v1/models</code>."
  },
  "du-erhaeltst-einen-code-class-inline-agent": {
   "en": "You receive an <code class=\"inline\">agent_api_key</code> — shown only once, store it safely.",
   "de": "Du erhältst einen <code class=\"inline\">agent_api_key</code> — einmalig sichtbar, sicher speichern.",
   "es": "Recibes un <code class=\"inline\">agent_api_key</code> — visible una sola vez, guárdalo bien.",
   "fr": "Vous recevez une <code class=\"inline\">agent_api_key</code> — visible une seule fois, conservez-la."
  },
  "quelle-code-class-inline-get-v1-me-usage": {
   "en": "Source: <code class=\"inline\">GET /v1/me/usage?window=24h|7d|30d|all</code> — aggregation per model, period and request.",
   "de": "Quelle: <code class=\"inline\">GET /v1/me/usage?window=24h|7d|30d|all</code> — Aggregation pro Modell, Zeitraum und Request.",
   "es": "Fuente: <code class=\"inline\">GET /v1/me/usage?window=24h|7d|30d|all</code> — agregación por modelo, periodo y solicitud.",
   "fr": "Source : <code class=\"inline\">GET /v1/me/usage?window=24h|7d|30d|all</code> — agrégation par modèle, période et requête."
  },
  "common.all": {
   "en": "All",
   "de": "Alle",
   "es": "Todos",
   "fr": "Tous"
  },
  "dash.greeting.morning": {
   "en": "Good morning",
   "de": "Guten Morgen",
   "es": "Buenos días",
   "fr": "Bonjour"
  },
  "dash.greeting.day": {
   "en": "Good afternoon",
   "de": "Guten Tag",
   "es": "Buenas tardes",
   "fr": "Bon après-midi"
  },
  "dash.greeting.evening": {
   "en": "Good evening",
   "de": "Guten Abend",
   "es": "Buenas noches",
   "fr": "Bonsoir"
  },
  "dash.window.24h": {
   "en": "24 hours",
   "de": "24 Stunden",
   "es": "24 horas",
   "fr": "24 heures"
  },
  "dash.window.7d": {
   "en": "7 days",
   "de": "7 Tage",
   "es": "7 días",
   "fr": "7 jours"
  },
  "dash.window.30d": {
   "en": "30 days",
   "de": "30 Tage",
   "es": "30 días",
   "fr": "30 jours"
  },
  "dash.key.copied": {
   "en": "API key copied",
   "de": "API-Key kopiert",
   "es": "API key copiada",
   "fr": "Clé API copiée"
  },
  "dash.key.regenerate.confirm": {
   "en": "Issue a new API key? The current one becomes invalid immediately.",
   "de": "Neuen API-Key ausstellen? Der bisherige wird sofort ungültig.",
   "es": "¿Emitir una nueva API key? La actual deja de ser válida de inmediato.",
   "fr": "Émettre une nouvelle clé API ? L'actuelle devient invalide immédiatement."
  },
  "dash.key.regenerate.prompt": {
   "en": "Password to confirm:",
   "de": "Passwort zur Bestätigung:",
   "es": "Contraseña para confirmar:",
   "fr": "Mot de passe pour confirmer :"
  },
  "dash.key.regenerate.done": {
   "en": "New API key issued — save it now.",
   "de": "Neuer API-Key ausgestellt — jetzt sichern.",
   "es": "Nueva API key emitida — guárdala ahora.",
   "fr": "Nouvelle clé API émise — sauvegardez-la maintenant."
  },
  "chat.prompt.quantum.label": {
   "en": "Explain quantum computing",
   "de": "Quantencomputing erklären",
   "es": "Explicar la computación cuántica",
   "fr": "Expliquer l'informatique quantique"
  },
  "chat.prompt.quantum.text": {
   "en": "Explain quantum computing in three sentences.",
   "de": "Erkläre Quantencomputing in drei Sätzen.",
   "es": "Explica la computación cuántica en tres frases.",
   "fr": "Expliquez l'informatique quantique en trois phrases."
  },
  "chat.prompt.python.label": {
   "en": "Python hello world",
   "de": "Python Hello-World",
   "es": "Hola mundo en Python",
   "fr": "Hello world en Python"
  },
  "chat.prompt.python.text": {
   "en": "Write a Python hello world with type hints.",
   "de": "Schreibe ein Python Hello-World mit Type Hints.",
   "es": "Escribe un hola mundo en Python con type hints.",
   "fr": "Écrivez un hello world Python avec des type hints."
  },
  "chat.prompt.ideas.label": {
   "en": "Side project ideas",
   "de": "Ideen für ein Nebenprojekt",
   "es": "Ideas para un proyecto secundario",
   "fr": "Idées de projet annexe"
  },
  "chat.prompt.ideas.text": {
   "en": "Give me three side project ideas.",
   "de": "Gib mir drei Ideen für ein Nebenprojekt.",
   "es": "Dame tres ideas para un proyecto secundario.",
   "fr": "Donnez-moi trois idées de projet annexe."
  },
  "chat.no_reply": {
   "en": "(no reply)",
   "de": "(keine Antwort)",
   "es": "(sin respuesta)",
   "fr": "(pas de réponse)"
  },
  "chat.no_credits": {
   "en": "Not enough credits — please top up.",
   "de": "Guthaben reicht nicht — bitte Credits aufladen.",
   "es": "Créditos insuficientes — recarga, por favor.",
   "fr": "Crédits insuffisants — veuillez recharger."
  },
  "chat.models_failed": {
   "en": "Models could not be loaded:",
   "de": "Modelle konnten nicht geladen werden:",
   "es": "No se pudieron cargar los modelos:",
   "fr": "Impossible de charger les modèles :"
  },
  "chat.error": {
   "en": "Chat error:",
   "de": "Chat-Fehler:",
   "es": "Error de chat:",
   "fr": "Erreur de chat :"
  },
  "credits.pack.token.10m": {
   "en": "approx. 10M tokens",
   "de": "ca. 10 Mio. Token",
   "es": "aprox. 10 M tokens",
   "fr": "env. 10 M tokens"
  },
  "credits.pack.token.50m": {
   "en": "approx. 50M tokens",
   "de": "ca. 50 Mio. Token",
   "es": "aprox. 50 M tokens",
   "fr": "env. 50 M tokens"
  },
  "credits.pack.token.200m": {
   "en": "approx. 200M tokens",
   "de": "ca. 200 Mio. Token",
   "es": "aprox. 200 M tokens",
   "fr": "env. 200 M tokens"
  },
  "credits.pack.all_models": {
   "en": "all models",
   "de": "alle Modelle",
   "es": "todos los modelos",
   "fr": "tous les modèles"
  },
  "credits.pack.prio": {
   "en": "priority queue",
   "de": "Prioritäts-Queue",
   "es": "cola prioritaria",
   "fr": "file prioritaire"
  },
  "credits.pack.top_prio": {
   "en": "highest priority",
   "de": "höchste Priorität",
   "es": "máxima prioridad",
   "fr": "priorité maximale"
  },
  "credits.pack.limits": {
   "en": "own limits",
   "de": "eigene Limits",
   "es": "límites propios",
   "fr": "limites propres"
  },
  "credits.pack.support": {
   "en": "standard support",
   "de": "Standard-Support",
   "es": "soporte estándar",
   "fr": "support standard"
  },
  "credits.pack.mail_support": {
   "en": "email support",
   "de": "E-Mail-Support",
   "es": "soporte por email",
   "fr": "support par e-mail"
  },
  "credits.buy_failed": {
   "en": "Purchase failed:",
   "de": "Kauf fehlgeschlagen:",
   "es": "Compra fallida:",
   "fr": "Achat échoué :"
  },
  "credits.topup.manual": {
   "en": "manual top-up",
   "de": "manuelle Aufladung",
   "es": "recarga manual",
   "fr": "rechargement manuel"
  },
  "credits.topup.saved": {
   "en": "Request saved. The admin will credit the balance.",
   "de": "Anfrage gespeichert. Der Admin schreibt die Credits gut.",
   "es": "Solicitud guardada. El admin abonará los créditos.",
   "fr": "Demande enregistrée. L'admin créditera le solde."
  },
  "nodes.bulk.status": {
   "en": "Toggle status",
   "de": "Status toggeln",
   "es": "Cambiar estado",
   "fr": "Basculer le statut"
  },
  "nodes.bulk.status.busy": {
   "en": "Status… ",
   "de": "Status… ",
   "es": "Estado… ",
   "fr": "Statut… "
  },
  "nodes.bulk.setting": {
   "en": "Setting… ",
   "de": "Setze… ",
   "es": "Aplicando… ",
   "fr": "Application… "
  },
  "nodes.bulk.whitelist_apply": {
   "en": "Apply whitelist",
   "de": "Whitelist anwenden",
   "es": "Aplicar whitelist",
   "fr": "Appliquer la whitelist"
  },
  "nodes.bulk.empty.confirm": {
   "en": "No models selected — sets the whitelist to \"nothing allowed\" for: {names}. Continue?",
   "de": "Keine Modelle ausgewählt — setzt die Whitelist auf \"nichts erlaubt\" für: {names}. Fortfahren?",
   "es": "Ningún modelo seleccionado — pone la whitelist en \"nada permitido\" para: {names}. ¿Continuar?",
   "fr": "Aucun modèle sélectionné — met la whitelist à « rien d'autorisé » pour : {names}. Continuer ?"
  },
  "nodes.none_allowed": {
   "en": "nothing allowed",
   "de": "nichts erlaubt",
   "es": "nada permitido",
   "fr": "rien d'autorisé"
  },
  "nodes.registered": {
   "en": "Node registered",
   "de": "Node registriert",
   "es": "Node registrado",
   "fr": "Node enregistré"
  },
  "nodes.deleted": {
   "en": "Node deleted",
   "de": "Node gelöscht",
   "es": "Node eliminado",
   "fr": "Node supprimé"
  },
  "nodes.whitelist_updated": {
   "en": "Model whitelist updated",
   "de": "Modell-Whitelist aktualisiert",
   "es": "Whitelist de modelos actualizada",
   "fr": "Whitelist de modèles mise à jour"
  },
  "nodes.update_failed": {
   "en": "Update failed:",
   "de": "Update fehlgeschlagen:",
   "es": "Actualización fallida:",
   "fr": "Mise à jour échouée :"
  },
  "nodes.toggle_failed": {
   "en": "Toggle failed:",
   "de": "Statuswechsel fehlgeschlagen:",
   "es": "Cambio de estado fallido:",
   "fr": "Basculement échoué :"
  },
  "profile.role.updated": {
   "en": "Role updated",
   "de": "Rolle aktualisiert",
   "es": "Rol actualizado",
   "fr": "Rôle mis à jour"
  },
  "profile.models.saved": {
   "en": "Model whitelist saved.",
   "de": "Modell-Whitelist gespeichert.",
   "es": "Whitelist de modelos guardada.",
   "fr": "Whitelist de modèles enregistrée."
  },
  "profile.models.updated": {
   "en": "Models updated",
   "de": "Modelle aktualisiert",
   "es": "Modelos actualizados",
   "fr": "Modèles mis à jour"
  },
  "usage.window.24h": {
   "en": "24 h",
   "de": "24 h",
   "es": "24 h",
   "fr": "24 h"
  },
  "usage.window.7d": {
   "en": "7 days",
   "de": "7 Tage",
   "es": "7 días",
   "fr": "7 jours"
  },
  "usage.window.30d": {
   "en": "30 days",
   "de": "30 Tage",
   "es": "30 días",
   "fr": "30 jours"
  },
  "usage.window.all": {
   "en": "Total",
   "de": "Gesamt",
   "es": "Total",
   "fr": "Total"
  },
  "usage.range.all": {
   "en": "the entire period",
   "de": "gesamter Zeitraum",
   "es": "todo el periodo",
   "fr": "toute la période"
  },
  "admin.include_inactive": {
   "en": "incl. inactive",
   "de": "inkl. inaktive",
   "es": "incl. inactivos",
   "fr": "y compris inactifs"
  },
  "admin.only_active": {
   "en": "active only",
   "de": "nur aktive",
   "es": "solo activos",
   "fr": "actifs seulement"
  },
  "admin.with_usage": {
   "en": "with usage in period",
   "de": "mit Verbrauch im Zeitraum",
   "es": "con consumo en el periodo",
   "fr": "avec usage sur la période"
  },
  "common.models": {
   "en": "Models",
   "de": "Modelle",
   "es": "Modelos",
   "fr": "Modèles"
  },
  "chat.choose_model": {
   "en": "Choose a model",
   "de": "Modell wählen",
   "es": "Elegir un modelo",
   "fr": "Choisir un modèle"
  },
  "fmt.range_suffix": {
   "en": " calls",
   "de": " Aufrufe",
   "es": " llamadas",
   "fr": " appels"
  },
  "range.last": {
   "en": "Last ",
   "de": "Letzte ",
   "es": "Últimos ",
   "fr": "Derniers "
  },
  "range.24h": {
   "en": "24 hours",
   "de": "24 Stunden",
   "es": "24 horas",
   "fr": "24 heures"
  },
  "range.7d": {
   "en": "7 days",
   "de": "7 Tage",
   "es": "7 días",
   "fr": "7 jours"
  },
  "range.30d": {
   "en": "30 days",
   "de": "30 Tage",
   "es": "30 días",
   "fr": "30 jours"
  },
  "admin.credits_on": {
   "en": "Credits on",
   "de": "Credits an",
   "es": "Créditos on",
   "fr": "Crédits on"
  },
  "admin.credits_off": {
   "en": "Credits off",
   "de": "Credits aus",
   "es": "Créditos off",
   "fr": "Crédits off"
  },
  "admin.credits_on_hint": {
   "en": "Usage is billed in credits. Accounts without balance cannot call models.",
   "de": "Nutzung wird in Credits abgerechnet. Konten ohne Guthaben können keine Modelle aufrufen.",
   "es": "El uso se factura en créditos. Las cuentas sin saldo no pueden llamar a los modelos.",
   "fr": "L’usage est facturé en crédits. Les comptes sans solde ne peuvent pas appeler de modèles."
  },
  "admin.credits_off_hint": {
   "en": "Credits are not charged; usage is counted in tokens only.",
   "de": "Es werden keine Credits abgerechnet; gezählt werden nur Token.",
   "es": "No se cobran créditos; solo se cuentan los tokens.",
   "fr": "Aucun crédit n’est facturé ; seuls les tokens sont comptés."
  },
  "admin.credits_confirm_on": {
   "en": "Switch the credits system on? Usage will be billed from now on.",
   "de": "Credits-System einschalten? Ab jetzt wird Nutzung abgerechnet.",
   "es": "¿Activar el sistema de créditos? A partir de ahora se facturará el uso.",
   "fr": "Activer le système de crédits ? L’usage sera facturé dès maintenant."
  },
  "admin.credits_confirm_off": {
   "en": "Switch the credits system off? Usage will no longer be billed.",
   "de": "Credits-System ausschalten? Nutzung wird dann nicht mehr abgerechnet.",
   "es": "¿Desactivar el sistema de créditos? El uso ya no se facturará.",
   "fr": "Désactiver le système de crédits ? L’usage ne sera plus facturé."
  },
  "admin.quota.unlimited": {
   "en": "Unlimited",
   "de": "Unbegrenzt",
   "es": "Ilimitado",
   "fr": "Illimité"
  },
  "admin.quota.balance": {
   "en": "Balance",
   "de": "Guthaben",
   "es": "Saldo",
   "fr": "Solde"
  },
  "admin.quota.blocked": {
   "en": "Blocked",
   "de": "Gesperrt",
   "es": "Bloqueado",
   "fr": "Bloqué"
  },
  "admin.quota.change_hint": {
   "en": "Click to switch the quota: unlimited → balance → blocked.",
   "de": "Klicken schaltet die Quota weiter: unbegrenzt → Guthaben → gesperrt.",
   "es": "Haz clic para cambiar la cuota: ilimitado → saldo → bloqueado.",
   "fr": "Cliquer fait passer la quota : illimité → solde → bloqué."
  },
  "fmt.range_now": {
   "en": "{since} – now",
   "de": "{since} – jetzt",
   "es": "{since} – ahora",
   "fr": "{since} – maintenant"
  },
  "unit.users_limit": {
   "en": "users (limit {limit})",
   "de": "Nutzern (Limit {limit})",
   "es": "usuarios (límite {limit})",
   "fr": "utilisateurs (limite {limit})"
  },
  "unit.users": {
   "en": "{shown} users",
   "de": "{shown} Nutzer",
   "es": "{shown} usuarios",
   "fr": "{shown} utilisateurs"
  },
  "fmt.plus_more": {
   "en": " +{n}",
   "de": " +{n}",
   "es": " +{n}",
   "fr": " +{n}"
  },
  "err.generic": {
   "en": "Error: ",
   "de": "Fehler: ",
   "es": "Error: ",
   "fr": "Erreur : "
  },
  "err.load_prefix": {
   "en": "Loading failed: ",
   "de": "Laden fehlgeschlagen: ",
   "es": "Error al cargar: ",
   "fr": "Échec du chargement : "
  },
  "nodes.bulk.status_ok": {
   "en": "Status: {ok}/{n} ok",
   "de": "Status: {ok}/{n} ok",
   "es": "Estado: {ok}/{n} ok",
   "fr": "Statut : {ok}/{n} ok"
  },
  "nodes.bulk.toggled": {
   "en": "{n} node(s) switched ({on} on, {off} paused)",
   "de": "{n} Node(s) umgeschaltet ({on} an, {off} pausiert)",
   "es": "{n} node(s) cambiados ({on} activos, {off} pausados)",
   "fr": "{n} node(s) basculés ({on} actifs, {off} en pause)"
  },
  "nodes.bulk.whitelist_ok": {
   "en": "Whitelist: {ok}/{n} ok",
   "de": "Whitelist: {ok}/{n} ok",
   "es": "Whitelist: {ok}/{n} ok",
   "fr": "Whitelist : {ok}/{n} ok"
  },
  "nodes.bulk.whitelist_result": {
   "en": "{n} node(s): whitelist = {label}",
   "de": "{n} Node(s): Whitelist = {label}",
   "es": "{n} node(s): whitelist = {label}",
   "fr": "{n} node(s) : whitelist = {label}"
  },
  "nodes.registered_hint": {
   "en": "Node #{id} registered. Agent key (copy now!):",
   "de": "Node #{id} registriert. Agent-Key (jetzt kopieren!):",
   "es": "Node #{id} registrado. Agent key (¡cópiala ahora!):",
   "fr": "Node #{id} enregistré. Agent key (à copier maintenant !) :"
  },
  "nodes.delete_confirm": {
   "en": "Really delete node #{id} ({name})?",
   "de": "Node #{id} ({name}) wirklich löschen?",
   "es": "¿Eliminar realmente el node #{id} ({name})?",
   "fr": "Vraiment supprimer le node #{id} ({name}) ?"
  },
  "profile.role_set": {
   "en": "Role set to '{role}'.",
   "de": "Rolle auf '{role}' gesetzt.",
   "es": "Rol establecido en '{role}'.",
   "fr": "Rôle défini sur « {role} »."
  },
  "unit.models_count": {
   "en": "{n} model(s)",
   "de": "{n} Modell(e)",
   "es": "{n} modelo(s)",
   "fr": "{n} modèle(s)"
  },
  "agent.comment_hint": {
   "en": "# Register the node first at /nodes.html",
   "de": "# Erst Node registrieren auf /nodes.html",
   "es": "# Primero registra el node en /nodes.html",
   "fr": "# Enregistrez d'abord le node sur /nodes.html"
  },
  "node.contribute.eyebrow": {
   "en": "Contribute",
   "de": "Beitragen",
   "es": "Aportar",
   "fr": "Contribuer"
  },
  "node.contribute.title": {
   "en": "Contribute your own node",
   "de": "Eigene Node beitragen",
   "es": "Aporta tu propio node",
   "fr": "Contribuer votre propre node"
  },
  "node.contribute.lede": {
   "en": "One command on your own machine is enough: the agent downloads itself, asks for the account key and registers the node with the pool. No repository, no Python, no prior registration.",
   "de": "Ein Befehl auf der eigenen Maschine genügt: der Agent lädt sich selbst, fragt den Account-Schlüssel ab und meldet die Node im Pool an. Kein Repository, kein Python, keine Registrierung im Voraus.",
   "es": "Basta con un comando en tu propia máquina: el agente se descarga solo, pide la account key y registra el node en el pool. Sin repositorio, sin Python y sin registro previo.",
   "fr": "Une seule commande sur votre propre machine suffit : l’agent se télécharge lui-même, demande l’account key et enregistre le node dans le pool. Pas de dépôt, pas de Python, pas d’inscription préalable."
  },
  "node.contribute.addr.choose": {
   "en": "Address in the command",
   "de": "Adresse im Befehl",
   "es": "Dirección en el comando",
   "fr": "Adresse dans la commande"
  },
  "node.contribute.addr.current": {
   "en": "This address",
   "de": "Diese Adresse",
   "es": "Esta dirección",
   "fr": "Cette adresse"
  },
  "node.contribute.addr.public": {
   "en": "Public address",
   "de": "Öffentliche Adresse",
   "es": "Dirección pública",
   "fr": "Adresse publique"
  },
  "node.contribute.cmd.unix": {
   "en": "Linux and macOS",
   "de": "Linux und macOS",
   "es": "Linux y macOS",
   "fr": "Linux et macOS"
  },
  "node.contribute.cmd.unix.hint": {
   "en": "Paste into a terminal and run. Needs nothing but curl and a SHA-256 tool.",
   "de": "In ein Terminal einfügen und ausführen. Braucht nur curl und ein SHA-256-Werkzeug.",
   "es": "Pega en un terminal y ejecuta. Solo necesita curl y una herramienta SHA-256.",
   "fr": "À coller dans un terminal et exécuter. Ne nécessite que curl et un outil SHA-256."
  },
  "node.contribute.cmd.windows": {
   "en": "Windows",
   "de": "Windows",
   "es": "Windows",
   "fr": "Windows"
  },
  "node.contribute.cmd.windows.hint": {
   "en": "Paste into PowerShell and run — not into the command prompt.",
   "de": "In PowerShell einfügen und ausführen — nicht in der Eingabeaufforderung.",
   "es": "Pega en PowerShell y ejecuta — no en el símbolo del sistema.",
   "fr": "À coller dans PowerShell et exécuter — pas dans l’invite de commandes."
  },
  "node.contribute.downloads.title": {
   "en": "Downloads",
   "de": "Downloads",
   "es": "Descargas",
   "fr": "Téléchargements"
  },
  "node.contribute.downloads.hint": {
   "en": "Every binary ships with a <code class=\"inline\">.sha256</code> file next to it. The installers check it before anything is installed — without a matching checksum the installation stops. Size and checksum shown here are read from the file that is actually being served, not from a list.",
   "de": "Zu jedem Binary liegt eine <code class=\"inline\">.sha256</code>-Datei. Die Installer prüfen sie, bevor etwas installiert wird — ohne passende Prüfsumme bricht die Installation ab. Größe und Prüfsumme hier werden aus der tatsächlich ausgelieferten Datei gelesen, nicht aus einer Liste.",
   "es": "Cada binary lleva junto un archivo <code class=\"inline\">.sha256</code>. Los instaladores lo comprueban antes de instalar nada — sin una suma coincidente la instalación se detiene. El tamaño y la suma que aparecen aquí se leen del archivo que realmente se sirve, no de una lista.",
   "fr": "Chaque binary est accompagné d’un fichier <code class=\"inline\">.sha256</code>. Les installateurs le vérifient avant toute installation — sans somme correspondante, l’installation s’arrête. La taille et la somme affichées ici sont lues dans le fichier réellement servi, pas dans une liste."
  },
  "node.contribute.col.file": {
   "en": "File",
   "de": "Datei",
   "es": "Archivo",
   "fr": "Fichier"
  },
  "node.contribute.col.size": {
   "en": "Size",
   "de": "Größe",
   "es": "Tamaño",
   "fr": "Taille"
  },
  "node.contribute.col.sha": {
   "en": "SHA-256",
   "de": "SHA-256",
   "es": "SHA-256",
   "fr": "SHA-256"
  },
  "node.contribute.key.title": {
   "en": "Account key",
   "de": "Account-Schlüssel",
   "es": "Account key",
   "fr": "Account key"
  },
  "node.contribute.key.body": {
   "en": "The installer writes it to the configuration as <code class=\"inline\">PORTAL_USER_KEY</code>. It is the API key of your account — the same one this portal signs you in with. It is shown in full once, when it is issued; in the <a href=\"profile.html#schluessel\" class=\"link\">account settings</a> you see prefix and date and can create a new one with your password at any time. A new key invalidates the previous one.",
   "de": "Der Installer schreibt ihn als <code class=\"inline\">PORTAL_USER_KEY</code> in die Konfiguration. Das ist der API-Schlüssel deines Kontos — derselbe, mit dem dich dieses Portal anmeldet. Er wird beim Ausstellen einmalig vollständig angezeigt; in den <a href=\"profile.html#schluessel\" class=\"link\">Kontoeinstellungen</a> siehst du Präfix und Datum und erzeugst mit deinem Passwort jederzeit einen neuen. Ein neuer Schlüssel macht den bisherigen ungültig.",
   "es": "El instalador lo escribe en la configuración como <code class=\"inline\">PORTAL_USER_KEY</code>. Es la API key de tu cuenta — la misma con la que este portal te autentica. Se muestra completa una sola vez, al emitirla; en los <a href=\"profile.html#schluessel\" class=\"link\">ajustes de cuenta</a> ves el prefijo y la fecha y puedes crear una nueva con tu contraseña cuando quieras. Una clave nueva invalida la anterior.",
   "fr": "L’installateur l’écrit dans la configuration sous <code class=\"inline\">PORTAL_USER_KEY</code>. C’est l’API key de votre compte — celle avec laquelle ce portail vous authentifie. Elle n’est affichée en entier qu’une seule fois, à son émission ; dans les <a href=\"profile.html#schluessel\" class=\"link\">paramètres du compte</a> vous voyez le préfixe et la date et pouvez en créer une nouvelle avec votre mot de passe à tout moment. Une nouvelle clé invalide la précédente."
  },
  "node.contribute.after.title": {
   "en": "What happens next",
   "de": "Was danach passiert",
   "es": "Qué pasa después",
   "fr": "Ce qui se passe ensuite"
  },
  "node.contribute.after.1": {
   "en": "The node appears in the list above — no registration in advance, the agent signs in with the account key itself.",
   "de": "Die Node erscheint in der Liste oben — ohne Registrierung im Voraus, der Agent meldet sich mit dem Account-Schlüssel selbst an.",
   "es": "El node aparece en la lista de arriba — sin registro previo, el agente se autentica con la account key.",
   "fr": "Le node apparaît dans la liste ci-dessus — sans inscription préalable, l’agent s’authentifie avec l’account key."
  },
  "node.contribute.after.2": {
   "en": "The connection runs outbound over WebSocket. No port has to be opened, no address released in the router.",
   "de": "Die Verbindung läuft ausgehend über WebSocket. Es muss kein Port geöffnet und keine Adresse im Router freigegeben werden.",
   "es": "La conexión sale por WebSocket. No hay que abrir ningún puerto ni liberar ninguna dirección en el router.",
   "fr": "La connexion sort en WebSocket. Aucun port à ouvrir, aucune adresse à libérer dans le routeur."
  },
  "node.contribute.after.3": {
   "en": "The agent runs as a service (systemd --user on Linux, launchd on macOS) and comes back after a reboot. No sudo.",
   "de": "Der Agent läuft als Dienst (systemd --user unter Linux, launchd unter macOS) und ist nach einem Neustart wieder da. Kein sudo.",
   "es": "El agente corre como servicio (systemd --user en Linux, launchd en macOS) y vuelve tras un reinicio. Sin sudo.",
   "fr": "L’agent tourne comme service (systemd --user sous Linux, launchd sous macOS) et revient après un redémarrage. Sans sudo."
  },
  "node.contribute.after.4": {
   "en": "Without a detected NVIDIA GPU the installer asks for the VRAM and writes <code class=\"inline\">NODE_VRAM_GB</code> to the configuration. Without that value the pool sends no job to this node.",
   "de": "Ohne erkannte NVIDIA-GPU fragt der Installer nach dem VRAM und schreibt <code class=\"inline\">NODE_VRAM_GB</code> in die Konfiguration. Fehlt der Wert, schickt der Pool dieser Node keinen Auftrag.",
   "es": "Sin una GPU NVIDIA detectada, el instalador pregunta por la VRAM y escribe <code class=\"inline\">NODE_VRAM_GB</code> en la configuración. Sin ese valor el pool no envía ningún trabajo a este node.",
   "fr": "Sans GPU NVIDIA détectée, l’installateur demande la VRAM et écrit <code class=\"inline\">NODE_VRAM_GB</code> dans la configuration. Sans cette valeur, le pool n’envoie aucune tâche à ce node."
  },
  "node.contribute.limits.title": {
   "en": "Not available",
   "de": "Nicht verfügbar",
   "es": "No disponible",
   "fr": "Non disponible"
  },
  "node.contribute.limits.body": {
   "en": "There is no <code class=\"inline\">darwin-x86_64</code> (Intel Mac) and no <code class=\"inline\">linux-arm64</code>: neither is built today. On such a machine the installer stops with a message about the architecture instead of setting up something wrong.",
   "de": "Es gibt kein <code class=\"inline\">darwin-x86_64</code> (Intel-Mac) und kein <code class=\"inline\">linux-arm64</code>: beides wird derzeit nicht gebaut. Auf so einem Rechner bricht der Installer mit einer Meldung zur Architektur ab, statt etwas Falsches einzurichten.",
   "es": "No hay <code class=\"inline\">darwin-x86_64</code> (Mac Intel) ni <code class=\"inline\">linux-arm64</code>: ninguno de los dos se compila actualmente. En una máquina así el instalador se detiene con un mensaje sobre la arquitectura, en lugar de configurar algo incorrecto.",
   "fr": "Il n’y a pas de <code class=\"inline\">darwin-x86_64</code> (Mac Intel) ni de <code class=\"inline\">linux-arm64</code> : aucun des deux n’est compilé actuellement. Sur une telle machine, l’installateur s’arrête avec un message sur l’architecture au lieu de configurer quelque chose de faux."
  },
  "node.contribute.copy": {
   "en": "Copy",
   "de": "Kopieren",
   "es": "Copiar",
   "fr": "Copier"
  },
  "node.contribute.copied": {
   "en": "Copied",
   "de": "Kopiert",
   "es": "Copiado",
   "fr": "Copié"
  },
  "node.contribute.copy_failed": {
   "en": "Copy failed — select the text and copy it by hand",
   "de": "Kopieren nicht möglich — bitte markieren und von Hand kopieren",
   "es": "No se pudo copiar — selecciona el texto y cópialo a mano",
   "fr": "Copie impossible — sélectionnez le texte et copiez-le à la main"
  },
  "node.contribute.download": {
   "en": "Download",
   "de": "Laden",
   "es": "Descargar",
   "fr": "Télécharger"
  },
  "node.contribute.pending": {
   "en": "checking…",
   "de": "wird ermittelt…",
   "es": "comprobando…",
   "fr": "vérification…"
  },
  "node.contribute.unavailable": {
   "en": "unavailable",
   "de": "nicht ermittelbar",
   "es": "no disponible",
   "fr": "indisponible"
  },
  "node.contribute.no_checksum": {
   "en": "no checksum file",
   "de": "keine Prüfsummendatei",
   "es": "sin archivo de suma",
   "fr": "pas de fichier de somme"
  }
 }
};
