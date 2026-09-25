"""
GPU-Pool WebSocket Connectivity Tests (Phase 1).

Covers:
  1. test_ws_auth_fail          - WS connect with wrong key -> server closes 4401
  2. test_ws_connect_success    - Real WS handshake -> DB state=connected
  3. test_ws_disconnect_cleanup - WS close -> DB state=disconnected
  4. test_ws_heartbeat_updates_timestamp - Ping -> last_ws_seen advances
  5. test_http_still_works      - Regression: existing v1 features still pass

Implementation note (decision documented):
  We use the real Python `websockets` client (>=13.x) to talk to the
  real backend. The backend is the v1 FastAPI on http://localhost:8765
  with the new /agent/connect endpoint mounted. The agent binary
  itself is NOT spawned — instead we drive the same protocol a real
  WS agent would, so we can test the connect/auth/heartbeat/close
  cycle end-to-end without GPU conflicts or a real Ollama round-trip.

  Reason: the agent's GPU code path is well-covered by v1's HTTP
  heartbeat tests; Phase 1 is about the transport and the server-side
  state machine, not the GPU. If/when Phase 2 adds the job stream,
  the agent-level test will be revisited.

Run with the API service reachable. Override with GPU_POOL_API.
    GPU_POOL_API=http://localhost:8765 python3 tests/test_ws_connectivity.py
"""
import asyncio
import json
import os
import sys
import time
import urllib.error
import urllib.request

# `websockets` is the same lib the agent uses (>=13.1)
try:
    import websockets
except ImportError:
    print("ERROR: 'websockets' package not installed. pip install websockets==13.1", file=sys.stderr)
    sys.exit(2)

API_HTTP = os.environ.get("GPU_POOL_API", "http://localhost:8000").rstrip("/")
# Derive WS URL from the HTTP one. Default test setup runs on 8765; 8000 is
# the in-container port but `websockets` talks to the host port.
def _to_ws_url(http_base: str, path: str) -> str:
    base = http_base.rstrip("/")
    if base.startswith("https://"):
        return "wss://" + base[len("https://"):] + path
    if base.startswith("http://"):
        return "ws://" + base[len("http://"):] + path
    return "ws://" + base + path

API_WS = _to_ws_url(API_HTTP, "/agent/connect")


def http(method, path, body=None, token=None, raw=False):
    url = f"{API_HTTP}{path}"
    data = None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            text = r.read().decode("utf-8")
            if raw:
                return r.status, text
            return r.status, (json.loads(text) if text else None)
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8")
        try:
            payload = json.loads(text)
        except Exception:
            payload = text
        if raw:
            return e.code, text
        return e.code, payload


PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
results = []


def check(name, cond, detail=""):
    tag = PASS if cond else FAIL
    print(f"  {tag} {name}{(' — ' + detail) if detail else ''}")
    results.append(bool(cond))
    return cond


async def _register_node(token: str, name: str) -> dict:
    """Register a node via REST and return the JSON response (incl. api_key + id).

    The endpoint returns 201 Created (per nodes.py: status_code=201).
    """
    status, body = http("POST", "/nodes/register", {
        "name": name, "gpu_type": "RTX 4090", "vram_gb": 24, "port": 11434,
    }, token=token)
    if status not in (200, 201):
        raise RuntimeError(f"/nodes/register failed: {status} {body}")
    return body


def _register_test_user() -> str:
    """Register a fresh user (role=provider) and return their API key."""
    import secrets as _s
    email = f"ws-test-{int(time.time())}-{_s.token_hex(4)}@example.com"
    status, body = http("POST", "/auth/register", {
        "email": email, "name": "WS Test", "password": "test123456", "role": "provider",
    })
    if status != 200:
        raise RuntimeError(f"register failed: {status} {body}")
    return body["api_key"], body["user_id"]


def _get_node_state(node_id: int, token: str = None) -> dict:
    """Connection state as the *owner* sees it.

    Since the auth hardening, last_ws_seen / ws_session_id are only returned to
    the node's owner (or an admin) - they are handles for a live transport and
    are not world-readable. The tests act as the node owner here, so they pass
    the owner's API key.
    """
    status, body = http("GET", f"/nodes/{node_id}/connection", token=token)
    if status != 200:
        return {"_http_status": status, "_http_body": body}
    return body


