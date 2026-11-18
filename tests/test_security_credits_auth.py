"""Waechter fuer SEC-03 (Guthaben) und SEC-04 (Passwort-Hash).

Beide waren nicht "im Code kaputt", sondern an einer Stelle anders als an der anderen: der
Admin-Pfad hatte Grenzen und PBKDF2, der Self-Registration-Pfad und das Admin-Anlegen nicht.
Diese Tests vergleichen die beiden Wege, damit sie nicht wieder auseinanderlaufen.
"""

import uuid


def _registrieren(client, **extra):
    koerper = {
        "email": f"sec-{uuid.uuid4().hex[:10]}@example.com",
        "name": "SEC Test",
        "password": "pw123456",
        "role": "both",
    }
    koerper.update(extra)
    r = client.post("/auth/register", json=koerper)
    assert r.status_code == 200, r.text
    return koerper["email"], r.json()


# --------------------------------------------------------------------------- SEC-03
def test_registrierung_kann_das_startguthaben_nicht_aufblaehen(client, db_session):
    """1e9 im Request darf nicht als Startguthaben landen (der Admin bucht es sonst mit)."""
    from models import User

    email, _ = _registrieren(client, initial_credits=1_000_000_000.0)
    db_session.expire_all()
    user = db_session.query(User).filter(User.email == email).first()
    assert user is not None
    assert user.signup_credits <= 1_000_000.0, user.signup_credits
    assert user.signup_credits == 100.0, f"Vorgabe erwartet, bekam {user.signup_credits}"


def test_startguthaben_kommt_aus_der_instanz(client, db_session, monkeypatch):
    """SIGNUP_CREDITS bestimmt den Wert — nicht der Registrierende."""
    from models import User

    monkeypatch.setenv("SIGNUP_CREDITS", "7.5")
    email, _ = _registrieren(client, initial_credits=999.0)
    db_session.expire_all()
    user = db_session.query(User).filter(User.email == email).first()
    assert user.signup_credits == 7.5, user.signup_credits


def test_admin_darf_startguthaben_weiterhin_setzen(client, admin_headers, db_session):
    """Der Admin-Weg behaelt das Feld (und seine Grenze) — dort ist es eine Admin-Entscheidung."""
    from models import User

    email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/admin/users", headers=admin_headers, json={
        "email": email, "name": "Admin Test", "password": "pw123456",
        "role": "both", "initial_credits": 250.0,
    })
    assert r.status_code == 201, r.text
    # Der Admin-Weg bucht das Guthaben sofort als Transaktion (statt es beim Freischalten
    # nachzuholen) — deshalb steht es nicht in signup_credits, sondern im Kontostand.
    assert r.json()["credits"] == 250.0, r.json()
    db_session.expire_all()
    user = db_session.query(User).filter(User.email == email).first()
    assert user is not None

    zu_viel = client.post("/admin/users", headers=admin_headers, json={
        "email": f"admin-{uuid.uuid4().hex[:8]}@example.com", "name": "Zu viel",
        "password": "pw123456", "role": "both", "initial_credits": 1e9,
    })
    assert zu_viel.status_code == 422, zu_viel.text


# --------------------------------------------------------------------------- SEC-04
def test_admin_angelegtes_passwort_ist_pbkdf2(client, admin_headers, db_session):
    """Vorher sha256 ohne Salt — rainbow-table-knackbar, bis der User sich einloggt."""
    from models import User

    email = f"pw-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/admin/users", headers=admin_headers, json={
        "email": email, "name": "PW Test", "password": "geheim12345",
        "role": "both", "initial_credits": 0.0,
    })
    assert r.status_code == 201, r.text
    db_session.expire_all()
    user = db_session.query(User).filter(User.email == email).first()
    assert user.password_hash.startswith("pbkdf2_sha256$"), user.password_hash[:40]

    # und der Login funktioniert mit diesem Hash
    login = client.post("/auth/login", json={"email": email, "password": "geheim12345"})
    assert login.status_code == 200, login.text


def test_passwort_aendern_im_admin_pfad_ist_pbkdf2(client, admin_headers, db_session):
    from models import User

    email = f"pw2-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/admin/users", headers=admin_headers, json={
        "email": email, "name": "PW2 Test", "password": "start12345",
        "role": "both", "initial_credits": 0.0,
    })
    assert r.status_code == 201, r.text
    db_session.expire_all()
    user = db_session.query(User).filter(User.email == email).first()

    aendern = client.patch(f"/admin/users/{user.id}", headers=admin_headers,
                           json={"password": "neues12345"})
    assert aendern.status_code == 200, aendern.text
    db_session.expire_all()
    user = db_session.query(User).filter(User.email == email).first()
    assert user.password_hash.startswith("pbkdf2_sha256$"), user.password_hash[:40]
    assert client.post("/auth/login", json={"email": email, "password": "neues12345"}).status_code == 200
