"""VRAM: Uebersteuerung, Routing-Gate und der sichtbare „assumed"-Fall.

Hintergrund (Fix 03.11.2026): ohne NVML (macOS/Apple Silicon, CPU-Node) meldete
der Agent 0 GB, beim Registrieren wurde daraus `max(1, …)` = 1 GB, und
pool.find_best_node verwarf die Node am VRAM-Gate. Ergebnis: online, aber nie
ein Auftrag — ohne Fehlermeldung.

Diese Tests halten drei Dinge fest: NODE_VRAM_GB gewinnt gegen die Messung, der
Wert kommt ohne Bearbeiten der Geräteseite im Portal an, und ohne beides bleibt
die Node am Gate haengen (statt still durchzurutschen).
"""
import importlib
import os
import sys
import uuid
from pathlib import Path

import pytest

AGENT_DIR = Path(__file__).resolve().parents[1] / "node-agent"
MODEL = "llama3.1:8b"  # Bedarf 4,0 GB (Vorgabe in pool._estimate_model_vram_gb)


# --------------------------------------------------------------------------
# Agentenseite: vram_report()
# --------------------------------------------------------------------------
@pytest.fixture(scope="module")
def agent_mod():
    saved = {k: os.environ.get(k) for k in ("NODE_ID", "NODE_API_KEY", "PORTAL_URL")}
    os.environ["NODE_ID"] = "1"
    os.environ["NODE_API_KEY"] = "test-key"
    os.environ["PORTAL_URL"] = "http://portal.test:8765"
    sys.path.insert(0, str(AGENT_DIR))
    try:
        sys.modules.pop("netinfo", None)
        sys.modules.pop("agent", None)
        module = importlib.import_module("agent")
    finally:
        sys.path.remove(str(AGENT_DIR))
        sys.modules.pop("netinfo", None)
        for k, old in saved.items():
            if old is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old
    yield module


def test_vram_report_prefers_the_declared_value(agent_mod, monkeypatch):
    monkeypatch.setattr(agent_mod, "NODE_VRAM_GB", "16")
    assert agent_mod.vram_report() == (16, "override")


def test_vram_report_uses_nvml_when_available(agent_mod, monkeypatch):
    monkeypatch.setattr(agent_mod, "NODE_VRAM_GB", "")
    monkeypatch.setattr(agent_mod, "gpu_summary", lambda: {"name": "RTX", "vram_gb": 12})
    assert agent_mod.vram_report() == (12, "detected")


def test_vram_report_falls_back_to_one_gigabyte_and_says_so(agent_mod, monkeypatch):
    """Der macOS-Fall: keine GPU, kein NODE_VRAM_GB -> 1 GB, aber als 'assumed'."""
    monkeypatch.setattr(agent_mod, "NODE_VRAM_GB", "")
    monkeypatch.setattr(agent_mod, "gpu_summary", lambda: {"name": "unknown", "vram_gb": 0})
    assert agent_mod.vram_report() == (1, "assumed")