async def test_ws_auth_fail():
    print("Test: WS connect with wrong key -> 4401")
    # Use node_id=1 with a deliberately wrong key. Even if node 1 doesn't exist
    # the server will close with 4401 (auth fail) before doing any DB write.
    bad_url = API_WS + "?node_id=1&node_key=node_definitely_wrong_xxxxxxxx"
    try:
        async with websockets.connect(bad_url, open_timeout=5) as ws:
            # If the server accepts and sends a frame, that's a fail.
            try:
                first = await asyncio.wait_for(ws.recv(), timeout=2.0)
                check("server did not stream data on bad auth", False, f"got: {first[:80]}")
            except websockets.ConnectionClosed as cc:
                check("close code is 4401", cc.code == 4401, f"got {cc.code} ({cc.reason})")
                return
            except asyncio.TimeoutError:
                check("server closed connection on bad auth", False, "timeout instead of close")
                return
            check("server closed connection on bad auth", False, "no close received")
    except websockets.InvalidStatus as e:
        # Some servers reject the handshake at HTTP level; the spec lets them.
        check("handshake rejected (InvalidStatus)", True, str(e.response.status_code) if hasattr(e, 'response') else str(e))
    except websockets.ConnectionClosed as cc:
        check("close code is 4401", cc.code == 4401, f"got {cc.code} ({cc.reason})")


async def test_ws_connect_success(token, node_id, node_key):
    """token = owner API key (needed for the privileged connection view)."""
    print(f"\nTest: WS connect success (node_id={node_id})")
    url = API_WS + f"?node_id={node_id}&node_key={node_key}"
    async with websockets.connect(url, open_timeout=5) as ws:
        # First frame should be the welcome.
        raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
        welcome = json.loads(raw)
        check("welcome.type == welcome", welcome.get("type") == "welcome", f"got {welcome.get('type')}")
        check("welcome.node_id == our node", welcome.get("node_id") == node_id, f"got {welcome.get('node_id')}")
        check("welcome.session_id present", bool(welcome.get("session_id")))

        # The DB should now show connected.
        await asyncio.sleep(0.2)  # let the server commit
        st = _get_node_state(node_id, token)
        check("REST /connection returns state=connected", st.get("state") == "connected", f"got {st.get('state')}")
        check("REST /connection has session_id", bool(st.get("ws_session_id")))
        check("REST /connection has last_ws_seen", st.get("last_ws_seen") is not None)
    # Exiting the `async with` closes the WS. Give the server a moment to clean up.
    await asyncio.sleep(0.3)
    st2 = _get_node_state(node_id, token)
    check("after close: state=disconnected", st2.get("state") == "disconnected", f"got {st2.get('state')}")
    check("after close: ws_session_id cleared", st2.get("ws_session_id") in (None, ""), f"got {st2.get('ws_session_id')}")


async def test_ws_disconnect_cleanup(token, node_id, node_key):
    print(f"\nTest: WS disconnect cleanup (node_id={node_id})")
    url = API_WS + f"?node_id={node_id}&node_key={node_key}"
    ws = await websockets.connect(url, open_timeout=5)
    try:
        # Consume welcome
        await asyncio.wait_for(ws.recv(), timeout=5.0)
        await asyncio.sleep(0.2)
        st = _get_node_state(node_id, token)
        check("during connection: state=connected", st.get("state") == "connected", f"got {st.get('state')}")
    finally:
        await ws.close()
    await asyncio.sleep(0.3)
    st2 = _get_node_state(node_id, token)
    check("after close: state=disconnected", st2.get("state") == "disconnected", f"got {st2.get('state')}")
    check("after close: ws_session_id null", st2.get("ws_session_id") in (None, ""), f"got {st2.get('ws_session_id')}")


async def test_ws_heartbeat_updates_timestamp(token, node_id, node_key):
    print(f"\nTest: WS heartbeat updates timestamp (node_id={node_id})")
    url = API_WS + f"?node_id={node_id}&node_key={node_key}"
    async with websockets.connect(url, open_timeout=5) as ws:
        # welcome
        welcome_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
        welcome = json.loads(welcome_raw)
        baseline = welcome.get("server_time")
        check("welcome has server_time", baseline is not None)
        await asyncio.sleep(0.2)
        st0 = _get_node_state(node_id, token)
        ts0 = st0.get("last_ws_seen")
        check("last_ws_seen is set after connect", ts0 is not None, f"got {ts0}")

        # Send a ping; expect a pong back and a fresh last_ws_seen.
        await ws.send(json.dumps({
            "type": "ping",
            "vram_used_gb": 12.34,
            "active_jobs": 2,
            "uptime": 99,
        }))
        # Drain frames for up to 3s looking for a pong
        pong_seen = False
        deadline = time.time() + 3.0
        while time.time() < deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=0.5)
                m = json.loads(raw)
                if m.get("type") == "pong":
                    pong_seen = True
                    break
            except asyncio.TimeoutError:
                continue
        check("server replied with pong", pong_seen)

        # Now send a second ping and verify last_ws_seen advanced
        await asyncio.sleep(1.1)
        await ws.send(json.dumps({"type": "ping", "vram_used_gb": 13.0, "active_jobs": 0, "uptime": 100}))
        await asyncio.sleep(0.5)
        st1 = _get_node_state(node_id, token)
        ts1 = st1.get("last_ws_seen")
        check("last_ws_seen advanced after second ping", ts1 is not None and ts0 is not None and ts1 > ts0, f"ts0={ts0} ts1={ts1}")


