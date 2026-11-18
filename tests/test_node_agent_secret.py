"""Der Node-Agent darf nicht ohne gemeinsames Geheimnis antworten.

Hintergrund (Fix 03.11.2026): `/v1/chat/completions` nahm jede Anfrage ohne
Schluessel an und leitete sie an das lokale Ollama weiter; `/health` verriet
ungemeldet Node-Id, GPU und Speicher. Schutz war allein die Bindung an die
Tailscale-Adresse.

Der Test importiert `node-agent/agent.py` isoliert (eigener Pfad, eigenes
netinfo — wie tests/test_node_agent_reconnect.py) und faehrt die App mit dem
FastAPI-Testclient. Er braucht kein Portal, keine GPU und kein Ollama.
"""
import importlib
import os
import sys
from pathlib import Path

import pytest

AGENT_DIR = Path(__file__).resolve().parents[1] / "node-agent"
SECRET = "test-shared-secret-0123456789"


@pytest.fixture(scope="module")
def agent_app():
    saved = {k: os.environ.get(k) for k in ("NODE_ID", "NODE_API_KEY", "PORTAL_URL", "NODE_SHARED_SECRET")}
    os.environ["NODE_ID"] = "1"
    os.environ["NODE_API_KEY"] = "test-key"
    os.environ["PORTAL_URL"] = "http://portal.test:8765"
    os.environ["NODE_SHARED_SECRET"] = SECRET
    sys.path.insert(0, str(AGENT_DIR))
    try:
        sys.modules.pop("netinfo", None)
        sys.modules.pop("agent", None)
        module = importlib.import_module("agent")
    finally:
        sys.path.remove(str(AGENT_DIR))
        sys.modules.pop("netinfo", None)
        for k, old in saved.items():
            if old is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old
    yield module


@pytest.fixture()
def http(agent_app):
    from fastapi.testclient import TestClient

    # Ohne `with`: der Lifespan (Heartbeat-Loop) soll hier nicht starten.
    return TestClient(agent_app.app)


BODY = {"model": "irgendein-modell", "messages": [{"role": "user", "content": "hallo"}]}


def test_chat_without_header_is_rejected(http):
    r = http.post("/v1/chat/completions", json=BODY)
    assert r.status_code == 401
    assert "X-Node-Secret" in r.json()["detail"]


def test_chat_with_wrong_header_is_rejected(http):
    r = http.post("/v1/chat/completions", json=BODY, headers={"X-Node-Secret": "falsch"})
    assert r.status_code == 401


def test_root_without_header_is_rejected(http):
    assert http.get("/").status_code == 401


def test_health_without_header_is_a_bare_liveness_signal(http):
    r = http.get("/health")
    assert r.status_code == 200
    body = r.json()
    # Nur {"ok": …} — keine Node-Id, keine GPU, kein Speicher.
    assert set(body) == {"ok"}
    assert isinstance(body["ok"], bool)


def test_health_with_header_reveals_details(http):
    r = http.get("/health", headers={"X-Node-Secret": SECRET})
    assert r.status_code == 200
    body = r.json()
    assert body["node_id"] == "1"
    assert "gpu" in body


def test_ohne_secret_aber_mit_node_key_bleibt_die_sperre_zu(http, agent_app):
    """Neuer Vertrag seit SEC-01: der Node-Key genuegt, das globale Secret ist nicht noetig.

    Frueher galt: kein NODE_SHARED_SECRET -> alles offen. Weil der Agent auf 0.0.0.0 hoert, war
    das ein offener LLM-Proxy (Startwarnung hin oder her). Jetzt leitet der Agent aus seinem
    eigenen Node-Key ein Token ab und verlangt es.
    """
    secret_vorher, key_vorher = agent_app.NODE_SHARED_SECRET, agent_app.NODE_API_KEY
    agent_app.NODE_SHARED_SECRET = ""
    agent_app.NODE_API_KEY = "test-key"
    try:
        assert http.get("/").status_code == 401
        assert http.post("/v1/chat/completions", json=BODY).status_code == 401
        gueltig = {"X-Node-Secret": agent_app._portal_token()}
        assert http.get("/", headers=gueltig).status_code == 200
    finally:
        agent_app.NODE_SHARED_SECRET = secret_vorher
        agent_app.NODE_API_KEY = key_vorher


def test_ohne_secret_und_ohne_node_key_bleibt_der_alte_zustand(http, agent_app):
    """Ein Agent, der noch nie registriert wurde, hat nichts zum Ableiten — weiter offen, mit Warnung.

    Das ist der einzige verbleibende offene Fall, und er ist beim Start angesagt. Sobald ein
    Node-Key existiert (Selbstregistrierung oder agent.env), greift die Sperre.
    """
    secret_vorher, key_vorher = agent_app.NODE_SHARED_SECRET, agent_app.NODE_API_KEY
    agent_app.NODE_SHARED_SECRET = ""
    agent_app.NODE_API_KEY = ""
    try:
        assert http.get("/").status_code == 200
        assert agent_app._portal_token() == ""
    finally:
        agent_app.NODE_SHARED_SECRET = secret_vorher
        agent_app.NODE_API_KEY = key_vorher
