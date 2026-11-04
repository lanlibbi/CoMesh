# LANA-63 — catalog part 7: strings that live in JS / Alpine expressions.
# These are reached by I18n.t("key") calls, not by data-i18n attributes.

KEYS = {
    "common.all": {"en": "All", "de": "Alle", "es": "Todos", "fr": "Tous"},

    "dash.greeting.morning": {"en": "Good morning", "de": "Guten Morgen", "es": "Buenos días", "fr": "Bonjour"},
    "dash.greeting.day": {"en": "Good afternoon", "de": "Guten Tag", "es": "Buenas tardes", "fr": "Bon après-midi"},
    "dash.greeting.evening": {"en": "Good evening", "de": "Guten Abend", "es": "Buenas noches", "fr": "Bonsoir"},
    "dash.window.24h": {"en": "24 hours", "de": "24 Stunden", "es": "24 horas", "fr": "24 heures"},
    "dash.window.7d": {"en": "7 days", "de": "7 Tage", "es": "7 días", "fr": "7 jours"},
    "dash.window.30d": {"en": "30 days", "de": "30 Tage", "es": "30 días", "fr": "30 jours"},
    "dash.key.copied": {"en": "API key copied", "de": "API-Key kopiert", "es": "API key copiada", "fr": "Clé API copiée"},
    "dash.key.regenerate.confirm": {"en": "Issue a new API key? The current one becomes invalid immediately.", "de": "Neuen API-Key ausstellen? Der bisherige wird sofort ungültig.", "es": "¿Emitir una nueva API key? La actual deja de ser válida de inmediato.", "fr": "Émettre une nouvelle clé API ? L'actuelle devient invalide immédiatement."},
    "dash.key.regenerate.prompt": {"en": "Password to confirm:", "de": "Passwort zur Bestätigung:", "es": "Contraseña para confirmar:", "fr": "Mot de passe pour confirmer :"},
    "dash.key.regenerate.done": {"en": "New API key issued — save it now.", "de": "Neuer API-Key ausgestellt — jetzt sichern.", "es": "Nueva API key emitida — guárdala ahora.", "fr": "Nouvelle clé API émise — sauvegardez-la maintenant."},

    "chat.prompt.quantum.label": {"en": "Explain quantum computing", "de": "Quantencomputing erklären", "es": "Explicar la computación cuántica", "fr": "Expliquer l'informatique quantique"},
    "chat.prompt.quantum.text": {"en": "Explain quantum computing in three sentences.", "de": "Erkläre Quantencomputing in drei Sätzen.", "es": "Explica la computación cuántica en tres frases.", "fr": "Expliquez l'informatique quantique en trois phrases."},
    "chat.prompt.python.label": {"en": "Python hello world", "de": "Python Hello-World", "es": "Hola mundo en Python", "fr": "Hello world en Python"},
    "chat.prompt.python.text": {"en": "Write a Python hello world with type hints.", "de": "Schreibe ein Python Hello-World mit Type Hints.", "es": "Escribe un hola mundo en Python con type hints.", "fr": "Écrivez un hello world Python avec des type hints."},
    "chat.prompt.ideas.label": {"en": "Side project ideas", "de": "Ideen für ein Nebenprojekt", "es": "Ideas para un proyecto secundario", "fr": "Idées de projet annexe"},
    "chat.prompt.ideas.text": {"en": "Give me three side project ideas.", "de": "Gib mir drei Ideen für ein Nebenprojekt.", "es": "Dame tres ideas para un proyecto secundario.", "fr": "Donnez-moi trois idées de projet annexe."},
    "chat.no_reply": {"en": "(no reply)", "de": "(keine Antwort)", "es": "(sin respuesta)", "fr": "(pas de réponse)"},
    "chat.no_credits": {"en": "Not enough credits — please top up.", "de": "Guthaben reicht nicht — bitte Credits aufladen.", "es": "Créditos insuficientes — recarga, por favor.", "fr": "Crédits insuffisants — veuillez recharger."},
    "chat.models_failed": {"en": "Models could not be loaded:", "de": "Modelle konnten nicht geladen werden:", "es": "No se pudieron cargar los modelos:", "fr": "Impossible de charger les modèles :"},
    "chat.error": {"en": "Chat error:", "de": "Chat-Fehler:", "es": "Error de chat:", "fr": "Erreur de chat :"},

    "credits.pack.token.10m": {"en": "approx. 10M tokens", "de": "ca. 10 Mio. Token", "es": "aprox. 10 M tokens", "fr": "env. 10 M tokens"},
    "credits.pack.token.50m": {"en": "approx. 50M tokens", "de": "ca. 50 Mio. Token", "es": "aprox. 50 M tokens", "fr": "env. 50 M tokens"},
    "credits.pack.token.200m": {"en": "approx. 200M tokens", "de": "ca. 200 Mio. Token", "es": "aprox. 200 M tokens", "fr": "env. 200 M tokens"},
    "credits.pack.all_models": {"en": "all models", "de": "alle Modelle", "es": "todos los modelos", "fr": "tous les modèles"},
    "credits.pack.prio": {"en": "priority queue", "de": "Prioritäts-Queue", "es": "cola prioritaria", "fr": "file prioritaire"},
    "credits.pack.top_prio": {"en": "highest priority", "de": "höchste Priorität", "es": "máxima prioridad", "fr": "priorité maximale"},
    "credits.pack.limits": {"en": "own limits", "de": "eigene Limits", "es": "límites propios", "fr": "limites propres"},
    "credits.pack.support": {"en": "standard support", "de": "Standard-Support", "es": "soporte estándar", "fr": "support standard"},
    "credits.pack.mail_support": {"en": "email support", "de": "E-Mail-Support", "es": "soporte por email", "fr": "support par e-mail"},
    "credits.buy_failed": {"en": "Purchase failed:", "de": "Kauf fehlgeschlagen:", "es": "Compra fallida:", "fr": "Achat échoué :"},
    "credits.topup.manual": {"en": "manual top-up", "de": "manuelle Aufladung", "es": "recarga manual", "fr": "rechargement manuel"},
    "credits.topup.saved": {"en": "Request saved. The admin will credit the balance.", "de": "Anfrage gespeichert. Der Admin schreibt die Credits gut.", "es": "Solicitud guardada. El admin abonará los créditos.", "fr": "Demande enregistrée. L'admin créditera le solde."},

    "nodes.bulk.status": {"en": "Toggle status", "de": "Status toggeln", "es": "Cambiar estado", "fr": "Basculer le statut"},
    "nodes.bulk.status.busy": {"en": "Status… ", "de": "Status… ", "es": "Estado… ", "fr": "Statut… "},
    "nodes.bulk.setting": {"en": "Setting… ", "de": "Setze… ", "es": "Aplicando… ", "fr": "Application… "},
    "nodes.bulk.whitelist_apply": {"en": "Apply whitelist", "de": "Whitelist anwenden", "es": "Aplicar whitelist", "fr": "Appliquer la whitelist"},
    "nodes.bulk.empty.confirm": {"en": "No models selected — sets the whitelist to \"nothing allowed\" for: {names}. Continue?", "de": "Keine Modelle ausgewählt — setzt die Whitelist auf \"nichts erlaubt\" für: {names}. Fortfahren?", "es": "Ningún modelo seleccionado — pone la whitelist en \"nada permitido\" para: {names}. ¿Continuar?", "fr": "Aucun modèle sélectionné — met la whitelist à « rien d'autorisé » pour : {names}. Continuer ?"},
    "nodes.none_allowed": {"en": "nothing allowed", "de": "nichts erlaubt", "es": "nada permitido", "fr": "rien d'autorisé"},
    "nodes.registered": {"en": "Node registered", "de": "Node registriert", "es": "Node registrado", "fr": "Node enregistré"},
    "nodes.deleted": {"en": "Node deleted", "de": "Node gelöscht", "es": "Node eliminado", "fr": "Node supprimé"},
    "nodes.whitelist_updated": {"en": "Model whitelist updated", "de": "Modell-Whitelist aktualisiert", "es": "Whitelist de modelos actualizada", "fr": "Whitelist de modèles mise à jour"},
    "nodes.update_failed": {"en": "Update failed:", "de": "Update fehlgeschlagen:", "es": "Actualización fallida:", "fr": "Mise à jour échouée :"},
    "nodes.toggle_failed": {"en": "Toggle failed:", "de": "Statuswechsel fehlgeschlagen:", "es": "Cambio de estado fallido:", "fr": "Basculement échoué :"},

    "profile.role.updated": {"en": "Role updated", "de": "Rolle aktualisiert", "es": "Rol actualizado", "fr": "Rôle mis à jour"},
    "profile.models.saved": {"en": "Model whitelist saved.", "de": "Modell-Whitelist gespeichert.", "es": "Whitelist de modelos guardada.", "fr": "Whitelist de modèles enregistrée."},
    "profile.models.updated": {"en": "Models updated", "de": "Modelle aktualisiert", "es": "Modelos actualizados", "fr": "Modèles mis à jour"},

    "usage.window.24h": {"en": "24 h", "de": "24 h", "es": "24 h", "fr": "24 h"},
    "usage.window.7d": {"en": "7 days", "de": "7 Tage", "es": "7 días", "fr": "7 jours"},
    "usage.window.30d": {"en": "30 days", "de": "30 Tage", "es": "30 días", "fr": "30 jours"},
    "usage.window.all": {"en": "Total", "de": "Gesamt", "es": "Total", "fr": "Total"},
    "usage.range.all": {"en": "the entire period", "de": "gesamter Zeitraum", "es": "todo el periodo", "fr": "toute la période"},

    "admin.include_inactive": {"en": "incl. inactive", "de": "inkl. inaktive", "es": "incl. inactivos", "fr": "y compris inactifs"},
    "admin.only_active": {"en": "active only", "de": "nur aktive", "es": "solo activos", "fr": "actifs seulement"},
    "admin.with_usage": {"en": "with usage in period", "de": "mit Verbrauch im Zeitraum", "es": "con consumo en el periodo", "fr": "avec usage sur la période"},

    # --- Nachzügler vom 04.11.2026 -------------------------------------
    # Diese Schlüssel wurden über I18n.t('…') mit EINZELNEN Anführungszeichen
    # aufgerufen. build_catalog.py zählte nur doppelte, hielt sie deshalb für
    # unbenutzt und strich sie — in jeder Sprache stand danach der rohe
    # Schlüssel in der Oberfläche. Der Generator liest jetzt beide Stile und
    # bricht ab, wenn ein Aufruf keinen Eintrag hat.
    "common.models": {"en": "Models", "de": "Modelle", "es": "Modelos", "fr": "Modèles"},
    "chat.choose_model": {"en": "Choose a model", "de": "Modell wählen", "es": "Elegir un modelo", "fr": "Choisir un modèle"},
    "fmt.range_suffix": {"en": " calls", "de": " Aufrufe", "es": " llamadas", "fr": " appels"},
    "range.last": {"en": "Last ", "de": "Letzte ", "es": "Últimos ", "fr": "Derniers "},
    "range.24h": {"en": "24 hours", "de": "24 Stunden", "es": "24 horas", "fr": "24 heures"},
    "range.7d": {"en": "7 days", "de": "7 Tage", "es": "7 días", "fr": "7 jours"},
    "range.30d": {"en": "30 days", "de": "30 Tage", "es": "30 días", "fr": "30 jours"},

    "admin.credits_on": {"en": "Credits on", "de": "Credits an", "es": "Créditos on", "fr": "Crédits on"},
    "admin.credits_off": {"en": "Credits off", "de": "Credits aus", "es": "Créditos off", "fr": "Crédits off"},
    "admin.credits_on_hint": {
        "en": "Usage is billed in credits. Accounts without balance cannot call models.",
        "de": "Nutzung wird in Credits abgerechnet. Konten ohne Guthaben können keine Modelle aufrufen.",
        "es": "El uso se factura en créditos. Las cuentas sin saldo no pueden llamar a los modelos.",
        "fr": "L’usage est facturé en crédits. Les comptes sans solde ne peuvent pas appeler de modèles.",
    },
    "admin.credits_off_hint": {
        "en": "Credits are not charged; usage is counted in tokens only.",
        "de": "Es werden keine Credits abgerechnet; gezählt werden nur Token.",
        "es": "No se cobran créditos; solo se cuentan los tokens.",
        "fr": "Aucun crédit n’est facturé ; seuls les tokens sont comptés.",
    },
    "admin.credits_confirm_on": {
        "en": "Switch the credits system on? Usage will be billed from now on.",
        "de": "Credits-System einschalten? Ab jetzt wird Nutzung abgerechnet.",
        "es": "¿Activar el sistema de créditos? A partir de ahora se facturará el uso.",
        "fr": "Activer le système de crédits ? L’usage sera facturé dès maintenant.",
    },
    "admin.credits_confirm_off": {
        "en": "Switch the credits system off? Usage will no longer be billed.",
        "de": "Credits-System ausschalten? Nutzung wird dann nicht mehr abgerechnet.",
        "es": "¿Desactivar el sistema de créditos? El uso ya no se facturará.",
        "fr": "Désactiver le système de crédits ? L’usage ne sera plus facturé.",
    },
    "admin.quota.unlimited": {"en": "Unlimited", "de": "Unbegrenzt", "es": "Ilimitado", "fr": "Illimité"},
    "admin.quota.balance": {"en": "Balance", "de": "Guthaben", "es": "Saldo", "fr": "Solde"},
    "admin.quota.blocked": {"en": "Blocked", "de": "Gesperrt", "es": "Bloqueado", "fr": "Bloqué"},
    "admin.quota.change_hint": {
        "en": "Click to switch the quota: unlimited → balance → blocked.",
        "de": "Klicken schaltet die Quota weiter: unbegrenzt → Guthaben → gesperrt.",
        "es": "Haz clic para cambiar la cuota: ilimitado → saldo → bloqueado.",
        "fr": "Cliquer fait passer la quota : illimité → solde → bloqué.",
    },
}
