"""Sicherheitsfix 2026-11-02: PayPals IPN wird beim Anbieter verifiziert.

Der Befund: /payments/paypal/ipn nahm jede POST-Meldung an und schrieb bei
payment_status=Completed Guthaben gut, ohne PayPal zu fragen. Dazu kamen vier
weitere Pfade (stripe/success, alipay/success, applepay/success,
stripe/simulate-success) und der Mock-Webhook, die ohne Anbieter-Bestaetigung
gutgeschrieben haben.

Diese Tests pinnen:
  1. Die Verifikation schickt den *Rohtext* unveraendert plus
     cmd=_notify-validate an PayPal und akzeptiert nur "VERIFIED".
  2. Ohne VERIFIED -> HTTP 400 und kein Guthaben.
  3. Betrag/Waehrung/Empfaenger muessen passen.
  4. Dieselbe txn_id schreibt nur einmal gut (auch nicht auf einen zweiten
     Auftrag).
  5. Alle Mock-Pfade sind ohne PAYMENTS_ALLOW_MOCK=1 geschlossen.

Run:  python -m pytest tests/test_payment_verification.py -q
"""
import asyncio

import httpx
import pytest

import payments
from models import Payment, get_user_credits


@pytest.fixture(autouse=True)
def _production_env(monkeypatch):
    """Produktionszustand: keine Mock-Gutschriften, Sandbox-IPN-URL."""
    monkeypatch.delenv("PAYMENTS_ALLOW_MOCK", raising=False)
    monkeypatch.setenv("PAYPAL_MODE", "sandbox")
    monkeypatch.delenv("PAYPAL_IPN_URL", raising=False)
    monkeypatch.delenv("PAYPAL_RECEIVER_EMAIL", raising=False)
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)


@pytest.fixture
def verified(monkeypatch):
    """Tut so, als haette PayPal die Meldung mit VERIFIED bestaetigt."""
    calls = []

    async def _fake(raw_body, transport=None):
        calls.append(raw_body)
        return True

    monkeypatch.setattr(payments, "_paypal_verify_ipn", _fake)
    return calls


@pytest.fixture
def rejected(monkeypatch):
    """PayPal antwortet INVALID (bzw. ist nicht erreichbar)."""
    calls = []

    async def _fake(raw_body, transport=None):
        calls.append(raw_body)
        return False

    monkeypatch.setattr(payments, "_paypal_verify_ipn", _fake)
    return calls


