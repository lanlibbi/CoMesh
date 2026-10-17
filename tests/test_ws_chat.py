#!/usr/bin/env python3
"""LANA-110/112 tests: authenticated WS chat endpoint.

Covers (quota semantics asserted on real WS frames, matching the endpoint):
- bad key -> hello, then error frame status 401, close
- blocked quota_mode -> error frame 403 (even with credits ON)
- unlimited user + credits ON -> success, never 402, no charge (CreditTransaction count unchanged)
- stream=true -> status/chunk frames then final; stream=false -> final only
- invalid JSON / bad fields -> safe error frame 400/422, session stays open (Fix 4)
- subprotocol handshake: accepted_subprotocol == "api-key.<raw>" (Fix 3)
- keepalive frames while routing runs: max frame gap < 25 s (Fix 1)
- balance mode, credits 0 -> error frame 402, no booking
- balance mode with balance > cost -> exactly one booking, final.credits negative

No GPU needed: pool.route_request is stubbed like in test_credits_flag.py.
"""
import os
import sys
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

pytestmark = pytest.mark.credits

from models import ApiKey, CreditTransaction, User
from auth import generate_api_key


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


def _mk_user(db_session, quota_mode="unlimited"):
    raw, key_hash, prefix = generate_api_key()
    user = User(email=f"ws-{uuid.uuid4().hex[:8]}@test.local", name="WS User",
                password_hash="x", role="both", quota_mode=quota_mode)
    db_session.add(user)
    db_session.flush()
    db_session.add(ApiKey(user_id=user.id, key_hash=key_hash, key_prefix=prefix,
                          label="ws-test", is_active=True))
    db_session.commit()
    return user, raw


def _stub_upstream(monkeypatch, content="ws ok", tokens=1000):
    import pool

    async def fake_route_request(db, user, ollama_payload, model, on_delta=None):
        return {
            "ok": True, "source": "local", "node_id": None, "error": None,
            "response": {"model": model,
                         "choices": [{"index": 0, "message": {"role": "assistant",
                                      "content": content}, "finish_reason": "stop"}],
                         "usage": {"prompt_tokens": tokens // 2,
                                   "completion_tokens": tokens // 2,
                                   "total_tokens": tokens}},
        }

    monkeypatch.setattr(pool, "route_request", fake_route_request)


def _frames(ws, until_types=("final",), maxn=50):
    got = []
    for _ in range(maxn):
        f = ws.receive_json()
        got.append(f)
        if f.get("type") in until_types:
            break
    return got


def test_ws_bad_key_rejected(client):
    with client.websocket_connect("/ws/chat?api_key=gpu_INVALID") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello"
        err = ws.receive_json()
        assert err["type"] == "error" and err["status"] == 401


def test_ws_blocked_user_gets_403_frame(client, admin_headers, db_session, monkeypatch):
    user, raw = _mk_user(db_session, quota_mode="unlimited")
    _stub_upstream(monkeypatch)
    # set blocked
    r = client.patch(f"/admin/users/{user.id}/quota", json={"quota_mode": "blocked"},
                     headers=admin_headers)
    assert r.status_code == 200
    with client.websocket_connect(f"/ws/chat?api_key={raw}") as ws:
        ws.receive_json()  # hello
        ws.send_text('{"id":"q1","model":"m","messages":[{"role":"user","content":"hi"}]}')
        err = ws.receive_json()
        assert err["type"] == "error" and err["status"] == 403


def test_ws_unlimited_stream_success_and_no_charge(client, admin_headers, db_session, monkeypatch):
    user, raw = _mk_user(db_session, quota_mode="unlimited")
    _stub_upstream(monkeypatch, content="abcdefgh" * 10)
    before = db_session.query(CreditTransaction).count()
    with client.websocket_connect(f"/ws/chat?api_key={raw}") as ws:
        ws.receive_json()  # hello
        ws.send_text('{"id":"s1","model":"m","stream":true,"messages":[{"role":"user","content":"hi"}]}')
        frames = _frames(ws, until_types=("final",))
        types = [f["type"] for f in frames]
        assert "error" not in types
        notes = [f.get("note") for f in frames if f["type"] == "status"]
        assert "routing" in notes and "generating" in notes
        chunks = [f for f in frames if f["type"] == "chunk"]
        assert chunks, "stream=true muss chunks liefern"
        final = frames[-1]
        assert final["type"] == "final"
        assert final["content"] == "abcdefgh" * 10
    db_session.expire_all()
    after = db_session.query(CreditTransaction).count()
    assert after == before  # unlimited: keine Abbuchung


def test_ws_no_stream_final_only(client, db_session, monkeypatch):
    user, raw = _mk_user(db_session)
    _stub_upstream(monkeypatch)
    with client.websocket_connect(f"/ws/chat?api_key={raw}") as ws:
        ws.receive_json()  # hello
        ws.send_text('{"id":"n1","model":"m","stream":false,"messages":[{"role":"user","content":"hi"}]}')
        f1 = ws.receive_json()
        assert f1["type"] in ("status",)
        f2 = ws.receive_json()
        assert f2["type"] in ("status",)
        final = ws.receive_json()
        assert final["type"] == "final" and final["content"] == "ws ok"


def test_ws_invalid_json_gets_error_frame(client, db_session):
    user, raw = _mk_user(db_session)
    with client.websocket_connect(f"/ws/chat?api_key={raw}") as ws:
        ws.receive_json()  # hello
        ws.send_text("kein-json")
        err = ws.receive_json()
        assert err["type"] == "error" and err["status"] == 400

# ---------------------------------------------------------------------------
# LANA-112 additions
# ---------------------------------------------------------------------------

