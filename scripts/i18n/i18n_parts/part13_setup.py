# -*- coding: utf-8 -*-
# Katalog-Teil 13: die Erstinstallation (setup.html).
#
# Diese Seite gibt es genau einmal im Leben einer Instanz: solange kein
# Administrator existiert. Sie braucht vier Sprachen wie jede andere Seite,
# auch wenn sie selten zu sehen ist — wer eine Instanz in Spanien aufsetzt,
# soll sie lesen können.
#
# Die deutschen Werte sind zeichengleich zum Markup (data-i18n), die
# Fehlertexte werden im Seitenskript über I18n.t geholt.

KEYS = {
    "title.setup": {
        "en": "Setup · CoMesh", "de": "Einrichtung · CoMesh",
        "es": "Configuración · CoMesh", "fr": "Installation · CoMesh",
    },
    "setup.aside_headline": {
        "en": "This instance is not set up yet.",
        "de": "Diese Instanz ist noch nicht eingerichtet.",
        "es": "Esta instancia aún no está configurada.",
        "fr": "Cette instance n'est pas encore installée.",
    },
    "setup.aside_text": {
        "en": "Create the administrator account now — it is the only step before the first sign-in.",
        "de": "Lege jetzt das Administratorkonto an — das ist der einzige Schritt vor der ersten Anmeldung.",
        "es": "Crea ahora la cuenta de administrador: es el único paso antes del primer inicio de sesión.",
        "fr": "Créez maintenant le compte administrateur : c'est la seule étape avant la première connexion.",
    },
    "setup.point.token": {
        "en": "The setup token is printed in the container's start-up output. Without it nobody can grant themselves administrator rights — not even the first stranger who finds the address.",
        "de": "Das Setup-Token steht in der Startausgabe des Containers. Ohne dieses Token legt sich niemand Administratorrechte an, auch nicht der erste Fremde, der die Adresse findet.",
        "es": "El token de configuración aparece en la salida de arranque del contenedor. Sin él nadie puede concederse derechos de administrador, ni siquiera el primer desconocido que encuentre la dirección.",
        "fr": "Le jeton d'installation figure dans la sortie de démarrage du conteneur. Sans lui, personne ne peut s'attribuer des droits d'administrateur, pas même le premier inconnu qui trouve l'adresse.",
    },
    "setup.point.password": {
        "en": "You sign in to the portal with this account. The password can be changed later in the admin area.",
        "de": "Mit diesem Konto meldest du dich im Portal an. Das Passwort lässt sich später in der Verwaltung ändern.",
        "es": "Con esta cuenta inicias sesión en el portal. La contraseña se puede cambiar más tarde en la administración.",
        "fr": "Ce compte sert à vous connecter au portail. Le mot de passe reste modifiable plus tard dans l'administration.",
    },
    "setup.point.closed": {
        "en": "Once created, this page is closed for good. It only comes back if the instance is set up again from scratch.",
        "de": "Nach dem Anlegen ist diese Seite dauerhaft geschlossen. Sie erscheint erst wieder, wenn die Instanz neu aufgesetzt wird.",
        "es": "Una vez creada, esta página queda cerrada para siempre. Solo reaparece si la instancia se instala de nuevo desde cero.",
        "fr": "Une fois le compte créé, cette page est définitivement fermée. Elle ne réapparaît que si l'instance est réinstallée de zéro.",
    },
    "setup.eyebrow": {
        "en": "First-time setup", "de": "Ersteinrichtung",
        "es": "Configuración inicial", "fr": "Première installation",
    },
    "setup.heading": {
        "en": "Create administrator", "de": "Administrator anlegen",
        "es": "Crear administrador", "fr": "Créer l'administrateur",
    },
    "setup.intro": {
        "en": "This step is needed only once. Afterwards this page is closed for good.",
        "de": "Dieser Schritt ist nur einmal nötig. Danach ist diese Seite dauerhaft geschlossen.",
        "es": "Este paso solo es necesario una vez. Después, esta página queda cerrada para siempre.",
        "fr": "Cette étape n'est nécessaire qu'une fois. Ensuite, cette page est définitivement fermée.",
    },
    "setup.token_label": {
        "en": "Setup token", "de": "Setup-Token",
        "es": "Token de configuración", "fr": "Jeton d'installation",
    },
    "setup.token_hint": {
        "en": "From the start-up output: docker compose logs api",
        "de": "Aus der Startausgabe: docker compose logs api",
        "es": "De la salida de arranque: docker compose logs api",
        "fr": "Depuis la sortie de démarrage : docker compose logs api",
    },
    "setup.name_label": {
        "en": "Name", "de": "Name", "es": "Nombre", "fr": "Nom",
    },
    "setup.password2_label": {
        "en": "Repeat password", "de": "Passwort wiederholen",
        "es": "Repetir contraseña", "fr": "Répéter le mot de passe",
    },
    "setup.password_hint": {
        "en": "At least 10 characters.", "de": "Mindestens 10 Zeichen.",
        "es": "Al menos 10 caracteres.", "fr": "Au moins 10 caractères.",
    },
    "setup.submit": {
        "en": "Create administrator", "de": "Administrator anlegen",
        "es": "Crear administrador", "fr": "Créer l'administrateur",
    },
    "setup.submitting": {
        "en": "Creating…", "de": "Wird angelegt…",
        "es": "Creando…", "fr": "Création…",
    },
    "setup.alt_login": {
        "en": 'Already set up? <a href="login.html" class="link">Sign in</a>',
        "de": 'Schon eingerichtet? <a href="login.html" class="link">Zur Anmeldung</a>',
        "es": '¿Ya configurado? <a href="login.html" class="link">Iniciar sesión</a>',
        "fr": 'Déjà installé ? <a href="login.html" class="link">Se connecter</a>',
    },
    "setup.ok": {
        "en": "Account created. Redirecting to sign-in.",
        "de": "Konto angelegt. Du wirst zur Anmeldung weitergeleitet.",
        "es": "Cuenta creada. Te redirigimos al inicio de sesión.",
        "fr": "Compte créé. Redirection vers la connexion.",
    },
    "setup.err_short": {
        "en": "The password needs at least 10 characters.",
        "de": "Das Passwort braucht mindestens 10 Zeichen.",
        "es": "La contraseña necesita al menos 10 caracteres.",
        "fr": "Le mot de passe doit contenir au moins 10 caractères.",
    },
    "setup.err_mismatch": {
        "en": "The passwords do not match.",
        "de": "Die Passwörter stimmen nicht überein.",
        "es": "Las contraseñas no coinciden.",
        "fr": "Les mots de passe ne correspondent pas.",
    },
    "setup.err_token": {
        "en": "The setup token is not correct.",
        "de": "Das Setup-Token stimmt nicht.",
        "es": "El token de configuración no es correcto.",
        "fr": "Le jeton d'installation est incorrect.",
    },
    "setup.err_closed": {
        "en": "Setup is already completed.",
        "de": "Die Einrichtung ist bereits abgeschlossen.",
        "es": "La configuración ya está completada.",
        "fr": "L'installation est déjà terminée.",
    },
    "setup.err_generic": {
        "en": "That did not work. Please try again.",
        "de": "Das hat nicht geklappt. Bitte noch einmal versuchen.",
        "es": "No ha funcionado. Inténtalo de nuevo.",
        "fr": "Cela n'a pas fonctionné. Veuillez réessayer.",
    },
}
