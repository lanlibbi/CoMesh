"""
GPU-Pool — WebSocket Transport Layer (Phase 1 + Phase 2).

Scope:
  Phase 1:
    - agent -> pool (outbound WSS) for connectivity tracking.
    - Accepts WS handshake at `/agent/connect`, authenticates the
      node via query params `?node_id=<id>&node_key=<api_key>`.
    - Tracks the connection in a process-local dict (`_WS_REGISTRY`)
      keyed by node_id.
    - Updates `gpu_nodes.connection_state`, `last_ws_seen`, `ws_session_id`.

  Phase 2 (this file's additional responsibilities):
    - Pool -> agent: dispatches a chat-completion *job* over the same
      WS connection and waits for a `job_result` reply.
    - Uses a `{job_id: asyncio.Future}` map for correlation.
    - The future is resolved by the receive loop when a `job_result`
      message arrives (or fails with `WSError` / `JobTimeoutError` on
      disconnect / timeout).

WS protocol (JSON over text frames):

  Server -> Agent (job request):
    {
      "type": "job",
      "job_id": "<uuid4>",
      "payload": { ... OpenAI /v1/chat/completions body ... }
    }

  Agent -> Server (job result):
    {
      "type": "job_result",
      "job_id": "<uuid4>",
      "ok": true,
      "response": { ... OpenAI /v1/chat/completions response ... }
    }
    Or on error:
    {
      "type": "job_result",
      "job_id": "<uuid4>",
      "ok": false,
      "error": "string"
    }

  Server -> Agent (ping):
    { "type": "ping" }                       # not used by server today
  Agent -> Server (ping, with telemetry):
    { "type": "ping", "vram_used_gb": ..., "vram_total_gb": ...,
      "active_jobs": ..., "uptime": ... }
  Agent -> Server (pong reply from server):
    { "type": "pong", "ts": <float> }

  Server -> Agent (welcome, on connect):
    { "type": "welcome", "node_id": <int>, "session_id": "<uuid>",
      "server_time": <float> }

Streaming: Phase 2 only supports NON-STREAMING jobs. The agent
ignores `payload.stream=true` and returns the full response in
`job_result.response`. Streaming via `job_result_chunk` frames is
deferred to Phase 3.

Custom close codes:
  4401  -> authentication failed (invalid node_id or api_key)
  4400  -> malformed handshake (missing params)
  1011  -> server error (uncaught exception; FastAPI default)

Single-Worker-Policy:
  `_WS_REGISTRY` and the pending-job futures map are process-local.
  The server MUST run with `--workers 1`. Multi-worker deployments
  need a shared broker (Redis pub/sub) — out of scope for Phase 1+2.
  The `docker-compose.yml` already pins workers=1.
"""
import asyncio
import json
import logging
import time
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import SessionLocal, get_db
from models import GpuNode

log = logging.getLogger("gpu-pool.ws")

router = APIRouter(tags=["ws"])


# ----------------------------------------------------------------------------
# Exceptions
# ----------------------------------------------------------------------------
class WSError(Exception):
    """Base class for WS-dispatcher errors."""


class JobTimeoutError(WSError):
    """Raised when a job_result is not received within the configured timeout."""


class NodeOfflineError(WSError):
    """Raised when no active WS connection exists for the requested node."""


# ----------------------------------------------------------------------------
# In-memory registry: {node_id (int): WebSocket}
# Process-local only. Multi-worker deployments (uvicorn --workers N) would
# need a shared broker (Redis pub/sub). Out of scope for Phase 1+2.
# Single-Worker-Policy: the server runs with --workers 1, so this map is
# authoritative for the whole process. See docker-compose.yml.
# ----------------------------------------------------------------------------
_WS_REGISTRY: Dict[int, WebSocket] = {}

# job_id -> asyncio.Future that resolves with the agent's job_result payload.
# Cleared by the receive loop on completion, on disconnect, or on timeout.
_PENDING_JOBS: Dict[str, "asyncio.Future[dict]"] = {}


def get_ws_connection(node_id: int) -> Optional[WebSocket]:
    """Return the active WebSocket for a node, or None if disconnected."""
    return _WS_REGISTRY.get(node_id)


def active_ws_node_ids() -> list:
    """Snapshot of node ids currently connected via WS (for tests/admin)."""
    return list(_WS_REGISTRY.keys())


def pending_job_count() -> int:
    """Number of in-flight job requests awaiting a result (for tests/admin)."""
    return len(_PENDING_JOBS)


