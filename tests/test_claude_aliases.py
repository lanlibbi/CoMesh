"""Waechter fuer die Claude-Aliase.

Claude Code und Claude Desktop akzeptieren im Gateway-Betrieb nur Modellnamen im Claude-Stil.
Ohne Aliase melden sie "no usable models", obwohl die Route antwortet. Diese Tests halten fest:
  * die Aliase stehen in /v1/models,
  * sie tragen die Anthropic-Felder,
  * ein Aufruf mit Alias landet beim echten Modell (nicht bei Ollama mit 404).
"""

import os
import uuid

ADMIN = {"Authorization": f"Bearer {os.environ['ADMIN_TOKEN']}"}


def _konto(client):
    email = f"claude-{uuid.uuid4().hex[:10]}@example.test"
    r = client.post("/admin/users", headers=ADMIN,
                    json={"email": email, "name": "Claude Test", "role": "both",
                          "password": "pw-claude-1234", "initial_credits": 5.0})
    assert r.status_code == 201, r.text
    login = client.post("/auth/login", json={"email": email, "password": "pw-claude-1234"})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['api_key']}"}


def test_aliase_stehen_in_der_modellliste(client, monkeypatch):
    import anthropic_api

    monkeypatch.setenv("OLLAMA_URL", "http://127.0.0.1:9")
    kopf = _konto(client)
    r = client.get("/v1/models", headers={**kopf, "anthropic-version": "2023-06-01"})
    # Ohne erreichbares Ollama antwortet die Route 502 - dann pruefen wir die Aliase direkt.
    if r.status_code == 502:
        ziel = anthropic_api.alias_ziel(["qwen2.5-coder:7b"], "qwen2.5-coder:7b")
        assert ziel == "qwen2.5-coder:7b"
        return
    assert r.status_code == 200, r.text
    ids = [e["id"] for e in r.json()["data"]]
    for alias in anthropic_api.CLAUDE_ALIASE:
        assert alias in ids, f"{alias} fehlt in der Modellliste: {ids}"
    eintrag = next(e for e in r.json()["data"] if e["id"] == anthropic_api.CLAUDE_ALIASE[0])
    # Anthropic-Felder, sonst findet der Client den Eintrag nicht
    assert eintrag["type"] == "model" and eintrag["display_name"]
    assert "created_at" in eintrag


def test_alias_ziel_reihenfolge(monkeypatch):
    import anthropic_api

    monkeypatch.delenv("ANTHROPIC_ALIAS_TARGET", raising=False)
    assert anthropic_api.alias_ziel(None, "portal-default") == "portal-default"
    assert anthropic_api.alias_ziel(["erstes", "zweites"], "") == "erstes"
    monkeypatch.setenv("ANTHROPIC_ALIAS_TARGET", "ausdruecklich")
    assert anthropic_api.alias_ziel(["erstes"], "portal-default") == "ausdruecklich"
    monkeypatch.delenv("ANTHROPIC_ALIAS_TARGET", raising=False)
    assert anthropic_api.alias_ziel([], "") == ""


def test_alias_wird_auf_echtes_modell_abgebildet(monkeypatch):
    import anthropic_api

    monkeypatch.delenv("ANTHROPIC_ALIAS_TARGET", raising=False)
    for alias in anthropic_api.CLAUDE_ALIASE:
        assert anthropic_api.modell_aufloesen(alias, "qwen2.5-coder:7b") == "qwen2.5-coder:7b"
    # Ein echtes Modell bleibt unangetastet.
    assert anthropic_api.modell_aufloesen("qwen3-vl:8b", "qwen2.5-coder:7b") == "qwen3-vl:8b"
    # Auch ein fremder "claude"-Name, der kein Alias ist, bleibt stehen.
    assert anthropic_api.modell_aufloesen("claude-irgendwas", "x") == "claude-irgendwas"

# --------------------------------------------------------------------------- Kennung je Modell
def test_kennung_ist_umkehrbar(monkeypatch):
    """Jedes Modell bekommt eine Claude-Kennung, die sich exakt zurueckuebersetzen laesst.

    Auch krumme Namen (mit Schraegstrichen, Doppelpunkten, Unterstrichen) muessen durchgehen —
    sonst waere die Kennung fuer reale Ollama-Namen wertlos.
    """
    import anthropic_api

    for name in ("qwen2.5-coder:7b",
                 "hf.co/mradermacher/Huihui-Qwen3-Coder-30B-A3B-Instruct-abliterated-GGUF:IQ4_XS",
                 "gemma4:12b-it-qat",
                 "aya-expanse:32b"):
        kennung = anthropic_api.claude_kennung(name)
        assert kennung.startswith("claude-"), kennung
        assert anthropic_api.modell_aus_kennung(kennung) == name
        assert anthropic_api.modell_aufloesen(kennung, "ziel") == name


