# LANA-… — catalog part 9: der Abschnitt „Eigene Node beitragen" auf nodes.html.
#
# Die Texte sind so geschrieben, dass sie die Grenzen benennen statt sie zu
# verschweigen: kein darwin-x86_64, kein linux-arm64, keine erneute Anzeige des
# Account-Schlüssels. Fachbegriffe (Node, Token, Model, API-Key, Pool, Provider,
# Owner, Treasury, VRAM, Tailscale, Credits) bleiben in jeder Locale gleich.
#
# Die Schlüssel mit `-html` im Kommentar werden über data-i18n-html eingesetzt;
# build_catalog.py vergleicht die Tags über alle vier Sprachen, sie müssen also
# in jeder Locale identisch sein (ein <code class="inline"> bleibt ein <code>).

KEYS = {
    # ================================================= nodes.html — beitragen
    "node.contribute.eyebrow": {
        "en": "Contribute",
        "de": "Beitragen",
        "es": "Aportar",
        "fr": "Contribuer",
    },
    "node.contribute.title": {
        "en": "Contribute your own node",
        "de": "Eigene Node beitragen",
        "es": "Aporta tu propio node",
        "fr": "Contribuer votre propre node",
    },
    "node.contribute.lede": {
        "en": "One command on your own machine is enough: the agent downloads itself, asks for the account key and registers the node with the pool. No repository, no Python, no prior registration.",
        "de": "Ein Befehl auf der eigenen Maschine genügt: der Agent lädt sich selbst, fragt den Account-Schlüssel ab und meldet die Node im Pool an. Kein Repository, kein Python, keine Registrierung im Voraus.",
        "es": "Basta con un comando en tu propia máquina: el agente se descarga solo, pide la account key y registra el node en el pool. Sin repositorio, sin Python y sin registro previo.",
        "fr": "Une seule commande sur votre propre machine suffit : l’agent se télécharge lui-même, demande l’account key et enregistre le node dans le pool. Pas de dépôt, pas de Python, pas d’inscription préalable.",
    },
    "node.contribute.addr.choose": {
        "en": "Address in the command",
        "de": "Adresse im Befehl",
        "es": "Dirección en el comando",
        "fr": "Adresse dans la commande",
    },
    "node.contribute.addr.current": {
        "en": "This address",
        "de": "Diese Adresse",
        "es": "Esta dirección",
        "fr": "Cette adresse",
    },
    "node.contribute.addr.public": {
        "en": "Public address",
        "de": "Öffentliche Adresse",
        "es": "Dirección pública",
        "fr": "Adresse publique",
    },
    "node.contribute.cmd.unix": {
        "en": "Linux and macOS",
        "de": "Linux und macOS",
        "es": "Linux y macOS",
        "fr": "Linux et macOS",
    },
    "node.contribute.cmd.unix.hint": {
        "en": "Paste into a terminal and run. Needs nothing but curl and a SHA-256 tool.",
        "de": "In ein Terminal einfügen und ausführen. Braucht nur curl und ein SHA-256-Werkzeug.",
        "es": "Pega en un terminal y ejecuta. Solo necesita curl y una herramienta SHA-256.",
        "fr": "À coller dans un terminal et exécuter. Ne nécessite que curl et un outil SHA-256.",
    },
    "node.contribute.cmd.windows": {
        "en": "Windows",
        "de": "Windows",
        "es": "Windows",
        "fr": "Windows",
    },
    "node.contribute.cmd.windows.hint": {
        "en": "Paste into PowerShell and run — not into the command prompt.",
        "de": "In PowerShell einfügen und ausführen — nicht in der Eingabeaufforderung.",
        "es": "Pega en PowerShell y ejecuta — no en el símbolo del sistema.",
        "fr": "À coller dans PowerShell et exécuter — pas dans l’invite de commandes.",
    },
    "node.contribute.downloads.title": {
        "en": "Downloads",
        "de": "Downloads",
        "es": "Descargas",
        "fr": "Téléchargements",
    },
    # html
    "node.contribute.downloads.hint": {
        "en": "Every binary ships with a <code class=\"inline\">.sha256</code> file next to it. The installers check it before anything is installed — without a matching checksum the installation stops. Size and checksum shown here are read from the file that is actually being served, not from a list.",
        "de": "Zu jedem Binary liegt eine <code class=\"inline\">.sha256</code>-Datei. Die Installer prüfen sie, bevor etwas installiert wird — ohne passende Prüfsumme bricht die Installation ab. Größe und Prüfsumme hier werden aus der tatsächlich ausgelieferten Datei gelesen, nicht aus einer Liste.",
        "es": "Cada binary lleva junto un archivo <code class=\"inline\">.sha256</code>. Los instaladores lo comprueban antes de instalar nada — sin una suma coincidente la instalación se detiene. El tamaño y la suma que aparecen aquí se leen del archivo que realmente se sirve, no de una lista.",
        "fr": "Chaque binary est accompagné d’un fichier <code class=\"inline\">.sha256</code>. Les installateurs le vérifient avant toute installation — sans somme correspondante, l’installation s’arrête. La taille et la somme affichées ici sont lues dans le fichier réellement servi, pas dans une liste.",
    },
    "node.contribute.col.file": {
        "en": "File",
        "de": "Datei",
        "es": "Archivo",
        "fr": "Fichier",
    },
    "node.contribute.col.size": {
        "en": "Size",
        "de": "Größe",
        "es": "Tamaño",
        "fr": "Taille",
    },
    "node.contribute.col.sha": {
        "en": "SHA-256",
        "de": "SHA-256",
        "es": "SHA-256",
        "fr": "SHA-256",
    },
    "node.contribute.key.title": {
        "en": "Account key",
        "de": "Account-Schlüssel",
        "es": "Account key",
        "fr": "Account key",
    },
    # html
    "node.contribute.key.body": {
        "en": "The installer writes it to the configuration as <code class=\"inline\">PORTAL_USER_KEY</code>. It is the API key of your account — the same one this portal signs you in with. It is shown in full once, when it is issued; in the <a href=\"profile.html#schluessel\" class=\"link\">account settings</a> you see prefix and date and can create a new one with your password at any time. A new key invalidates the previous one.",
        "de": "Der Installer schreibt ihn als <code class=\"inline\">PORTAL_USER_KEY</code> in die Konfiguration. Das ist der API-Schlüssel deines Kontos — derselbe, mit dem dich dieses Portal anmeldet. Er wird beim Ausstellen einmalig vollständig angezeigt; in den <a href=\"profile.html#schluessel\" class=\"link\">Kontoeinstellungen</a> siehst du Präfix und Datum und erzeugst mit deinem Passwort jederzeit einen neuen. Ein neuer Schlüssel macht den bisherigen ungültig.",
        "es": "El instalador lo escribe en la configuración como <code class=\"inline\">PORTAL_USER_KEY</code>. Es la API key de tu cuenta — la misma con la que este portal te autentica. Se muestra completa una sola vez, al emitirla; en los <a href=\"profile.html#schluessel\" class=\"link\">ajustes de cuenta</a> ves el prefijo y la fecha y puedes crear una nueva con tu contraseña cuando quieras. Una clave nueva invalida la anterior.",
        "fr": "L’installateur l’écrit dans la configuration sous <code class=\"inline\">PORTAL_USER_KEY</code>. C’est l’API key de votre compte — celle avec laquelle ce portail vous authentifie. Elle n’est affichée en entier qu’une seule fois, à son émission ; dans les <a href=\"profile.html#schluessel\" class=\"link\">paramètres du compte</a> vous voyez le préfixe et la date et pouvez en créer une nouvelle avec votre mot de passe à tout moment. Une nouvelle clé invalide la précédente.",
    },
    "node.contribute.after.title": {
        "en": "What happens next",
        "de": "Was danach passiert",
        "es": "Qué pasa después",
        "fr": "Ce qui se passe ensuite",
    },
    "node.contribute.after.1": {
        "en": "The node appears in the list above — no registration in advance, the agent signs in with the account key itself.",
        "de": "Die Node erscheint in der Liste oben — ohne Registrierung im Voraus, der Agent meldet sich mit dem Account-Schlüssel selbst an.",
        "es": "El node aparece en la lista de arriba — sin registro previo, el agente se autentica con la account key.",
        "fr": "Le node apparaît dans la liste ci-dessus — sans inscription préalable, l’agent s’authentifie avec l’account key.",
    },
    "node.contribute.after.2": {
        "en": "The connection runs outbound over WebSocket. No port has to be opened, no address released in the router.",
        "de": "Die Verbindung läuft ausgehend über WebSocket. Es muss kein Port geöffnet und keine Adresse im Router freigegeben werden.",
        "es": "La conexión sale por WebSocket. No hay que abrir ningún puerto ni liberar ninguna dirección en el router.",
        "fr": "La connexion sort en WebSocket. Aucun port à ouvrir, aucune adresse à libérer dans le routeur.",
    },
    "node.contribute.after.3": {
        "en": "The agent runs as a service (systemd --user on Linux, launchd on macOS) and comes back after a reboot. No sudo.",
        "de": "Der Agent läuft als Dienst (systemd --user unter Linux, launchd unter macOS) und ist nach einem Neustart wieder da. Kein sudo.",
        "es": "El agente corre como servicio (systemd --user en Linux, launchd en macOS) y vuelve tras un reinicio. Sin sudo.",
        "fr": "L’agent tourne comme service (systemd --user sous Linux, launchd sous macOS) et revient après un redémarrage. Sans sudo.",
    },
    # html
    "node.contribute.after.4": {
        "en": "Without a detected NVIDIA GPU the installer asks for the VRAM and writes <code class=\"inline\">NODE_VRAM_GB</code> to the configuration. Without that value the pool sends no job to this node.",
        "de": "Ohne erkannte NVIDIA-GPU fragt der Installer nach dem VRAM und schreibt <code class=\"inline\">NODE_VRAM_GB</code> in die Konfiguration. Fehlt der Wert, schickt der Pool dieser Node keinen Auftrag.",
        "es": "Sin una GPU NVIDIA detectada, el instalador pregunta por la VRAM y escribe <code class=\"inline\">NODE_VRAM_GB</code> en la configuración. Sin ese valor el pool no envía ningún trabajo a este node.",
        "fr": "Sans GPU NVIDIA détectée, l’installateur demande la VRAM et écrit <code class=\"inline\">NODE_VRAM_GB</code> dans la configuration. Sans cette valeur, le pool n’envoie aucune tâche à ce node.",
    },
    "node.contribute.limits.title": {
        "en": "Not available",
        "de": "Nicht verfügbar",
        "es": "No disponible",
        "fr": "Non disponible",
    },
    # html
    "node.contribute.limits.body": {
        "en": "There is no <code class=\"inline\">darwin-x86_64</code> (Intel Mac) and no <code class=\"inline\">linux-arm64</code>: neither is built today. On such a machine the installer stops with a message about the architecture instead of setting up something wrong.",
        "de": "Es gibt kein <code class=\"inline\">darwin-x86_64</code> (Intel-Mac) und kein <code class=\"inline\">linux-arm64</code>: beides wird derzeit nicht gebaut. Auf so einem Rechner bricht der Installer mit einer Meldung zur Architektur ab, statt etwas Falsches einzurichten.",
        "es": "No hay <code class=\"inline\">darwin-x86_64</code> (Mac Intel) ni <code class=\"inline\">linux-arm64</code>: ninguno de los dos se compila actualmente. En una máquina así el instalador se detiene con un mensaje sobre la arquitectura, en lugar de configurar algo incorrecto.",
        "fr": "Il n’y a pas de <code class=\"inline\">darwin-x86_64</code> (Mac Intel) ni de <code class=\"inline\">linux-arm64</code> : aucun des deux n’est compilé actuellement. Sur une telle machine, l’installateur s’arrête avec un message sur l’architecture au lieu de configurer quelque chose de faux.",
    },

    # ------------------------------------------------- über nodes.js gesetzt
    "node.contribute.copy": {
        "en": "Copy",
        "de": "Kopieren",
        "es": "Copiar",
        "fr": "Copier",
    },
    "node.contribute.copied": {
        "en": "Copied",
        "de": "Kopiert",
        "es": "Copiado",
        "fr": "Copié",
    },
    "node.contribute.copy_failed": {
        "en": "Copy failed — select the text and copy it by hand",
        "de": "Kopieren nicht möglich — bitte markieren und von Hand kopieren",
        "es": "No se pudo copiar — selecciona el texto y cópialo a mano",
        "fr": "Copie impossible — sélectionnez le texte et copiez-le à la main",
    },
    "node.contribute.download": {
        "en": "Download",
        "de": "Laden",
        "es": "Descargar",
        "fr": "Télécharger",
    },
    "node.contribute.pending": {
        "en": "checking…",
        "de": "wird ermittelt…",
        "es": "comprobando…",
        "fr": "vérification…",
    },
    "node.contribute.unavailable": {
        "en": "unavailable",
        "de": "nicht ermittelbar",
        "es": "no disponible",
        "fr": "indisponible",
    },
    "node.contribute.no_checksum": {
        "en": "no checksum file",
        "de": "keine Prüfsummendatei",
        "es": "sin archivo de suma",
        "fr": "pas de fichier de somme",
    },

    # ------------------------------------------- nodes.html — Rollen-Hinweis
    # Die Seite ist für jedes Konto offen. Registrieren und Massenaktionen
    # brauchen `provider`; ein Consumer stellt die Rolle selbst im Profil um
    # (PUT /v1/me/role) — der Hinweis verlinkt genau dorthin, statt zu
    # behaupten, ein Administrator müsse eingreifen.
    # html — Schritt 01 der Ablauf-Liste; stand als einziger Schritt ohne
    # Schlüssel da und blieb deshalb in jeder Sprache deutsch.
    "node.explain.key": {
        "en": "You receive an <code class=\"inline\">agent_api_key</code> — shown once, store it safely.",
        "de": "Du erhältst einen <code class=\"inline\">agent_api_key</code> — einmalig sichtbar, sicher speichern.",
        "es": "Recibes una <code class=\"inline\">agent_api_key</code> — visible una sola vez, guárdala de forma segura.",
        "fr": "Vous recevez une <code class=\"inline\">agent_api_key</code> — affichée une seule fois, à conserver en lieu sûr.",
    },
    "node.role_gate.title": {
        "en": "Role not set yet",
        "de": "Rolle noch nicht gesetzt",
        "es": "Rol aún no configurado",
        "fr": "Rôle pas encore défini",
    },
    # html
    "node.role_gate.body": {
        "en": "The installation commands below work for every account. The agent registers the node with your account key, though, and for that your account needs the role <b>provider</b> (or <b>both</b>). You change that yourself in the <a href=\"profile.html#rolle\" class=\"link\">profile</a> — no administrator needed. Your node then appears in the list on this page.",
        "de": "Die Installationsbefehle unten gelten für jedes Konto. Der Agent meldet die Node aber mit deinem Account-Schlüssel an, und dafür muss dein Konto die Rolle <b>provider</b> (oder <b>both</b>) tragen. Das stellst du selbst im <a href=\"profile.html#rolle\" class=\"link\">Profil</a> um — ein Administrator ist dafür nicht nötig. Danach erscheint deine Node in der Liste dieser Seite.",
        "es": "Los comandos de instalación de abajo sirven para cualquier cuenta. Pero el agente registra el node con la clave de tu cuenta y para eso tu cuenta necesita el rol <b>provider</b> (o <b>both</b>). Eso lo cambias tú mismo en el <a href=\"profile.html#rolle\" class=\"link\">perfil</a> — no hace falta un administrador. Después tu node aparece en la lista de esta página.",
        "fr": "Les commandes d’installation ci-dessous valent pour tout compte. Mais l’agent enregistre le node avec la clé de votre compte, et pour cela votre compte doit avoir le rôle <b>provider</b> (ou <b>both</b>). Vous le changez vous-même dans le <a href=\"profile.html#rolle\" class=\"link\">profil</a> — aucun administrateur n’est nécessaire. Votre node apparaît ensuite dans la liste de cette page.",
    },
    "node.role_gate.cta": {
        "en": "Change role in profile",
        "de": "Rolle im Profil ändern",
        "es": "Cambiar el rol en el perfil",
        "fr": "Changer le rôle dans le profil",
    },
    "node.list.empty_consumer": {
        "en": "As soon as the agent runs on your machine, the node appears here — the commands are above under “Contribute your own node”.",
        "de": "Sobald der Agent auf deiner Maschine läuft, erscheint die Node hier — die Befehle stehen oben unter „Eigene Node beitragen“.",
        "es": "En cuanto el agente corra en tu máquina, el node aparece aquí — los comandos están arriba en «Aporta tu propio node».",
        "fr": "Dès que l’agent tourne sur votre machine, le node apparaît ici — les commandes sont plus haut sous « Contribuer votre propre node ».",
    },

    # ------------------------------------------------ index.html — Node-Karte
    "dash.node.eyebrow": {
        "en": "Node",
        "de": "Node",
        "es": "Node",
        "fr": "Node",
    },
    "dash.node.title_none": {
        "en": "Share your GPU",
        "de": "Teile deine GPU",
        "es": "Comparte tu GPU",
        "fr": "Partagez votre GPU",
    },
    "dash.node.title_has": {
        "en": "Your node",
        "de": "Deine Node",
        "es": "Tu node",
        "fr": "Votre node",
    },
    "dash.node.lede_none": {
        "en": "One machine with a GPU is enough: the installer sets up the agent, the node signs in with your account key and takes jobs. 70 % of the job cost is credited to you.",
        "de": "Ein Rechner mit GPU genügt: der Installer richtet den Agenten ein, die Node meldet sich mit deinem Account-Schlüssel an und nimmt Aufträge an. 70 % der Job-Kosten gehen als Credits an dich.",
        "es": "Basta una máquina con GPU: el instalador prepara el agente, el node se registra con la clave de tu cuenta y acepta trabajos. El 70 % del coste del trabajo se te abona en credits.",
        "fr": "Une machine avec GPU suffit : l’installateur installe l’agent, le node s’authentifie avec la clé de votre compte et prend des tâches. 70 % du coût de la tâche vous sont crédités.",
    },
    "dash.node.lede_has": {
        "en": "These machines are linked to your account. Status and models are managed on the node page.",
        "de": "Diese Maschinen sind mit deinem Konto verbunden. Status und Modelle pflegst du auf der Node-Seite.",
        "es": "Estas máquinas están vinculadas a tu cuenta. El estado y los modelos se gestionan en la página de nodes.",
        "fr": "Ces machines sont liées à votre compte. L’état et les modèles se gèrent sur la page des nodes.",
    },
    "dash.node.cta": {
        "en": "To the installation guide",
        "de": "Zum Installationsweg",
        "es": "A la guía de instalación",
        "fr": "Vers l’installation",
    },
    "dash.node.cmd_label": {
        "en": "Install — Linux and macOS",
        "de": "Installation — Linux und macOS",
        "es": "Instalación — Linux y macOS",
        "fr": "Installation — Linux et macOS",
    },
    "dash.node.cmd_hint": {
        "en": "Paste into a terminal. The installer asks for the account key without echoing it, verifies the checksum and sets up the service — no sudo. For Windows the PowerShell command is on the node page.",
        "de": "In ein Terminal einfügen. Der Installer fragt den Account-Schlüssel verdeckt ab, prüft die Prüfsumme und richtet den Dienst ein — ohne sudo. Für Windows steht der PowerShell-Befehl auf der Node-Seite.",
        "es": "Pega en un terminal. El instalador pide la clave sin mostrarla, comprueba la suma y prepara el servicio — sin sudo. Para Windows el comando de PowerShell está en la página de nodes.",
        "fr": "À coller dans un terminal. L’installateur demande la clé sans l’afficher, vérifie la somme et installe le service — sans sudo. Pour Windows, la commande PowerShell se trouve sur la page des nodes.",
    },
    "dash.node.role_hint": {
        "en": "— the agent registers the node with your account key; the account therefore needs the role provider (or both).",
        "de": "— der Agent meldet die Node mit deinem Account-Schlüssel an; dafür muss das Konto die Rolle provider (oder both) tragen.",
        "es": "— el agente registra el node con la clave de tu cuenta; por eso la cuenta necesita el rol provider (o both).",
        "fr": "— l’agent enregistre le node avec la clé de votre compte ; le compte doit donc avoir le rôle provider (ou both).",
    },
    "dash.node.manage": {
        "en": "Manage nodes",
        "de": "Nodes verwalten",
        "es": "Gestionar nodes",
        "fr": "Gérer les nodes",
    },
}
