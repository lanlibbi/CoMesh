#!/usr/bin/env python3
"""LANA-110 tests: authenticated WS chat endpoint.

Covers:
- bad key -> hello, then error frame status 401, close
- blocked quota_mode -> error frame 403 (even with credits ON)
- unlimited user + credits ON -> success, never 402, no charge (CreditTransaction count unchanged)
- stream=true -> status/chunk frames then final; stream=false -> final only
- HTTP /v1/chat/completions stays untouched (regression via existing suites)

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

    async def fake_route_request(db, user, ollama_payload, model):
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