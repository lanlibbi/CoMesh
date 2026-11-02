"""Sicherheitsfix 2026-11-02: Die Login-Sperre darf nicht pro Proxy keyen.

Befund: nginx setzte X-Real-IP auf $remote_addr, und $remote_addr war hinter
Cloudflare immer 172.31.0.1 (Docker-Gateway vor dem veroeffentlichten Port).
Die Anwendung ignorierte den Header ohnehin und nahm die Socket-Adresse
(172.31.0.3, der nginx-Container). Ergebnis: ein einziger Zaehler fuer alle
Benutzer — fuenf Fehlversuche sperrten die ganze Installation.

Diese Tests pinnen die Auswertung in ratelimit.client_ip():
  * ohne TRUST_PROXY_HEADERS bleibt die Socket-Adresse massgeblich
  * mit Flag + vertrauenswuerdigem Peer gewinnt X-Real-IP
  * ein nicht vertrauenswuerdiger Peer (LAN, direkt auf 8765) kann den Header
    NICHT faelschen
  * X-Forwarded-For schlaegt X-Real-IP nicht
"""
import pytest
from starlette.requests import Request

import ratelimit


def _request(peer, **headers):
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/auth/login",
        "raw_path": b"/auth/login",
        "query_string": b"",
        "server": ("api", 8000),
        "client": (peer, 45678),
        "headers": [(k.lower().replace("_", "-").encode(), v.encode())
                    for k, v in headers.items()],
    }
    return Request(scope)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("TRUST_PROXY_HEADERS", raising=False)
    monkeypatch.delenv("TRUSTED_PROXY_NETS", raising=False)


def test_without_flag_the_socket_peer_wins(monkeypatch):
    req = _request("172.31.0.3", x_real_ip="203.0.113.7")
    assert ratelimit.client_ip(req) == "172.31.0.3"

    monkeypatch.setenv("TRUST_PROXY_HEADERS", "1")
    assert ratelimit.client_ip(req) == "203.0.113.7"


def test_trusted_proxy_header_is_used(monkeypatch):
    monkeypatch.setenv("TRUST_PROXY_HEADERS", "1")
    req = _request("172.31.0.3", x_real_ip="203.0.113.7")
    assert ratelimit.client_ip(req) == "203.0.113.7"


def test_two_clients_behind_the_proxy_get_different_keys(monkeypatch):
    monkeypatch.setenv("TRUST_PROXY_HEADERS", "1")
    a = ratelimit.client_ip(_request("172.31.0.3", x_real_ip="203.0.113.7"))
    b = ratelimit.client_ip(_request("172.31.0.3", x_real_ip="198.51.100.20"))
    assert a != b
    assert ratelimit.login_keys(a, "x@example.com")[0] != ratelimit.login_keys(b, "x@example.com")[0]


def test_untrusted_peer_cannot_spoof_the_header(monkeypatch):
    """Wer die API direkt auf 8765 erreicht, darf sich keine IP aussuchen."""
    monkeypatch.setenv("TRUST_PROXY_HEADERS", "1")
    lan = _request("192.168.2.50", x_real_ip="203.0.113.7")
    assert ratelimit.client_ip(lan) == "192.168.2.50"

    tailnet = _request("100.126.79.111", x_real_ip="203.0.113.7")
    assert ratelimit.client_ip(tailnet) == "100.126.79.111"


def test_x_real_ip_wins_over_forwarded_for(monkeypatch):
    monkeypatch.setenv("TRUST_PROXY_HEADERS", "1")
    req = _request("172.31.0.3",
                   x_real_ip="203.0.113.7",
                   x_forwarded_for="1.2.3.4, 203.0.113.7")
    assert ratelimit.client_ip(req) == "203.0.113.7"


def test_forwarded_for_is_fallback_only(monkeypatch):
    monkeypatch.setenv("TRUST_PROXY_HEADERS", "1")
    req = _request("172.31.0.3", x_forwarded_for="203.0.113.7, 172.31.0.3")
    assert ratelimit.client_ip(req) == "203.0.113.7"


def test_trusted_nets_are_configurable(monkeypatch):
    monkeypatch.setenv("TRUST_PROXY_HEADERS", "1")
    monkeypatch.setenv("TRUSTED_PROXY_NETS", "10.9.0.0/16")
    assert ratelimit.client_ip(_request("172.31.0.3", x_real_ip="203.0.113.7")) == "172.31.0.3"
    assert ratelimit.client_ip(_request("10.9.4.2", x_real_ip="203.0.113.7")) == "203.0.113.7"


def test_non_ip_peer_falls_back_safely(monkeypatch):
    """Der TestClient-Peer heisst "testclient" — kein Grund fuer eine Ausnahme."""
    monkeypatch.setenv("TRUST_PROXY_HEADERS", "1")
    assert ratelimit.client_ip(_request("testclient", x_real_ip="203.0.113.7")) == "testclient"
