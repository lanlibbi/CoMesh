"""
Tests for the credits feature flag (config.yaml: credits_enabled).

Scope: prove that the flag — not the code path — decides whether usage is
metered, so it can be flipped back on later without a code change or migration.

  1. flag OFF -> a request with a zero/negative balance succeeds (no HTTP 402)
  2. flag ON  -> the same request is refused with 402 (legacy behaviour intact)
  3. flag OFF -> no CreditTransaction is booked for a successful request
  4. flag ON  -> exactly one CreditTransaction is booked (balance decreases)
  5. the flag is advertised on /v1/me, /health and /payments/config so any UI can
     hide or show the billing surfaces without a redeploy

No GPU/Ollama is needed: pool.route_request is stubbed with a canned OpenAI-shaped
response, so the tests exercise the portal's own accounting, not the model.

Run from the repo root:
    .venv/bin/pytest tests/test_credits_flag.py -q
"""
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# database.py resolves its SQLite path at import time -> point DATA_DIR at a
# throwaway directory before importing anything that pulls in the app.
_TMP_DATA_DIR = tempfile.mkdtemp(prefix="gpu-pool-credits-tests-")
os.environ.setdefault("DATA_DIR", _TMP_DATA_DIR)
os.environ.setdefault("SEED_KEY_PATH", os.path.join(_TMP_DATA_DIR, "seed_api_key.txt"))
os.environ.setdefault("ADMIN_API_KEY", "gpu_testadmin000000000000000000000000000000")

pytestmark = pytest.mark.credits


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def client():
    from main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture
def flag():
    """Set credits_enabled (env override) for one test; restore afterwards."""
    import config

    original_env = os.environ.get("CREDITS_ENABLED")
    original_cache = dict(config.get_config())

    def _set(enabled: bool):
        os.environ["CREDITS_ENABLED"] = "1" if enabled else "0"
        config.reload_config()
        assert config.credits_enabled() is enabled, "flag override did not take effect"

    yield _set

    if original_env is None:
        os.environ.pop("CREDITS_ENABLED", None)
    else:
        os.environ["CREDITS_ENABLED"] = original_env
    config._cache.clear()
    config._cache.update(original_cache)


def _new_user(client, initial_credits: float = 0.0):
    """Register a fresh user and return (headers, user_id, api_key)."""
    email = f"credits-{uuid.uuid4().hex[:10]}@example.com"
    r = client.post("/auth/register", json={
        "email": email, "name": "Credits Test", "password": "pw12345",
        "role": "both", "initial_credits": initial_credits,
    })
    assert r.status_code == 200, r.text
    body = r.json()

    # Legacy-Tests pruefen den Balance-Pfad: Tester auf quota_mode=balance
    # (Default seit Admin-Quota-Feature: 'unlimited' wuerde nie abbuchen)
    from database import SessionLocal as _SL
    from models import User as _U
    _db = _SL()
    try:
        _u = _db.query(_U).filter(_U.id == body["user_id"]).first()
        if _u is not None:
            _u.quota_mode = "balance"
            _db.commit()
    finally:
        _db.close()
    return {"Authorization": f"Bearer {body['api_key']}"}, body["user_id"], body["api_key"]


def _stub_upstream(monkeypatch, tokens: int = 1000):
    """Replace the pool router with a canned successful OpenAI-shaped response."""
    import pool

    async def fake_route_request(db, user, ollama_payload, model):
        return {
            "ok": True,
            "source": "local",
            "node_id": None,
            "error": None,
            "response": {
                "model": model,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"},
                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": tokens // 2, "completion_tokens": tokens // 2,
                          "total_tokens": tokens},
            },
        }

    monkeypatch.setattr(pool, "route_request", fake_route_request)


def _chat(client, headers):
    return client.post("/v1/chat/completions", headers=headers, json={
        "model": "qwen2.5-coder:7b",
        "messages": [{"role": "user", "content": "hi"}],
    })


def _credit_rows(db_session, user_id):
    from models import CreditTransaction
    return db_session.query(CreditTransaction).filter(
        CreditTransaction.user_id == user_id
    ).all()