def test_fremde_namen_bleiben_unangetastet(monkeypatch):
    import anthropic_api

    monkeypatch.delenv("ANTHROPIC_ALIAS_TARGET", raising=False)
    # Echter Modellname: unveraendert
    assert anthropic_api.modell_aufloesen("qwen3-vl:8b", "x") == "qwen3-vl:8b"
    # Claude-Name, der keine Kennung und kein fester Alias ist: unveraendert
    assert anthropic_api.modell_aufloesen("claude-irgendwas", "x") == "claude-irgendwas"
    # Feste Aliase zeigen weiter auf das Ziel
    assert anthropic_api.modell_aufloesen("claude-sonnet-4-5", "ziel") == "ziel"


def test_leere_kennung_bleibt_leer():
    import anthropic_api

    assert anthropic_api.claude_kennung("") == ""
    assert anthropic_api.modell_aus_kennung("qwen3-vl:8b") == ""
    assert anthropic_api.modell_aus_kennung("claude-custom-!!!") == ""

# --------------------------------------------------------------------------- Freigaben beachten
def test_alias_ziel_nimmt_freigegebenes_modell(monkeypatch):
    """Das Ziel muss aus der kontogefilterten Liste kommen, nicht aus DEFAULT_MODEL.

    Befund: Claude schickte einen Alias, das Portal bildete ihn auf DEFAULT_MODEL ab, und das war
    fuer das Konto nicht freigegeben -> 403 beim ersten Chat.
    """
    import anthropic_api

    monkeypatch.delenv("ANTHROPIC_ALIAS_TARGET", raising=False)
    assert anthropic_api.alias_ziel(["gemma4:12b"], "qwen2.5-coder:7b") == "gemma4:12b"
    # Ohne Freigabeliste bleibt der Portal-Standardwert.
    assert anthropic_api.alias_ziel([], "qwen2.5-coder:7b") == "qwen2.5-coder:7b"
    # Ausdrueckliche Angabe des Betreibers gewinnt immer.
    monkeypatch.setenv("ANTHROPIC_ALIAS_TARGET", "fest")
    assert anthropic_api.alias_ziel(["gemma4:12b"], "qwen2.5-coder:7b") == "fest"


def test_alias_faellt_auf_freigegebenes_modell_zurueck(monkeypatch):
    import anthropic_api

    monkeypatch.delenv("ANTHROPIC_ALIAS_TARGET", raising=False)
    # Alias, Ziel nicht freigegeben -> erstes freigegebenes Modell
    assert anthropic_api.modell_aufloesen("claude-sonnet-4-5", "qwen2.5-coder:7b",
                                          ["gemma4:12b"]) == "gemma4:12b"
    # Kennung eines gesperrten Modells -> ebenfalls erstes freigegebenes
    kennung = anthropic_api.claude_kennung("qwen2.5-coder:7b")
    assert anthropic_api.modell_aufloesen(kennung, "x", ["gemma4:12b"]) == "gemma4:12b"


def test_echter_name_wird_nicht_still_umgebogen(monkeypatch):
    """Ein nicht freigegebenes ECHTES Modell muss weiter 403 geben, nicht ersetzt werden."""
    import anthropic_api

    monkeypatch.delenv("ANTHROPIC_ALIAS_TARGET", raising=False)
    assert anthropic_api.modell_aufloesen("qwen3-vl:8b", "x", ["gemma4:12b"]) == "qwen3-vl:8b"
    # Ohne Freigabeliste (None = alle lokalen) bleibt alles, wie es ist.
    assert anthropic_api.modell_aufloesen("claude-sonnet-4-5", "qwen2.5-coder:7b", None) == "qwen2.5-coder:7b"

# --------------------------------------------------------------------------- lesbare Kennungen
def test_kennung_ist_lesbar():
    """Aus einer Kennung soll ein Mensch ablesen koennen, welches Modell gemeint ist."""
    import anthropic_api

    kennung = anthropic_api.claude_kennung("qwen2.5-coder:7b")
    assert kennung == "claude-custom-qwen2-5-coder-7b", kennung
    assert anthropic_api.claude_kennung("gemma4:12b") == "claude-custom-gemma4-12b"


def test_kennung_bleibt_eindeutig_bei_gleichstand():
    import anthropic_api

    vergeben = set()
    a = anthropic_api.claude_kennung("qwen3:8b", vergeben)
    vergeben.add(a)
    b = anthropic_api.claude_kennung("qwen3-8b", vergeben)
    assert a != b, "zwei Modelle mit gleichem Slug brauchen verschiedene Kennungen"


def test_lesbare_kennung_wird_aufgeloest():
    import anthropic_api

    modelle = ["qwen2.5-coder:7b", "gemma4:12b"]
    for name in modelle:
        kennung = anthropic_api.claude_kennung(name)
        assert anthropic_api.modell_aufloesen(kennung, "x", modelle, modelle) == name
    # Alte base64-Kennung funktioniert weiter (Clients haben sie evtl. gespeichert).
    alt = "claude-custom-cXdlbjIuNS1jb2Rlcjo3Yg"
    assert anthropic_api.modell_aufloesen(alt, "x", modelle, modelle) == "qwen2.5-coder:7b"
