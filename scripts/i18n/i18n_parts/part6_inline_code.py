# LANA-63 — catalog part 6: sentences that embed inline <code> or <a> markup.
# These are html-mode entries: the value carries the markup, because word order
# around the inline part differs between languages (ZH/FR move it).
# The <code> content itself is a Fachbegriff and stays verbatim everywhere.

KEYS = {
    "quelle-code-class-inline-get-admin-usage": {
        "en": "Source: <code class=\"inline\">GET /admin/usage?window=24h|7d|30d|all&amp;limit=50&amp;include_inactive=true</code> — the same shape as the user's own usage endpoint.",
        "de": "Quelle: <code class=\"inline\">GET /admin/usage?window=24h|7d|30d|all&amp;limit=50&amp;include_inactive=true</code> — dieselbe Form wie der eigene Nutzungs-Endpunkt.",
        "es": "Fuente: <code class=\"inline\">GET /admin/usage?window=24h|7d|30d|all&amp;limit=50&amp;include_inactive=true</code> — la misma forma que el endpoint de consumo propio.",
        "fr": "Source : <code class=\"inline\">GET /admin/usage?window=24h|7d|30d|all&amp;limit=50&amp;include_inactive=true</code> — même forme que l'endpoint d'usage personnel.",
        },

    "auf-a-href-nodes-html-class-link-meine": {
        "en": "Fill in <a href=\"nodes.html\" class=\"link\">My nodes</a>. The response contains the <code class=\"inline\">agent_api_key</code> — shown once.",
        "de": "Auf <a href=\"nodes.html\" class=\"link\">Meine Nodes</a> ausfüllen. Die Antwort enthält den <code class=\"inline\">agent_api_key</code> — einmalig sichtbar.",
        "es": "Rellena <a href=\"nodes.html\" class=\"link\">Mis nodes</a>. La respuesta incluye el <code class=\"inline\">agent_api_key</code> — visible una sola vez.",
        "fr": "À remplir sur <a href=\"nodes.html\" class=\"link\">Mes nodes</a>. La réponse contient la <code class=\"inline\">agent_api_key</code> — affichée une seule fois.",
        },

    "live-aus-code-class-inline-get-v1-me-usage": {
        "en": "Live from <code class=\"inline\">GET /v1/me/usage</code> — details and the period switcher are in the <a href=\"usage.html\" class=\"link\">Usage tab</a>.",
        "de": "Live aus <code class=\"inline\">GET /v1/me/usage</code> — Details und Zeitraum-Umschalter im <a href=\"usage.html\" class=\"link\">Usage-Tab</a>.",
        "es": "En vivo desde <code class=\"inline\">GET /v1/me/usage</code> — los detalles y el selector de periodo están en la <a href=\"usage.html\" class=\"link\">pestaña Usage</a>.",
        "fr": "En direct depuis <code class=\"inline\">GET /v1/me/usage</code> — les détails et le sélecteur de période sont dans l'<a href=\"usage.html\" class=\"link\">onglet Usage</a>.",
        },

    "fuer-code-class-inline-v1-chat-completions": {
        "en": "For <code class=\"inline\">/v1/chat/completions</code> and <code class=\"inline\">/v1/models</code>.",
        "de": "Für <code class=\"inline\">/v1/chat/completions</code> und <code class=\"inline\">/v1/models</code>.",
        "es": "Para <code class=\"inline\">/v1/chat/completions</code> y <code class=\"inline\">/v1/models</code>.",
        "fr": "Pour <code class=\"inline\">/v1/chat/completions</code> et <code class=\"inline\">/v1/models</code>.",
        },

    "du-erhaeltst-einen-code-class-inline-agent": {
        "en": "You receive an <code class=\"inline\">agent_api_key</code> — shown only once, store it safely.",
        "de": "Du erhältst einen <code class=\"inline\">agent_api_key</code> — einmalig sichtbar, sicher speichern.",
        "es": "Recibes un <code class=\"inline\">agent_api_key</code> — visible una sola vez, guárdalo bien.",
        "fr": "Vous recevez une <code class=\"inline\">agent_api_key</code> — visible une seule fois, conservez-la.",
        },

    "quelle-code-class-inline-get-v1-me-usage": {
        "en": "Source: <code class=\"inline\">GET /v1/me/usage?window=24h|7d|30d|all</code> — aggregation per model, period and request.",
        "de": "Quelle: <code class=\"inline\">GET /v1/me/usage?window=24h|7d|30d|all</code> — Aggregation pro Modell, Zeitraum und Request.",
        "es": "Fuente: <code class=\"inline\">GET /v1/me/usage?window=24h|7d|30d|all</code> — agregación por modelo, periodo y solicitud.",
        "fr": "Source : <code class=\"inline\">GET /v1/me/usage?window=24h|7d|30d|all</code> — agrégation par modèle, période et requête.",
        },
}
