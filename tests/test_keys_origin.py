"""Tests: Schluessel loeschen und Portal-Adresse.

Geprueft wird echtes Verhalten gegen die laufende API (Fixture `client`), nicht nur das Vorhandensein
einer Route:

1. Freigeben, Schluessel ausstellen, loeschen - und danach ist er wirklich weg (nicht in der Liste
   und fuer die Authentifizierung ungueltig).
2. Ein fremder Schluessel laesst sich nicht loeschen.
3. Eine unbekannte Id liefert 404.
4. `/v1/portal-info` liefert die Adresse der Anfrage ohne Einstellung und die Einstellung, wenn
   `COMESH_PUBLIC_BASE_URL` gesetzt ist.

Hinweis zur Freigabe: Die Registrierung legt Konten absichtlich mit `is_active=False` und
`registration_status="pending"` an; erst die Freigabe durch einen Administrator macht sie nutzbar.
Der Test geht diesen Weg ueber `/admin/registrations/{id}/approve`.
"""

import uuid

import pytest

pytestmark = pytest.mark.integration


def _konto_freigeben(client, admin_headers, rolle="provider"):
    """Konto anlegen, per Admin freigeben, anmelden. Gibt (headers, email) zurueck."""
    email = f"keydel-{uuid.uuid4().hex[:10]}@example.com"
    r = client.post("/auth/register", json={
        "email": email, "name": "Key Tester", "password": "pw123456", "role": rolle,
    })
    assert r.status_code in (200, 201, 409), r.text[:200]
    user_id = r.json().get("user_id")

    if user_id:
        freigabe = client.post(f"/admin/registrations/{user_id}/approve", headers=admin_headers)
        assert freigabe.status_code in (200, 204, 409), freigabe.text[:200]

    anmeldung = client.post("/auth/login", json={"email": email, "password": "pw123456"})
    assert anmeldung.status_code == 200, anmeldung.text[:200]
    token = anmeldung.json().get("api_key") or anmeldung.json().get("token")
    return {"Authorization": f"Bearer {token}"}, email


def _schluessel_ausstellen(client, headers):
    r = client.post("/v1/me/keys", json={"password": "pw123456"}, headers=headers)
    assert r.status_code == 200, r.text[:200]
    return r.json()["api_key"]


def test_schluessel_loeschen_entfernt_ihn_wirklich(client, admin_headers):
    headers, _ = _konto_freigeben(client, admin_headers)
    schluessel = _schluessel_ausstellen(client, headers)

    assert client.get("/v1/me", headers={"Authorization": f"Bearer {schluessel}"}).status_code == 200

    liste = client.get("/v1/me/keys", headers=headers).json()
    eintrag = next(k for k in liste["keys"] if k["is_active"])
    assert "id" in eintrag, "Die Liste muss die Id liefern, sonst ist Loeschen nicht moeglich"

    weg = client.delete(f"/v1/me/keys/{eintrag['id']}", headers=headers)
    assert weg.status_code == 200, weg.text[:200]

    danach = client.get("/v1/me/keys", headers=headers).json()
    assert not any(k["id"] == eintrag["id"] for k in danach["keys"]), "Eintrag steht noch in der Liste"

    nachher = client.get("/v1/me", headers={"Authorization": f"Bearer {schluessel}"})
    assert nachher.status_code == 401, f"geloeschter Schluessel wird noch akzeptiert ({nachher.status_code})"


def test_fremden_schluessel_kann_man_nicht_loeschen(client, admin_headers):
    headers_a, _ = _konto_freigeben(client, admin_headers)
    headers_b, _ = _konto_freigeben(client, admin_headers)
    _schluessel_ausstellen(client, headers_a)

    id_a = next(k["id"] for k in client.get("/v1/me/keys", headers=headers_a).json()["keys"] if k["is_active"])

    versuch = client.delete(f"/v1/me/keys/{id_a}", headers=headers_b)
    assert versuch.status_code == 404, f"fremder Schluessel war loeschbar ({versuch.status_code})"

    assert any(k["id"] == id_a for k in client.get("/v1/me/keys", headers=headers_a).json()["keys"])


def test_unbekannte_id_liefert_404(client, admin_headers):
    headers, _ = _konto_freigeben(client, admin_headers)
    assert client.delete("/v1/me/keys/99999999", headers=headers).status_code == 404


def test_portal_info_ohne_einstellung(client, monkeypatch):
    monkeypatch.delenv("COMESH_PUBLIC_BASE_URL", raising=False)
    d = client.get("/v1/portal-info").json()
    assert d["base_url"].startswith("http"), d
    assert d["downloads_url"].endswith("/downloads"), d
    assert d["public_url_configured"] is False
    assert d["source"] == "request"
    assert d["setting"] == "COMESH_PUBLIC_BASE_URL"


def test_portal_info_mit_einstellung(client, monkeypatch):
    monkeypatch.setenv("COMESH_PUBLIC_BASE_URL", "https://portal.example.org/")
    d = client.get("/v1/portal-info").json()
    assert d["base_url"] == "https://portal.example.org", d
    assert d["downloads_url"] == "https://portal.example.org/downloads", d
    assert d["public_url_configured"] is True
    assert d["source"] == "setting"
