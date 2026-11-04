"""Modellfreigabe gehört dem Provider: Rechte-Matrix für `PUT /nodes/{id}`.

Ein Provider entscheidet selbst, welche Modelle seine Maschine anderen anbietet.
Vorher war der Endpunkt zwar eigentümergebunden, aber Admins kamen gar nicht
durch (404) — und die Oberfläche bot die Freigabe nur über den Katalog des
Portal-Hosts an. Diese Tests halten die Rechte fest:

| Wer | `PUT /nodes/{id}` | `/enable` | `DELETE` | `/rotate-key` |
|---|---|---|---|---|
| Eigentümer | 200 | 200 | 204 | 200 |
| Fremder | 404 | 404 | 404 | 404 |
| Admin | 200 | (eigener Endpunkt) | 404 | 200 |

`owner_id` lässt sich über den Endpunkt nicht umhängen.
"""
import os
import uuid

import pytest

pytestmark = pytest.mark.admin


def _admin_headers():
    return {"Authorization": f"Bearer {os.environ['ADMIN_TOKEN']}"}


def _konto(client, role="provider", name="Provider"):
    email = f"node-{uuid.uuid4().hex[:10]}@example.test"
    r = client.post("/admin/users", headers=_admin_headers(), json={
        "email": email, "name": name, "role": role,
        "password": "pw-nodes-1234", "initial_credits": 10.0,
    })
    assert r.status_code == 201, r.text
    login = client.post("/auth/login", json={"email": email, "password": "pw-nodes-1234"})
    assert login.status_code == 200, login.text
    return r.json()["user_id"], {"Authorization": f"Bearer {login.json()['api_key']}"}


def _node(client, headers):
    r = client.post("/nodes/register", headers=headers, json={
        "name": f"node-{uuid.uuid4().hex[:8]}", "gpu_type": "Test GPU",
        "vram_gb": 24, "hourly_rate": 0.05,
        "node_url": "http://node-rights.example.test:11435", "port": 11435,
    })
    assert r.status_code == 201, r.text
    return r.json()


def test_owner_may_set_the_models_of_its_own_node(client):
    uid, owner = _konto(client)
    node = _node(client, owner)

    r = client.put(f"/nodes/{node['id']}", headers=owner,
                   json={"allowed_models": ["mein-modell:7b", "cloud-gpt"]})
    assert r.status_code == 200, r.text
    assert r.json()["allowed_models"] == ["mein-modell:7b", "cloud-gpt"]

    # Der Katalog des Portal-Hosts spielt dabei keine Rolle: der Name steht so
    # in der Freigabe, auch wenn ihn hier niemand kennt.
    detail = client.get(f"/nodes/{node['id']}").json()
    assert detail["allowed_models"] == ["mein-modell:7b", "cloud-gpt"]


def test_owner_may_clear_the_list_back_to_default(client):
    """`NULL` = alle lokalen Modelle. Ohne eigenes Kennzeichen käme man nie dorthin."""
    _uid, owner = _konto(client)
    node = _node(client, owner)
    client.put(f"/nodes/{node['id']}", headers=owner, json={"allowed_models": ["a:1b"]})

    r = client.put(f"/nodes/{node['id']}", headers=owner, json={"clear_allowed_models": True})
    assert r.status_code == 200, r.text
    assert r.json()["allowed_models"] is None


def test_stranger_cannot_touch_the_node(client):
    _uid, owner = _konto(client)
    _uid2, fremder = _konto(client, name="Fremder")
    node = _node(client, owner)

    r = client.put(f"/nodes/{node['id']}", headers=fremder,
                   json={"allowed_models": ["fremd:1b"], "name": "gekapert"})
    assert r.status_code == 404, r.text
    # Und nichts wurde geschrieben.
    detail = client.get(f"/nodes/{node['id']}").json()
    assert detail["allowed_models"] is None
    assert detail["name"] == node["name"]

    for method, pfad in (
        ("post", f"/nodes/{node['id']}/enable?enabled=false"),
        ("post", f"/nodes/{node['id']}/rotate-key"),
        ("delete", f"/nodes/{node['id']}"),
    ):
        r = getattr(client, method)(pfad, headers=fremder)
        assert r.status_code == 404, f"{method} {pfad} -> {r.status_code} {r.text}"


def test_admin_may_edit_any_node(client):
    """Die Administration behält den Zugriff — sie verliert ihn nicht durch die neuen Rechte.

    Der Admin braucht hier einen *echten* Kontoschlüssel: `/nodes/...` prüft über
    `get_current_user` (Datenbank), nicht über den Bootstrap-Token aus
    `ADMIN_TOKEN`, den nur `/admin/...` akzeptiert.
    """
    _uid, owner = _konto(client)
    _aid, admin = _konto(client, role="admin", name="Admin Zwei")
    node = _node(client, owner)

    r = client.put(f"/nodes/{node['id']}", headers=admin,
                   json={"allowed_models": ["admin-set:7b"], "description": "von der Administration"})
    assert r.status_code == 200, r.text
    assert r.json()["allowed_models"] == ["admin-set:7b"]
    assert r.json()["description"] == "von der Administration"


def test_owner_cannot_reassign_the_node(client):
    """`owner_id` ist kein Feld der Anfrage — ein Umhängen bleibt wirkungslos."""
    uid, owner = _konto(client)
    fremd_id, _fremd = _konto(client, name="Ziel")
    node = _node(client, owner)

    r = client.put(f"/nodes/{node['id']}", headers=owner,
                   json={"owner_id": fremd_id, "allowed_models": ["x:1b"]})
    assert r.status_code == 200, r.text
    assert r.json()["owner_id"] == uid
