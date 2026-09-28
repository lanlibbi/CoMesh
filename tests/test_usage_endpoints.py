"""
Tests for the usage analytics endpoints (GET /v1/me/usage, GET /admin/usage).

The aggregation itself is the thing under test: windows, per-model grouping,
credit sums, gap-filled series, share calculation, role gating and tenant
isolation. Requests are inserted straight into the `usages` table (no Ollama
involved), so the suite stays offline and fast.
"""
import uuid
from datetime import datetime, timedelta

import pytest

from models import PoolJob, Usage, User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _register(client, role="both", credits=None):
    email = f"usage-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/auth/register", json={
        "email": email, "name": "Usage Tester", "password": "pw12345", "role": role,
    })
    assert r.status_code in (200, 201), r.text
    body = r.json()
    return {"Authorization": f"Bearer {body['api_key']}"}, body


def _user_id(email):
    from database import SessionLocal
    db = SessionLocal()
    try:
        return db.query(User).filter(User.email == email).one().id
    finally:
        db.close()


def _add_usage(user_id, model, total, when, prompt=None, completion=None, credits=None):
    """Insert one usage row at an explicit UTC timestamp."""
    from database import SessionLocal
    db = SessionLocal()
    try:
        prompt = total // 3 if prompt is None else prompt
        completion = total - prompt if completion is None else completion
        db.add(Usage(
            user_id=user_id,
            api_key_id=None,
            model=model,
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=total,
            credits_charged=round(total / 1000.0 * 0.001, 6) if credits is None else credits,
            created_at=when,
        ))
        db.commit()
    finally:
        db.close()


def _add_job(user_id, model, latency_ms, when, status="succeeded"):
    from database import SessionLocal
    db = SessionLocal()
    try:
        db.add(PoolJob(
            user_id=user_id, node_id=None, model=model, source="local", status=status,
            prompt_tokens=0, completion_tokens=0, total_tokens=0, job_cost=0.0,
            latency_ms=latency_ms, started_at=when, finished_at=when,
        ))
        db.commit()
    finally:
        db.close()


def _now():
    return datetime.utcnow()


# ---------------------------------------------------------------------------
# Shape / auth
# ---------------------------------------------------------------------------
def test_my_usage_requires_authentication(client):
    assert client.get("/v1/me/usage").status_code == 401


def test_my_usage_rejects_unknown_window(client):
    headers, _ = _register(client)
    r = client.get("/v1/me/usage", headers=headers, params={"window": "gestern"})
    assert r.status_code == 422
    assert "window" in r.text.lower()


