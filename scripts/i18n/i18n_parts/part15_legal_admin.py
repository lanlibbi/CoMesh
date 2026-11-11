# -*- coding: utf-8 -*-
# Katalog-Teil 15: Admin-Maske für die Rechtstexte (admin-legal.html).
#
# Die Texte selbst liegen nicht hier — sie sind Betreibersache und kommen aus der
# Datenbank oder der Umgebung der jeweiligen Instanz. Hier stehen nur die
# Beschriftungen des Formulars.

KEYS = {
    "title.admin_legal": {
        "en": "Legal notice · CoMesh", "de": "Rechtstexte · CoMesh",
        "es": "Textos legales · CoMesh", "fr": "Textes juridiques · CoMesh",
    },
    "nav.admin.legal": {
        "en": "Legal", "de": "Rechtstexte", "es": "Legal", "fr": "Mentions",
    },
    "legal_admin.title": {
        "en": "Legal texts of this instance", "de": "Rechtstexte dieser Instanz",
        "es": "Textos legales de esta instancia", "fr": "Textes juridiques de cette instance",
    },
    "legal_admin.intro": {
        "en": "These details appear in the imprint, the privacy policy and the terms of use. They apply to this instance only — every operator enters their own.",
        "de": "Diese Angaben erscheinen im Impressum, in der Datenschutzerklärung und in den Nutzungsbedingungen. Sie gelten nur für diese Instanz — jeder Betreiber trägt seine eigenen ein.",
        "es": "Estos datos aparecen en el aviso legal, la política de privacidad y las condiciones de uso. Solo se aplican a esta instancia: cada operador introduce los suyos.",
        "fr": "Ces informations figurent dans les mentions légales, la politique de confidentialité et les conditions d'utilisation. Elles ne concernent que cette instance — chaque exploitant saisit les siennes.",
    },
    "legal_admin.not_admin": {
        "en": "Only accounts with the role “admin” may change the legal texts.",
        "de": "Nur Konten mit der Rolle „admin“ dürfen die Rechtstexte ändern.",
        "es": "Solo las cuentas con el rol «admin» pueden modificar los textos legales.",
        "fr": "Seuls les comptes ayant le rôle « admin » peuvent modifier les textes juridiques.",
    },
    "legal_admin.open_title": {
        "en": "Still missing", "de": "Noch offen",
        "es": "Pendiente", "fr": "Encore manquant",
    },
    "legal_admin.open_hint": {
        "en": "As long as mandatory details are missing, the pages show a notice and are kept out of search engines.",
        "de": "Solange Pflichtangaben fehlen, zeigen die Seiten einen Hinweis und werden nicht von Suchmaschinen erfasst.",
        "es": "Mientras falten datos obligatorios, las páginas muestran un aviso y quedan fuera de los buscadores.",
        "fr": "Tant que des mentions obligatoires manquent, les pages affichent un avertissement et restent hors des moteurs de recherche.",
    },
    "legal_admin.done_title": {
        "en": "Complete", "de": "Vollständig", "es": "Completo", "fr": "Complet",
    },
    "legal_admin.done_hint": {
        "en": "All mandatory details are set. Check the pages once yourself:",
        "de": "Alle Pflichtangaben sind eingetragen. Prüfe die Seiten einmal selbst:",
        "es": "Todos los datos obligatorios están registrados. Revisa las páginas una vez:",
        "fr": "Toutes les mentions obligatoires sont renseignées. Vérifiez les pages une fois :",
    },
    "legal_admin.form_title": {
        "en": "Operator details", "de": "Angaben des Betreibers",
        "es": "Datos del operador", "fr": "Coordonnées de l'exploitant",
    },
    "legal_admin.firma": {
        "en": "Company or name", "de": "Firma oder Name",
        "es": "Empresa o nombre", "fr": "Société ou nom",
    },
    "legal_admin.strasse": {
        "en": "Street and number", "de": "Straße und Hausnummer",
        "es": "Calle y número", "fr": "Rue et numéro",
    },
    "legal_admin.plz_ort": {
        "en": "Postal code and city", "de": "Postleitzahl und Ort",
        "es": "Código postal y ciudad", "fr": "Code postal et ville",
    },
    "legal_admin.land": {
        "en": "Country", "de": "Land", "es": "País", "fr": "Pays",
    },
    "legal_admin.telefon": {
        "en": "Phone", "de": "Telefon", "es": "Teléfono", "fr": "Téléphone",
    },
    "legal_admin.vertreten": {
        "en": "Represented by", "de": "Vertreten durch",
        "es": "Representado por", "fr": "Représenté par",
    },
    "legal_admin.register": {
        "en": "Commercial register", "de": "Registereintrag",
        "es": "Registro mercantil", "fr": "Registre du commerce",
    },
    "legal_admin.ustid": {
        "en": "VAT identification number", "de": "Umsatzsteuer-Identifikationsnummer",
        "es": "Número de identificación fiscal", "fr": "Numéro d'identification TVA",
    },
    "legal_admin.ds_email": {
        "en": "E-mail for privacy requests", "de": "E-Mail für Datenschutzanfragen",
        "es": "Correo para solicitudes de privacidad", "fr": "E-mail pour les demandes de confidentialité",
    },
    "legal_admin.hosting": {
        "en": "Hosting provider", "de": "Hosting-Anbieter",
        "es": "Proveedor de alojamiento", "fr": "Hébergeur",
    },
    "legal_admin.hosting_hint": {
        "en": "Appears in the privacy policy under “Operation and data processing agreements”.",
        "de": "Erscheint in der Datenschutzerklärung unter „Betrieb und Auftragsverarbeitung“.",
        "es": "Aparece en la política de privacidad bajo «Operación y encargados del tratamiento».",
        "fr": "Apparaît dans la politique de confidentialité sous « Exploitation et sous-traitance ».",
    },
    "legal_admin.env_hint": {
        "en": "Some values come from this instance's environment. An entry here takes precedence.",
        "de": "Einige Werte stammen aus der Umgebung dieser Instanz. Ein Eintrag hier hat Vorrang.",
        "es": "Algunos valores provienen del entorno de esta instancia. Una entrada aquí tiene prioridad.",
        "fr": "Certaines valeurs proviennent de l'environnement de cette instance. Une saisie ici est prioritaire.",
    },
    "legal_admin.saving": {
        "en": "Saving…", "de": "Wird gespeichert…", "es": "Guardando…", "fr": "Enregistrement…",
    },
    "legal_admin.open_imprint": {
        "en": "View imprint", "de": "Impressum ansehen",
        "es": "Ver aviso legal", "fr": "Voir les mentions légales",
    },
    "legal_admin.saved_ok": {
        "en": "Saved. All mandatory details are set.",
        "de": "Gespeichert. Alle Pflichtangaben sind eingetragen.",
        "es": "Guardado. Todos los datos obligatorios están registrados.",
        "fr": "Enregistré. Toutes les mentions obligatoires sont renseignées.",
    },
    "legal_admin.saved_open": {
        "en": "Saved. Still missing: {n} mandatory detail(s).",
        "de": "Gespeichert. Es fehlen noch {n} Pflichtangabe(n).",
        "es": "Guardado. Aún faltan {n} datos obligatorios.",
        "fr": "Enregistré. Il manque encore {n} mention(s) obligatoire(s).",
    },
    "legal_admin.save_failed": {
        "en": "Saving failed.", "de": "Speichern fehlgeschlagen.",
        "es": "Error al guardar.", "fr": "Échec de l'enregistrement.",
    },
    "legal_admin.upstream_hint": {
        "en": "CoMesh is free software (MIT). Whoever operates an instance is responsible for the legal texts of that instance — not the authors of the software.",
        "de": "CoMesh ist freie Software (MIT). Für die Rechtstexte einer Instanz ist verantwortlich, wer sie betreibt — nicht die Autoren der Software.",
        "es": "CoMesh es software libre (MIT). De los textos legales de una instancia responde quien la opera, no los autores del software.",
        "fr": "CoMesh est un logiciel libre (MIT). Les textes juridiques d'une instance relèvent de son exploitant, pas des auteurs du logiciel.",
    },
}
