# LANA-63 — catalog part 2: page strings.
# Keys are the ones emitted by extract.py (slug of the German source), so the
# data-i18n attributes in the markup map 1:1 onto this table.
#
# Untranslated on purpose in every locale (Fachbegriffe, product rule):
# Node, Token, Model/Modell, Credits, API-Key, Pool, Provider, Consumer, Owner,
# Treasury, VRAM, Tailscale, Docker, Ollama, OpenAI, JSON, Admin, Dashboard,
# Usage, Earnings, Agent, Profil.

KEYS = {
    "konto-api-zugang-und-die-letzten-aufrufe": {"en": "Account, API access and recent calls at a glance.", "de": "Konto, API-Zugang und die letzten Aufrufe auf einen Blick.", "es": "Cuenta, acceso a la API y las últimas llamadas de un vistazo.", "fr": "Compte, accès API et derniers appels en un coup d'œil."},
    "noch-kein-konto-a-href-register-html-class": {"en": "No account yet? <a href=\"register.html\" class=\"link\">Register</a>.", "de": "Noch kein Konto? <a href=\"register.html\" class=\"link\">Registrieren</a>.", "es": "¿Aún sin cuenta? <a href=\"register.html\" class=\"link\">Registrarse</a>.", "fr": "Pas encore de compte ? <a href=\"register.html\" class=\"link\">S'inscrire</a>."},
    "konto-anlegen-und-mitmachen": {"en": "Create an account and join in.", "de": "Konto anlegen und mitmachen.", "es": "Crea una cuenta y participa.", "fr": "Créez un compte et participez."},
    "b-eigene-hardware-einbringen-b-der-node": {"en": "<b>Bring your own hardware.</b> The node agent runs as a container and announces the GPU to the pool.", "de": "<b>Eigene Hardware einbringen.</b> Der Node-Agent läuft als Container und meldet die GPU an den Pool.", "es": "<b>Aporta tu propio hardware.</b> El agente de node se ejecuta como contenedor y anuncia la GPU al pool.", "fr": "<b>Apportez votre matériel.</b> L'agent de node tourne en conteneur et annonce le GPU au pool."},
    "login.intro": {"en": "One pool of machines with a free GPU, one OpenAI-compatible entry point. Free, carried by the community — no subscription, no per-token billing.", "de": "Ein Pool aus Rechnern mit freier GPU, ein einziger OpenAI-kompatibler Zugang. Kostenlos, getragen von der Community — kein Abo, keine Abrechnung pro Token.", "es": "Un pool de máquinas con GPU libre, un único acceso compatible con OpenAI. Gratis y sostenido por la comunidad: sin suscripción ni facturación por Token.", "fr": "Un pool de machines avec un GPU libre, un seul accès compatible OpenAI. Gratuit et porté par la communauté — sans abonnement, sans facturation par Token."},
    "login.no_account": {
        "en": 'No account yet? <a href="register.html" class="link">Register</a>.',
        "de": 'Noch kein Konto? <a href="register.html" class="link">Registrieren</a>.',
        "es": '¿Aún sin cuenta? <a href="register.html" class="link">Registrarse</a>.',
        "fr": 'Pas encore de compte ? <a href="register.html" class="link">S\'inscrire</a>.',
    },
    "login.point.api": {
        "en": '<b>OpenAI-compatible API.</b> Existing clients and SDKs work without changes.',
        "de": '<b>OpenAI-kompatible API.</b> Bestehende Clients und SDKs funktionieren ohne Anpassung.',
        "es": '<b>API compatible con OpenAI.</b> Los clientes y SDK existentes funcionan sin cambios.',
        "fr": '<b>API compatible OpenAI.</b> Les clients et SDK existants fonctionnent sans modification.',
    },
    "login.point.hardware": {
        "en": '<b>Bring your own hardware.</b> The Node agent runs as a container and reports the GPU to the Pool.',
        "de": '<b>Eigene Hardware einbringen.</b> Der Node-Agent läuft als Container und meldet die GPU an den Pool.',
        "es": '<b>Aporta tu propio hardware.</b> El agente Node se ejecuta como contenedor y anuncia la GPU al Pool.',
        "fr": "<b>Apportez votre matériel.</b> L'agent Node tourne en conteneur et annonce le GPU au Pool.",
    },
    "login.point.models": {
        "en": '<b>Models stay under control.</b> Whitelist per Node and per account, cloud models unlocked explicitly.',
        "de": '<b>Modelle bleiben kontrollierbar.</b> Pro Node und pro Konto als Whitelist steuerbar, Cloud-Modelle explizit freizuschalten.',
        "es": '<b>Los Model siguen controlables.</b> Lista blanca por Node y por cuenta, Model en la nube se habilitan explícitamente.',
        "fr": '<b>Les Model restent contrôlables.</b> Liste blanche par Node et par compte, Model cloud débloqués explicitement.',
    },
    "register.role.consumer": {
        "en": '<b>Consumer.</b> Use the API, provide no hardware. For machines without a usable GPU.',
        "de": '<b>Consumer.</b> API nutzen, keine Hardware bereitstellen. Für Rechner ohne nutzbare GPU.',
        "es": '<b>Consumer.</b> Usar la API, sin aportar hardware. Para equipos sin GPU utilizable.',
        "fr": "<b>Consumer.</b> Utiliser l'API, sans fournir de matériel. Pour les machines sans GPU utilisable.",
    },
    "register.role.provider": {
        "en": '<b>Provider.</b> Register Nodes and earn Credits, no own API calls.',
        "de": '<b>Provider.</b> Nodes registrieren und Credits verdienen, keine eigenen API-Calls.',
        "es": '<b>Provider.</b> Registrar Nodes y ganar Credits, sin llamadas propias a la API.',
        "fr": '<b>Provider.</b> Enregistrer des Nodes et gagner des Credits, sans appels API propres.',
    },
    "register.role.both": {
        "en": '<b>Both.</b> Full access — contribute and use at the same time.',
        "de": '<b>Beides.</b> Voller Zugriff — Einbringen und Nutzen gleichzeitig.',
        "es": '<b>Ambos.</b> Acceso completo: aportar y usar a la vez.',
        "fr": '<b>Les deux.</b> Accès complet — apporter et utiliser en même temps.',
    },
    "register.models_limited": {
        "en": 'Limit the models',
        "de": 'Modelle einschränken',
        "es": 'Limitar los Model',
        "fr": 'Limiter les Model',
    },
    "register.models_optional": {
        "en": 'optional — empty means: all local models, no cloud',
        "de": 'optional — leer bedeutet: alle lokalen Modelle, keine Cloud',
        "es": 'opcional — vacío significa: todos los Model locales, sin nube',
        "fr": 'facultatif — vide signifie : tous les Model locaux, sans cloud',
    },
    "register.role_hint": {
        "en": 'Can be changed any time later in the <a href="profile.html" class="link">profile</a>.',
        "de": 'Später im <a href="profile.html" class="link">Profil</a> jederzeit änderbar.',
        "es": 'Se puede cambiar en cualquier momento en el <a href="profile.html" class="link">perfil</a>.',
        "fr": 'Modifiable à tout moment dans le <a href="profile.html" class="link">profil</a>.',
    },
    "login.foot.openai": {
        "en": 'OpenAI-compatible API',
        "de": 'OpenAI-kompatible API',
        "es": 'API compatible con OpenAI',
        "fr": 'API compatible OpenAI',
    },
    "api_key_no_bearer": {
        'en': '— in config files and SDKs only the key, without "Bearer".',
        'de': '— in Konfigurationsdateien und SDKs nur der Schlüssel, ohne „Bearer".',
        'es': '— en archivos de configuración y SDKs solo la clave, sin "Bearer".',
        'fr': '— dans les fichiers de configuration et SDK, seulement la clé, sans « Bearer ».',
    },
    "login.tagline": {"en": "Contribute GPUs to the pool, use the whole pool through one OpenAI-compatible API — free and powered by your community.", "de": "Stelle GPUs für den Pool bereit und nutze den ganzen Pool über eine einzige OpenAI-kompatible API — kostenlos und von deiner Community getragen.", "es": "Aporta GPUs al pool y usa todo el pool a través de una única API compatible con OpenAI: gratis y sostenido por tu comunidad.", "fr": "Apportez des GPU au pool et utilisez tout le pool via une seule API compatible OpenAI — gratuit et porté par votre communauté."},
    # =========================================================== login.html

    "rechner-mit-freier-gpu-stellen-ihre": {
        "en": "Machines with a free GPU offer their capacity, others use it through an OpenAI-compatible API. Billing runs on Credits — per Token, not per subscription.",
        "de": "Rechner mit freier GPU stellen ihre Leistung bereit, andere nutzen sie über eine OpenAI-kompatible API. Abrechnung läuft über Credits — pro Token, nicht pro Abo.",
        "es": "Las máquinas con GPU libre ofrecen su capacidad y otras la usan a través de una API compatible con OpenAI. La facturación va por Credits — por Token, no por suscripción.",
        "fr": "Les machines disposant d'un GPU libre mettent leur puissance à disposition, d'autres l'utilisent via une API compatible OpenAI. La facturation se fait en Credits — par Token, sans abonnement.",
        },
    "b-openai-kompatible-api-b-bestehende": {
        "en": "<b>OpenAI-compatible API.</b> Existing clients and SDKs work without changes.",
        "de": "<b>OpenAI-kompatible API.</b> Bestehende Clients und SDKs funktionieren ohne Anpassung.",
        "es": "<b>API compatible con OpenAI.</b> Los clientes y SDK existentes funcionan sin cambios.",
        "fr": "<b>API compatible OpenAI.</b> Les clients et SDK existants fonctionnent sans modification.",
        },
    "b-eigene-hardware-einbringen-b-der-node": {
        "en": "<b>Bring your own hardware.</b> The node agent runs as a container, 70 % of job cost goes to the owner.",
        "de": "<b>Eigene Hardware einbringen.</b> Der Node-Agent läuft als Container, 70 % der Job-Kosten gehen an den Owner.",
        "es": "<b>Aporta tu propio hardware.</b> El agente de node se ejecuta como contenedor; el 70 % del coste del job va al owner.",
        "fr": "<b>Apportez votre matériel.</b> L'agent de node tourne en conteneur ; 70 % du coût du job revient à l'owner.",
        },
    "b-modelle-bleiben-kontrollierbar-b-pro-node": {
        "en": "<b>Models stay under control.</b> Allow-listed per node and per account; cloud models are opted into explicitly.",
        "de": "<b>Modelle bleiben kontrollierbar.</b> Pro Node und pro Konto als Whitelist steuerbar, Cloud-Modelle explizit freizuschalten.",
        "es": "<b>Los modelos siguen bajo control.</b> Lista blanca por node y por cuenta; los modelos cloud se habilitan explícitamente.",
        "fr": "<b>Les modèles restent contrôlables.</b> Liste blanche par node et par compte ; les modèles cloud s'activent explicitement.",
        },
    "melde-dich-an-um-credits-nodes-und-api-keys": {
        "en": "Sign in to manage Credits, Nodes and API keys.",
        "de": "Melde dich an, um Credits, Nodes und API-Keys zu verwalten.",
        "es": "Inicia sesión para gestionar Credits, Nodes y API keys.",
        "fr": "Connectez-vous pour gérer Credits, Nodes et clés API.",
        },
    "name-beispiel-de": {
        "en": "name@example.com", "de": "name@beispiel.de",
        "es": "nombre@ejemplo.es", "fr": "nom@exemple.fr"},
    "anmeldung-laeuft": {
        "en": "Signing in…", "de": "Anmeldung läuft…", "es": "Iniciando sesión…",
        "fr": "Connexion…"},
    "noch-kein-konto-a-href-register-html-class": {
        "en": "No account yet? <a href=\"register.html\" class=\"link\">Register</a> — 100 Credits to start.",
        "de": "Noch kein Konto? <a href=\"register.html\" class=\"link\">Registrieren</a> — 100 Credits zum Start.",
        "es": "¿Aún sin cuenta? <a href=\"register.html\" class=\"link\">Registrarse</a> — 100 Credits de inicio.",
        "fr": "Pas encore de compte ? <a href=\"register.html\" class=\"link\">S'inscrire</a> — 100 Credits pour commencer.",
        },
    "anmelden": {"en": "Sign in", "de": "Anmelden", "es": "Iniciar sesión", "fr": "Connexion"},
    "e-mail": {"en": "E-mail", "de": "E-Mail", "es": "Correo electrónico", "fr": "E-mail"},
    "passwort": {"en": "Password", "de": "Passwort", "es": "Contraseña", "fr": "Mot de passe"},

    # ========================================================= register.html

    "ein-konto-deckt-beides-ab-die-api-nutzen": {
        "en": "One account covers both: using the API and contributing your own GPUs. The role decides what is unlocked — changeable in the profile at any time.",
        "de": "Ein Konto deckt beides ab: die API nutzen und eigene GPUs bereitstellen. Die Rolle legt fest, was freigeschaltet wird — im Profil jederzeit änderbar.",
        "es": "Una cuenta cubre ambas cosas: usar la API y aportar tus propias GPUs. El rol define qué se habilita — modificable en el perfil.",
        "fr": "Un seul compte couvre les deux : utiliser l'API et fournir vos propres GPU. Le rôle détermine ce qui est débloqué — modifiable dans le profil.",
        },
    "b-consumer-b-api-nutzen-keine-hardware": {
        "en": "<b>Consumer.</b> Use the API, contribute no hardware. For machines without a usable GPU.",
        "de": "<b>Consumer.</b> API nutzen, keine Hardware bereitstellen. Für Rechner ohne nutzbare GPU.",
        "es": "<b>Consumer.</b> Usar la API sin aportar hardware. Para equipos sin GPU utilizable.",
        "fr": "<b>Consumer.</b> Utiliser l'API sans fournir de matériel. Pour les machines sans GPU exploitable.",
        },
    "b-provider-b-nodes-registrieren-und-credits": {
        "en": "<b>Provider.</b> Register nodes and earn Credits, no API calls of your own.",
        "de": "<b>Provider.</b> Nodes registrieren und Credits verdienen, keine eigenen API-Calls.",
        "es": "<b>Provider.</b> Registrar nodes y ganar Credits, sin llamadas API propias.",
        "fr": "<b>Provider.</b> Enregistrer des nodes et gagner des Credits, sans appels API propres.",
        },
    "b-beides-b-voller-zugriff-einbringen-und": {
        "en": "<b>Both.</b> Full access — contributing and consuming at the same time.",
        "de": "<b>Beides.</b> Voller Zugriff — Einbringen und Nutzen gleichzeitig.",
        "es": "<b>Ambos.</b> Acceso completo — aportar y consumir a la vez.",
        "fr": "<b>Les deux.</b> Accès complet — apporter et consommer en même temps.",
        },
    "neues-konto": {"en": "New account", "de": "Neues Konto", "es": "Cuenta nueva", "fr": "Nouveau compte"},
    "registrieren": {"en": "Register", "de": "Registrieren", "es": "Registrarse", "fr": "S'inscrire"},
    "name": {"en": "Name", "de": "Name", "es": "Nombre", "fr": "Nom"},
    "vor-und-nachname": {"en": "First and last name", "de": "Vor- und Nachname", "es": "Nombre y apellidos", "fr": "Prénom et nom"},
    "mindestens-6-zeichen": {"en": "at least 6 characters", "de": "mindestens 6 Zeichen", "es": "mínimo 6 caracteres", "fr": "au moins 6 caractères"},
    "eigene-gpus-teilen-keine-api-calls": {"en": "Share your own GPUs, no API calls.", "de": "Eigene GPUs teilen, keine API-Calls.", "es": "Compartir tus propias GPUs, sin llamadas API.", "fr": "Partager vos GPU, aucun appel API."},
    "gpus-teilen-und-api-nutzen-standard": {"en": "Share GPUs and use the API — default.", "de": "GPUs teilen und API nutzen — Standard.", "es": "Compartir GPUs y usar la API — por defecto.", "fr": "Partager des GPU et utiliser l'API — par défaut."},
    "modelle-einschraenken-span-class-hint": {
        "en": "Limit models <span class=\"hint\">optional — empty means: all local models, no cloud</span>",
        "de": "Modelle einschränken <span class=\"hint\">optional — leer bedeutet: alle lokalen Modelle, keine Cloud</span>",
        "es": "Limitar modelos <span class=\"hint\">opcional — vacío significa: todos los modelos locales, sin cloud</span>",
        "fr": "Limiter les modèles <span class=\"hint\">optionnel — vide signifie : tous les modèles locaux, pas de cloud</span>",
        },
    "spaeter-im-a-href-profile-html-class-link": {
        "en": "Changeable any time later in the <a href=\"profile.html\" class=\"link\">profile</a>.",
        "de": "Später im <a href=\"profile.html\" class=\"link\">Profil</a> jederzeit änderbar.",
        "es": "Modificable en cualquier momento en el <a href=\"profile.html\" class=\"link\">perfil</a>.",
        "fr": "Modifiable à tout moment dans le <a href=\"profile.html\" class=\"link\">profil</a>.",
        },
    "konto-anlegen": {"en": "Create account", "de": "Konto anlegen", "es": "Crear cuenta", "fr": "Créer le compte"},
    "wird-angelegt": {"en": "Creating…", "de": "Wird angelegt…", "es": "Creando…", "fr": "Création…"},
    "schon-registriert-a-href-login-html-class": {
        "en": "Already registered? <a href=\"login.html\" class=\"link\">Sign in</a>",
        "de": "Schon registriert? <a href=\"login.html\" class=\"link\">Anmelden</a>",
        "es": "¿Ya registrado? <a href=\"login.html\" class=\"link\">Iniciar sesión</a>",
        "fr": "Déjà inscrit ? <a href=\"login.html\" class=\"link\">Connexion</a>",
        },

    # ============================================================ index.html
    "api-key-jetzt-sichern": {"en": "Secure the API key now", "de": "API-Key jetzt sichern", "es": "Guarda ahora la API key", "fr": "Sécurisez la clé API maintenant"},
    "dieser-schluessel-wird-nur-einmal": {"en": "This key is shown in full only once. It is the only way to reach the API.", "de": "Dieser Schlüssel wird nur einmal vollständig angezeigt. Er ist die einzige Zugangsmöglichkeit zur API.", "es": "Esta clave solo se muestra completa una vez. Es el único acceso a la API.", "fr": "Cette clé n'est affichée en entier qu'une seule fois. C'est le seul accès à l'API."},
    "habe-ich-gesichert": {"en": "I saved it", "de": "Habe ich gesichert", "es": "La he guardado", "fr": "Je l'ai sauvegardée"},
    "uebersicht": {"en": "Overview", "de": "Übersicht", "es": "Resumen", "fr": "Aperçu"},

    "credit-guthaben": {"en": "Credit balance", "de": "Credit-Guthaben", "es": "Saldo de Credits", "fr": "Solde de Credits"},
    "entspricht-ca-span-x-text-fmtnumber-math": {
        "en": "roughly <span x-text=\"fmtNumber(Math.floor((me?.credits || 0) * 1000))\"></span> Token",
        "de": "entspricht ca. <span x-text=\"fmtNumber(Math.floor((me?.credits || 0) * 1000))\"></span> Token",
        "es": "equivale a unos <span x-text=\"fmtNumber(Math.floor((me?.credits || 0) * 1000))\"></span> Token",
        "fr": "correspond à environ <span x-text=\"fmtNumber(Math.floor((me?.credits || 0) * 1000))\"></span> Token",
        },
    "chat-oeffnen": {"en": "Open chat", "de": "Chat öffnen", "es": "Abrir chat", "fr": "Ouvrir le chat"},
    "registriert": {"en": "Registered", "de": "Registriert", "es": "Registrado", "fr": "Inscrit"},
    "verbrauch": {"en": "Consumption", "de": "Verbrauch", "es": "Consumo", "fr": "Consommation"},
    "pro-tag-verbrauchte-token": {"en": "Token consumed per day.", "de": "Pro Tag verbrauchte Token.", "es": "Token consumidos por día.", "fr": "Token consommés par jour."},
    "kennzahlen": {"en": "Metrics", "de": "Kennzahlen", "es": "Métricas", "fr": "Indicateurs"},
    "api-aufrufe": {"en": "API calls", "de": "API-Aufrufe", "es": "Llamadas API", "fr": "Appels API"},
    "token-verbraucht": {"en": "Token consumed", "de": "Token verbraucht", "es": "Token consumidos", "fr": "Token consommés"},
    "details-und-zeitraum-umschalter-im": {
        "en": "— details and period switcher in the",
        "de": "— Details und Zeitraum-Umschalter im",
        "es": "— detalles y selector de periodo en",
        "fr": "— détails et sélecteur de période dans",
        },
    "zugang": {"en": "Access", "de": "Zugang", "es": "Acceso", "fr": "Accès"},
    "neu-ausstellen": {"en": "Issue new", "de": "Neu ausstellen", "es": "Emitir nueva", "fr": "Émettre une nouvelle"},
    "anzeigen": {"en": "Show", "de": "Anzeigen", "es": "Mostrar", "fr": "Afficher"},
    "verbergen": {"en": "Hide", "de": "Verbergen", "es": "Ocultar", "fr": "Masquer"},
    "kopieren": {"en": "Copy", "de": "Kopieren", "es": "Copiar", "fr": "Copier"},
    "protokoll": {"en": "Log", "de": "Protokoll", "es": "Registro", "fr": "Journal"},
    "letzte-api-aufrufe": {"en": "Recent API calls", "de": "Letzte API-Aufrufe", "es": "Últimas llamadas API", "fr": "Derniers appels API"},
    "noch-keine-aufrufe-der-chat-ist-der": {"en": "No calls yet. The chat is the fastest route to a first request.", "de": "Noch keine Aufrufe. Der Chat ist der schnellste Weg zum ersten Request.", "es": "Aún sin llamadas. El chat es la vía más rápida a la primera solicitud.", "fr": "Aucun appel pour l'instant. Le chat est le chemin le plus rapide vers une première requête."},
    "oder-direkt-per-curl": {"en": "Or directly with curl:", "de": "Oder direkt per curl:", "es": "O directamente con curl:", "fr": "Ou directement avec curl :"},
    "wann": {"en": "When", "de": "Wann", "es": "Cuándo", "fr": "Quand"},
    "modell": {"en": "Model", "de": "Modell", "es": "Modelo", "fr": "Modèle"},
    "authorization-bearer-lt-api-key-gt": {"en": "Authorization: Bearer &lt;api-key&gt;", "de": "Authorization: Bearer &lt;api-key&gt;", "es": "Authorization: Bearer &lt;api-key&gt;", "fr": "Authorization: Bearer &lt;api-key&gt;"},
}