def test_my_usage_empty_account_is_zeroed_but_well_formed(client):
    headers, _ = _register(client)
    r = client.get("/v1/me/usage", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["window"] == "7d"
    assert body["granularity"] == "day"
    assert body["totals"]["requests"] == 0
    assert body["totals"]["total_tokens"] == 0
    assert body["totals"]["models_used"] == 0
    assert body["models"] == []
    assert body["recent"] == []
    # Gap-filled: the 7d window renders 8 day buckets (start of today-7d .. today).
    assert len(body["series"]) == 8
    assert all(b["total_tokens"] == 0 for b in body["series"])


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------
def test_usage_aggregates_per_model_with_totals_and_shares(client):
    headers, me = _register(client)
    uid = _user_id(me["email"])
    now = _now()

    # a: 3 requests / 30_000 tokens, b: 1 request / 10_000 tokens
    for _ in range(3):
        _add_usage(uid, "model-a", 10_000, now - timedelta(hours=2))
    _add_usage(uid, "model-b", 10_000, now - timedelta(hours=1))

    body = client.get("/v1/me/usage", headers=headers, params={"window": "24h"}).json()

    assert body["totals"]["requests"] == 4
    assert body["totals"]["total_tokens"] == 40_000
    assert body["totals"]["prompt_tokens"] + body["totals"]["completion_tokens"] == 40_000
    assert body["totals"]["models_used"] == 2
    assert body["totals"]["credits"] == pytest.approx(0.04, abs=1e-6)

    models = {m["model"]: m for m in body["models"]}
    assert models["model-a"]["requests"] == 3
    assert models["model-a"]["total_tokens"] == 30_000
    assert models["model-b"]["requests"] == 1
    assert models["model-b"]["total_tokens"] == 10_000

    # Share is token-weighted, heavy model first.
    assert body["models"][0]["model"] == "model-a"
    assert models["model-a"]["share"] == pytest.approx(0.75, abs=1e-4)
    assert models["model-b"]["share"] == pytest.approx(0.25, abs=1e-4)
    assert models["model-a"]["credits"] == pytest.approx(0.03, abs=1e-6)


def test_usage_window_filters_out_older_requests(client):
    headers, me = _register(client)
    uid = _user_id(me["email"])
    now = _now()

    _add_usage(uid, "fresh", 1_000, now - timedelta(hours=1))
    _add_usage(uid, "midday", 2_000, now - timedelta(days=3))
    _add_usage(uid, "ancient", 4_000, now - timedelta(days=20))

    def tokens(window):
        return client.get("/v1/me/usage", headers=headers, params={"window": window}).json()

    assert tokens("24h")["totals"]["total_tokens"] == 1_000
    assert tokens("7d")["totals"]["total_tokens"] == 3_000
    assert tokens("30d")["totals"]["total_tokens"] == 7_000
    assert tokens("all")["totals"]["total_tokens"] == 7_000

    # Window aliases resolve to the same result.
    assert tokens("week")["window"] == "7d"
    assert tokens("week")["totals"]["total_tokens"] == 3_000


def test_usage_series_is_gap_filled_and_labeled(client):
    headers, me = _register(client)
    uid = _user_id(me["email"])
    now = _now()

    _add_usage(uid, "sparse", 5_000, now - timedelta(days=2))
    _add_usage(uid, "sparse", 5_000, now - timedelta(days=2, hours=1))

    body = client.get("/v1/me/usage", headers=headers, params={"window": "7d"}).json()
    by_bucket = {b["bucket"]: b for b in body["series"]}

    today = now.strftime("%Y-%m-%d")
    target = (now - timedelta(days=2)).strftime("%Y-%m-%d")
    assert by_bucket[target]["total_tokens"] == 10_000
    assert by_bucket[target]["requests"] == 2
    assert by_bucket[today]["total_tokens"] == 0
    # Every bucket carries a renderable label and sorted order is preserved.
    assert all(b["label"] for b in body["series"])
    assert [b["bucket"] for b in body["series"]] == sorted(b["bucket"] for b in body["series"])


def test_usage_24h_series_buckets_by_hour(client):
    headers, me = _register(client)
    uid = _user_id(me["email"])
    now = _now()

    _add_usage(uid, "hourly", 1_000, now - timedelta(hours=1))

    body = client.get("/v1/me/usage", headers=headers, params={"window": "24h"}).json()
    assert body["granularity"] == "hour"
    assert len(body["series"]) == 25                      # 24h window, inclusive edges
    assert sum(b["total_tokens"] for b in body["series"]) == 1_000


def test_usage_average_latency_is_per_model(client):
    headers, me = _register(client)
    uid = _user_id(me["email"])
    now = _now()

    for _ in range(4):
        _add_usage(uid, "lat-model", 1_000, now - timedelta(minutes=30))
    _add_job(uid, "lat-model", 100, now - timedelta(minutes=30))
    _add_job(uid, "lat-model", 300, now - timedelta(minutes=29))

    body = client.get("/v1/me/usage", headers=headers, params={"window": "24h"}).json()
    m = next(x for x in body["models"] if x["model"] == "lat-model")
    assert m["avg_latency_ms"] == 200
    assert body["totals"]["avg_latency_ms"] == 200


def test_usage_recent_requests_are_newest_first_and_limited(client):
    headers, me = _register(client)
    uid = _user_id(me["email"])
    now = _now()

    for i in range(5):
        _add_usage(uid, f"m{i}", 100, now - timedelta(minutes=10 - i))

    body = client.get("/v1/me/usage", headers=headers,
                      params={"window": "24h", "recent_limit": 3}).json()
    assert len(body["recent"]) == 3
    assert [r["model"] for r in body["recent"]] == ["m4", "m3", "m2"]
    assert all(r["created_at"] for r in body["recent"])

    # recent_limit is bounded by the schema.
    assert client.get("/v1/me/usage", headers=headers,
                      params={"recent_limit": 9999}).status_code == 422


def test_usage_is_scoped_to_the_calling_user(client):
    """Two accounts with requests in the same window must not see each other."""
    headers_a, me_a = _register(client)
    headers_b, me_b = _register(client)
    uid_a, uid_b = _user_id(me_a["email"]), _user_id(me_b["email"])
    now = _now()

    _add_usage(uid_a, "only-a", 7_000, now - timedelta(minutes=5))
    _add_usage(uid_b, "only-b", 9_000, now - timedelta(minutes=4))

    a = client.get("/v1/me/usage", headers=headers_a, params={"window": "24h"}).json()
    b = client.get("/v1/me/usage", headers=headers_b, params={"window": "24h"}).json()

    assert a["totals"]["total_tokens"] == 7_000
    assert [m["model"] for m in a["models"]] == ["only-a"]
    assert b["totals"]["total_tokens"] == 9_000
    assert [m["model"] for m in b["models"]] == ["only-b"]


# ---------------------------------------------------------------------------
# Admin view
# ---------------------------------------------------------------------------
def test_admin_usage_requires_authentication(client):
    assert client.get("/admin/usage").status_code == 401


def test_admin_usage_rejects_non_admin(client):
    headers, _ = _register(client)
    assert client.get("/admin/usage", headers=headers).status_code == 403


def test_admin_usage_reports_every_user_per_model(client, admin_headers):
    headers, me = _register(client)
    uid = _user_id(me["email"])
    now = _now()
    _add_usage(uid, "admin-visible", 12_000, now - timedelta(minutes=3))

    body = client.get("/admin/usage", headers=admin_headers,
                      params={"window": "24h"}).json()
    assert body["window"] == "24h"
    assert body["totals"]["total_tokens"] >= 12_000
    assert body["totals"]["models_used"] >= 1

    row = next(u for u in body["users"] if u["user_id"] == uid)
    assert row["email"] == me["email"]
    assert row["total_tokens"] == 12_000
    assert row["requests"] == 1
    assert row["models_used"] == 1
    assert [m["model"] for m in row["models"]] == ["admin-visible"]
    # Heaviest user first.
    assert body["users"][0]["total_tokens"] >= body["users"][-1]["total_tokens"]


def test_admin_usage_limit_and_window_validation(client, admin_headers):
    assert client.get("/admin/usage", headers=admin_headers,
                      params={"window": "nope"}).status_code == 422
    assert client.get("/admin/usage", headers=admin_headers,
                      params={"limit": 0}).status_code == 422
    limited = client.get("/admin/usage", headers=admin_headers,
                         params={"window": "all", "limit": 1}).json()
    assert len(limited["users"]) <= 1
