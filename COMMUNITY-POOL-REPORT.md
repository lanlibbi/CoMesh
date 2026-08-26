# Community GPU-Pool — POC Extension (v0.3.0)

This extends the GPU-Pool POC on `portal-host` with **community GPU-sharing**.
GPU-owners can register their machines, the portal load-balances
OpenAI-compatible chat requests across the pool, and earnings are split
70/20/10 (owner / platform / treasury).

## What was added

### Backend (`/home/christian/projects/opencode-poc/`)

| File | Purpose |
|------|---------|
| `models.py` *(extended)* | New tables: `gpu_nodes`, `node_heartbeats`, `node_earnings`, `pool_jobs` |
| `nodes.py` *(new)* | `/nodes/{register,list,my,id,id/heartbeat,id/enable,delete,stats/summary}` |
| `pool.py` *(new)* | `find_best_node`, `route_request`, `distribute_revenue`; `/pool/{route-preview,jobs,earnings/mine}` |
| `main.py` *(extended)* | Load-balances `/v1/chat/completions` through `pool.route_request`; charges credits; records `PoolJob` + `NodeEarning`; `/health` now reports the community summary |

### Frontend — FastAPI router (`/home/christian/projects/opencode-poc/frontend/`)

| Page | Path | What it does |
|------|------|--------------|
| `nodes.html` | `/nodes` | Register a new GPU + list "my nodes" with toggle/delete |
| `pool.html`  | `/pool`  | Live community pool overview (auto-refresh 10s) |
| `earnings.html` | `/earnings` | Owner's earnings: total + per-node + per-event table |
| `agent.html` | `/agent`  | Setup guide + ready-to-paste `docker run` command |

The `frontend.py` router was updated to serve the four new pages and their JS bundles.

### Frontend — Alpine SPA (`/home/christian/projects/opencode-poc/frontend-alpine/`)

The Alpine frontend (port 3000) also got the same four pages, re-skinned in
Tailwind/Alpine style. The nginx proxy now forwards `/api/nodes/*` and
`/api/pool/*` to the backend.

### Node-Agent (`/home/christian/projects/opencode-poc/node-agent/`)

A small FastAPI service that runs on each contributor's machine.

| File | Purpose |
|------|---------|
| `agent.py` | Heartbeat loop + `/v1/chat/completions` proxy to local Ollama |
| `Dockerfile` | `python:3.11-slim` + `psutil` + `pynvml`; runs as `uvicorn agent:app` on `AGENT_PORT` |
| `requirements.txt` | Pinned deps |
| `README.md` | Setup instructions (Tailscale, `docker run`, health check) |

### Docker compose

`docker-compose.yml` got a commented-out `node-agent` service block that
shows the recommended deployment for local testing. In production, the
agent runs on each contributor's machine — it's not on the portal host.

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  Portal (portal-host:8765)                                       │
│  ┌─────────────────────┐                                         │
│  │ /v1/chat/completions│                                         │
│  └──────────┬──────────┘                                         │
│             │                                                     │
│     pool.route_request()                                         │
│      1. try local Ollama (host.docker.internal:11434)           │
│      2. find_best_node() + forward via /v1/chat/completions      │
│      3. cloud overflow (stub → 503)                              │
│             │                                                     │
│   ┌─────────┴─────────────┐                                       │
│   │ /pool/earnings/mine   │ ← 70% to owner, 20% platform, 10%    │
│   │ /pool/jobs            │   treasury (NodeEarning rows)        │
│   │ /nodes/{register,my,  │                                       │
│   │  list,stats/summary,  │                                       │
│   │  heartbeat,delete}    │                                       │
│   └───────────────────────┘                                       │
└──────────────────────────────────────────────────────────────────┘
            │
            │  Tailscale (or docker network for testing)
            ▼