# --------------------------------------------------------------------------
# Portalseite: Routing-Gate
# --------------------------------------------------------------------------
def _provider_headers(client):
    email = f"vram-provider-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/auth/register", json={
        "email": email, "name": "VRAM Provider", "password": "pw123456", "role": "provider",
    })
    assert r.status_code in (200, 201), r.text
    user_id = r.json()["user_id"]
    admin = {"Authorization": f"Bearer {os.environ['ADMIN_TOKEN']}"}
    client.post(f"/admin/registrations/{user_id}/approve", headers=admin)
    r = client.post("/auth/login", json={"email": email, "password": "pw123456"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['api_key']}"}


def _register_node(client, headers, vram_gb, hourly_rate, vram_source=None):
    body = {
        "name": f"vram-node-{uuid.uuid4().hex[:8]}",
        "gpu_type": "Test GPU",
        "vram_gb": vram_gb,
        "hourly_rate": hourly_rate,
        "node_url": f"http://node-{uuid.uuid4().hex[:6]}.example.test:11435",
        "port": 11435,
        "backend": "ollama",
    }
    if vram_source:
        body["vram_source"] = vram_source
    r = client.post("/nodes/register", headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _beat(client, node, vram_gb=None, vram_source=None):
    body = {"status": "online", "gpu_util": 0.0, "vram_used_gb": 0.0,
            "vram_total_gb": float(node["vram_gb"]), "active_jobs": 0}
    if vram_gb is not None:
        body["vram_gb"] = vram_gb
    if vram_source is not None:
        body["vram_source"] = vram_source
    r = client.post(f"/nodes/{node['id']}/heartbeat",
                    headers={"X-Node-Key": node["agent_api_key"]}, json=body)
    assert r.status_code == 204, r.text


def _gate(client, db_session, only_ids):
    """find_best_node, aber ausschliesslich unter den Nodes dieses Tests."""
    import pool
    from models import GpuNode

    alle = [n.id for n in db_session.query(GpuNode).all()]
    fremde = [i for i in alle if i not in only_ids]
    return pool.find_best_node(db_session, MODEL, exclude_node_ids=fremde)


def test_declared_vram_opens_the_routing_gate(client, db_session):
    headers = _provider_headers(client)
    klein = _register_node(client, headers, vram_gb=1, hourly_rate=0.01,
                           vram_source="assumed")     # der macOS-Fall
    gross = _register_node(client, headers, vram_gb=16, hourly_rate=0.20,
                           vram_source="override")
    _beat(client, klein)
    _beat(client, gross)

    gewaehlt = _gate(client, db_session, {klein["id"], gross["id"]})
    assert gewaehlt is not None and gewaehlt.id == gross["id"], (
        f"1-GB-Node darf nicht gewinnen, gewaehlt: {getattr(gewaehlt, 'id', None)} / "
        f"klein={klein['id']} gross={gross['id']}"
    )

    # Ohne Uebersteuerung bleibt die kleine Node am Gate haengen.
    from models import GpuNode
    klein_row = db_session.query(GpuNode).filter(GpuNode.id == klein["id"]).first()
    assert klein_row.vram_source == "assumed"
    db_session.query(GpuNode).filter(GpuNode.id == gross["id"]).update(
        {"vram_gb": 1, "vram_source": "assumed"}
    )
    db_session.commit()
    assert _gate(client, db_session, {klein["id"], gross["id"]}) is None


def test_heartbeat_adopts_a_declared_vram(client, db_session):
    """NODE_VRAM_GB nachtragen aendert den Portalwert — ohne Geräteseite."""
    from models import GpuNode

    headers = _provider_headers(client)
    node = _register_node(client, headers, vram_gb=1, hourly_rate=0.10,
                          vram_source="assumed")
    _beat(client, node, vram_gb=24, vram_source="override")

    row = db_session.query(GpuNode).filter(GpuNode.id == node["id"]).first()
    db_session.refresh(row)
    assert row.vram_gb == 24
    assert row.vram_source == "override"


def test_assumed_vram_is_visible_to_the_admin(client, admin_headers):
    """Der stille Fall muss in der Adminliste sichtbar sein."""
    headers = _provider_headers(client)
    node = _register_node(client, headers, vram_gb=1, hourly_rate=0.30,
                          vram_source="assumed")
    r = client.get("/admin/nodes?limit=100", headers=admin_headers)
    assert r.status_code == 200, r.text
    treffer = [n for n in r.json()["nodes"] if n["id"] == node["id"]]
    assert treffer and treffer[0]["vram_source"] == "assumed"


def test_vram_source_is_exposed_on_the_public_catalogue(client):
    headers = _provider_headers(client)
    node = _register_node(client, headers, vram_gb=8, hourly_rate=0.40,
                          vram_source="detected")
    _beat(client, node)
    r = client.get("/nodes/list")
    assert r.status_code == 200, r.text
    treffer = [n for n in r.json() if n["id"] == node["id"]]
    assert treffer and treffer[0]["vram_source"] == "detected"
