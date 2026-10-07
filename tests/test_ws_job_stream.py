"""
GPU-Pool WebSocket Job-Stream Tests (Phase 2).

Covers:
  1. test_ws_job_roundtrip            - In-process FastAPI test-server
                                        (TestClient). Simulated agent
                                        connects via WS, user POSTs
                                        /v1/chat/completions, server
                                        routes via WS, agent replies,
                                        response returns, PoolJob booked.
  2. test_ws_job_timeout              - Agent receives job but never
                                        replies -> JobTimeoutError raised
                                        by send_job_via_ws. We exercise
                                        the dispatcher directly with a
                                        short timeout.
  3. test_ws_node_offline_routes_http - Node has no WS connection -> the
                                        HTTP fallback path is used (we
                                        mock pool.httpx.AsyncClient to
                                        count calls).
  4. test_ws_job_error_propagation    - Agent replies with ok:false ->
                                        WSError raised; route_request
                                        falls back to HTTP.
  5. test_v1_still_green              - Regression: v1 + Phase-1 tests
                                        against the LIVE docker api.

Why in-process for 1-4:
  Phase 2 routing logic lives in the server process (ws._WS_REGISTRY,
  _PENDING_JOBS). To test it deterministically we run the server in
  the same process as the test. We use a private ephemeral ASGI
  client (`httpx.AsyncClient(transport=ASGITransport(app=app))`)
  bound to a free port for the WS test agent to dial into. The WS
  endpoint binds on 127.0.0.1:<free> via uvicorn in a task. This
  mirrors the Phase-1 test pattern (test_ws_connectivity.py) but
  without depending on the long-running docker container.

Test 5 is the regression: we hit the LIVE docker container at
http://localhost:8765 to confirm v1 + Phase-1 still work end-to-end.

Run:
    GPU_POOL_API=http://localhost:8765 python3 tests/test_ws_job_stream.py
"""
import asyncio
import json
import os
import secrets
import socket
import sys
import time
import urllib.error
import urllib.request
from typing import Optional

# `websockets` is the same lib the agent uses
try:
    import websockets
except ImportError:
    print("ERROR: 'websockets' package not installed. pip install websockets==13.1", file=sys.stderr)
    sys.exit(2)

# httpx is needed for the ASGI in-process client
import httpx

API_HTTP = os.environ.get("GPU_POOL_API", "http://localhost:8000").rstrip("/")


def _to_ws_url(http_base: str, path: str) -> str:
    base = http_base.rstrip("/")
    if base.startswith("https://"):
        return "wss://" + base[len("https://"):] + path
    if base.startswith("http://"):
        return "ws://" + base[len("http://"):] + path
    return "ws://" + base + path


API_WS = _to_ws_url(API_HTTP, "/agent/connect")


def http_live(method, path, body=None, token=None, raw=False):
    """Hit the LIVE docker container (regression tests)."""
    url = f"{API_HTTP}{path}"
    data = None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
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


# ----------------------------------------------------------------------------
# In-process FastAPI test server
# ----------------------------------------------------------------------------
def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


async def _start_test_server():
    """Start a uvicorn server in a background asyncio task, return (port, app).

    The server runs the real main:app. Returns the bound port and the
    ASGI app reference (so tests can issue in-process ASGI calls if needed).
    """
    import uvicorn
    # Ensure project root is on sys.path
    proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if proj_root not in sys.path:
        sys.path.insert(0, proj_root)
    # Use a private DATA_DIR for the test DB
    test_data_dir = os.path.join("/tmp", f"gpu_pool_test_{os.getpid()}_{int(time.time())}")
    os.makedirs(test_data_dir, exist_ok=True)
    os.environ["DATA_DIR"] = test_data_dir
    # main.py's seed user tries to write /data/seed_api_key.txt; redirect.
    os.environ["SEED_KEY_PATH"] = os.path.join(test_data_dir, "seed_api_key.txt")
    # Re-import main fresh so it picks up the DATA_DIR
    for mod in ("main", "database", "models", "ws", "pool", "auth", "nodes", "payments", "frontend"):
        if mod in sys.modules:
            del sys.modules[mod]
    import main as main_mod  # noqa: E402
    app = main_mod.app
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port,
                            log_level="warning", lifespan="on")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    # Wait for the server to be ready (async-friendly)
    for _ in range(100):
        if server.started:
            break
        await asyncio.sleep(0.1)
    else:
        raise RuntimeError("test server failed to start")
    return port, app, server, task, test_data_dir


