"""
Tests for the admin surface: role gating, user management, cluster-wide node
visibility, idempotency, and the audit trail.

Run from the repo root:
    GPU_POOL_API=... .venv/bin/pytest tests -q      # or simply:
    .venv/bin/pytest tests/test_admin_endpoints.py -q
"""
import hashlib
import json
import os
import uuid

import pytest

pytestmark = pytest.mark.admin


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def _non_admin_headers(client):
    """Create (or reuse) a plain 'both' user and return headers + identity."""
    email = "plain-user@example.com"
    r = client.post("/auth/register", json={
        "email": email, "name": "Plain User", "password": "pw123456", "role": "both",
    })
    if r.status_code == 409:
        r = client.post("/auth/login", json={"email": email, "password": "pw123456"})
    else:
        body_tmp = r.json()
        admin_headers = {"Authorization": f"Bearer {os.environ['ADMIN_TOKEN']}"}
        client.post(f"/admin/registrations/{body_tmp['user_id']}/approve", headers=admin_headers)
        r = client.post("/auth/login", json={"email": email, "password": "pw123456"})
    assert r.status_code in (200, 201), r.text
    body = r.json()
    return {"Authorization": f"Bearer {body['api_key']}"}, body


def _register_node(client, headers, name=None, port=11434):
    name = name or f"test-node-{uuid.uuid4().hex[:8]}"
    r = client.post("/nodes/register", headers=headers, json={
        "name": name,
        "gpu_type": "Test GPU",
        "vram_gb": 24,
        "hourly_rate": 0.05,
        "node_url": "http://node-1.example.test:11435",
        "port": port,
        "backend": "ollama",
    })
    assert r.status_code == 201, r.text
    return r.json()


def _heartbeat(client, node, status="online"):
    r = client.post(
        f"/nodes/{node['id']}/heartbeat",
        headers={"X-Node-Key": node["agent_api_key"]},
        json={"status": status, "gpu_util": 0.25, "vram_used_gb": 4.0,
              "vram_total_gb": float(node["vram_gb"]), "active_jobs": 0},
    )
    assert r.status_code == 204, r.text


# ----------------------------------------------------------------------------
# Role gating
# ----------------------------------------------------------------------------
def test_admin_endpoints_require_authentication(client):
    for path in ("/admin/whoami", "/admin/overview", "/admin/users", "/admin/nodes"):
        assert client.get(path).status_code == 401, path


def test_admin_endpoints_reject_non_admin(client):
    headers, _ = _non_admin_headers(client)
    for path in ("/admin/whoami", "/admin/overview", "/admin/users", "/admin/nodes"):
        r = client.get(path, headers=headers)
        assert r.status_code == 403, f"{path} -> {r.status_code} {r.text}"
    # Mutations are gated too.
    r = client.post("/admin/users", headers=headers,
                    json={"email": "sneaky@example.com", "name": "Sneaky"})
    assert r.status_code == 403


