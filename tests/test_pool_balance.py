"""Lastverteilung: zwei Nodes mit demselben Modell teilen sich die Anfragen.

Vorher war `find_best_node` rein score-basiert und damit deterministisch: bei
zwei identischen Nodes gewann immer derselbe Eintrag, der zweite bekam nie einen
Auftrag. Diese Tests messen das neue Verhalten am echten Router-Pfad
(`pool.route_request`), nicht an einer Nachbildung:

  * mehrere Anfragen hintereinander landen abwechselnd auf beiden Nodes,
  * zwei gleichzeitige Anfragen laufen auf **verschiedenen** Nodes,
  * der Zähler laufender Anfragen steht danach wieder auf 0 (kein Leck),
  * ein Fehler auf der Node lässt keine Last stehen.
"""
import asyncio
import uuid
from datetime import datetime

import pytest

from models import GpuNode, User

MODELL = "lasttest:7b"


@pytest.fixture()
def zwei_nodes(client):
    """Zwei gleichwertige, online Nodes mit demselben Modell — und sonst keine."""
    from database import SessionLocal

    db = SessionLocal()
    vorher = []
    try:
        for n in db.query(GpuNode).filter(GpuNode.is_enabled == True).all():  # noqa: E712
            vorher.append(n.id)
            n.is_enabled = False
        db.commit()

        email = f"pool-{uuid.uuid4().hex[:8]}@example.test"
        user = User(email=email, name="Pool Tester", password_hash=None,
                    is_active=True, role="both")
        db.add(user)
        db.commit()
        db.refresh(user)

        ids = []
        for name in ("balance-a", "balance-b"):
            node = GpuNode(
                owner_id=user.id, name=name, gpu_type="Test GPU", vram_gb=24,
                hourly_rate=0.05, status="online", last_seen=datetime.utcnow(),
                is_enabled=True, node_url=f"http://{name}.example.test:11435",
                port=11435, backend="ollama", current_utilization=0.0,
            )
            node.set_allowed_models([MODELL])
            db.add(node)
            db.commit()
            db.refresh(node)
            ids.append(node.id)

        yield {"user_id": user.id, "nodes": ids}
    finally:
        db.close()
        # Andere Nodes wieder anschalten, damit der Rest der Suite unberührt bleibt.
        db2 = SessionLocal()
        try:
            for nid in vorher:
                n = db2.query(GpuNode).filter(GpuNode.id == nid).first()
                if n is not None:
                    n.is_enabled = True
            db2.commit()
        finally:
            db2.close()


@pytest.fixture()
def router(client, monkeypatch):
    """`route_request` ohne lokales Ollama und ohne echten Node-Verkehr."""
    import main
    import pool

    # Lokales Ollama ist im Test nicht erreichbar -> der Router geht in den Pool.
    monkeypatch.setattr(main, "OLLAMA_URL", "http://127.0.0.1:1", raising=False)
    pool.reset_inflight()
    yield pool
    pool.reset_inflight()


def _payload():
    return {"model": MODELL, "messages": [{"role": "user", "content": "hi"}], "stream": False}


def _antwort(node_id):
    return {
        "model": MODELL,
        "message": {"role": "assistant", "content": f"von node {node_id}"},
        "prompt_eval_count": 3,
        "eval_count": 5,
    }


def _user(db, zwei_nodes):
    return db.query(User).filter(User.id == zwei_nodes["user_id"]).first()


def test_sequential_requests_alternate_between_identical_nodes(zwei_nodes, router, monkeypatch):
    """Sechs Anfragen hintereinander: die Nodes wechseln sich ab."""
    from database import SessionLocal

    db = SessionLocal()
    try:
        user = _user(db, zwei_nodes)
        gesehen = []

        async def _fake_forward(node, payload, timeout=300.0):
            return _antwort(node.id)

        monkeypatch.setattr(router, "_forward_to_node", _fake_forward)
        for _ in range(6):
            res = asyncio.run(router.route_request(db, user, _payload(), MODELL))
            assert res["ok"] is True, res
            assert res["source"] == "community", res
            gesehen.append(res["node_id"])

        a, b = zwei_nodes["nodes"]
        assert set(gesehen) == {a, b}, f"nur eine Node bedient: {gesehen}"
        # Reihum, nicht zufällig: die Reihenfolge wechselt bei jeder Anfrage.
        assert gesehen[0] != gesehen[1] and gesehen[1] != gesehen[2], gesehen
        # Kein Zähler bleibt stehen.
        assert router.inflight_snapshot() == {}
    finally:
        db.close()


def test_two_concurrent_requests_use_different_nodes(zwei_nodes, router, monkeypatch):
    """Zwei gleichzeitige Anfragen dürfen nicht auf derselben Node landen."""
    from database import SessionLocal

    db = SessionLocal()
    try:
        user = _user(db, zwei_nodes)
        a, b = zwei_nodes["nodes"]
        gesehen = []

        async def _langsam(node, payload, timeout=300.0):
            # Lange genug, dass die zweite Anfrage den Zähler sieht.
            await asyncio.sleep(0.15)
            gesehen.append(node.id)
            return _antwort(node.id)

        monkeypatch.setattr(router, "_forward_to_node", _langsam)

        async def _beide():
            return await asyncio.gather(
                router.route_request(db, user, _payload(), MODELL),
                router.route_request(db, user, _payload(), MODELL),
            )

        res = asyncio.run(_beide())
        assert all(r["ok"] for r in res), res
        assert sorted(gesehen) == sorted([a, b]), f"beide auf derselben Node: {gesehen}"
        assert router.inflight_snapshot() == {}
    finally:
        db.close()


def test_inflight_counter_does_not_leak_on_failure(zwei_nodes, router, monkeypatch):
    """Ein Fehler auf jeder Node darf keinen Zählerstand hinterlassen."""
    from database import SessionLocal

    db = SessionLocal()
    try:
        user = _user(db, zwei_nodes)

        async def _kaputt(node, payload, timeout=300.0):
            raise RuntimeError("node down")

        monkeypatch.setattr(router, "_forward_to_node", _kaputt)
        res = asyncio.run(router.route_request(db, user, _payload(), MODELL))
        assert res["ok"] is False
        assert router.inflight_snapshot() == {}, "Zähler leckt nach einem Fehler"
    finally:
        db.close()


def test_counter_during_a_running_request(zwei_nodes, router, monkeypatch):
    """Während einer laufenden Anfrage steht die Node mit 1 im Zähler."""
    from database import SessionLocal

    db = SessionLocal()
    try:
        user = _user(db, zwei_nodes)
        a, b = zwei_nodes["nodes"]
        beobachtet = {}

        async def _schaut_nach(node, payload, timeout=300.0):
            beobachtet["self"] = router.node_inflight(node.id)
            beobachtet["other"] = router.node_inflight(b if node.id == a else a)
            return _antwort(node.id)

        monkeypatch.setattr(router, "_forward_to_node", _schaut_nach)
        res = asyncio.run(router.route_request(db, user, _payload(), MODELL))
        assert res["ok"] is True
        assert beobachtet["self"] == 1
        assert beobachtet["other"] == 0
        assert router.inflight_snapshot() == {}
    finally:
        db.close()
