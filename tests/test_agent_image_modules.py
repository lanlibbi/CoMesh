"""Prüft, dass alle lokalen Module des Agenten im Abbild landen.

Ein Modul, das `agent.py` importiert, aber im Dockerfile nicht kopiert wird, fällt erst beim Start
auf — und dann als Neustart-Kreis des Containers (`ModuleNotFoundError`). Genau das ist mit
`envfile.py` passiert.
"""

import pathlib
import re

BASIS = pathlib.Path(__file__).resolve().parent.parent
AGENT_DIR = BASIS / "node-agent"
AGENT = AGENT_DIR / "agent.py"
DOCKERFILE = AGENT_DIR / "Dockerfile"


def _lokale_module() -> set:
    """Modulnamen, deren Datei im Agent-Ordner liegt (also mitkopiert werden müssen)."""
    text = AGENT.read_text(encoding="utf-8")
    namen = set()
    for treffer in re.finditer(r"^\s*(?:from\s+([A-Za-z_][A-Za-z0-9_]*)\s+import|import\s+([A-Za-z_][A-Za-z0-9_]*))",
                               text, re.M):
        name = treffer.group(1) or treffer.group(2)
        if name and (AGENT_DIR / f"{name}.py").is_file():
            namen.add(name)
    return namen


def test_alle_lokalen_module_werden_kopiert():
    module = _lokale_module()
    assert module, "keine lokalen Importe gefunden - Test greift ins Leere"

    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    kopiert = set(re.findall(r"node-agent/([A-Za-z_][A-Za-z0-9_]*)\.py", dockerfile))

    fehlend = sorted(module - kopiert)
    assert not fehlend, (
        "Diese lokalen Module importiert agent.py, das Dockerfile kopiert sie aber nicht: "
        + ", ".join(fehlend)
        + " - Folge: ModuleNotFoundError beim Start des Containers"
    )
