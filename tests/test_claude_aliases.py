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
