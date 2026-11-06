"""Node-lokale Modelle: melden, speichern, anbieten, dorthin routen.

Hintergrund: der Modellkatalog des Portals kam ausschliesslich vom zentralen
Ollama (`OLLAMA_URL`). Ein Provider, der auf seiner eigenen Maschine etwas
anderes laufen hat — qwen3:4b/8b/14b auf einem Windows-Rechner, ein
Llama-Server hinter `BACKEND=openai` —, konnte es deshalb niemandem anbieten:
das Modell fehlte in der Auswahl, obwohl die Node es bedienen kann.

Diese Tests halten die vier Schritte fest, an denen die Kette haengt:

  1. Der Agent fragt sein Backend und legt die Namen in den Heartbeat
     (`backend_models`, `send_heartbeat`).
  2. Das Portal speichert sie je Node (`POST /nodes/{id}/heartbeat`).
  3. `GET /v1/models` fuehrt sie auf, auch ohne Eintrag im zentralen Katalog,
     aber weiterhin gefiltert nach `can_use_model` und nur fuer aktive Nodes.
  4. Das Routing schickt einen Aufruf an eine Node, die das Modell gemeldet hat
     — nicht an eine, die es nicht hat (`GpuNode.can_serve_model`,
     `pool.find_best_node`, `pool.route_request`).
"""
import asyncio
import importlib
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

import pytest

AGENT_DIR = Path(__file__).resolve().parents[1] / "node-agent"

# Liegt nur auf der einen Node — genau der Fall aus dem Auftrag.
NODE_MODELL = "qwen3:4b"
# Liegt auf der anderen Node und ist auch im zentralen Katalog.
ANDERES_MODELL = "llama3.1:8b"


def _nur_lokal() -> str:
    """Ein Modellname, den nur dieser eine Test erzeugt (keine Kreuzwirkung)."""
    return f"nur-lokal-{uuid.uuid4().hex[:8]}:4b"


# --------------------------------------------------------------------------
# Agentenseite
# --------------------------------------------------------------------------
class _Antwort:
    """Minimaler httpx.Response-Ersatz."""

    def __init__(self, payload=None, status_code=200):
        self._payload = payload if payload is not None else {}
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class _FakeClient:
    """httpx.AsyncClient-Ersatz: beantwortet GET (Backend) und POST (Portal)."""

    def __init__(self, get_payload=None, get_status=200):
        self.get_payload = get_payload if get_payload is not None else {}
        self.get_status = get_status
        self.gets = []
        self.posts = []

    async def get(self, url, timeout=None, **kwargs):
        self.gets.append(url)
        return _Antwort(self.get_payload, self.get_status)

    async def post(self, url, json=None, headers=None, timeout=None, **kwargs):
        self.posts.append({"url": url, "json": json, "headers": headers})
        return _Antwort({}, 204)


@pytest.fixture(scope="module")
def agent_mod():
    """`agent.py` als Modul — mit NODE_ID/Schluessel, aber ohne laufenden Agenten."""
    saved = {k: os.environ.get(k) for k in ("NODE_ID", "NODE_API_KEY", "PORTAL_URL", "BACKEND")}
    os.environ["NODE_ID"] = "1"
    os.environ["NODE_API_KEY"] = "test-key"
    os.environ["PORTAL_URL"] = "http://portal.test:8765"
    os.environ.pop("BACKEND", None)
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


def test_agent_liest_die_modellliste_des_ollama_backends(agent_mod):
    client = _FakeClient(get_payload={"models": [
        {"name": NODE_MODELL},
        {"name": ANDERES_MODELL},
        {"name": NODE_MODELL},          # doppelt -> nur einmal melden
    ]})
    namen = asyncio.run(agent_mod.backend_models(client))
    assert namen == [NODE_MODELL, ANDERES_MODELL]
    # Gefragt wird das Backend, nicht das Portal.
    assert client.gets == [agent_mod.backend_list_url()]


def test_agent_liest_die_modellliste_eines_openai_backends(agent_mod, monkeypatch):
    monkeypatch.setattr(agent_mod, "BACKEND", "openai")
    client = _FakeClient(get_payload={"object": "list", "data": [
        {"id": NODE_MODELL}, {"id": "  "}, {"id": "local-vllm"},
    ]})
    assert asyncio.run(agent_mod.backend_models(client)) == [NODE_MODELL, "local-vllm"]
    assert client.gets == [f"{agent_mod.INFERENCE_URL}/v1/models"]


def test_agent_meldet_keine_liste_wenn_das_backend_schweigt(agent_mod):
    """`None` heisst: unbekannt. Das Portal behaelt dann die letzte Meldung."""
    client = _FakeClient(get_payload={"error": "down"}, get_status=500)
    assert asyncio.run(agent_mod.backend_models(client)) is None


