"""agent.env muss auch mit BOM gelesen werden koennen.

PowerShell 5.1 schreibt mit `Set-Content -Encoding utf8` ein BOM. Ohne Gegenmassnahme wird der
erste Schluessel zu "\\ufeffPORTAL_URL" und bleibt wirkungslos - die Selbstregistrierung wird
stillschweigend uebersprungen und die Node bleibt offline, ohne Fehlermeldung.
"""

import importlib.util
import os
import pathlib

BASIS = pathlib.Path(__file__).resolve().parent.parent
AGENT = BASIS / "node-agent" / "agent.py"


def _lade_agent():
    spec = importlib.util.spec_from_file_location("comesh_agent_test", AGENT)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def test_bom_wird_entfernt(tmp_path):
    datei = tmp_path / "agent.env"
    # BOM ausdruecklich voranstellen, wie es PowerShell 5.1 tut
    datei.write_text("\ufeffPORTAL_URL=http://127.0.0.1:8765\nPORTAL_USER_KEY=egal\n", encoding="utf-8")

    agent = _lade_agent()
    for name in ("PORTAL_URL", "PORTAL_USER_KEY", "COMESH_AGENT_ENV"):
        os.environ.pop(name, None)
    agent._load_env_file(str(datei))

    assert os.environ.get("PORTAL_URL") == "http://127.0.0.1:8765", (
        "PORTAL_URL wurde nicht gesetzt - das BOM klebt am Schluesselnamen"
    )
    assert os.environ.get("PORTAL_USER_KEY") == "egal"