def _fail_pending_for_node(node_id: int, reason: str) -> int:
    """Fail all pending jobs for a node (called on disconnect cleanup)."""
    failed = 0
    # Snapshot keys; we'll mutate _PENDING_JOBS while iterating.
    for jid in list(_PENDING_JOBS.keys()):
        fut = _PENDING_JOBS.get(jid)
        if fut is None or fut.done():
            continue
        fut.set_exception(NodeOfflineError(f"node {node_id} disconnected: {reason}"))
        _PENDING_JOBS.pop(jid, None)
        failed += 1
    return failed


# ----------------------------------------------------------------------------
# Job dispatcher (Phase 2)
# ----------------------------------------------------------------------------
async def send_job_via_ws(
    node_id: int,
    payload: dict,
    *,
    timeout: float = 120.0,
) -> dict:
    """Send a chat-completion job over the node's WS and await the result.

    Args:
        node_id: The numeric GpuNode.id of the target agent.
        payload: OpenAI-shaped /v1/chat/completions body. The agent
                 forwards it to its local Ollama and returns the response.
        timeout: Seconds to wait for a `job_result` reply before failing.

    Returns:
        The agent's `job_result` payload dict, e.g.
        {"type": "job_result", "job_id": "...", "ok": true,
         "response": {... OpenAI response ...}}

    Raises:
        NodeOfflineError: No active WS connection for the node.
        JobTimeoutError:  Agent did not answer within `timeout`.
        WSError:          Agent returned `ok: false` (error in result.error).
    """
    ws = _WS_REGISTRY.get(node_id)
    if ws is None:
        raise NodeOfflineError(f"node {node_id} has no active WS connection")

    job_id = str(uuid.uuid4())
    loop = asyncio.get_running_loop()
    fut: "asyncio.Future[dict]" = loop.create_future()
    _PENDING_JOBS[job_id] = fut

    frame = json.dumps({"type": "job", "job_id": job_id, "payload": payload})
    try:
        await ws.send_text(frame)
    except Exception as e:
        # Send failed -> fail the future + cleanup.
        _PENDING_JOBS.pop(job_id, None)
        if not fut.done():
            fut.set_exception(WSError(f"send_job_via_ws send failed: {e!r}"))
        raise

    try:
        result = await asyncio.wait_for(fut, timeout=timeout)
    except asyncio.TimeoutError:
        _PENDING_JOBS.pop(job_id, None)
        log.warning(f"WS job timeout: node_id={node_id} job_id={job_id} after {timeout}s")
        raise JobTimeoutError(f"job {job_id} on node {node_id} timed out after {timeout}s")
    finally:
        # Future was already popped by the receive loop on success; this is
        # belt-and-suspenders for the timeout path.
        _PENDING_JOBS.pop(job_id, None)

    # Surface agent-reported errors as WSError (caller decides how to handle).
    if not result.get("ok", False):
        err = result.get("error") or "agent returned ok=false"
        raise WSError(f"agent error: {err}")

    return result


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def _authenticate_node(db: Session, node_id: int, node_key: str) -> Optional[GpuNode]:
    """Look up the node and check its raw api_key. Returns the node on success, None on failure."""
    if not node_id or not node_key:
        return None
    try:
        nid = int(node_id)
    except (TypeError, ValueError):
        return None
    node = db.query(GpuNode).filter(GpuNode.id == nid).first()
    if not node:
        return None
    if not node.api_key or node.api_key != node_key:
        return None
    if not node.is_enabled:
        # Owner paused this node — refuse WS just like we'd refuse HTTP.
        return None
    return node


def _set_state(db: Session, node: GpuNode, state: str, session_id: Optional[str], ts: Optional[float]) -> None:
    """Persist connection state + session id + last-seen timestamp atomically.

    session_id semantics:
      - non-None string  -> write that session id (used for new connections)
      - None             -> CLEAR the session id (used for disconnect cleanup)
    We must distinguish "leave alone" from "clear". For Phase 1+2 the only
    callers either set a fresh id on connect or explicitly clear on
    disconnect, so we always overwrite the column. If we ever need a
    "leave alone" path we'll add a sentinel.
    """
    node.connection_state = state
    node.ws_session_id = session_id  # None clears, str sets
    if ts is not None:
        node.last_ws_seen = ts
    db.add(node)
    db.commit()


# ----------------------------------------------------------------------------
# Schemas
# ----------------------------------------------------------------------------
class ConnectionStateOut(BaseModel):
    node_id: int
    state: str
    last_ws_seen: Optional[float] = None
    ws_session_id: Optional[str] = None
    is_enabled: bool


