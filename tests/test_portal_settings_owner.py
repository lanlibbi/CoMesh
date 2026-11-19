"""Waechter fuer die Punkte aus dem Fixpaket: Portal-Adresse, Besitzerwechsel, Sichtbarkeit.

Diese Tests halten fest, was ein Nutzer im Portal sehen und aendern darf:
  * die Portal-Adresse setzt nur ein Admin, sie landet in der Datenbank und geht der Umgebung vor,
  * ein Besitzerwechsel ist Admin-Sache und wird protokolliert,
  * fremde Konten sehen von einer Node nur die oeffentliche Form mit den freigegebenen Modellen.
"""

import os
import uuid

ADMIN = {"Authorization": f"Bearer {os.environ['ADMIN_TOKEN']}"}


def _konto(client, role="both", name="Konto"):
    email = f"fix-{uuid.uuid4().hex[:10]}@example.test"
    r = client.post("/admin/users", headers=ADMIN,
                    json={"email": email, "name": name, "role": role,
                          "password": "pw-fix-1234", "initial_credits": 10.0})
    assert r.status_code == 201, r.text
    login = client.post("/auth/login", json={"email": email, "password": "pw-fix-1234"})
    assert login.status_code == 200, login.text
    return {"id": r.json()["user_id"], "email": email,
            "headers": {"Authorization": f"Bearer {login.json()['api_key']}"}}


def _node(client, konto):
    r = client.post("/nodes/register", headers=konto["headers"], json={
        "name": f"fix-node-{uuid.uuid4().hex[:6]}", "gpu_type": "Test GPU", "vram_gb": 16,
        "hourly_rate": 0.05, "node_url": f"http://node-{uuid.uuid4().hex[:6]}.example.test:11435",
        "port": 11435,
    })
    assert r.status_code == 201, r.text
    return r.json()


# --------------------------------------------------------------------------- Portal-Adresse
def test_admin_setzt_portal_adresse(client):
    """Die Adresse landet in der Datenbank, gewinnt gegen die Umgebung und steht in portal-info."""
    neu = "https://comesh.example.test"
    r = client.put("/admin/portal-settings", headers=ADMIN, json={"public_base_url": neu + "/"})
    assert r.status_code == 200, r.text
    assert r.json()["public_base_url"] == neu
    assert r.json()["connect_endpoint"] == neu + "/v1"

    info = client.get("/v1/portal-info").json()
    assert info["base_url"] == neu
    assert info["source"] == "setting"
    assert info["connect_endpoint"] == neu + "/v1"
    assert info["downloads_url"] == neu + "/downloads"


def test_adresse_wieder_entfernen(client):
    client.put("/admin/portal-settings", headers=ADMIN, json={"public_base_url": "https://zwischen.example"})
    r = client.put("/admin/portal-settings", headers=ADMIN, json={"public_base_url": ""})
    assert r.status_code == 200, r.text
    assert r.json()["public_base_url"] == ""
    assert client.get("/v1/portal-info").json()["source"] != "setting"


def test_ungueltige_adresse_wird_abgelehnt(client):
    for wert in ("ftp://example.test", "https://example.test/mit/pfad", ""):
        if wert == "":
            continue
        r = client.put("/admin/portal-settings", headers=ADMIN, json={"public_base_url": wert})
        assert r.status_code == 422, f"{wert} haette abgelehnt werden muessen: {r.text}"


def test_nur_admin_darf_die_adresse_setzen(client):
    konto = _konto(client, role="both")
    r = client.put("/admin/portal-settings", headers=konto["headers"],
                   json={"public_base_url": "https://boese.example"})
    assert r.status_code in (401, 403), r.text
    assert client.get("/v1/portal-info").json()["base_url"] != "https://boese.example"


# --------------------------------------------------------------------------- Besitzerwechsel
def test_admin_kann_den_besitzer_wechseln(client, db_session):
    alt = _konto(client)
    neu = _konto(client)
    node = _node(client, alt)

    r = client.put(f"/admin/nodes/{node['id']}/owner", headers=ADMIN, json={"owner_id": neu["id"]})
    assert r.status_code == 200, r.text
    assert r.json()["owner_id"] == neu["id"]

    from models import GpuNode

    db_session.expire_all()
    assert db_session.query(GpuNode).filter(GpuNode.id == node["id"]).first().owner_id == neu["id"]

    # Der neue Besitzer verwaltet die Node jetzt wie eine eigene.
    eigene = client.get("/nodes/my", headers=neu["headers"]).json()
    assert any(n["id"] == node["id"] for n in eigene)
    alte = client.get("/nodes/my", headers=alt["headers"]).json()
    assert not any(n["id"] == node["id"] for n in alte)


def test_besitzerwechsel_nur_admin(client):
    a = _konto(client)
    b = _konto(client)
    node = _node(client, a)
    r = client.put(f"/admin/nodes/{node['id']}/owner", headers=a["headers"], json={"owner_id": b["id"]})
    assert r.status_code in (401, 403), r.text


def test_unbekanntes_konto_wird_abgelehnt(client):
    a = _konto(client)
    node = _node(client, a)
    r = client.put(f"/admin/nodes/{node['id']}/owner", headers=ADMIN, json={"owner_id": 999999})
    assert r.status_code == 404, r.text


# --------------------------------------------------------------------------- Sichtbarkeit
def test_fremdes_konto_sieht_nur_die_oeffentliche_form(client):
    besitzer = _konto(client)
    fremd = _konto(client, role="consumer")
    node = _node(client, besitzer)

    oeffentlich = client.get(f"/nodes/{node['id']}", headers=fremd["headers"])
    assert oeffentlich.status_code == 200, oeffentlich.text
    f = oeffentlich.json()
    for feld in ("node_url", "owner_id", "earnings_total", "reported_models", "tailscale_ip", "port"):
        assert feld not in f, f"{feld} darf ein fremdes Konto nicht sehen: {sorted(f.keys())}"
    # Was sie nutzen duerfen, bleibt sichtbar.
    assert "allowed_models" in f
    assert f["name"] == node["name"]

    voll = client.get(f"/nodes/{node['id']}", headers=besitzer["headers"]).json()
    assert "node_url" in voll and "owner_id" in voll