# ----------------------------------------------------------------------------
# Simulated agent
# ----------------------------------------------------------------------------
class SimulatedAgent:
    """Behaves like a real WS-mode node-agent for one connection."""

    def __init__(self, ws_base: str, node_id: int, node_key: str, *,
                 ollama_response=None, ollama_error=None,
                 ignore_jobs: bool = False, reply_delay: float = 0.0,
                 simulate_timeout: bool = False):
        self.node_id = node_id
        self.node_key = node_key
        self.url = ws_base + f"?node_id={node_id}&node_key={node_key}"
        self.ollama_response = ollama_response or self._default_ollama_response()
        self.ollama_error = ollama_error
        self.ignore_jobs = ignore_jobs
        self.reply_delay = reply_delay
        self.simulate_timeout = simulate_timeout
        self.ws = None
        self._recv_task = None
        self._stop = False
        self.received_jobs = []

    def _default_ollama_response(self) -> dict:
        return {
            "id": "chatcmpl-simulated",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": "qwen2.5-coder:7b",
            "choices": [
                {"index": 0,
                 "message": {"role": "assistant", "content": "pong from sim-agent"},
                 "finish_reason": "stop"},
            ],
            "usage": {"prompt_tokens": 4, "completion_tokens": 4, "total_tokens": 8},
        }

    async def __aenter__(self):
        self.ws = await websockets.connect(self.url, open_timeout=5, ping_interval=None)
        welcome_raw = await asyncio.wait_for(self.ws.recv(), timeout=5.0)
        self.welcome = json.loads(welcome_raw)
        self._recv_task = asyncio.create_task(self._drain_loop())
        return self

    async def __aexit__(self, *args):
        self._stop = True
        try:
            if self._recv_task is not None:
                self._recv_task.cancel()
                try:
                    await self._recv_task
                except (asyncio.CancelledError, Exception):
                    pass
            if self.ws is not None:
                await self.ws.close()
        except Exception:
            pass

    async def _drain_loop(self):
        try:
            while not self._stop:
                try:
                    raw = await asyncio.wait_for(self.ws.recv(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                except websockets.ConnectionClosed:
                    return
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue
                mtype = (msg.get("type") or "").lower()
                if mtype == "job":
                    self.received_jobs.append(msg)
                    if self.ignore_jobs or self.simulate_timeout:
                        continue
                    if self.reply_delay > 0:
                        await asyncio.sleep(self.reply_delay)
                    if self.ollama_error:
                        reply = {"type": "job_result", "job_id": msg["job_id"],
                                 "ok": False, "error": self.ollama_error}
                    else:
                        reply = {"type": "job_result", "job_id": msg["job_id"],
                                 "ok": True, "response": self.ollama_response}
                    try:
                        await self.ws.send(json.dumps(reply))
                    except Exception:
                        return
        except asyncio.CancelledError:
            return
        except Exception:
            return


# ----------------------------------------------------------------------------
# Tests 1-4: in-process
# ----------------------------------------------------------------------------
class InProcessEnv:
    """Holds the in-process test server + an httpx.AsyncClient bound to it."""

    def __init__(self):
        self.port = None
        self.app = None
        self.server = None
        self.task = None
        self.data_dir = None
        self.http = None
        self.ws_base = None

    async def __aenter__(self):
        # Start uvicorn in a background task in the same loop. We
        # re-use the loop so server + tests share the same _WS_REGISTRY
        # (this is the whole point of the in-process design).
        self.port, self.app, self.server, self.task, self.data_dir = await _start_test_server()
        self.ws_base = f"ws://127.0.0.1:{self.port}/agent/connect"
        self.http = httpx.AsyncClient(base_url=f"http://127.0.0.1:{self.port}",
                                       timeout=30.0)
        return self

    async def __aexit__(self, *args):
        try:
            if self.http:
                await self.http.aclose()
            if self.server:
                self.server.should_exit = True
            if self.task:
                try:
                    await asyncio.wait_for(self.task, timeout=5.0)
                except (asyncio.TimeoutError, Exception):
                    self.task.cancel()
        except Exception:
            pass
        # Clean up test DB
        try:
            import shutil
            if self.data_dir and os.path.isdir(self.data_dir):
                shutil.rmtree(self.data_dir, ignore_errors=True)
        except Exception:
            pass


async def test_ws_job_roundtrip(env: InProcessEnv):
    print("\nTest 1: WS job roundtrip (user -> server -> WS -> sim-agent -> result)")
    # Register user via in-process HTTP
    email = f"wjs-test1-{int(time.time())}-{secrets.token_hex(4)}@example.com"
    r = await env.http.post("/auth/register", json={
        "email": email, "name": "WJS Test", "password": "x", "role": "both",
        "initial_credits": 50,
    })
    check("register user 200", r.status_code == 200, f"got {r.status_code}: {r.text[:200]}")
    if r.status_code != 200:
        return
    api_key = r.json()["api_key"]

    # Allow the model on the user
    r = await env.http.put("/v1/me/allowed-models",
                           json={"allowed_models": ["qwen2.5-coder:7b"]},
                           headers={"Authorization": f"Bearer {api_key}"})
    check("PUT allowed_models 200", r.status_code == 200, str(r.status_code))

    # Register a node
    r = await env.http.post("/nodes/register", json={
        "name": f"wjs-node-{secrets.token_hex(3)}",
        "gpu_type": "RTX 4090", "vram_gb": 24, "port": 11435,
    }, headers={"Authorization": f"Bearer {api_key}"})
    check("register node 201", r.status_code in (200, 201), f"got {r.status_code}: {r.text[:200]}")
    if r.status_code not in (200, 201):
        return
    node = r.json()
    node_id = node["id"]
    node_key = node["agent_api_key"]

    # Push heartbeat (X-Node-Key header) so _is_online passes
    r = await env.http.post(
        f"/nodes/{node_id}/heartbeat",
        json={"status": "online", "gpu_util": 0.1, "vram_used_gb": 1.0,
              "vram_total_gb": 24.0, "active_jobs": 0},
        headers={"X-Node-Key": node_key, "Content-Type": "application/json"},
    )
    check("heartbeat 204", r.status_code == 204, f"got {r.status_code}: {r.text[:200]}")

    # Connect the simulated agent via WS
    sim = SimulatedAgent(env.ws_base, node_id, node_key,
                         ollama_response={
                             "id": "chatcmpl-test-roundtrip",
                             "object": "chat.completion",
                             "created": int(time.time()),
                             "model": "qwen2.5-coder:7b",
                             "choices": [{"index": 0,
                                          "message": {"role": "assistant",
                                                      "content": "roundtrip ok"},
                                          "finish_reason": "stop"}],
                             "usage": {"prompt_tokens": 3, "completion_tokens": 2,
                                       "total_tokens": 5},
                         })
    await sim.__aenter__()
    try:
        await asyncio.sleep(0.3)
        # Verify connection state via REST
        r = await env.http.get(f"/nodes/{node_id}/connection")
        st = r.json() if r.status_code == 200 else {}
        check("WS state = connected", st.get("state") == "connected",
              f"got {st.get('state')}")

        # We must force the community path. The in-process server's
        # OLLAMA_URL is the default (http://host.docker.internal:11434
        # for docker, or http://localhost:11434 for host). Either way,
        # the local Ollama may or may not be reachable. If it IS, the
        # router uses local and we never hit the WS path. To force the
        # WS path we patch main.OLLAMA_URL to a dead address.
        import main as _main_mod
        from main import OLLAMA_URL as _real_url
        _main_mod.OLLAMA_URL = "http://127.0.0.1:1"  # dead
        try:
            # Issue the chat request
            r = await env.http.post("/v1/chat/completions", json={
                "model": "qwen2.5-coder:7b",
                "messages": [{"role": "user", "content": "say 'roundtrip ok'"}],
                "max_tokens": 8,
            }, headers={"Authorization": f"Bearer {api_key}"})
            check("chat returns 200", r.status_code == 200,
                  f"got {r.status_code}: {r.text[:200]}")
            body = r.json() if r.status_code == 200 else {}
            check("source = community", body.get("source") == "community",
                  f"got {body.get('source')}")
            check("node_id matches", body.get("node_id") == node_id,
                  f"got {body.get('node_id')}")
            choices = (body.get("choices") or [])
            check("response has choices", bool(choices),
                  f"got {body}")
            if choices:
                content = (choices[0].get("message") or {}).get("content", "")
                check("response content = 'roundtrip ok'",
                      content == "roundtrip ok", f"got {content!r}")
            check("sim agent received the job", len(sim.received_jobs) == 1,
                  f"got {len(sim.received_jobs)}")
            if sim.received_jobs:
                payload = sim.received_jobs[0].get("payload") or {}
                check("job payload model matches",
                      payload.get("model") == "qwen2.5-coder:7b",
                      f"got {payload.get('model')}")
        finally:
            _main_mod.OLLAMA_URL = _real_url

        # Verify a PoolJob row was booked
        # We hit the /pool/jobs endpoint (requires auth) and look for
        # a row with source=community + node_id=ours.
        r = await env.http.get("/pool/jobs?limit=20",
                                headers={"Authorization": f"Bearer {api_key}"})
        if r.status_code == 200:
            jobs = r.json()
            mine = [j for j in jobs if j.get("node_id") == node_id
                    and j.get("source") == "community"
                    and j.get("model") == "qwen2.5-coder:7b"]
            check("PoolJob booked (community, this node)",
                  len(mine) >= 1, f"found {len(mine)} matching jobs")
            if mine:
                check("PoolJob status = succeeded",
                      mine[0].get("status") == "succeeded",
                      f"got {mine[0].get('status')}")
        else:
            print(f"  (info) /pool/jobs status {r.status_code} — skipping PoolJob check")
    finally:
        await sim.__aexit__(None, None, None)


async def test_ws_job_timeout(env: InProcessEnv):
    print("\nTest 2: WS job timeout (agent receives job but never replies)")
    # Register user/node
    email = f"wjs-test2-{int(time.time())}-{secrets.token_hex(4)}@example.com"
    r = await env.http.post("/auth/register", json={
        "email": email, "name": "WJS Test 2", "password": "x", "role": "both",
        "initial_credits": 50,
    })
    api_key = r.json()["api_key"]
    await env.http.put("/v1/me/allowed-models",
                       json={"allowed_models": ["qwen2.5-coder:7b"]},
                       headers={"Authorization": f"Bearer {api_key}"})
    r = await env.http.post("/nodes/register", json={
        "name": f"wjs-tmo-node-{secrets.token_hex(3)}",
        "gpu_type": "RTX 4090", "vram_gb": 24, "port": 11435,
    }, headers={"Authorization": f"Bearer {api_key}"})
    node = r.json()
    node_id = node["id"]
    node_key = node["agent_api_key"]
    await env.http.post(
        f"/nodes/{node_id}/heartbeat",
        json={"status": "online", "gpu_util": 0.1, "vram_used_gb": 1.0,
              "vram_total_gb": 24.0, "active_jobs": 0},
        headers={"X-Node-Key": node_key},
    )

    # Connect sim agent that never replies
    sim = SimulatedAgent(env.ws_base, node_id, node_key, simulate_timeout=True)
    await sim.__aenter__()
    try:
        await asyncio.sleep(0.3)

        # Call send_job_via_ws directly with a short timeout. This
        # exercises the dispatcher's timeout branch deterministically.
        from ws import send_job_via_ws, JobTimeoutError, _PENDING_JOBS
        # snapshot pending count
        before = len(_PENDING_JOBS)
        try:
            await send_job_via_ws(node_id, {
                "model": "qwen2.5-coder:7b",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": False,
            }, timeout=1.5)
            check("JobTimeoutError was raised", False, "no exception raised")
        except JobTimeoutError as e:
            check("JobTimeoutError was raised", True, str(e)[:80])
        # Pending map should be cleaned up
        check("_PENDING_JOBS cleaned up after timeout",
              len(_PENDING_JOBS) == before, f"before={before} after={len(_PENDING_JOBS)}")
        check("sim agent received the job (never replied)",
              len(sim.received_jobs) == 1, f"got {len(sim.received_jobs)}")
    finally:
        await sim.__aexit__(None, None, None)


async def test_ws_node_offline_routes_http(env: InProcessEnv):
    print("\nTest 3: node with WS disconnected -> HTTP fallback")
    # We register a node, heartbeat it, but DO NOT connect WS. The router
    # will see connection_state=disconnected and use the HTTP fallback.
    # We mock pool.httpx.AsyncClient so the HTTP fallback hits our mock
    # and we can count calls.
    email = f"wjs-test3-{int(time.time())}-{secrets.token_hex(4)}@example.com"
    r = await env.http.post("/auth/register", json={
        "email": email, "name": "WJS Test 3", "password": "x", "role": "both",
        "initial_credits": 50,
    })
    api_key = r.json()["api_key"]
    await env.http.put("/v1/me/allowed-models",
                       json={"allowed_models": ["qwen2.5-coder:7b"]},
                       headers={"Authorization": f"Bearer {api_key}"})
    r = await env.http.post("/nodes/register", json={
        "name": f"wjs-offline-node-{secrets.token_hex(3)}",
        "gpu_type": "RTX 4090", "vram_gb": 24, "port": 11435,
        "node_url": "http://127.0.0.1:11435",  # so _forward_to_node can build a URL
    }, headers={"Authorization": f"Bearer {api_key}"})
    node = r.json()
    node_id = node["id"]
    node_key = node["agent_api_key"]
    await env.http.post(
        f"/nodes/{node_id}/heartbeat",
        json={"status": "online", "gpu_util": 0.1, "vram_used_gb": 1.0,
              "vram_total_gb": 24.0, "active_jobs": 0},
        headers={"X-Node-Key": node_key},
    )
    # Disable any other nodes so find_best_node picks THIS one
    # (the in-process test server shares one DB across tests 1-3, so
    # Test 1's node is still online + enabled when Test 3 runs).
    from database import SessionLocal
    from models import GpuNode
    _db = SessionLocal()
    try:
        others = _db.query(GpuNode).filter(GpuNode.id != node_id).all()
        for n in others:
            n.is_enabled = False
        _db.commit()
    finally:
        _db.close()

    # No WS connection -> HTTP fallback
    from ws import get_ws_connection
    check("WS connection is absent (no agent connected)",
          get_ws_connection(node_id) is None)

    # Mock pool.httpx.AsyncClient.post: only count (and respond) for
    # the community /v1/chat/completions URL. The local-Ollama call
    # uses /api/chat and must be allowed to fail naturally so the router
    # falls back to community. We patch the AsyncClient class itself
    # and route non-target URLs to the real httpx (snapshotted BEFORE
    # the patch, to avoid infinite recursion).
    import pool as pool_mod
    import httpx as _hx
    # Snapshot the real AsyncClient BEFORE patching
    _RealAsyncClient = _hx.AsyncClient

    http_calls = []

    class _MockResponse:
        status_code = 200
        def __init__(self, payload):
            self._payload = payload
        def json(self):
            return self._payload
        def raise_for_status(self):
            if self.status_code >= 400:
                raise _hx.HTTPStatusError(
                    "mock fail", request=_hx.Request("POST", "http://mock"),
                    response=self,
                )

    class _DelegatingClient:
        """AsyncClient wrapper that mocks /v1/chat/completions but
        delegates /api/chat to the real httpx (so the local-Ollama
        call still fails with ConnectError -> community fallback)."""
        def __init__(self, *args, **kwargs):
            self._real = _RealAsyncClient(*args, **kwargs)
            self.timeout = kwargs.get("timeout", 120.0)
        async def __aenter__(self):
            self._real = await self._real.__aenter__()
            return self
        async def __aexit__(self, *args):
            return await self._real.__aexit__(*args)
        async def post(self, url, json=None, **kwargs):
            if "/v1/chat/completions" in url:
                http_calls.append(url)
                return _MockResponse({
                    "id": "chatcmpl-mock",
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": (json or {}).get("model", "x"),
                    "choices": [{"index": 0,
                                 "message": {"role": "assistant",
                                             "content": "from http fallback"},
                                 "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1,
                              "total_tokens": 2},
                })
            return await self._real.post(url, json=json, **kwargs)

    # Patch + force community path
    original_client = pool_mod.httpx.AsyncClient
    pool_mod.httpx.AsyncClient = _DelegatingClient
    import main as _main_mod
    from main import OLLAMA_URL as _real_url
    _main_mod.OLLAMA_URL = "http://127.0.0.1:1"  # dead — forces community path
    try:
        r = await env.http.post("/v1/chat/completions", json={
            "model": "qwen2.5-coder:7b",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 4,
        }, headers={"Authorization": f"Bearer {api_key}"})
        check("chat returns 200", r.status_code == 200,
              f"got {r.status_code}: {r.text[:200]}")
        body = r.json() if r.status_code == 200 else {}
        check("source = community", body.get("source") == "community",
              f"got {body.get('source')}")
        check("node_id matches", body.get("node_id") == node_id)
        content = ((body.get("choices") or [{}])[0].get("message") or {}).get("content", "")
        check("response content from http fallback",
              content == "from http fallback", f"got {content!r}")
        check("HTTP fallback was called (>= 1 httpx.post)",
              len(http_calls) >= 1, f"calls={http_calls}")
        check("HTTP fallback URL targets /v1/chat/completions",
              any("/v1/chat/completions" in u for u in http_calls),
              f"calls={http_calls}")
    finally:
        pool_mod.httpx.AsyncClient = original_client
        _main_mod.OLLAMA_URL = _real_url


async def test_ws_job_error_propagation(env: InProcessEnv):
    print("\nTest 4: agent returns ok:false -> WSError raised; router falls back")
    email = f"wjs-test4-{int(time.time())}-{secrets.token_hex(4)}@example.com"
    r = await env.http.post("/auth/register", json={
        "email": email, "name": "WJS Test 4", "password": "x", "role": "both",
        "initial_credits": 50,
    })
    api_key = r.json()["api_key"]
    await env.http.put("/v1/me/allowed-models",
                       json={"allowed_models": ["qwen2.5-coder:7b"]},
                       headers={"Authorization": f"Bearer {api_key}"})
    r = await env.http.post("/nodes/register", json={
        "name": f"wjs-err-node-{secrets.token_hex(3)}",
        "gpu_type": "RTX 4090", "vram_gb": 24, "port": 11435,
    }, headers={"Authorization": f"Bearer {api_key}"})
    node = r.json()
    node_id = node["id"]
    node_key = node["agent_api_key"]
    await env.http.post(
        f"/nodes/{node_id}/heartbeat",
        json={"status": "online", "gpu_util": 0.1, "vram_used_gb": 1.0,
              "vram_total_gb": 24.0, "active_jobs": 0},
        headers={"X-Node-Key": node_key},
    )

    # Connect a sim agent that replies with ok:false
    sim = SimulatedAgent(env.ws_base, node_id, node_key,
                         ollama_error="simulated ollama down (test)")
    await sim.__aenter__()
    try:
        await asyncio.sleep(0.3)

        # 1) Direct send_job_via_ws: must raise WSError
        from ws import send_job_via_ws, WSError
        try:
            await send_job_via_ws(node_id, {
                "model": "qwen2.5-coder:7b",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": False,
            }, timeout=5.0)
            check("send_job_via_ws raised WSError", False, "no exception")
        except WSError as e:
            check("send_job_via_ws raised WSError", True, str(e)[:80])
            check("WSError contains the agent's error message",
                  "simulated ollama down" in str(e), str(e)[:120])

        # 2) route_request via REST: must NOT crash. WS fails -> HTTP
        #    fallback -> with no inbound agent, HTTP fails too -> router
        #    returns source=cloud, ok=False -> user gets 503.
        # Force the community path by pointing OLLAMA_URL at a dead port.
        import main as _main_mod
        from main import OLLAMA_URL as _real_url
        _main_mod.OLLAMA_URL = "http://127.0.0.1:1"
        try:
            r = await env.http.post("/v1/chat/completions", json={
                "model": "qwen2.5-coder:7b",
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 4,
            }, headers={"Authorization": f"Bearer {api_key}"})
            check("chat did not 500 (clean error code)",
                  r.status_code in (200, 502, 503),
                  f"got {r.status_code}: {r.text[:200]}")
            if r.status_code == 200:
                body = r.json()
                check("source not 'community' on agent error",
                      body.get("source") != "community",
                      f"got {body.get('source')}")
        finally:
            _main_mod.OLLAMA_URL = _real_url
    finally:
        await sim.__aexit__(None, None, None)


async def test_v1_still_green():
    print("\nTest 5: v1 + Phase-1 WS regression against LIVE docker")
    import subprocess
    for test_path in ("tests/test_features.py", "tests/test_ws_connectivity.py"):
        env = dict(os.environ)
        env["GPU_POOL_API"] = API_HTTP
        proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        proc = subprocess.run(
            [sys.executable, test_path],
            env=env, capture_output=True, text=True, timeout=180,
            cwd=proj_root,
        )
        ok = proc.returncode == 0
        check(f"{test_path} exit=0", ok, f"returncode={proc.returncode}")
        if not ok:
            print("    --- stdout (tail) ---")
            print(proc.stdout[-1500:])
            print("    --- stderr (tail) ---")
            print(proc.stderr[-1500:])


# ----------------------------------------------------------------------------
# Entrypoint
# ----------------------------------------------------------------------------
async def main():
    print(f"GPU-Pool WS job-stream tests (in-process + live regression)")
    print(f"  live API: {API_HTTP}")
    print("=" * 60)
    try:
        # Tests 1-4 in-process
        async with InProcessEnv() as env:
            await test_ws_job_roundtrip(env)
            await test_ws_job_timeout(env)
            await test_ws_node_offline_routes_http(env)
            await test_ws_job_error_propagation(env)
        # Test 5: live regression
        await test_v1_still_green()
    except Exception as e:
        import traceback
        traceback.print_exc()
        results.append(False)

    print()
    failed = sum(1 for r in results if not r)
    total = len(results)
    if failed == 0:
        print(f"\033[32mAll {total} checks passed\033[0m")
        return 0
    print(f"\033[31m{failed} of {total} checks FAILED\033[0m")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
