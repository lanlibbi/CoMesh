"""Lebenszeichen einer Node: WebSocket, HTTP-Heartbeat und die Folgen.

Hintergrund (Fix 03.11.2026): im WS-Betrieb setzte der Ping nur `last_ws_seen`,
waehrend `_is_online` in pool.py/nodes.py/admin.py `last_seen` und `status`
verlangte. Eine verbundene Node fiel damit nach 90 s aus dem Routing, obwohl die
Verbindung stand. Diese Tests halten beide Regeln fest — und dass sie sich nicht
gegenseitig aushebeln.
"""
import time
from datetime import datetime, timedelta

from models import GpuNode


def _node(**kw):
    """Eine GpuNode ohne Datenbankzeile — _is_online arbeitet nur auf Attributen."""
    base = dict(
        id=9999, owner_id=1, name="test", gpu_type="Test", vram_gb=16,
        status="online", hourly_rate=0.05, port=11435, backend="ollama",
        is_enabled=True, current_utilization=0.0, vram_used_gb=0.0,
        total_hours=0.0, earnings_total=0.0, created_at=datetime.utcnow(),
        connection_state="disconnected", last_ws_seen=None, last_seen=None,
    )
    base.update(kw)
    return GpuNode(**base)


def test_ws_ping_alone_keeps_node_online():
    """Der Fall, der kaputt war: Verbindung steht, kein HTTP-Heartbeat."""
    node = _node(connection_state="connected", last_ws_seen=time.time(),
                 last_seen=None, status="offline")
    from pool import _is_online as pool_online
    import nodes as nodes_mod
    import admin as admin_mod

    assert pool_online(node) is True
    assert nodes_mod._is_online(node) is True
    assert admin_mod._is_online(node, datetime.utcnow()) is True


def test_stale_ws_ping_is_offline():
    """Ein Ping von vor zwei Minuten zaehlt nicht mehr (90-s-Frist)."""
    node = _node(connection_state="connected", last_ws_seen=time.time() - 120,
                 last_seen=None, status="offline")
    from pool import _is_online as pool_online

    assert pool_online(node) is False


def test_closed_connection_is_offline():
    """Nach dem Trennen schreibt der Server 'disconnected' + 'offline'.

    Der Zeitstempel des letzten Pings steht dann noch frisch in der Zeile; ohne
    die Statuspruefung saehe die Node trotzdem online aus.
    """
    node = _node(connection_state="disconnected", last_ws_seen=time.time(),
                 last_seen=datetime.utcnow(), status="offline")
    from pool import _is_online as pool_online
    import nodes as nodes_mod

    assert pool_online(node) is False
    assert nodes_mod._is_online(node) is False


def test_http_heartbeat_still_counts():
    """Die alte Regel bleibt gueltig: frischer Heartbeat = online."""
    node = _node(connection_state="disconnected", last_ws_seen=None,
                 last_seen=datetime.utcnow() - timedelta(seconds=10), status="online")
    from pool import _is_online as pool_online
    import nodes as nodes_mod

    assert pool_online(node) is True
    assert nodes_mod._is_online(node) is True


def test_stale_heartbeat_is_offline():
    node = _node(connection_state="disconnected",
                 last_seen=datetime.utcnow() - timedelta(seconds=120), status="online")
    from pool import _is_online as pool_online

    assert pool_online(node) is False


def test_disabled_node_is_never_online():
    node = _node(is_enabled=False, connection_state="connected",
                 last_ws_seen=time.time(), last_seen=datetime.utcnow(), status="online")
    from pool import _is_online as pool_online

    assert pool_online(node) is False