def test_heartbeat_traegt_die_modellliste(agent_mod, monkeypatch):
    monkeypatch.setattr(agent_mod, "get_gpu_info", lambda: {
        "utilization": 0.0, "vram_used_gb": 0.0, "vram_total_gb": 8.0, "active_jobs": 0,
    })
    monkeypatch.setattr(agent_mod, "vram_report", lambda: (8, "detected"))
    monkeypatch.setattr(agent_mod, "advertised_host", lambda: "node.example.test")
    client = _FakeClient(get_payload={"models": [{"name": NODE_MODELL}]})

    asyncio.run(agent_mod.send_heartbeat(client))

    assert len(client.posts) == 1, client.posts
    gesendet = client.posts[0]["json"]
    assert gesendet["models"] == [NODE_MODELL]
    assert gesendet["advertise_host"] == "node.example.test"


# --------------------------------------------------------------------------
# Modellrechte: was eine Node bedienen darf
# --------------------------------------------------------------------------
def test_node_mit_meldung_bedient_nur_gemeldete_modelle():
    from models import GpuNode

    node = GpuNode(name="x", gpu_type="y", vram_gb=8)
    node.set_reported_models([NODE_MODELL])
    assert node.can_serve_model(NODE_MODELL) is True
    assert node.can_serve_model(ANDERES_MODELL) is False

    # Eine Freigabe erweitert das Angebot nicht: die Maschine hat das Modell nicht.
    node.set_allowed_models([ANDERES_MODELL])
    assert node.can_serve_model(ANDERES_MODELL) is False
    assert node.can_serve_model(NODE_MODELL) is False

    # Cloud-Modelle laufen nicht im Backend der Node und haengen nicht an der Meldung.
    node.set_allowed_models(["cloud-gpt"])
    assert node.can_serve_model("cloud-gpt") is True


def test_node_ohne_meldung_verhaelt_sich_wie_bisher():
    from models import GpuNode

    node = GpuNode(name="x", gpu_type="y", vram_gb=8)
    node.set_reported_models([])            # Backend erreichbar, nichts installiert
    assert node.get_reported_models() == []
    # Unbekannt/unbrauchbar -> die Freigabe entscheidet allein.
    node.set_reported_models(None)
    assert node.get_reported_models() is None
    assert node.can_serve_model(NODE_MODELL) is True
    assert node.can_serve_model("cloud-gpt") is False


# --------------------------------------------------------------------------
# Portalseite: Hilfen
# --------------------------------------------------------------------------
def _konto(client, role="both", name="Provider"):
    """Konto ueber den Adminweg anlegen (freigegeben, mit API-Schluessel)."""
    email = f"reported-{uuid.uuid4().hex[:10]}@example.test"
    r = client.post("/admin/users", headers={"Authorization": f"Bearer {os.environ['ADMIN_TOKEN']}"},
                    json={"email": email, "name": name, "role": role,
                          "password": "pw-reported-1234", "initial_credits": 10.0})
    assert r.status_code == 201, r.text
    login = client.post("/auth/login", json={"email": email, "password": "pw-reported-1234"})
    assert login.status_code == 200, login.text
    return {"id": r.json()["user_id"], "email": email,
            "headers": {"Authorization": f"Bearer {login.json()['api_key']}"}}


def _node(client, headers):
    r = client.post("/nodes/register", headers=headers, json={
        "name": f"reported-{uuid.uuid4().hex[:8]}", "gpu_type": "Test GPU",
        "vram_gb": 24, "hourly_rate": 0.05,
        "node_url": f"http://node-{uuid.uuid4().hex[:6]}.example.test:11435", "port": 11435,
    })
    assert r.status_code == 201, r.text
    return r.json()


def _beat(client, node, models=None, status="online"):
    body = {"status": status, "gpu_util": 0.0, "vram_used_gb": 0.0,
            "vram_total_gb": float(node["vram_gb"]), "active_jobs": 0}
    if models is not None:
        body["models"] = models
    r = client.post(f"/nodes/{node['id']}/heartbeat",
                    headers={"X-Node-Key": node["agent_api_key"]}, json=body)
    assert r.status_code == 204, r.text


class _ZentralerKatalog:
    """Ersetzt `httpx.AsyncClient` in main: fester Katalog des zentralen Ollama."""

    models = [{"name": ANDERES_MODELL, "modified_at": "2026-01-01T00:00:00Z"}]

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, **kwargs):
        return _Antwort({"models": list(self.models)})


class _FakeHttpx:
    """Nur was main.py von httpx braucht."""

    AsyncClient = _ZentralerKatalog


