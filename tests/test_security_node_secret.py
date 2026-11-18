"""SEC-01/01b: Waechter fuer das Node-Geheimnis und die Adresspruefung.

Der Kern des Befunds war: das globale `NODE_SHARED_SECRET` ging an eine vom Benutzer gewaehlte
Adresse. Diese Tests halten fest, dass es das nicht mehr tut — und dass die Adresspruefung LAN-
Adressen weiter erlaubt (sonst waere das Produkt kaputt).
"""

import os
import sys
import types

import pytest


def _node(**kwargs):
    """Minimaler Node-Ersatz mit dem einen Feld, das zaehlt."""
    felder = {"id": 1, "api_key_hash": "", "agent_version": "0.6.28"}
    felder.update(kwargs)
    return types.SimpleNamespace(**felder)


# --------------------------------------------------------------------------- Header
def test_header_enthaelt_nie_das_globale_secret(monkeypatch):
    import hashlib
    import hmac

    import pool

    monkeypatch.setenv("NODE_SHARED_SECRET", "SUPER-SECRET-NODE-SHARED-KEY")
    monkeypatch.delenv("ALLOW_LEGACY_NODE_SECRET", raising=False)

    knoten = _node(api_key_hash=hashlib.sha256(b"gpu_nodekey").hexdigest())
    kopf = pool.node_request_headers(knoten)

    assert kopf["X-Node-Secret"] != "SUPER-SECRET-NODE-SHARED-KEY"
    erwartet = hmac.new(knoten.api_key_hash.encode(), b"comesh-portal-v1", hashlib.sha256).hexdigest()
    assert kopf["X-Node-Secret"] == erwartet


def test_ohne_node_kein_header(monkeypatch):
    """Ohne Node-Objekt gibt es nichts abzuleiten — dann bleibt der Kopf leer (fail closed)."""
    import pool

    monkeypatch.setenv("NODE_SHARED_SECRET", "SUPER-SECRET-NODE-SHARED-KEY")
    monkeypatch.delenv("ALLOW_LEGACY_NODE_SECRET", raising=False)
    assert pool.node_request_headers() == {}
    assert pool.node_request_headers(_node()) == {}


def test_legacy_schalter_schickt_das_secret_nur_auf_ansage(monkeypatch):
    """Die Uebergangszeit ist ausdruecklich: nur mit ALLOW_LEGACY_NODE_SECRET=1."""
    import pool

    monkeypatch.setenv("NODE_SHARED_SECRET", "SUPER-SECRET-NODE-SHARED-KEY")
    monkeypatch.setenv("ALLOW_LEGACY_NODE_SECRET", "1")
    kopf = pool.node_request_headers(_node())     # Node ohne Schluessel-Hash
    assert kopf["X-Node-Secret"] == "SUPER-SECRET-NODE-SHARED-KEY"


# --------------------------------------------------------------------------- Adresspruefung
@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "gopher://127.0.0.1:11435",
    "ftp://example.com",
])
def test_fremde_schemata_abgelehnt(url):
    from netinfo import node_url_is_allowed

    assert node_url_is_allowed(url) is False


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:11435",
    "http://localhost:11435",
    "http://169.254.169.254/latest/meta-data",
    "http://[::1]:11435",
    "http://0.0.0.0:11435",
])
def test_loopback_und_link_local_abgelehnt(url):
    from netinfo import node_url_is_allowed

    assert node_url_is_allowed(url) is False


@pytest.mark.parametrize("url", [
    "http://192.168.1.50:11435",
    "http://10.0.0.42:11435",
    "http://172.16.5.9:11435",
])
def test_lan_adressen_bleiben_erlaubt(url):
    """CoMesh lebt davon, dass Nodes im LAN haengen — hier darf nichts blockieren."""
    from netinfo import node_url_is_allowed

    assert node_url_is_allowed(url) is True


def test_normalisieren_verwirft_fremde_schemata():
    from netinfo import normalize_node_url

    assert normalize_node_url("file:///etc/passwd") is None
    assert normalize_node_url("192.168.1.50:11435") == "http://192.168.1.50:11435"


def test_registrierung_lehnt_loopback_mit_422_ab(monkeypatch):
    from fastapi import HTTPException

    import nodes

    monkeypatch.delenv("ALLOW_RESTRICTED_NODE_URLS", raising=False)
    with pytest.raises(HTTPException) as fehler:
        nodes.resolve_node_url("http://127.0.0.1:11435", None, 11435)
    assert fehler.value.status_code == 422

    # Notausgang fuer getrennte Deployments
    monkeypatch.setenv("ALLOW_RESTRICTED_NODE_URLS", "1")
    assert nodes.resolve_node_url("http://127.0.0.1:11435", None, 11435) == "http://127.0.0.1:11435"


# --------------------------------------------------------------------------- Agentenseite
def _agent_modul(monkeypatch, node_key="gpu_nodekey"):
    """Laedt node-agent/agent.py als Modul (ohne Serverstart)."""
    monkeypatch.setenv("NODE_API_KEY", node_key)
    monkeypatch.setenv("NODE_ID", "1")
    monkeypatch.setenv("PORTAL_URL", "http://127.0.0.1:9")
    pfad = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "node-agent")
    if pfad not in sys.path:
        sys.path.insert(0, pfad)
    import importlib

    # Der Agent hat sein *eigenes* netinfo.py (mit gpu_summary). Das Portal-Modul gleichen Namens
    # liegt sonst schon im Modulcache, und der Import scheitert an einer fehlenden Funktion.
    for name in ("agent", "netinfo"):
        sys.modules.pop(name, None)
    try:
        return importlib.import_module("agent")
    finally:
        # Wichtig: der Agent bringt sein eigenes netinfo mit. Bliebe es im Modulcache, braechen
        # anschliessend alle Portal-Tests, weil dort `node_url_is_allowed` fehlt.
        sys.modules.pop("netinfo", None)
        if pfad in sys.path:
            sys.path.remove(pfad)


def test_agent_berechnet_dasselbe_token_wie_das_portal(monkeypatch):
    import hashlib

    import pool

    agent = _agent_modul(monkeypatch, node_key="gpu_nodekey")
    portal_token = pool.node_token_for(_node(api_key_hash=hashlib.sha256(b"gpu_nodekey").hexdigest()))
    assert agent._portal_token() == portal_token
    assert len(portal_token) == 64


def test_agent_ist_ohne_secret_nicht_mehr_offen(monkeypatch):
    """Mit Node-Key verlangt der Agent das Token — auch wenn NODE_SHARED_SECRET fehlt."""
    from fastapi.testclient import TestClient

    monkeypatch.delenv("NODE_SHARED_SECRET", raising=False)
    monkeypatch.delenv("NODE_ALLOW_LEGACY_SHARED_SECRET", raising=False)
    agent = _agent_modul(monkeypatch)

    with TestClient(agent.app) as c:
        ohne = c.post("/v1/chat/completions", json={"model": "m", "messages": []})
        falsch = c.post("/v1/chat/completions", json={"model": "m", "messages": []},
                        headers={"X-Node-Secret": "irgendwas"})
        richtig = c.post("/v1/chat/completions", json={"model": "m", "messages": []},
                         headers={"X-Node-Secret": agent._portal_token()})

    assert ohne.status_code == 401, ohne.text
    assert falsch.status_code == 401, falsch.text
    # Mit gueltigem Token kommt die Anfrage durch die Sperre (Antwort danach ist Sache des Routers).
    assert richtig.status_code != 401, richtig.text