def test_admin_bootstrap_identity(client, admin_headers):
    r = client.get("/admin/whoami", headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "admin"


# ----------------------------------------------------------------------------
# User management
# ----------------------------------------------------------------------------
def test_user_listing_includes_inactive_and_filters(client, admin_headers):
    email = f"inactive-{uuid.uuid4().hex[:8]}@example.com"
    created = client.post("/admin/users", headers=admin_headers,
                          json={"email": email, "name": "Will Be Inactive",
                                "initial_credits": 5.0}).json()
    uid = created["user_id"]

    # Deactivate -> must still be listed (that is the point of an admin list).
    r = client.patch(f"/admin/users/{uid}", headers=admin_headers, json={"is_active": False})
    assert r.status_code == 200, r.text
    assert r.json()["is_active"] is False

    listing = client.get("/admin/users", headers=admin_headers,
                         params={"q": email}).json()
    assert listing["total"] >= 1
    assert any(u["id"] == uid and u["is_active"] is False for u in listing["users"])

    # include_inactive=false hides it again.
    active_only = client.get("/admin/users", headers=admin_headers,
                             params={"q": email, "include_inactive": False}).json()
    assert all(u["id"] != uid for u in active_only["users"])

    # role filter
    by_role = client.get("/admin/users", headers=admin_headers,
                         params={"role": "not-a-role"})
    assert by_role.status_code == 422


def test_create_user_is_idempotent_by_email(client, admin_headers):
    email = f"dup-{uuid.uuid4().hex[:8]}@example.com"
    payload = {"email": email, "name": "Dup User", "initial_credits": 10.0}
    first = client.post("/admin/users", headers=admin_headers, json=payload)
    assert first.status_code == 201, first.text
    assert first.json()["created"] is True

    second = client.post("/admin/users", headers=admin_headers, json=payload)
    assert second.status_code == 201, second.text
    assert second.json()["created"] is False
    assert second.json()["user_id"] == first.json()["user_id"]

    users = client.get("/admin/users", headers=admin_headers, params={"q": email}).json()
    assert users["total"] == 1, "email must not produce a duplicate user row"

    # No extra credits were booked on the replay.
    detail = client.get(f"/admin/users/{first.json()['user_id']}", headers=admin_headers).json()
    assert detail["credits"] == pytest.approx(10.0)


def test_topup_is_idempotent_with_key(client, admin_headers, db_session):
    from models import AdminAuditLog, CreditTransaction

    email = f"topup-{uuid.uuid4().hex[:8]}@example.com"
    uid = client.post("/admin/users", headers=admin_headers,
                      json={"email": email, "name": "Topup User",
                            "initial_credits": 0.0}).json()["user_id"]
    key = f"test-topup-{uuid.uuid4()}"
    body = {"amount": 25.0, "reason": "pytest idempotency"}

    r1 = client.post(f"/admin/users/{uid}/topup", headers={**admin_headers, "Idempotency-Key": key}, json=body)
    assert r1.status_code == 200, r1.text
    assert r1.json()["credits"] == pytest.approx(25.0)
    assert r1.json()["replayed"] is False
    tx_id = r1.json()["transaction_id"]

    r2 = client.post(f"/admin/users/{uid}/topup", headers={**admin_headers, "Idempotency-Key": key}, json=body)
    assert r2.status_code == 200, r2.text
    assert r2.json()["replayed"] is True
    assert r2.json()["transaction_id"] == tx_id
    assert r2.json()["credits"] == pytest.approx(25.0), "replay must not double-book credits"

    # Exactly one credit transaction exists for that reason.
    rows = db_session.query(CreditTransaction).filter(
        CreditTransaction.user_id == uid, CreditTransaction.reason == body["reason"]
    ).all()
    assert len(rows) == 1

    # Same key, different action -> conflict, not a silent mis-replay.
    conflict = client.post(f"/admin/users/{uid}/keys",
                           headers={**admin_headers, "Idempotency-Key": key})
    assert conflict.status_code == 409


def test_key_rotation_never_stores_or_replays_the_secret(client, admin_headers, db_session):
    from models import AdminAuditLog, ApiKey

    email = f"rotate-{uuid.uuid4().hex[:8]}@example.com"
    uid = client.post("/admin/users", headers=admin_headers,
                      json={"email": email, "name": "Rotate User"}).json()["user_id"]
    key = f"test-rotate-{uuid.uuid4()}"

    r1 = client.post(f"/admin/users/{uid}/keys",
                     headers={**admin_headers, "Idempotency-Key": key})
    assert r1.status_code == 200, r1.text
    raw = r1.json()["api_key"]
    assert raw and raw.startswith("gpu_")
    assert r1.json()["revoked_key_ids"], "the previous key must be revoked on rotation"

    # The rotated key works.
    me = client.get("/v1/me", headers={"Authorization": f"Bearer {raw}"})
    assert me.status_code == 200 and me.json()["id"] == uid

    keys_after_first = db_session.query(ApiKey).filter(
        ApiKey.user_id == uid, ApiKey.is_active == True  # noqa: E712
    ).count()

    r2 = client.post(f"/admin/users/{uid}/keys",
                     headers={**admin_headers, "Idempotency-Key": key})
    assert r2.status_code == 200, r2.text
    assert r2.json()["replayed"] is True
    assert r2.json()["api_key"] is None, "a replay must never hand back the secret"

    keys_after_replay = db_session.query(ApiKey).filter(
        ApiKey.user_id == uid, ApiKey.is_active == True  # noqa: E712
    ).count()
    assert keys_after_replay == keys_after_first, "replay must not issue another key"

    # The raw key must never appear in the audit trail.
    for row in db_session.query(AdminAuditLog).filter(AdminAuditLog.target_id == uid).all():
        assert raw not in (row.result or "")
        assert raw not in (row.payload or "")
        assert raw[:20] not in (row.result or "")


def test_key_revocation_is_idempotent(client, admin_headers):
    email = f"revoke-{uuid.uuid4().hex[:8]}@example.com"
    detail = client.post("/admin/users", headers=admin_headers,
                         json={"email": email, "name": "Revoke User"}).json()
    uid = detail["user_id"]
    key_id = client.get(f"/admin/users/{uid}", headers=admin_headers).json()["keys"][0]["id"]

    r1 = client.post(f"/admin/users/{uid}/keys/{key_id}/revoke", headers=admin_headers)
    assert r1.status_code == 200 and r1.json()["revoked"] is True
    assert r1.json()["already_inactive"] is False

    r2 = client.post(f"/admin/users/{uid}/keys/{key_id}/revoke", headers=admin_headers)
    assert r2.status_code == 200, "revoking an inactive key is a successful no-op"
    assert r2.json()["already_inactive"] is True

    # The revoked key no longer authenticates.
    assert client.get("/v1/me", headers={"Authorization": f"Bearer {detail['api_key']}"}).status_code == 401


def test_admin_can_grant_and_user_cannot_self_grant_admin(client, admin_headers):
    headers, body = _non_admin_headers(client)

    # A user cannot promote themselves.
    r = client.put("/v1/me/role", headers=headers, json={"role": "admin"})
    assert r.status_code == 422, r.text

    # An existing admin can.
    r = client.patch(f"/admin/users/{body['user_id']}", headers=admin_headers, json={"role": "admin"})
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "admin"
    assert client.get("/admin/whoami", headers=headers).status_code == 200

    # ...and can take it back.
    r = client.patch(f"/admin/users/{body['user_id']}", headers=admin_headers, json={"role": "both"})
    assert r.json()["role"] == "both"
    assert client.get("/admin/whoami", headers=headers).status_code == 403


def test_admin_update_is_idempotent_and_validates_role(client, admin_headers):
    email = f"upd-{uuid.uuid4().hex[:8]}@example.com"
    uid = client.post("/admin/users", headers=admin_headers,
                      json={"email": email, "name": "Update User"}).json()["user_id"]

    bad = client.patch(f"/admin/users/{uid}", headers=admin_headers, json={"role": "root"})
    assert bad.status_code == 422

    a = client.patch(f"/admin/users/{uid}", headers=admin_headers,
                     json={"name": "Renamed", "allowed_models": ["qwen2.5-coder:7b"]})
    b = client.patch(f"/admin/users/{uid}", headers=admin_headers,
                     json={"name": "Renamed", "allowed_models": ["qwen2.5-coder:7b"]})
    assert a.status_code == 200 and b.status_code == 200
    assert a.json()["name"] == b.json()["name"] == "Renamed"
    assert b.json()["allowed_models"] == ["qwen2.5-coder:7b"]

    # Cloud models are dropped unless allow_cloud is set.
    c = client.patch(f"/admin/users/{uid}", headers=admin_headers,
                     json={"allowed_models": ["gpt-cloud-x", "qwen2.5-coder:7b"]})
    assert c.json()["allowed_models"] == ["qwen2.5-coder:7b"]
    d = client.patch(f"/admin/users/{uid}", headers=admin_headers,
                     json={"allowed_models": ["gpt-cloud-x"], "allow_cloud": True})
    assert d.json()["allowed_models"] == ["gpt-cloud-x"]
    assert d.json()["allow_cloud"] is True


def test_admin_cannot_lock_themselves_out(client, admin_headers):
    """The guard compares against the *calling user*, so this needs a real
    admin account token - the suite's static ADMIN_TOKEN is operator mode and
    resolves to no user (id 0)."""
    email = f"self-admin-{uuid.uuid4().hex[:8]}@example.com"
    created = client.post("/admin/users", headers=admin_headers,
                          json={"email": email, "name": "Self Admin",
                                "role": "admin"}).json()
    assert created.get("api_key"), created
    uid = created["user_id"]
    headers = {"Authorization": f"Bearer {created['api_key']}"}

    me = client.get("/admin/whoami", headers=headers).json()
    assert me["id"] == uid and me["role"] == "admin", me

    assert client.patch(f"/admin/users/{uid}", headers=headers,
                        json={"is_active": False}).status_code == 409
    assert client.patch(f"/admin/users/{uid}", headers=headers,
                        json={"role": "consumer"}).status_code == 409


# ----------------------------------------------------------------------------
# Nodes: every node, including offline and disabled
# ----------------------------------------------------------------------------
def test_node_overview_includes_offline_and_disabled(client, admin_headers):
    headers, _ = _non_admin_headers(client)

    online = _register_node(client, headers, name="visible-online-node")
    _heartbeat(client, online)
    offline = _register_node(client, headers, name="visible-offline-node", port=11435)

    listing = client.get("/admin/nodes", headers=admin_headers, params={"limit": 500})
    assert listing.status_code == 200, listing.text
    body = listing.json()
    by_id = {n["id"]: n for n in body["nodes"]}

    assert online["id"] in by_id and offline["id"] in by_id, "offline nodes must be listed"
    assert by_id[online["id"]]["effective_status"] in ("online", "busy")
    assert by_id[online["id"]]["online"] is True
    assert by_id[offline["id"]]["effective_status"] == "offline"
    assert by_id[offline["id"]]["online"] is False

    # The public listing hides the offline node by default — proving the admin
    # view is actually different.
    public = client.get("/nodes/list", params={"only_online": True}).json()
    assert offline["id"] not in [n["id"] for n in public]

    filt = client.get("/admin/nodes", headers=admin_headers, params={"status": "offline"}).json()
    assert all(n["effective_status"] == "offline" for n in filt["nodes"])
    assert offline["id"] in [n["id"] for n in filt["nodes"]]

    # A disabled node gets its own status instead of masquerading as offline.
    assert client.post(f"/nodes/{offline['id']}/enable",
                       headers=headers, params={"enabled": False}).status_code == 200
    after = client.get("/admin/nodes", headers=admin_headers, params={"status": "disabled"}).json()
    row = next(n for n in after["nodes"] if n["id"] == offline["id"])
    assert row["effective_status"] == "disabled"
    assert row["is_enabled"] is False

    hidden = client.get("/admin/nodes", headers=admin_headers,
                        params={"include_disabled": False}).json()
    assert offline["id"] not in [n["id"] for n in hidden["nodes"]]


def test_admin_node_listing_reports_agent_key_presence(client, admin_headers):
    """Split out of test_node_overview_* so the rest of the listing stays green."""
    headers, _ = _non_admin_headers(client)
    node = _register_node(client, headers, name="agent-key-node", port=11437)
    rows = client.get("/admin/nodes", headers=admin_headers,
                      params={"limit": 500}).json()["nodes"]
    row = next(n for n in rows if n["id"] == node["id"])
    assert row["has_agent_key"] is True


def test_admin_node_detail_exposes_heartbeat_and_owner(client, admin_headers):
    headers, _ = _non_admin_headers(client)
    node = _register_node(client, headers, name="detail-node", port=11436)
    _heartbeat(client, node, status="busy")

    r = client.get(f"/admin/nodes/{node['id']}", headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["owner_email"] == "plain-user@example.com"
    assert body["heartbeats_24h"] >= 1
    assert body["last_heartbeat"]["status"] == "busy"
    assert body["connection_state"] in ("connected", "connecting", "disconnected")
    assert client.get("/admin/nodes/99999999", headers=admin_headers).status_code == 404


def test_admin_can_toggle_another_users_node_idempotently(client, admin_headers):
    headers, _ = _non_admin_headers(client)
    node = _register_node(client, headers, name="toggle-node", port=11437)

    key = f"test-enable-{uuid.uuid4()}"
    me = client.get("/v1/me", headers=headers).json()
    url = f"/admin/users/{me['id']}/nodes/{node['id']}/enable"

    r1 = client.post(url, headers={**admin_headers, "Idempotency-Key": key}, params={"enabled": False})
    assert r1.status_code == 200, r1.text
    assert r1.json()["is_enabled"] is False
    assert r1.json()["effective_status"] == "disabled"

    r2 = client.post(url, headers={**admin_headers, "Idempotency-Key": key}, params={"enabled": False})
    assert r2.status_code == 200 and r2.json()["replayed"] is True

    r3 = client.post(url, headers=admin_headers, params={"enabled": False})
    assert r3.status_code == 200 and r3.json()["is_enabled"] is False

    r4 = client.post(url, headers=admin_headers, params={"enabled": True})
    assert r4.json()["is_enabled"] is True

    # A node that does not belong to the given user is a 404, not a 403 leak.
    assert client.post(f"/admin/users/999999/nodes/{node['id']}/enable",
                       headers=admin_headers).status_code == 404


def test_admin_overview_reports_platform_state(client, admin_headers):
    r = client.get("/admin/overview", headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["users_total"] >= 1
    assert body["admins_total"] >= 1
    assert body["nodes_total"] >= 1
    assert body["nodes_total"] == body["nodes_online"] + body["nodes_offline"] + body["nodes_disabled"]
    assert "generated_at" in body