def _ws_frames(ws, first, until=("final",), maxn=80):
    """Send a request and collect frames until one of `until` types arrives."""
    ws.send_text(first)
    got = []
    for _ in range(maxn):
        f = ws.receive_json()
        got.append(f)
        if f.get("type") in until or f.get("type") == "error":
            break
    return got


def test_ws_subprotocol_handshake_echoes_key(client, db_session):
    """Fix 3: server must echo the offered api-key.* subprotocol."""
    user, raw = _mk_user(db_session)
    with client.websocket_connect("/ws/chat", subprotocols=[f"api-key.{raw}"]) as ws:
        assert ws.accepted_subprotocol == f"api-key.{raw}"
        assert ws.receive_json()["type"] == "hello"


def test_ws_query_param_fallback_still_works(client, db_session):
    """Fix 6 fallback: ?api_key= still authenticates when no subprotocol offered."""
    user, raw = _mk_user(db_session)
    with client.websocket_connect(f"/ws/chat?api_key={raw}") as ws:
        assert ws.receive_json()["type"] == "hello"


def test_ws_bad_frame_validation_survives_session(client, db_session, monkeypatch):
    """Fix 4: malformed max_tokens -> safe 422 error frame, session stays open."""
    user, raw = _mk_user(db_session)
    _stub_upstream(monkeypatch)
    with client.websocket_connect(f"/ws/chat?api_key={raw}") as ws:
        ws.receive_json()  # hello
        ws.send_text('{"id":"b1","model":"m","max_tokens":"nonsense","messages":[{"role":"user","content":"hi"}]}')
        err = ws.receive_json()
        assert err["type"] == "error" and err["status"] == 422
        assert "int" not in str(err.get("message", ""))  # no exception-text leak
        # session must still be usable
        frames = _ws_frames(ws, '{"id":"b2","model":"m","messages":[{"role":"user","content":"hi"}]}')
        assert frames[-1]["type"] == "final"


def test_ws_keepalive_frames_close_gap(client, db_session, monkeypatch):
    """Fix 1: while routing runs, keepalive frames flow (gap << CF idle timeout)."""
    import asyncio
    import pool
    from time import monotonic as now

    async def slow_route(db, user, ollama_payload, model, on_delta=None):
        await asyncio.sleep(3.0)
        return {
            "ok": True, "source": "local", "node_id": None, "error": None,
            "response": {"model": model,
                         "choices": [{"index": 0, "message": {"role": "assistant",
                                      "content": "slow"}, "finish_reason": "stop"}],
                         "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}},
        }

    monkeypatch.setattr(pool, "route_request", slow_route)
    import ws as ws_mod
    monkeypatch.setattr(ws_mod, "_KEEPALIVE_INTERVAL_S", 0.4)
    user, raw = _mk_user(db_session)
    with client.websocket_connect(f"/ws/chat?api_key={raw}") as ws:
        ws.receive_json()  # hello
        ws.send_text('{"id":"k1","model":"m","messages":[{"role":"user","content":"hi"}]}')
        stamps = []
        for _ in range(10):
            stamps.append((now(), ws.receive_json()))
            if stamps[-1][1].get("type") in ("final", "error"):
                break
    types = [f["type"] for _, f in stamps]
    assert types[0] == "status" and types[-1] == "final"
    gaps = [t2[0] - t1[0] for t1, t2 in zip(stamps, stamps[1:])]
    assert max(gaps) < 25.0, f"max frame gap {max(gaps):.1f}s exceeds CF-safe bound"
    assert "keepalive" in types


def test_ws_balance_mode_zero_credits_gets_402(client, admin_headers, db_session, monkeypatch, flag):
    """quota_mode=balance + empty balance -> error frame 402, no booking."""
    flag(True)
    user, raw = _mk_user(db_session)
    r = client.patch(f"/admin/users/{user.id}/quota", json={"quota_mode": "balance"},
                     headers=admin_headers)
    assert r.status_code == 200
    _stub_upstream(monkeypatch)
    before = db_session.query(CreditTransaction).count()
    with client.websocket_connect(f"/ws/chat?api_key={raw}") as ws:
        ws.receive_json()
        ws.send_text('{"id":"z1","model":"m","messages":[{"role":"user","content":"hi"}]}')
        err = ws.receive_json()
        assert err["type"] == "error" and err["status"] == 402
    db_session.expire_all()
    assert db_session.query(CreditTransaction).count() == before


def test_ws_balance_mode_books_once_and_negative_credits(client, admin_headers, db_session, monkeypatch, flag):
    """quota_mode=balance + balance > cost -> exactly one booking, final.credits negative."""
    flag(True)
    user, raw = _mk_user(db_session)
    r = client.patch(f"/admin/users/{user.id}/quota", json={"quota_mode": "balance"},
                     headers=admin_headers)
    assert r.status_code == 200
    _stub_upstream(monkeypatch, tokens=1000)  # cost = 1000/1000 * 0.001 = 0.001
    db_session.expire_all()
    from models import User as _U
    db_session.add(CreditTransaction(user_id=user.id, amount=1.0, balance_after=1.0,
                                     reason="test seed"))
    if db_session.query(_U).filter(_U.id == user.id).first().quota_mode != "balance":
        db_session.query(_U).filter(_U.id == user.id).update({"quota_mode": "balance"})
    db_session.commit()
    before = db_session.query(CreditTransaction).count()
    with client.websocket_connect(f"/ws/chat?api_key={raw}") as ws:
        ws.receive_json()
        frames = _ws_frames(ws, '{"id":"p1","model":"m","messages":[{"role":"user","content":"hi"}]}')
        assert frames[-1]["type"] == "final"
        assert float(frames[-1]["credits"]) < 0
    db_session.expire_all()
    assert db_session.query(CreditTransaction).count() == before + 1  # exactly one booking