@pytest.fixture(scope="module")
def db_session():
    from database import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 1 + 2: the request gate
# ---------------------------------------------------------------------------
def test_chat_without_credits_succeeds_when_flag_off(client, flag, monkeypatch):
    """Requests run unlimited: a 0-balance account is not refused."""
    flag(False)
    _stub_upstream(monkeypatch)
    headers, _, _ = _new_user(client, initial_credits=0.0)

    r = _chat(client, headers)
    assert r.status_code == 200, f"flag off must not enforce a balance: {r.status_code} {r.text}"
    assert r.json()["choices"][0]["message"]["content"] == "ok"


def test_chat_without_credits_is_402_when_flag_on(client, flag, monkeypatch):
    """Legacy behaviour survives: flipping the flag back on re-enables the gate."""
    flag(True)
    _stub_upstream(monkeypatch)
    headers, _, _ = _new_user(client, initial_credits=0.0)

    r = _chat(client, headers)
    assert r.status_code == 402, f"flag on must enforce the balance: {r.status_code} {r.text}"
    assert "insufficient credits" in r.json()["detail"].lower()


def test_flag_off_does_not_charge_the_account(client, flag, monkeypatch, db_session):
    flag(False)
    _stub_upstream(monkeypatch, tokens=2000)
    headers, user_id, _ = _new_user(client, initial_credits=0.0)
    before = len(_credit_rows(db_session, user_id))

    assert _chat(client, headers).status_code == 200
    db_session.expire_all()

    rows = _credit_rows(db_session, user_id)
    assert len(rows) == before, "no charge may be booked while credits are disabled"
    assert not any(row.amount < 0 for row in rows), "the balance must not go negative"


def test_flag_on_charges_the_account(client, flag, monkeypatch, db_session):
    flag(True)
    _stub_upstream(monkeypatch, tokens=2000)
    headers, user_id, _ = _new_user(client, initial_credits=5.0)
    before = len(_credit_rows(db_session, user_id))

    assert _chat(client, headers).status_code == 200
    db_session.expire_all()

    rows = _credit_rows(db_session, user_id)
    assert len(rows) == before + 1, "exactly one charge per request"
    charge = rows[-1]
    assert charge.amount < 0
    assert "chat:" in charge.reason


def test_flag_off_keeps_usage_rows_for_later_billing(client, flag, monkeypatch, db_session):
    """Token accounting is data, not enforcement — it must keep being recorded."""
    from models import Usage

    flag(False)
    _stub_upstream(monkeypatch, tokens=1234)
    headers, user_id, _ = _new_user(client, initial_credits=0.0)

    assert _chat(client, headers).status_code == 200
    db_session.expire_all()

    rows = db_session.query(Usage).filter(Usage.user_id == user_id).all()
    assert rows and rows[-1].total_tokens == 1234


# ---------------------------------------------------------------------------
# 3: the flag is observable by the UI
# ---------------------------------------------------------------------------
def test_flag_is_exposed_to_clients(client, flag):
    flag(False)
    headers, _, api_key = _new_user(client, initial_credits=0.0)

    me = client.get("/v1/me", headers=headers)
    assert me.status_code == 200, me.text
    assert me.json()["credits_enabled"] is False

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["credits_enabled"] is False

    cfg = client.get("/payments/config", headers=headers)
    assert cfg.status_code == 200, cfg.text
    assert cfg.json()["credits_enabled"] is False

    # The login/register payload must carry it too, or a fresh session would
    # render the billing surfaces until the first /v1/me refresh.
    login = client.post("/auth/login", json={
        "email": client.get("/v1/me", headers=headers).json()["email"],
        "password": "pw12345",
    })
    assert login.status_code == 200, login.text
    assert login.json()["credits_enabled"] is False

    # Login rotates the key (the old one is revoked), so flip the flag and
    # re-check with the key the login just issued.
    flag(True)
    fresh = {"Authorization": f"Bearer {login.json()['api_key']}"}
    assert client.get("/v1/me", headers=fresh).json()["credits_enabled"] is True