┌──────────────────────────────────────────────────────────────────┐
│  Node-Agent (contributor's machine:11435)                        │
│  ┌─────────────────────────┐  ┌──────────────────────────┐       │
│  │ POST /v1/chat/completions├─►│ local Ollama :11434       │      │
│  │ (OpenAI-compatible)     │  │ (existing daemon)         │      │
│  └─────────────────────────┘  └──────────────────────────┘       │
│  ┌─────────────────────────┐                                     │
│  │ POST /nodes/{id}/heartbeat (every 30s)  ──► Portal            │
│  └─────────────────────────┘                                     │
└──────────────────────────────────────────────────────────────────┘
```

## Endpoint summary

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `POST` | `/v1/chat/completions` | user API key | OpenAI-compatible; routes through pool |
| `POST` | `/nodes/register` | user API key | Register a new GPU; returns `agent_api_key` once |
| `GET`  | `/nodes/list` | (public) | Online community nodes |
| `GET`  | `/nodes/my` | user API key | Caller's nodes |
| `GET`  | `/nodes/{id}` | (public) | Single node detail |
| `POST` | `/nodes/{id}/heartbeat` | `X-Node-Key` header | Agent pushes status update |
| `POST` | `/nodes/{id}/enable?enabled=true\|false` | user API key | Pause/resume |
| `DELETE` | `/nodes/{id}` | user API key | Remove a node |
| `GET`  | `/nodes/stats/summary` | (public) | Community totals: nodes, VRAM, util, rate range |
| `GET`  | `/pool/jobs` | user API key | Recent community jobs (admin/observability) |
| `GET`  | `/pool/earnings/mine` | user API key | Owner's earnings: total + by-node + per-event |
| `POST` | `/pool/route-preview` | user API key | "Where would this request land right now?" |

## Verified end-to-end (test run on 2026-06-05)

| Test | Result |
|------|--------|
| Login as `test@example.com` | ✅ got API key |
| `POST /nodes/register` (×2) | ✅ got `agent_api_key` for each |
| `POST /nodes/{id}/heartbeat` with `X-Node-Key` | ✅ 204 No Content |
| `GET /nodes/list` shows online nodes | ✅ |
| `GET /nodes/stats/summary` | ✅ `online_nodes=2, total_vram_gb=48` |
| `POST /v1/chat/completions` (local Ollama up) | ✅ `source: "local"` |
| Force-fail local (bad `OLLAMA_URL`) + `POST /v1/chat/completions` | ✅ routes to community node #2 |
| Full E2E: portal → node-agent (`/v1/chat/completions`) → fake ollama (`/api/chat`) | ✅ `source: "community", node_id: 2`, content proves all 3 hops |
| `GET /pool/earnings/mine` after E2E run | ✅ `owner_share=8e-6, platform_share=2e-6, treasury_share=1e-6` (70/20/10 split) |
| `GET /pool/jobs` | ✅ both local and community jobs logged with `latency_ms` |
| Node-agent: starts, sends first heartbeat, periodic heartbeats, `/health` and `/v1/chat/completions` work | ✅ |
| All 4 new pages (`:8765` and `:3000`) + their JS bundles | ✅ HTTP 200 |

## Security notes

- **API keys are stored hashed** (SHA-256); the user API key is shown once at
  creation, the `agent_api_key` is shown once at node registration. There
  is **no key-recovery endpoint** — losing either means re-issue.
- **Tailscale**: the README explicitly tells contributors NOT to expose
  the agent's port on the public internet. The portal uses the
  `tailscale_ip` registered on the node to forward; if the IP is wrong,
  the request fails cleanly and the next-best node is tried.
- **Heartbeat auth**: the agent uses a separate `X-Node-Key` header, NOT
  the user's account API key. This way the user's account key is never
  exposed to the agent process.
- **Connection-failure vs HTTP-failure**: the load-balancer only falls
  back to community on a real connection failure (timeout / connection
  refused). HTTP 4xx/5xx from local Ollama (e.g. model not found) is
  surfaced to the user as a 502 — we don't silently re-route a
  malformed request.

## Future work (out of scope for this PR)

- Real RunPod/Vast overflow (the cloud branch in `pool.route_request` is
  currently a stub returning 503).
- Prometheus exporter: `NodeHeartbeat` rows are kept for analysis but no
  `/metrics` endpoint is exposed yet.
- Async background task to update `GpuNode.total_hours` (currently 0; we'd
  compute it from the heartbeat history).
- Top-up earnings to user balances (currently the 70% is tracked on
  `NodeEarning` rows and the `GpuNode.earnings_total` field, but we
  don't move credits into the user's spendable balance).

## Phase 1 — WebSocket Connectivity (2026-06-10)

This phase adds the **outbound** WebSocket transport that node-agents use
to connect to the portal. The HTTP heartbeat path stays as a fallback;
the load-balancer and the in-pool chat routing are unchanged.

### Why

The HTTP heartbeat + reverse-connection model from v0.3.0 forces every
provider to expose a Tailscale-reachable port. Real contributors
generally can't or won't open inbound ports. The outbound WSS flips
that: the agent dials out, the portal never needs to reach into the
contributor's network. Phase 1 implements the transport + state
tracking only; the actual job stream lands in Phase 2.

### What was built

| File | Change |
|------|--------|
| `models.py` *(extended)* | New `GpuNode` columns: `connection_state` (TEXT, default `'disconnected'`), `last_ws_seen` (REAL, Unix-ts), `ws_session_id` (TEXT, UUID) |
| `ws.py` *(new)* | WebSocket endpoint `GET /agent/connect` (auth via query params `?node_id=…&node_key=…`), in-memory `_WS_REGISTRY` (placeholder for the future job stream), and REST `GET /nodes/{id}/connection` for status |
| `main.py` *(extended)* | Mounts the new `ws` router, adds idempotent migration `_ensure_node_ws_columns()` to the lifespan |
| `requirements.txt` | Adds `websockets==13.1` (FastAPI 0.115 already ships WebSocket support) |
| `node-agent/agent.py` *(extended)* | Adds `AGENT_TRANSPORT=ws` mode: outbound WS client with exponential reconnect (1s → 30s cap), 15s ping with `vram_used_gb` + `active_jobs` + `uptime`. HTTP mode unchanged. `--transport=ws` CLI override also supported. |
| `node-agent/requirements.txt` | Adds `websockets==13.1` |
| `tests/test_ws_connectivity.py` *(new)* | 5 tests / 23 checks, see below |

### Auth model

The agent passes `node_id` and `node_key` (the `agent_api_key` from
`POST /nodes/register`) as **query params** on the WS URL. The portal's
`/agent/connect` handler:

  - Returns close code **4400** if either param is missing.
  - Returns close code **4401** if the `node_id` doesn't exist, the key
    doesn't match, or the node has been paused (`is_enabled=False`).
  - On success, generates a UUID `ws_session_id`, writes
    `connection_state='connected'` and `last_ws_seen=now()` to the DB,
    and stores the WebSocket in the process-local `_WS_REGISTRY`.

This is intentionally a "scoped by node" auth model — the WS key is
the per-node `agent_api_key`, never the user's account key. Query
params (vs headers) make the URL self-describing for the `websockets`
client and for browser dev-tools debugging.

### Lifecycle / state machine

```
   [disconnected] ---WS open + auth OK---> [connecting] --immediate--> [connected]
                          |
                          +-- WS close / error / process crash ----> [disconnected]
```

- On connect: `connection_state='connected'`, `ws_session_id=<uuid>`,
  `last_ws_seen=now()`.
- On every `{type:"ping"}` JSON frame: `last_ws_seen=now()`,
  optionally `vram_used_gb` and `active_jobs` are pulled into the row
  for free (cheap to keep current), reply with `{type:"pong"}`.
- On any close (clean, abrupt, or error): `connection_state='disconnected'`,
  `ws_session_id=NULL`, `last_ws_seen=now()`. Cleanup is in a `finally:`
  block and runs even on uncaught exceptions.

### REST status endpoint

```
GET /nodes/{id}/connection
-> {node_id, state, last_ws_seen, ws_session_id, is_enabled}
```

Auth: not required for the POC. Returns 404 if the node doesn't exist.
This is what the test suite and the future admin/UI will poll.

### Test results

```
GPU-Pool WS connectivity tests against http://localhost:8765
============================================================
Test: WS connect with wrong key -> 4401
  PASS close code is 4401
Test: WS connect success (node_id=…)
  PASS welcome.type == welcome
  PASS welcome.node_id == our node
  PASS welcome.session_id present
  PASS REST /connection returns state=connected
  PASS REST /connection has session_id
  PASS REST /connection has last_ws_seen
  PASS after close: state=disconnected
  PASS after close: ws_session_id cleared
Test: WS disconnect cleanup (node_id=…)
  PASS during connection: state=connected
  PASS after close: state=disconnected
  PASS after close: ws_session_id null
Test: WS heartbeat updates timestamp (node_id=…)
  PASS welcome has server_time
  PASS last_ws_seen is set after connect
  PASS server replied with pong
  PASS last_ws_seen advanced after second ping
Test: v1 HTTP regression
  PASS register returns 200
  PASS GET /v1/me -> 200
  PASS me.email matches
  PASS GET /v1/available-models -> 200
  PASS response has 'models' array
  PASS cloud model blocked (403)
  PASS POST /nodes/register -> 201

============================================================
All 23 checks passed against http://localhost:8765
```

Plus the existing v1 feature suite (`tests/test_features.py`) still
passes 24/24. Real-agent end-to-end check (start `python3 agent.py
--transport=ws` against a registered node) was also verified manually
on `portal-host`: the agent connected, received the welcome, pinged,
and on timeout the portal flipped the node to `disconnected` cleanly.

### Design decision: WS test uses Python `websockets` client, not the agent binary

The test suite drives the same protocol a real WS-mode agent would
(connect / welcome / ping / pong / close), but does **not** spawn the
agent process. Reason: the agent's GPU code path is well covered by
v1's HTTP-heartbeat tests; Phase 1 is about the transport and the
server-side state machine, not the GPU. A `websockets` test client
also avoids GPU/Ollama conflicts when run on the same host as the
backend. Phase 2 will revisit this when the job stream needs real
agent↔portal roundtrips.

### Open points for Phase 2 (job stream)

- Replace the placeholder `_WS_REGISTRY` use with a real job-dispatch
  protocol (`{type:"job", job_id, payload}` from server → agent;
  `{type:"job_result", job_id, response}` back).
- Move the in-pool chat-completion proxy (`POST /v1/chat/completions`
  on the agent) onto the WS as a request/response frame, so the HTTP
  agent can finally stop listening on port 11435.
- Switch the pool router to consider `connection_state='connected'`
  (or `last_ws_seen` recency) when picking nodes.
- Consider a multi-worker-safe registry (Redis pub/sub) if/when we
  scale uvicorn beyond a single worker.

### Open points for Phase 3+

- Per-job isolation / sandbox on the agent side (the agent currently
  proxies whatever the portal asks for; in production we want a model
  whitelist + per-job resource caps).
- mTLS or scoped JWT instead of raw `node_key` in the URL query.
- Live admin UI: "currently connected" list, with RTT / uptime / VRAM.
- Prometheus exporter for connection duration + heartbeat gaps.

---

## Phase 2 — WS Job Stream (2026-06-10)

Phase 2 made the pool actually **use** the WS the agent already opens
in Phase 1. The portal now dispatches chat-completion jobs over the
existing WebSocket, and the agent answers with a `job_result` frame
on the same connection. In the steady state this drops the
provider's inbound-port count from **2 (11435 agent + 11434 Ollama)**
to **0 (Ollama is local; the agent only opens OUTBOUND)**.

### What was built

- **WS protocol extension (`ws.py`)** — `send_job_via_ws(node_id,
  payload, timeout)` async dispatcher. Backed by a `{job_id:
  asyncio.Future}` map (`_PENDING_JOBS`). Receive loop resolves the
  future when a matching `job_result` frame arrives; on disconnect we
  fail all in-flight futures with `NodeOfflineError` so callers don't
  hang. Full protocol shape (job + job_result + ping/pong + welcome)
  documented in the ws.py module docstring.

- **Pool router switch (`pool.py`)** — `route_request`'s community
  branch now checks `node.connection_state` per node. Connected →
  `_forward_to_node_ws` (no HTTP at all). Disconnected → original
  HTTP `_forward_to_node` (bit-identical to v1, kept as Phase-3
  cleanup target). On WS errors (NodeOfflineError / JobTimeoutError
  / WSError) we try the HTTP fallback for the SAME node before
  continuing to the next-best node. Whitelist ordering is preserved
  — `find_best_node`'s score sort is unchanged; connection_state is
  just a filter, not a sorter.

- **Agent WS handler (`node-agent/agent.py`)** — `_handle_job_frame`
  background task. Forces `payload.stream=false` (Phase 2 is
  non-streaming only — documented in code), calls the extracted
  `_ollama_chat_non_streaming` helper, replies with `job_result` on
  success or `ok:false, error:...` on Ollama failure. HTTP mode is
  still bit-identical and used as the fallback path.

- **Single-Worker-Policy** — `_WS_REGISTRY` and `_PENDING_JOBS` are
  process-local dicts. `docker-compose.yml` now pins
  `--workers 1` explicitly with a comment explaining why. Phase 3+
  will swap in Redis pub/sub; until then, **do not bump the worker
  count** — the dispatcher would silently fail and HTTP fallback
  would take over without warning.

- **Tests (`tests/test_ws_job_stream.py`, NEW, 5 cases / 29
  checks)** — In-process approach: uvicorn runs the real `main:app`
  in a background task in the same event loop as the test, so the
  simulated agent and the server share `_WS_REGISTRY` and
  `_PENDING_JOBS` — that's the actual state we want to exercise. The
  `SimulatedAgent` (a `websockets` client) connects to the local WS
  endpoint and replies to `job` frames with a configurable
  `job_result`. v1 + Phase-1 regression runs as a subprocess against
  the live Docker container at `http://localhost:8765`.

### Test results (final run)

```
=== v1 regression ===
All tests passed against http://localhost:8765          (24/24)

=== phase 1 ws ===
All 23 checks passed against http://localhost:8765      (23/23)

=== phase 2 ws job stream ===
Test 1: WS job roundtrip ...                           (14 PASS)
Test 2: WS job timeout ...                             ( 3 PASS)
Test 3: HTTP fallback (WS disconnected) ...            ( 7 PASS)
Test 4: agent ok:false -> WSError propagation ...      ( 3 PASS)
Test 5: v1 + Phase-1 regression against LIVE ...       ( 2 PASS)
All 29 checks passed
```

### Phase 3+ — backlog

- **Streaming** — Add `job_result_chunk` ND-JSON frames so
  `payload.stream=true` is honoured. Frontend gets SSE-style chunks.
- **Auth hardening** — Replace `node_key` URL-query with scoped JWT
  (short TTL, signed with `node.api_key`). mTLS as a later option.
- **Multi-worker / Redis pub/sub** — Move `_WS_REGISTRY` and
  `_PENDING_JOBS` to a shared broker so we can scale uvicorn
  horizontally. Single-Worker-Policy can then be relaxed.
- **Drop HTTP fallback** — Once the WS rollout is complete, remove
  `_forward_to_node` (HTTP) entirely and the agent's HTTP server.
  Agents run WS-only.
- **Live admin UI** — "Currently Connected" list with RTT / VRAM /
  uptime, served via WS broadcast of `_WS_REGISTRY` updates.
- **Per-job sandboxing on the agent** — Model whitelist enforcement
  + resource caps (CPU/RAM/VRAM) per job.
- **Prometheus exporter** — Connection duration, heartbeat gaps, job
  latency, `_PENDING_JOBS.size`, per-node throughput.
