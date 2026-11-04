# Konto löschen (Admin) und Modellfreigabe am Gerät (Provider).
#
# Zwei Themen in einem Teil, weil sie im selben Lauf entstanden sind: der
# Löschknopf in der Kontenliste und das Freitextfeld für die Modelle einer Node.
# Beides sind Oberflächentexte, die in allen vier Sprachen stehen müssen —
# ein fest eingebauter deutscher Satz auf einer englischen Seite ist derselbe
# Fehler wie eine fehlende Übersetzung.

KEYS = {
    # ---------------------------------------------------------------- Dashboard
    "api_key_manage": {
        "en": "Manage keys",
        "de": "Schlüssel verwalten",
        "es": "Gestionar claves",
        "fr": "Gérer les clés",
    },

    # ------------------------------------------------------- Gerät: Modellfreigabe
    "node.models.free_label": {
        "en": "Models on this node",
        "de": "Modelle dieser Node",
        "es": "Modelos de este nodo",
        "fr": "Modèles de ce nœud",
    },
    "node.models.free_placeholder": {
        "en": "qwen2.5-coder:7b, llama3.1:8b",
        "de": "qwen2.5-coder:7b, llama3.1:8b",
        "es": "qwen2.5-coder:7b, llama3.1:8b",
        "fr": "qwen2.5-coder:7b, llama3.1:8b",
    },
    "node.models.free_hint": {
        "en": ("One model name per line or separated by commas. Empty means: all local models "
               "on this machine, no cloud models. This list is what others can use through "
               "your node."),
        "de": ("Ein Modellname je Zeile oder durch Komma getrennt. Leer heißt: alle lokalen "
               "Modelle dieser Maschine, keine Cloud-Modelle. Genau diese Liste bestimmt, "
               "welche Modelle andere über deine Node nutzen können."),
        "es": ("Un nombre de modelo por línea o separados por comas. Vacío significa: todos "
               "los modelos locales de esta máquina, ningún modelo en la nube. Esta lista "
               "determina qué modelos pueden usar otros a través de tu nodo."),
        "fr": ("Un nom de modèle par ligne ou séparés par des virgules. Vide signifie : tous "
               "les modèles locaux de cette machine, aucun modèle cloud. C'est cette liste "
               "qui détermine ce que les autres peuvent utiliser via votre nœud."),
    },
    "node.models.catalog_hint": {
        "en": ("The list below is the portal host's catalog — not the models on your node. "
               "Anything that exists only on your machine goes in the field above."),
        "de": ("Die Liste unten ist der Katalog des Portal-Hosts — nicht die Modelle deiner "
               "Node. Was nur auf deiner Maschine liegt, steht oben im Feld."),
        "es": ("La lista de abajo es el catálogo del host del portal — no los modelos de tu "
               "nodo. Lo que solo existe en tu máquina va en el campo de arriba."),
        "fr": ("La liste ci-dessous est le catalogue de l'hôte du portail — pas les modèles "
               "de votre nœud. Ce qui n'existe que sur votre machine se met dans le champ "
               "ci-dessus."),
    },
    "node.models.adopt": {
        "en": "Add to the selection",
        "de": "In die Auswahl übernehmen",
        "es": "Añadir a la selección",
        "fr": "Ajouter à la sélection",
    },
    "nodes.models.adopted": {
        "en": "{n} model(s) added to the selection",
        "de": "{n} Modell(e) in die Auswahl übernommen",
        "es": "{n} modelo(s) añadido(s) a la selección",
        "fr": "{n} modèle(s) ajouté(s) à la sélection",
    },

    # ------------------------------------------------------------ Konto löschen
    "admin.delete.confirm": {
        "en": "Delete the account {email}? Its API keys and sessions are removed with it.",
        "de": ("Konto {email} löschen? Die API-Schlüssel und Sitzungen des Kontos "
               "verschwinden mit."),
        "es": ("¿Eliminar la cuenta {email}? Sus claves de API y sesiones se eliminan "
               "también."),
        "fr": ("Supprimer le compte {email} ? Ses clés d'API et sessions disparaissent "
               "avec."),
    },
    "admin.delete.confirm2": {
        "en": ("Really delete? Node earnings are kept so the books stay correct, but the "
               "account itself cannot be restored."),
        "de": ("Wirklich löschen? Die Einnahmen der Nodes bleiben erhalten, damit die "
               "Abrechnung stimmt — das Konto selbst lässt sich nicht wiederherstellen."),
        "es": ("¿Eliminar de verdad? Los ingresos de los nodos se conservan para que las "
               "cuentas cuadren, pero la cuenta en sí no se puede restaurar."),
        "fr": ("Vraiment supprimer ? Les revenus des nœuds sont conservés pour que la "
               "comptabilité reste juste, mais le compte lui-même est irrécupérable."),
    },
    "admin.delete.keys": {
        "en": "{n} key(s) removed",
        "de": "{n} Schlüssel entfernt",
        "es": "{n} clave(s) eliminada(s)",
        "fr": "{n} clé(s) supprimée(s)",
    },
    "admin.delete.nodes_kept": {
        "en": "nodes kept with their earnings: {ids}",
        "de": "Nodes mit Einnahmen behalten: {ids}",
        "es": "nodos conservados con sus ingresos: {ids}",
        "fr": "nœuds conservés avec leurs revenus : {ids}",
    },
    "admin.delete.nodes_removed": {
        "en": "{n} node(s) without earnings removed",
        "de": "{n} Node(s) ohne Einnahmen entfernt",
        "es": "{n} nodo(s) sin ingresos eliminado(s)",
        "fr": "{n} nœud(s) sans revenus supprimé(s)",
    },
    "admin.delete.done": {
        "en": "{email} deleted. {details}",
        "de": "{email} gelöscht. {details}",
        "es": "{email} eliminada. {details}",
        "fr": "{email} supprimé. {details}",
    },
    "admin.delete.failed": {
        "en": "The account could not be deleted",
        "de": "Konto konnte nicht gelöscht werden",
        "es": "No se pudo eliminar la cuenta",
        "fr": "Le compte n'a pas pu être supprimé",
    },
}