# ----------------------------------------------------------------------------
# REST status endpoint (for tests + admin)
# ----------------------------------------------------------------------------
@router.get("/nodes/{node_id}/connection", response_model=ConnectionStateOut)
def get_node_connection(node_id: int, db: Session = Depends(get_db)):
    """Return the WebSocket connection state for a single node."""
    node = db.query(GpuNode).filter(GpuNode.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return ConnectionStateOut(
        node_id=node.id,
        state=getattr(node, "connection_state", "disconnected") or "disconnected",
        last_ws_seen=getattr(node, "last_ws_seen", None),
        ws_session_id=getattr(node, "ws_session_id", None),
        is_enabled=bool(node.is_enabled),
    )


# ----------------------------------------------------------------------------
# WebSocket endpoint
# ----------------------------------------------------------------------------
@router.websocket("/agent/connect")
async def agent_connect(
    websocket: WebSocket,
    node_id: Optional[int] = Query(default=None, description="Numeric GpuNode.id"),
    node_key: Optional[str] = Query(default=None, alias="node_key", description="Raw GpuNode.api_key"),
):
    """Outbound WS endpoint for node-agents.

    Lifecycle:
      1. Accept the WebSocket (we accept first so we can send a clean close code).
      2. Authenticate via query params.
      3. On success: mark DB state = 'connected', generate session id, add to registry.
      4. Loop: receive messages. Two message types are handled:
         - {"type": "ping", ...}        -> update last_ws_seen, send pong
         - {"type": "job_result", ...}  -> resolve the matching future in
                                            _PENDING_JOBS with the payload
         Unknown types are logged and tolerated (forward-compat).
      5. On disconnect (any reason): mark DB state = 'disconnected', clear
         session id, remove from registry, fail any in-flight pending jobs
         with NodeOfflineError so callers unblock promptly.
    """
    # Accept the WebSocket unconditionally — we need the channel to send a close code.
    await websocket.accept()

    # --- 1. Validate handshake
    if node_id is None or not node_key:
        log.warning("WS handshake missing node_id/node_key")
        await websocket.close(code=4400, reason="missing node_id or node_key")
        return

    db = SessionLocal()
    try:
        node = _authenticate_node(db, node_id, node_key)
        if node is None:
            log.warning(f"WS auth failed for node_id={node_id}")
            await websocket.close(code=4401, reason="invalid node_id or api_key")
            return

        # --- 2. Mark connecting briefly, then connected.
        session_id = str(uuid.uuid4())
        _set_state(db, node, "connecting", session_id, time.time())
        _set_state(db, node, "connected", session_id, time.time())
        _WS_REGISTRY[node.id] = websocket
        log.info(f"WS connected: node_id={node.id} session={session_id}")

        # Tell the agent we're good (optional but helpful for first-message tests).
        try:
            await websocket.send_text(json.dumps({
                "type": "welcome",
                "node_id": node.id,
                "session_id": session_id,
                "server_time": time.time(),
            }))
        except Exception as e:
            log.warning(f"WS welcome send failed: {e}")

        # --- 3. Receive loop
        while True:
            try:
                raw = await websocket.receive_text()
            except WebSocketDisconnect:
                break
            except Exception as e:
                log.warning(f"WS receive error node_id={node.id}: {e}")
                break

            ts = time.time()
            try:
                msg = json.loads(raw)
            except Exception:
                # Non-JSON: ignore but still count as a heartbeat tick (agent may probe).
                node.last_ws_seen = ts
                db.add(node)
                db.commit()
                continue

            mtype = (msg.get("type") or "").lower()

            if mtype == "ping":
                # Update heartbeat timestamp; opportunistically pull vram/jobs.
                node.last_ws_seen = ts
                if isinstance(msg.get("vram_used_gb"), (int, float)):
                    node.vram_used_gb = float(msg["vram_used_gb"])
                if isinstance(msg.get("active_jobs"), int):
                    pass  # we don't store this on the node row in v1
                db.add(node)
                db.commit()
                # Acknowledge so the agent can measure RTT if it wants to.
                try:
                    await websocket.send_text(json.dumps({
                        "type": "pong",
                        "ts": ts,
                    }))
                except Exception:
                    break

            elif mtype == "job_result":
                # Phase 2: correlate reply with the dispatcher's future.
                job_id = msg.get("job_id")
                if not job_id:
                    log.warning(f"WS job_result without job_id from node_id={node.id}: {msg}")
                    continue
                fut = _PENDING_JOBS.pop(job_id, None)
                if fut is None:
                    # Late reply (already timed out, or unknown id). Drop.
                    log.debug(f"WS job_result for unknown/expired job_id={job_id}")
                    continue
                if not fut.done():
                    fut.set_result(msg)
                # else: race with timeout — already failed, ignore.

            elif mtype in ("goodbye", "bye", "close"):
                # Polite disconnect
                break

            else:
                # Unknown type — accept silently for forward-compat. Still keep-alive.
                node.last_ws_seen = ts
                db.add(node)
                db.commit()

    except WebSocketDisconnect:
        # Normal close path
        pass
    except Exception as e:
        log.exception(f"WS unhandled error node_id={node_id}: {e}")
        try:
            await websocket.close(code=1011, reason="server error")
        except Exception:
            pass
    finally:
        # --- 4. Cleanup — always run.
        try:
            db.close()
        except Exception:
            pass
        # Re-open a session for the cleanup write (the loop one may be closed).
        try:
            cleanup_db = SessionLocal()
            try:
                node_row = cleanup_db.query(GpuNode).filter(GpuNode.id == node_id).first() if node_id else None
                if node_row is not None:
                    _set_state(cleanup_db, node_row, "disconnected", None, time.time())
                    log.info(f"WS disconnected: node_id={node_row.id}")
            finally:
                cleanup_db.close()
        except Exception as e:
            log.warning(f"WS cleanup DB write failed: {e}")
        # Fail any pending jobs for this node so callers don't hang.
        if node_id is not None:
            failed = _fail_pending_for_node(node_id, "ws disconnect")
            if failed:
                log.info(f"WS cleanup: failed {failed} pending job(s) for node_id={node_id}")
        # Remove from in-memory registry (idempotent).
        if node_id is not None:
            _WS_REGISTRY.pop(node_id, None)


# ----------------------------------------------------------------------------
# LANA-110: WS chat completions (streaming over WebSocket, proxy/CF-tunnel safe)
# ----------------------------------------------------------------------------
import json as _json
import asyncio as _asyncio
import time as _time
import datetime as _dt

_WS_CHAT_DOC = """OpenAI-compatible chat completions over WebSocket.

Framing (JSON, one object per message):
  client -> server: {"id": <echo>, "model": "...", "messages": [...],
                     "stream": true|false, "max_tokens": n, "temperature": f}
  server -> client: {"type": "hello"}                                on connect
                    {"id": echo, "type": "error", "detail": str, "status": int}
                    {"id": echo, "type": "status", "note": str}       progress pings
                    {"id": echo, "type": "chunk", "delta": str}       (stream=true)
                    {"id": echo, "type": "final", "content": str,
                     "usage": {...}, "model": str, "credits": str}    summary

Auth: query param ?api_key=<raw> (browsers cannot set headers on WS) or
Sec-WebSocket-Protocol: api-key.<raw>. Same key rules as the HTTP path.

Quota: mirrors /v1/chat/completions exactly — DB-backed credits flag
(LANA-88) + per-user quota_mode (blocked -> error frame, balance -> floor
check, unlimited -> skip charging). Booking (Usage/CreditTransaction/PoolJob/
revenue) identical to the HTTP path.
"""


def _ws_auth_user(db, user_key):
    """Resolve a raw api key to its active User (same rule as get_current_user)."""
    if not user_key:
        return None
    from auth import hash_api_key
    from models import ApiKey, User
    kh = hash_api_key(user_key)
    key = db.query(ApiKey).filter(ApiKey.key_hash == kh, ApiKey.is_active == True).first()  # noqa: E712
    if key is None:
        return None
    u = db.query(User).filter(User.id == key.user_id).first()
    if u is None or not getattr(u, "is_active", True):
        return None
    return u


@router.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    await websocket.accept()
    await websocket.send_text(_json.dumps({"type": "hello"}))

    user_key = websocket.query_params.get("api_key") or ""
    if not user_key:
        for sub in (websocket.headers.get("sec-websocket-protocol") or "").split(","):
            s = sub.strip()
            if s.startswith("api-key."):
                user_key = s[len("api-key."):]
                break

    from models import ApiKey, User, Usage, CreditTransaction, PoolJob, GpuNode
    from database import SessionLocal
    from pool import route_request
    from config import credits_enabled
    from main import COST_PER_1K_TOKENS, DEFAULT_MODEL, distribute_revenue

    db = SessionLocal()
    _ws_open = True
    try:
        user = _ws_auth_user(db, user_key)
        if user is None:
            await websocket.send_text(_json.dumps({"type": "error", "status": 401,
                                                   "detail": "Invalid or inactive API key."}))
            await websocket.close(code=4401)
            return
        while _ws_open:
            raw = await websocket.receive_text()
            try:
                req = _json.loads(raw)
            except Exception:
                await websocket.send_text(_json.dumps({"type": "error", "status": 400,
                                                       "detail": "invalid JSON frame"}))
                continue
            echo = req.get("id")

            # ---- quota (mirrors main.chat_completions, LANA-88 semantics) ----
            qm = (getattr(user, "quota_mode", "unlimited") or "unlimited")
            if qm == "blocked":
                await websocket.send_text(_json.dumps({"id": echo, "type": "error", "status": 403,
                                                       "detail": "Your account is blocked from using this pool by the administrator."}))
                continue
            billing = credits_enabled(db) and (qm != "unlimited")
            balance = float(db.query(func.coalesce(func.sum(CreditTransaction.amount), 0.0))
                            .filter(CreditTransaction.user_id == user.id).scalar() or 0.0)
            model = req.get("model") or DEFAULT_MODEL
            if billing and balance < 0.01:
                await websocket.send_text(_json.dumps({"id": echo, "type": "error", "status": 402,
                                                       "detail": f"Insufficient credits. Current balance: {balance:.4f}"}))
                continue

            stream = bool(req.get("stream", False))

            async def _send_status(note):
                await websocket.send_text(_json.dumps({"id": echo, "type": "status", "note": note}))

            await _send_status("routing")
            ollama_payload = {
                "model": model,
                "messages": req.get("messages", []),
                "stream": False,  # Phase 2: upstream non-streaming; WS carries progress
                "options": {"temperature": req.get("temperature")},
            }
            if req.get("max_tokens") is not None:
                ollama_payload["options"]["num_predict"] = int(req["max_tokens"])

            t0 = _time.time()
            routed = await route_request(db, user, ollama_payload, model)
            if not routed["ok"]:
                status = 403 if routed["source"] == "denied" else (503 if routed["source"] == "cloud" else 502)
                await websocket.send_text(_json.dumps({"id": echo, "type": "error", "status": status,
                                                       "detail": routed.get("error") or "Routing failed"}))
                continue

            await _send_status("generating")
            resp = routed["response"]
            msg = (resp.get("choices", [{}])[0].get("message", {}) or {})
            content = msg.get("content", "")
            usage_d = resp.get("usage", {}) or {}
            prompt_tokens = int(usage_d.get("prompt_tokens", 0) or 0)
            completion_tokens = int(usage_d.get("completion_tokens", 0) or 0)
            total_tokens = int(usage_d.get("total_tokens", prompt_tokens + completion_tokens) or 0)

            if stream and content:
                # Phase 2: chunk the finished content (progressive feel). Phase 3
                # streams true upstream deltas via the node WS job stream.
                CH = 24
                for i in range(0, len(content), CH):
                    await websocket.send_text(_json.dumps({"id": echo, "type": "chunk",
                                                           "delta": content[i:i + CH]}))
                    await _asyncio.sleep(0)

            cost = round((total_tokens / 1000.0) * COST_PER_1K_TOKENS, 6)
            api_key = db.query(ApiKey).filter(ApiKey.user_id == user.id, ApiKey.is_active == True).first()  # noqa: E712
            db.add(Usage(user_id=user.id,
                         api_key_id=api_key.id if api_key else None,
                         model=model,
                         prompt_tokens=prompt_tokens,
                         completion_tokens=completion_tokens,
                         total_tokens=total_tokens,
                         credits_charged=cost))
            if billing:
                db.add(CreditTransaction(user_id=user.id, amount=-cost,
                                         balance_after=round(balance - cost, 6),
                                         reason=f"ws-chat: {model} ({total_tokens} tokens, src={routed['source']})"))
            pj = PoolJob(user_id=user.id, node_id=routed.get("node_id"), model=model,
                         source=routed["source"], status="succeeded",
                         prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
                         total_tokens=total_tokens, job_cost=cost,
                         latency_ms=int((_time.time() - t0) * 1000),
                         finished_at=_dt.datetime.utcnow())
            db.add(pj)
            db.flush()
            if routed["source"] == "community" and routed.get("node_id"):
                node = db.query(GpuNode).filter(GpuNode.id == routed["node_id"]).first()
                if node is not None:
                    distribute_revenue(db, node, cost, pool_job=pj)
            db.commit()

            await websocket.send_text(_json.dumps({"id": echo, "type": "final", "model": model,
                                                   "content": content, "usage": usage_d,
                                                   "credits": (f"-{cost}" if billing else f"informational:{cost}")}))
    except WebSocketDisconnect:
        return
    except Exception as e:  # never crash the socket silently
        import logging as _log_mod
        _log_mod.getLogger("ws").exception("ws_chat failed")
        try:
            await websocket.send_text(_json.dumps({"type": "error", "status": 500, "detail": str(e)[:200]}))
            await websocket.close()
        except Exception:
            pass
    finally:
        db.close()