def test_http_still_works():
    """Regression: v1 endpoints still work after WS additions."""
    print("\nTest: v1 HTTP regression")
    import secrets as _s
    email = f"ws-regress-{int(time.time())}-{_s.token_hex(4)}@example.com"
    status, body = http("POST", "/auth/register", {
        "email": email, "name": "WS Regress", "password": "test123456", "role": "provider",
    })
    check("register returns 200", status == 200, str(status))
    if status != 200:
        return
    key = body["api_key"]
    # /v1/me still works
    status, me = http("GET", "/v1/me", token=key)
    check("GET /v1/me -> 200", status == 200, str(status))
    check("me.email matches", me.get("email") == email, f"got {me.get('email')}")
    # /v1/available-models still works
    status, am = http("GET", "/v1/available-models", token=key)
    check("GET /v1/available-models -> 200", status == 200, str(status))
    check("response has 'models' array", isinstance(am.get("models"), list))
    # /v1/chat/completions with cloud model -> 403 (whitelist default)
    status, cc = http("POST", "/v1/chat/completions", {
        "model": "minimax-m3:cloud",
        "messages": [{"role": "user", "content": "hi"}],
    }, token=key)
    check("cloud model blocked (403)", status == 403, f"got {status}")
    # /nodes/register still works
    status, node = http("POST", "/nodes/register", {
        "name": f"regress-node-{_s.token_hex(3)}",
        "gpu_type": "RTX 4090", "vram_gb": 24, "port": 11434,
    }, token=key)
    # /nodes/register returns 201 Created
    check("POST /nodes/register -> 201", status == 201, f"got {status}")
    if status == 200:
        # /nodes/{id}/connection (new) returns disconnected. Anonymous callers
        # only get the state (no session id / last-seen); the owner gets more.
        status, conn = http("GET", f"/nodes/{node['id']}/connection")
        check("GET /nodes/{id}/connection -> 200", status == 200, str(status))
        check("state=disconnected for never-connected node", conn.get("state") == "disconnected", f"got {conn.get('state')}")
        check("anonymous callers do not receive the ws session id",
              conn.get("ws_session_id") is None, str(conn.get("ws_session_id")))
        status, conn_owner = http("GET", f"/nodes/{node['id']}/connection", token=key)
        check("owner sees the full connection record", status == 200 and conn_owner.get("state") == "disconnected",
              f"got {status}/{conn_owner.get('state')}")


async def amain():
    print(f"GPU-Pool WS connectivity tests against {API_HTTP}")
    print("=" * 60)

    # 1. auth fail
    await test_ws_auth_fail()

    # Set up: register a user and a node for the remaining tests.
    token, _ = _register_test_user()
    node = await _register_node(token, f"ws-test-{int(time.time())}")
    node_id = node["id"]
    # The response uses 'agent_api_key' as the field name (model: NodeRegistered);
    # internally it maps to GpuNode.api_key. The WS handler compares against api_key.
    node_key = node["agent_api_key"]

    # 2. connect success (also exercises the disconnect cleanup path via the
    #    `async with` exit, so it doubles as test #3 conceptually — but we
    #    still run an explicit test #3 for the abrupt-close path).
    await test_ws_connect_success(token, node_id, node_key)

    # 3. disconnect cleanup (abrupt close path)
    await test_ws_disconnect_cleanup(token, node_id, node_key)

    # 4. heartbeat updates timestamp
    await test_ws_heartbeat_updates_timestamp(token, node_id, node_key)

    # 5. regression: v1 HTTP still works
    test_http_still_works()

    print()
    print("=" * 60)
    fails = sum(1 for r in results if not r)
    if fails == 0:
        print(f"All {len(results)} checks passed against {API_HTTP}")
        return 0
    print(f"{fails} of {len(results)} checks FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(amain()))
