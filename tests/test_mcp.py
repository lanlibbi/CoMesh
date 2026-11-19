"""Tests fuer den MCP-Endpunkt."""

import json
import os
import uuid

ADMIN = {"Authorization": f"Bearer {os.environ['ADMIN_TOKEN']}"}


def _konto(client):
    email = f"mcp-{uuid.uuid4().hex[:10]}@example.test"
    r = client.post("/admin/users", headers=ADMIN,
                    json={"email": email, "name": "MCP Test", "role": "both",
                          "password": "pw-mcp-1234", "initial_credits": 5.0})
    assert r.status_code == 201, r.text
    login = client.post("/auth/login", json={"email": email, "password": "pw-mcp-1234"})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['api_key']}"}


def _rpc(client, koerper, headers):
    return client.post("/mcp", json=koerper, headers={**headers, "Accept": "application/json",
                                                      "Content-Type": "application/json"})


def test_ohne_schluessel_401(client):
    r = _rpc(client, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}, {})
    assert r.status_code == 401, r.text
    assert r.json()["error"]["code"] == -32001


def test_initialize_handshake(client):
    """Claude fragt zuerst initialize; ohne passende Antwort bricht die Verbindung ab."""
    kopf = _konto(client)
    r = _rpc(client, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                      "params": {"protocolVersion": "2025-06-18",
                                 "capabilities": {},
                                 "clientInfo": {"name": "claude", "version": "x"}}}, kopf)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["jsonrpc"] == "2.0" and d["id"] == 1
    erg = d["result"]
    assert erg["protocolVersion"], erg
    assert "tools" in erg["capabilities"], erg
    assert erg["serverInfo"]["name"] == "comesh"


def test_benachrichtigung_bekommt_202(client):
    kopf = _konto(client)
    r = _rpc(client, {"jsonrpc": "2.0", "method": "notifications/initialized"}, kopf)
    assert r.status_code == 202, r.text


def test_tools_list(client):
    kopf = _konto(client)
    r = _rpc(client, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, kopf)
    assert r.status_code == 200, r.text
    namen = [t["name"] for t in r.json()["result"]["tools"]]
    assert "list_models" in namen and "ask" in namen and "whoami" in namen
    for t in r.json()["result"]["tools"]:
        assert t["inputSchema"]["type"] == "object"


def test_whoami_nennt_rolle(client):
    kopf = _konto(client)
    r = _rpc(client, {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                      "params": {"name": "whoami", "arguments": {}}}, kopf)
    assert r.status_code == 200, r.text
    erg = r.json()["result"]
    assert erg["isError"] is False
    text = erg["content"][0]["text"]
    assert "Rolle" in text and "Freigaben" in text


def test_unbekanntes_werkzeug_ist_kein_crash(client):
    kopf = _konto(client)
    r = _rpc(client, {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                      "params": {"name": "gibtsnicht", "arguments": {}}}, kopf)
    assert r.status_code == 200, r.text
    assert r.json()["result"]["isError"] is True


def test_unbekannte_methode_meldet_fehler(client):
    kopf = _konto(client)
    r = _rpc(client, {"jsonrpc": "2.0", "id": 5, "method": "resources/list", "params": {}}, kopf)
    assert r.status_code == 200, r.text
    assert r.json()["error"]["code"] == -32601


def test_selbstauskunft_ueber_get(client):
    r = client.get("/mcp")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["protocol"] and "list_models" in d["tools"]