def _register(client, email, password="test123456"):
    """Registrieren, freigeben, einloggen — liefert user_id + nutzbaren Schluessel."""
    import os

    r = client.post("/auth/register", json={
        "email": email, "name": "IPN Test", "password": password,
        "role": "both", "initial_credits": 0,
    })
    assert r.status_code in (200, 201), r.text
    body = r.json()

    admin_headers = {"Authorization": f"Bearer {os.environ['ADMIN_TOKEN']}"}
    client.post(f"/admin/registrations/{body['user_id']}/approve", headers=admin_headers)

    login = client.post("/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    return {"user_id": body["user_id"], "api_key": login.json()["api_key"]}


def _pending_payment(db, user_id, amount=10.0, credits=1000):
    p = Payment(
        user_id=user_id, provider="paypal", amount=amount, currency="EUR",
        status="pending", credits_added=credits, transaction_id="PAYPAL-UNITTEST",
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _ipn(payment, **overrides):
    form = {
        "txn_type": "web_accept",
        "payment_status": "Completed",
        "txn_id": f"TXN-{payment.id}",
        "custom": f"payment_id:{payment.id}",
        "mc_gross": f"{payment.amount:.2f}",
        "mc_currency": "EUR",
        "receiver_email": "shop@example.com",
        "payer_email": "kunde@example.com",
    }
    form.update(overrides)
    return {k: v for k, v in form.items() if v is not None}


# ---------------------------------------------------------------------------
# 1. Das Protokoll selbst
# ---------------------------------------------------------------------------
def test_verification_echoes_raw_body_with_notify_validate(monkeypatch):
    """PayPal verlangt die Meldung *unveraendert*, in derselben Kodierung."""
    raw = b"mc_gross=10.00&custom=payment_id%3A7&txn_id=ABC&payment_status=Completed"
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.content
        seen["ctype"] = request.headers.get("content-type", "")
        return httpx.Response(200, text="VERIFIED")

    ok = asyncio.run(payments._paypal_verify_ipn(
        raw, transport=httpx.MockTransport(handler)
    ))
    assert ok is True
    assert seen["body"] == raw + b"&cmd=_notify-validate"
    assert seen["url"] == "https://ipnpb.sandbox.paypal.com/cgi-bin/webscr"
    assert seen["ctype"].startswith("application/x-www-form-urlencoded")


def test_verification_rejects_invalid_answer():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="INVALID")

    assert asyncio.run(payments._paypal_verify_ipn(
        b"txn_id=FAKE", transport=httpx.MockTransport(handler)
    )) is False


def test_verification_fails_closed_on_network_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("kein Netz")

    assert asyncio.run(payments._paypal_verify_ipn(
        b"txn_id=FAKE", transport=httpx.MockTransport(handler)
    )) is False


def test_verification_rejects_empty_body():
    assert asyncio.run(payments._paypal_verify_ipn(b"")) is False


def test_ipn_url_follows_mode(monkeypatch):
    monkeypatch.setenv("PAYPAL_MODE", "live")
    assert payments.paypal_ipn_url() == "https://ipnpb.paypal.com/cgi-bin/webscr"
    monkeypatch.setenv("PAYPAL_MODE", "sandbox")
    assert payments.paypal_ipn_url() == "https://ipnpb.sandbox.paypal.com/cgi-bin/webscr"
    monkeypatch.setenv("PAYPAL_IPN_URL", "http://127.0.0.1:9999/cgi-bin/webscr")
    assert payments.paypal_ipn_url() == "http://127.0.0.1:9999/cgi-bin/webscr"


# ---------------------------------------------------------------------------
# 2. Der Endpunkt
# ---------------------------------------------------------------------------
def test_forged_ipn_is_rejected_and_credits_nothing(client, db_session, rejected):
    """Der Kern des Befunds: gefaelschte IPN -> 400, kein Guthaben."""
    user = _register(client, "ipn-forged@example.com")
    payment = _pending_payment(db_session, user["user_id"])
    before = get_user_credits(db_session, user["user_id"])

    r = client.post("/payments/paypal/ipn", data=_ipn(payment))

    assert r.status_code == 400, r.text
    assert len(rejected) == 1, "die Verifikation wurde nicht aufgerufen"
    db_session.expire_all()
    assert get_user_credits(db_session, user["user_id"]) == before
    assert db_session.query(Payment).filter(Payment.id == payment.id).first().status == "pending"


def test_amount_mismatch_is_rejected(client, db_session, verified):
    user = _register(client, "ipn-amount@example.com")
    payment = _pending_payment(db_session, user["user_id"], amount=10.0)
    before = get_user_credits(db_session, user["user_id"])

    r = client.post("/payments/paypal/ipn", data=_ipn(payment, mc_gross="0.01"))

    assert r.status_code == 400, r.text
    assert "amount" in r.json()["detail"].lower()
    db_session.expire_all()
    assert get_user_credits(db_session, user["user_id"]) == before
    assert db_session.query(Payment).filter(Payment.id == payment.id).first().status == "pending"


def test_wrong_currency_is_rejected(client, db_session, verified):
    user = _register(client, "ipn-currency@example.com")
    payment = _pending_payment(db_session, user["user_id"])
    r = client.post("/payments/paypal/ipn", data=_ipn(payment, mc_currency="USD"))
    assert r.status_code == 400, r.text


def test_wrong_receiver_is_rejected(client, db_session, verified, monkeypatch):
    monkeypatch.setenv("PAYPAL_RECEIVER_EMAIL", "shop@example.com")
    user = _register(client, "ipn-receiver@example.com")
    payment = _pending_payment(db_session, user["user_id"])
    before = get_user_credits(db_session, user["user_id"])

    r = client.post("/payments/paypal/ipn", data=_ipn(payment, receiver_email="boese@example.net"))

    assert r.status_code == 400, r.text
    db_session.expire_all()
    assert get_user_credits(db_session, user["user_id"]) == before


def test_not_completed_credits_nothing(client, db_session, verified):
    user = _register(client, "ipn-pending@example.com")
    payment = _pending_payment(db_session, user["user_id"])
    before = get_user_credits(db_session, user["user_id"])

    r = client.post("/payments/paypal/ipn", data=_ipn(payment, payment_status="Pending"))

    assert r.status_code == 200, r.text
    assert r.json()["handled"] is False
    db_session.expire_all()
    assert get_user_credits(db_session, user["user_id"]) == before


def test_unbound_ipn_is_rejected(client, db_session, verified):
    user = _register(client, "ipn-nobind@example.com")
    payment = _pending_payment(db_session, user["user_id"])
    r = client.post("/payments/paypal/ipn", data=_ipn(payment, custom=None))
    assert r.status_code == 400, r.text


def test_verified_ipn_credits_once_and_is_idempotent(client, db_session, verified):
    user = _register(client, "ipn-idem@example.com")
    payment = _pending_payment(db_session, user["user_id"], amount=10.0, credits=1000)
    before = get_user_credits(db_session, user["user_id"])

    first = client.post("/payments/paypal/ipn", data=_ipn(payment))
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "succeeded"

    db_session.expire_all()
    after_first = get_user_credits(db_session, user["user_id"])
    assert after_first == before + 1000

    # Dieselbe txn_id ein zweites Mal: keine zweite Gutschrift.
    again = client.post("/payments/paypal/ipn", data=_ipn(payment))
    assert again.status_code == 200, again.text
    assert again.json()["status"] == "already_succeeded"

    db_session.expire_all()
    assert get_user_credits(db_session, user["user_id"]) == after_first


def test_same_txn_id_cannot_credit_a_second_payment(client, db_session, verified):
    user = _register(client, "ipn-replay@example.com")
    first = _pending_payment(db_session, user["user_id"], amount=10.0, credits=1000)
    second = _pending_payment(db_session, user["user_id"], amount=10.0, credits=1000)
    before = get_user_credits(db_session, user["user_id"])

    assert client.post("/payments/paypal/ipn", data=_ipn(first)).status_code == 200

    replay = client.post("/payments/paypal/ipn", data=_ipn(second, txn_id=f"TXN-{first.id}"))
    assert replay.status_code == 400, replay.text

    db_session.expire_all()
    assert get_user_credits(db_session, user["user_id"]) == before + 1000
    assert db_session.query(Payment).filter(Payment.id == second.id).first().status == "pending"


# ---------------------------------------------------------------------------
# 3. Die anderen Gutschrift-Pfade
# ---------------------------------------------------------------------------
def test_mock_paypal_capture_is_closed(client, db_session):
    user = _register(client, "mock-capture@example.com")
    payment = _pending_payment(db_session, user["user_id"])
    before = get_user_credits(db_session, user["user_id"])
    headers = {"Authorization": f"Bearer {user['api_key']}"}

    r = client.get(f"/payments/paypal/capture?payment_id={payment.id}&mock=1",
                   headers=headers, follow_redirects=False)

    assert r.status_code == 503, r.text
    db_session.expire_all()
    assert get_user_credits(db_session, user["user_id"]) == before


def test_simulate_success_is_hidden_without_mock_flag(client, db_session):
    user = _register(client, "mock-simulate@example.com")
    payment = _pending_payment(db_session, user["user_id"])
    headers = {"Authorization": f"Bearer {user['api_key']}"}

    r = client.post(f"/payments/stripe/simulate-success?payment_id={payment.id}",
                    headers=headers)

    assert r.status_code == 404, r.text


def test_stripe_webhook_without_secret_is_closed(client, db_session):
    user = _register(client, "stripe-hook@example.com")
    payment = _pending_payment(db_session, user["user_id"])
    before = get_user_credits(db_session, user["user_id"])

    r = client.post("/payments/stripe/webhook", json={
        "type": "checkout.session.completed",
        "data": {"object": {"metadata": {"payment_id": str(payment.id)}}},
    })

    assert r.status_code == 503, r.text
    db_session.expire_all()
    assert get_user_credits(db_session, user["user_id"]) == before


def test_stripe_success_without_confirmation_is_closed(client, db_session):
    user = _register(client, "stripe-success@example.com")
    payment = _pending_payment(db_session, user["user_id"])
    headers = {"Authorization": f"Bearer {user['api_key']}"}
    before = get_user_credits(db_session, user["user_id"])

    r = client.get(f"/payments/stripe/success?payment_id={payment.id}", headers=headers)

    assert r.status_code == 503, r.text
    db_session.expire_all()
    assert get_user_credits(db_session, user["user_id"]) == before


def test_alipay_and_applepay_success_without_confirmation_are_closed(client, db_session):
    user = _register(client, "wallet-success@example.com")
    headers = {"Authorization": f"Bearer {user['api_key']}"}
    before = get_user_credits(db_session, user["user_id"])

    for path, param in (("alipay", "session_id"), ("applepay", "payment_intent")):
        payment = _pending_payment(db_session, user["user_id"])
        r = client.get(f"/payments/{path}/success?payment_id={payment.id}&{param}=fake_ref",
                       headers=headers)
        assert r.status_code == 503, f"{path}: {r.status_code} {r.text}"

    db_session.expire_all()
    assert get_user_credits(db_session, user["user_id"]) == before


def test_mock_flag_still_allows_development_flow(client, db_session, monkeypatch):
    """PAYMENTS_ALLOW_MOCK=1 haelt den Entwicklungsfluss am Leben."""
    monkeypatch.setenv("PAYMENTS_ALLOW_MOCK", "1")
    user = _register(client, "mock-dev@example.com")
    payment = _pending_payment(db_session, user["user_id"], amount=10.0, credits=1000)
    headers = {"Authorization": f"Bearer {user['api_key']}"}
    before = get_user_credits(db_session, user["user_id"])

    r = client.get(f"/payments/stripe/success?payment_id={payment.id}", headers=headers)

    assert r.status_code == 200, r.text
    db_session.expire_all()
    assert get_user_credits(db_session, user["user_id"]) == before + 1000
