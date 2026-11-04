"""Tests für `DELETE /admin/users/{id}` — Konto löschen, Abrechnung behalten.

Die Erwartungen stehen im Endpunkt-Docstring; hier werden sie gemessen:

  * Schlüssel **und** Sitzungsmarken verschwinden mit dem Konto (danach 401),
  * eine Node ohne Umsatz verschwindet mit,
  * eine Node **mit** Umsatz bleibt, wird stillgelegt und verliert ihren Agent-Schlüssel,
  * `node_earnings`, `pool_jobs`, `usages`, `credit_transactions`, `payments` bleiben
    erhalten und zeigen auf ein Platzhalterkonto (anonymisiert),
  * das Platzhalterkonto steht nicht in der Kontenliste,
  * Selbstlöschung und der letzte Admin sind gesperrt.
"""
import uuid

import pytest

pytestmark = pytest.mark.admin


def _admin_headers():
    import os
    return {"Authorization": f"Bearer {os.environ['ADMIN_TOKEN']}"}


def _neues_konto(client, role="both", name="Delete Me"):
    """Ein frisches Konto per Admin anlegen und einloggen."""
    import os
    email = f"del-{uuid.uuid4().hex[:10]}@example.test"
    r = client.post("/admin/users", headers=_admin_headers(), json={
        "email": email, "name": name, "role": role,
        "password": "pw-delete-1234", "initial_credits": 42.0,
    })
    assert r.status_code == 201, r.text
    uid = r.json()["user_id"]
    login = client.post("/auth/login", json={"email": email, "password": "pw-delete-1234"})
    assert login.status_code == 200, login.text
    return uid, email, {"Authorization": f"Bearer {login.json()['api_key']}"}, login.json()["api_key"]


def _node(client, headers, name=None, rate=0.05):
    r = client.post("/nodes/register", headers=headers, json={
        "name": name or f"node-{uuid.uuid4().hex[:8]}",
        "gpu_type": "Test GPU", "vram_gb": 24, "hourly_rate": rate,
        "node_url": "http://node-del.example.test:11435", "port": 11435,
        "allowed_models": ["qwen2.5-coder:7b"],
    })
    assert r.status_code == 201, r.text
    return r.json()


def test_delete_removes_keys_and_sessions(client):
    uid, email, headers, key = _neues_konto(client)
    # Der angemeldete Schlüssel funktioniert.
    assert client.get("/v1/me", headers=headers).status_code == 200

    r = client.delete(f"/admin/users/{uid}", headers=_admin_headers())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["deleted"] is True
    assert body["keys_removed"] >= 1

    # Konto weg, Schlüssel wertlos — kein 500, sondern 401.
    assert client.get("/v1/me", headers=headers).status_code == 401
    assert client.get(f"/admin/users/{uid}", headers=_admin_headers()).status_code == 404


def test_delete_keeps_node_with_earnings_and_anonymizes_books(client):
    """Der Kern der Anforderung: die Einnahmen der Node überleben das Konto."""
    from database import SessionLocal
    from models import GpuNode, NodeEarning, PoolJob, User

    uid, email, headers, _key = _neues_konto(client, role="provider")
    node = _node(client, headers, name="Earning Node")

    db = SessionLocal()
    try:
        db.add(NodeEarning(
            node_id=node["id"], owner_id=uid, job_cost=10.0,
            owner_share=7.0, platform_share=2.0, treasury_share=1.0,
        ))
        db.add(PoolJob(node_id=node["id"], user_id=uid, model="qwen2.5-coder:7b",
                       source="community", status="succeeded"))
        db.commit()
    finally:
        db.close()

    r = client.delete(f"/admin/users/{uid}", headers=_admin_headers())
    assert r.status_code == 200, r.text
    body = r.json()
    assert node["id"] in body["nodes_kept"]
    assert body["node_earnings_anonymized"] >= 1
    assert body["pool_jobs_anonymized"] >= 1
    tomb_id = body["tombstone_user_id"]
    assert tomb_id and tomb_id != uid

    db = SessionLocal()
    try:
        konto = db.query(User).filter(User.id == uid).first()
        assert konto is None, "die users-Zeile muss weg sein"

        tomb = db.query(User).filter(User.id == tomb_id).first()
        assert tomb is not None
        assert tomb.registration_status == "deleted"
        assert tomb.is_active is False
        assert tomb.quota_mode == "blocked"

        # Die Node lebt weiter, gehört dem Platzhalter und ist stillgelegt.
        n = db.query(GpuNode).filter(GpuNode.id == node["id"]).first()
        assert n is not None
        assert n.owner_id == tomb_id
        assert n.is_enabled is False
        assert n.api_key_hash is None

        # Die Einnahmen sind noch da — nur ohne Personenbezug.
        verdienst = db.query(NodeEarning).filter(NodeEarning.node_id == node["id"]).all()
        assert len(verdienst) == 1
        assert verdienst[0].owner_id == tomb_id
        assert round(verdienst[0].owner_share, 6) == 7.0
    finally:
        db.close()

    # Die stillgelegte Node nimmt keine Heartbeats mehr an (Schlüssel gelöscht).
    hb = client.post(f"/nodes/{node['id']}/heartbeat",
                     headers={"X-Node-Key": node["agent_api_key"]},
                     json={"status": "online"})
    assert hb.status_code == 401, hb.text


