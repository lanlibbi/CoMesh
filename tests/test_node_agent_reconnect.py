"""LANA-48: the node-agent's WS loop must survive a dead portal.

The agent has to reconnect on its own after a network fault — no supervisor,
no restart. These tests pin the three failure shapes we actually saw:

1. the portal refuses the connection      -> exponential backoff, capped
2. the connection is accepted but the welcome never arrives (stall) -> reconnect
3. the socket dies mid-heartbeat          -> reconnect, backoff reset to 1s

`ws_loop()` is an endless `while True`, so the tests stop it by raising a
sentinel from the patched `asyncio.sleep` after the interesting part has been
observed. No real socket, no real sleep, no portal required.

Isolation: `node-agent/` also ships a `netinfo.py`, and the portal imports its
own `netinfo` from the repo root. Importing the agent must therefore clean up
`sys.path` *and* `sys.modules` again, otherwise the portal fixtures in
`tests/conftest.py` pick up the wrong module and the whole suite errors out.
Same for the environment: the agent reads PORTAL_URL/NODE_ID at import time, so
those variables are set for the import and restored right afterwards.
"""

import asyncio
import json
import sys
from pathlib import Path

import pytest

AGENT_DIR = Path(__file__).resolve().parents[1] / "node-agent"
_AGENT_ENV = {
    "NODE_ID": "1",
    "NODE_API_KEY": "test-key",
    "PORTAL_URL": "http://portal.test:8765",
}


@pytest.fixture(scope="module")
def agent_mod():
    """Import node-agent/agent.py without leaking its path, modules or env."""
    import os

    saved_env = {k: os.environ.get(k) for k in _AGENT_ENV}
    for key, value in _AGENT_ENV.items():
        os.environ.setdefault(key, value)

    sys.path.insert(0, str(AGENT_DIR))
    try:
        sys.modules.pop("netinfo", None)
        import agent as agent_module
    finally:
        sys.path.remove(str(AGENT_DIR))
        # The portal (main.py) imports the root netinfo; never hand it the agent's.
        sys.modules.pop("netinfo", None)
        for key, old in saved_env.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old

    yield agent_module


class _StopLoop(Exception):
    """Raised by the patched sleep to end the endless ws_loop."""


class FakeWS:
    """One fake connection. `behaviour` decides how it misbehaves."""

    def __init__(self, behaviour):
        self.behaviour = behaviour
        self.welcomed = False

    async def __aenter__(self):
        if self.behaviour == "refuse":
            raise ConnectionRefusedError("portal unreachable")
        return self

    async def __aexit__(self, *exc):
        return False

    async def recv(self):
        if self.behaviour == "welcome_timeout":
            raise asyncio.TimeoutError()
        if not self.welcomed:
            self.welcomed = True
            return json.dumps({"type": "welcome", "node_id": "1"})
        # Nothing buffered: the drain loop in ws_loop expects this.
        raise asyncio.TimeoutError()

    async def send(self, data):
        if self.behaviour == "stall_after_welcome":
            raise ConnectionResetError("heartbeat write failed")
        return None


def _run_ws_loop(monkeypatch, agent, behaviours, max_connects=50):
    """Run ws_loop against a scripted list of fake connections.

    Returns (connect_attempts, sleeps) where sleeps excludes the ordinary
    heartbeat interval, so only reconnect backoffs remain.
    """
    attempts = []

    def fake_connect(url, **kwargs):
        attempts.append(url.split("?")[0])
        index = len(attempts) - 1
        behaviour = behaviours[index] if index < len(behaviours) else behaviours[-1]
        return FakeWS(behaviour)

    sleeps = []
    real_sleep = asyncio.sleep

    async def fake_sleep(delay, *args, **kwargs):
        if delay != agent.WS_HEARTBEAT_SEC:
            sleeps.append(delay)
        if len(attempts) >= max_connects or len(sleeps) >= 12:
            raise _StopLoop()
        await real_sleep(0)

    monkeypatch.setattr("websockets.connect", fake_connect)
    monkeypatch.setattr(agent, "get_gpu_info", lambda: {})

    async def runner():
        with pytest.raises(_StopLoop):
            await agent.ws_loop()

    # asyncio.sleep is used by the loop under test; patch it globally for the run.
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    asyncio.run(runner())
    return attempts, sleeps


def test_refused_connections_back_off_exponentially_and_cap(monkeypatch, agent_mod):
    attempts, sleeps = _run_ws_loop(monkeypatch, agent_mod, ["refuse"])

    assert len(attempts) >= 5, "the agent must keep retrying, not give up"
    cap = float(agent_mod.WS_RECONNECT_MAX_SEC)
    expected = [min(v, cap) for v in (1.0, 2.0, 4.0, 8.0, 16.0)]
    assert sleeps[: len(expected)] == expected
    assert all(v <= cap for v in sleeps), "backoff must never exceed the cap"


def test_welcome_timeout_triggers_reconnect(monkeypatch, agent_mod):
    attempts, sleeps = _run_ws_loop(
        monkeypatch, agent_mod, ["welcome_timeout"], max_connects=3
    )

    assert len(attempts) >= 2, "a stalled welcome must be treated as a failed connect"
    assert sleeps[0] == 1.0
    assert sleeps[1] == 2.0, "backoff grows while the welcome never arrives"


def test_mid_heartbeat_disconnect_reconnects_and_resets_backoff(monkeypatch, agent_mod):
    # refuse, refuse, then a good connection that dies on the first heartbeat.
    attempts, sleeps = _run_ws_loop(
        monkeypatch, agent_mod, ["refuse", "refuse", "stall_after_welcome", "refuse"]
    )

    assert len(attempts) >= 4, "the socket died, the agent must come back by itself"
    assert sleeps[:3] == [1.0, 2.0, 1.0], (
        "a successful welcome resets the backoff to 1s; the two refusals before it "
        "had grown it to 1s/2s"
    )
    assert sleeps[3] == 2.0, "backoff grows again after the reset"


def test_ws_loop_targets_the_agent_connect_route(monkeypatch, agent_mod):
    attempts, _ = _run_ws_loop(monkeypatch, agent_mod, ["refuse"], max_connects=2)

    assert attempts, "ws_loop never tried to connect"
    assert all(url.endswith("/agent/connect") for url in attempts)