def _katalog(client, headers):
    r = client.get("/v1/models", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


# --------------------------------------------------------------------------
# 2. Das Portal speichert die gemeldeten Modelle je Node
# --------------------------------------------------------------------------
def test_portal_speichert_die_gemeldeten_modelle(client):
    konto = _konto(client)
    node = _node(client, konto["headers"])
    assert node["reported_models"] is None          # vor dem ersten Heartbeat: unbekannt

    _beat(client, node, models=[NODE_MODELL, ANDERES_MODELL, NODE_MODELL])

    detail = client.get(f"/nodes/{node['id']}").json()
    assert detail["reported_models"] == [NODE_MODELL, ANDERES_MODELL]
    assert detail["reported_models_at"]
    # Die Freigabe des Besitzers bleibt davon unberuehrt.
    assert detail["allowed_models"] is None


def test_heartbeat_ohne_meldung_laesst_die_liste_stehen(client):
    """Ein Agent, der sein Backend nicht abfragen konnte, loescht nichts."""
    konto = _konto(client)
    node = _node(client, konto["headers"])
    _beat(client, node, models=[NODE_MODELL])
    _beat(client, node, models=None)

    assert client.get(f"/nodes/{node['id']}").json()["reported_models"] == [NODE_MODELL]


# --------------------------------------------------------------------------
# 3. GET /v1/models fuehrt die gemeldeten Modelle auf
# --------------------------------------------------------------------------
def test_v1_models_fuehrt_ein_nur_lokal_vorhandenes_modell_auf(client, monkeypatch):
    import main
    monkeypatch.setattr(main, "httpx", _FakeHttpx)

    modell = _nur_lokal()
    konto = _konto(client)
    node = _node(client, konto["headers"])
    _beat(client, node, models=[modell, ANDERES_MODELL])

    katalog = _katalog(client, konto["headers"])
    namen = [m.get("name") for m in katalog["models"]]
    ids = [m["id"] for m in katalog["data"]]

    # Das node-lokale Modell steht drin, obwohl der zentrale Katalog es nicht kennt ...
    assert modell in namen
    assert modell in ids
    # ... das Modell aus dem zentralen Katalog bleibt genau einmal drin.
    assert namen.count(ANDERES_MODELL) == 1
    eintrag = [m for m in katalog["models"] if m.get("name") == modell][0]
    assert eintrag["source"] == "node"
    assert node["id"] in eintrag["node_ids"]


def test_v1_models_zeigt_keine_modelle_pausierter_nodes(client, monkeypatch):
    import main
    monkeypatch.setattr(main, "httpx", _FakeHttpx)

    modell = _nur_lokal()
    konto = _konto(client)
    node = _node(client, konto["headers"])
    _beat(client, node, models=[modell])
    r = client.post(f"/nodes/{node['id']}/enable?enabled=false", headers=konto["headers"])
    assert r.status_code == 200, r.text

    namen = [m.get("name") for m in _katalog(client, konto["headers"])["models"]]
    assert modell not in namen


def test_v1_models_zeigt_kein_modell_das_der_provider_nicht_freigibt(client, monkeypatch):
    """Gemeldet heisst nicht automatisch angeboten: die Freigabe der Node gilt auch hier."""
    import main
    monkeypatch.setattr(main, "httpx", _FakeHttpx)

    versteckt = _nur_lokal()
    sichtbar = f"nur-lokal-{uuid.uuid4().hex[:8]}:8b"
    konto = _konto(client)
    node = _node(client, konto["headers"])
    _beat(client, node, models=[versteckt, sichtbar])
    r = client.put(f"/nodes/{node['id']}", headers=konto["headers"],
                   json={"allowed_models": [sichtbar]})
    assert r.status_code == 200, r.text

    namen = [m.get("name") for m in _katalog(client, konto["headers"])["models"]]
    assert sichtbar in namen
    assert versteckt not in namen


def test_v1_models_haelt_die_freigabe_des_kontos_ein(client, monkeypatch):
    """Ein Consumer ohne Freigabe bekommt auch die gemeldeten Modelle nicht."""
    import main
    from database import SessionLocal
    from models import User

    monkeypatch.setattr(main, "httpx", _FakeHttpx)

    modell = _nur_lokal()
    provider = _konto(client)
    node = _node(client, provider["headers"])
    _beat(client, node, models=[modell])

    consumer = _konto(client, role="consumer", name="Consumer")
    namen = [m.get("name") for m in _katalog(client, consumer["headers"])["models"]]
    assert modell not in namen

    # Mit Freigabe auf genau dieses Modell ist es da.
    db = SessionLocal()
    try:
        konto = db.query(User).filter(User.email == consumer["email"]).first()
        konto.set_allowed_models([modell])
        db.commit()
    finally:
        db.close()
    namen = [m.get("name") for m in _katalog(client, consumer["headers"])["models"]]
    assert modell in namen


# --------------------------------------------------------------------------
# 4. Routing: nur an Nodes, die das Modell gemeldet haben
# --------------------------------------------------------------------------
@pytest.fixture()
def bauplatz(client):
    """Spielwiese: alle anderen Nodes pausiert, ein frisches Konto fuer unsere Nodes."""
    from database import SessionLocal
    from models import GpuNode, User

    db = SessionLocal()
    vorher = []
    for n in db.query(GpuNode).filter(GpuNode.is_enabled == True).all():  # noqa: E712
        vorher.append(n.id)
        n.is_enabled = False
    db.commit()

    user = User(email=f"routing-{uuid.uuid4().hex[:8]}@example.test", name="Routing Tester",
                password_hash=None, is_active=True, role="both")
    db.add(user)
    db.commit()
    db.refresh(user)

    def baue(name, stunde, gemeldet):
        node = GpuNode(
            owner_id=user.id, name=f"{name}-{uuid.uuid4().hex[:4]}", gpu_type="Test GPU",
            vram_gb=24, hourly_rate=stunde, status="online", last_seen=datetime.utcnow(),
            is_enabled=True, node_url=f"http://{name}.example.test:11435",
            port=11435, backend="ollama", current_utilization=0.0,
        )
        if gemeldet is not None:
            node.set_reported_models(gemeldet)
        db.add(node)
        db.commit()
        db.refresh(node)
        return node.id

    yield baue, db, user.id

    db.close()
    db2 = SessionLocal()
    try:
        for nid in vorher:
            n = db2.query(GpuNode).filter(GpuNode.id == nid).first()
            if n is not None:
                n.is_enabled = True
        db2.commit()
    finally:
        db2.close()


def test_routing_geht_an_die_node_die_das_modell_gemeldet_hat(bauplatz):
    """Die billigere Node hat das Modell nicht — sie darf den Auftrag nicht bekommen."""
    baue, db, _uid = bauplatz
    hat_es = baue("hat-es", 0.50, [NODE_MODELL])
    hat_es_nicht = baue("hat-es-nicht", 0.01, [ANDERES_MODELL])

    import pool
    pool.reset_inflight()
    try:
        gewaehlt = pool.find_best_node(db, NODE_MODELL)
        assert gewaehlt is not None, "keine Node gefunden, obwohl eine das Modell meldet"
        assert gewaehlt.id == hat_es, (
            f"Auftrag ging an Node {gewaehlt.id} (hat_es={hat_es}, ohne={hat_es_nicht})"
        )
    finally:
        pool.reset_inflight()


def test_node_ohne_meldung_bleibt_waehlbar(bauplatz):
    """Alte Agenten melden nichts — dort entscheidet weiter nur die Freigabe."""
    baue, db, _uid = bauplatz
    unbekannt = baue("unbekannt", 0.02, None)

    import pool
    pool.reset_inflight()
    try:
        gewaehlt = pool.find_best_node(db, NODE_MODELL)
        assert gewaehlt is not None and gewaehlt.id == unbekannt
    finally:
        pool.reset_inflight()


def test_gemeldete_node_gewinnt_gegen_unbekannte_node(bauplatz):
    """Von zwei moeglichen Nodes gewinnt die, die das Modell bestaetigt hat."""
    baue, db, _uid = bauplatz
    bestaetigt = baue("bestaetigt", 0.50, [NODE_MODELL])
    baue("unbekannt", 0.02, None)

    import pool
    pool.reset_inflight()
    try:
        gewaehlt = pool.find_best_node(db, NODE_MODELL)
        assert gewaehlt is not None and gewaehlt.id == bestaetigt
    finally:
        pool.reset_inflight()


def test_route_request_schickt_den_auftrag_an_die_passende_node(bauplatz, monkeypatch):
    """Der echte Router-Pfad: lokales Ollama weg, Weiterleitung an die Node simuliert."""
    import main
    import pool
    from models import User

    baue, db, uid = bauplatz
    hat_es = baue("echt-hat-es", 0.50, [NODE_MODELL])
    baue("echt-hat-es-nicht", 0.01, [ANDERES_MODELL])

    monkeypatch.setattr(main, "OLLAMA_URL", "http://127.0.0.1:1", raising=False)
    ziele = []

    async def _fake_forward(node, payload, timeout=300.0):
        ziele.append(node.id)
        return {"model": NODE_MODELL,
                "message": {"role": "assistant", "content": "hallo"},
                "prompt_eval_count": 1, "eval_count": 1}

    monkeypatch.setattr(pool, "_forward_to_node", _fake_forward)
    pool.reset_inflight()
    try:
        user = db.query(User).filter(User.id == uid).first()
        res = asyncio.run(pool.route_request(
            db, user,
            {"model": NODE_MODELL, "messages": [{"role": "user", "content": "hi"}], "stream": False},
            NODE_MODELL,
        ))
    finally:
        pool.reset_inflight()

    assert res["ok"] is True, res
    assert res["source"] == "community", res
    assert res["node_id"] == hat_es
    assert ziele == [hat_es]