def test_delete_removes_node_without_earnings(client):
    from database import SessionLocal
    from models import GpuNode

    uid, _email, headers, _key = _neues_konto(client, role="provider")
    node = _node(client, headers, name="Empty Node")

    r = client.delete(f"/admin/users/{uid}", headers=_admin_headers())
    assert r.status_code == 200, r.text
    assert node["id"] in r.json()["nodes_removed"]

    db = SessionLocal()
    try:
        assert db.query(GpuNode).filter(GpuNode.id == node["id"]).first() is None
    finally:
        db.close()


def test_tombstone_is_hidden_from_the_user_list(client):
    uid, email, _headers, _key = _neues_konto(client)
    r = client.delete(f"/admin/users/{uid}", headers=_admin_headers())
    tomb_id = r.json()["tombstone_user_id"]

    r = client.get("/admin/users?limit=200", headers=_admin_headers())
    assert r.status_code == 200
    ids = [u["id"] for u in r.json()["users"]]
    assert tomb_id not in ids
    assert uid not in ids

    # Auf Nachfrage ist er sichtbar (Nachvollziehbarkeit der Abrechnung).
    r = client.get("/admin/users?include_deleted=true&limit=200", headers=_admin_headers())
    assert tomb_id in [u["id"] for u in r.json()["users"]]


def test_admin_cannot_delete_its_own_account(client):
    """Selbstlöschung ist gesperrt — sonst sperrt sich die Administration aus.

    Mit einem *echten* Admin-Konto (Datenbank-Schlüssel), nicht mit dem
    Bootstrap-Token: nur so gibt es eine Konto-Id, die sich löschen ließe.
    """
    aid, _email, headers, _key = _neues_konto(client, role="admin", name="Admin Selbst")
    r = client.delete(f"/admin/users/{aid}", headers=headers)
    assert r.status_code == 409, r.text
    # Das Konto steht danach noch.
    assert client.get("/v1/me", headers=headers).status_code == 200


def test_delete_is_idempotent_with_key(client):
    uid, _email, _headers, _key = _neues_konto(client)
    key = f"del-{uuid.uuid4().hex}"
    r1 = client.delete(f"/admin/users/{uid}", headers={**_admin_headers(),
                                                      "Idempotency-Key": key})
    assert r1.status_code == 200, r1.text
    r2 = client.delete(f"/admin/users/{uid}", headers={**_admin_headers(),
                                                      "Idempotency-Key": key})
    # Wiederholung liefert das gespeicherte Ergebnis statt eines 404.
    assert r2.status_code == 200, r2.text
    assert r2.json().get("replayed") is True


def test_delete_unknown_user_returns_404(client):
    r = client.delete("/admin/users/99999999", headers=_admin_headers())
    assert r.status_code == 404


def test_delete_requires_admin(client):
    uid, _email, headers, _key = _neues_konto(client)
    r = client.delete(f"/admin/users/{uid}", headers=headers)
    assert r.status_code == 403, r.text
