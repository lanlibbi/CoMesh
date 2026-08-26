"""
Community GPU-Pool load-balancing + revenue distribution.

Two layers:

  * `PoolRouter` (class) — picks the best node for a given request.
    Scoring weights: online > enough free VRAM > low utilization > low rate
    > Tailscale reachability (we assume yes if registered).
  * `distribute_revenue` (function) — splits a job's revenue 70/20/10
    (owner / platform / treasury) and writes a NodeEarning row +
    bumps GpuNode.earnings_total. The platform/treasury side is
    tracked as a single global PlatformAccount row (singleton).

Endpoints (mounted under /pool):
  GET  /pool/stats           community pool summary (no auth, used by the
                             dashboard's "Community: 156 GB VRAM" hero)
  GET  /pool/jobs            recent jobs across the pool (auth required)
  GET  /pool/route           debug/preview: "where would this request land?"
                             useful for the admin dashboard.
"""
import asyncio
import logging
import time
from datetime import datetime
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import (
    GpuNode, NodeEarning, PoolJob, User, get_user_credits,
)

log = logging.getLogger("gpu-pool.pool")

router = APIRouter(prefix="/pool", tags=["pool"])


# ----------------------------------------------------------------------------
# Revenue split (configurable, kept simple for the POC)
# ----------------------------------------------------------------------------
OWNER_SHARE = 0.70
PLATFORM_SHARE = 0.20
TREASURY_SHARE = 0.10


# ----------------------------------------------------------------------------
# Load-balancing
# ----------------------------------------------------------------------------
class NodeCandidate:
    """Lightweight wrapper used during scoring."""
    __slots__ = ("node", "score", "free_vram_gb")

    def __init__(self, node: GpuNode, score: float, free_vram_gb: float):
        self.node = node
        self.score = score
        self.free_vram_gb = free_vram_gb


def _is_online(node: GpuNode) -> bool:
    if not node.is_enabled or node.last_seen is None or node.status not in ("online", "busy"):
        return False
    return (datetime.utcnow() - node.last_seen).total_seconds() < 90


def _node_allows_model(node: GpuNode, model: str) -> bool:
    """True if the node's whitelist (or default) admits the model."""
    return node.can_serve_model(model)


def _user_allows_model(user: User, model: str) -> bool:
    """True if the user's whitelist (or default) admits the model."""
    return user.can_use_model(model)


def find_best_node(
    db: Session,
    model: str,
    user: Optional[User] = None,
    tokens_needed: int = 1024,
    exclude_node_ids: Optional[List[int]] = None,
) -> Optional[GpuNode]:
    """
    Pick the best community node for a request.

    Filters (in order):
      1. User's whitelist must admit the model (cloud model + no opt-in -> skip).
      2. Node must be online (last_seen < 90s ago, status online/busy)
      3. Node's whitelist must admit the model.
      4. Node must have enough free VRAM to plausibly host the model.
      5. Score: lower utilization + lower hourly_rate is better.
    """
    exclude = set(exclude_node_ids or [])
    nodes = db.query(GpuNode).filter(GpuNode.is_enabled == True).all()
    if not nodes:
        return None

    # rough VRAM headroom needed (GB) for this model
    model_vram_need = _estimate_model_vram_gb(model)
    candidates: List[NodeCandidate] = []

    for n in nodes:
        if n.id in exclude:
            continue
        if not _is_online(n):
            continue
        # Per-node model whitelist (also gates cloud models)
        if not _node_allows_model(n, model):
            continue
        # Per-user model whitelist
        if user is not None and not _user_allows_model(user, model):
            continue
        free_vram = max(0.0, n.vram_gb - n.vram_used_gb)
        if free_vram < model_vram_need:
            continue

        # Lower is better. We weight price more heavily than utilization
        # because in the POC every node is on Tailscale — the bottleneck
        # is willingness to be cheap, not network latency.
        score = (
            n.hourly_rate * 1.0
            + n.current_utilization * 0.5
            + (0.0 if n.status == "online" else 0.2)  # busy penalty
        )
        candidates.append(NodeCandidate(n, score, free_vram))

    if not candidates:
        return None
    candidates.sort(key=lambda c: c.score)
    return candidates[0].node


def _estimate_model_vram_gb(model: str) -> float:
    """Very rough VRAM budget by model name. Tuned for common Ollama tags."""
    m = (model or "").lower()
    # explicit size hints like ":7b", ":13b", ":70b"
    for size_tag, gb in [("70b", 40.0), ("33b", 20.0), (":13b", 9.0), (":7b", 5.0),
                         (":3b", 2.5), (":1b", 1.5), ("mini", 2.0), ("small", 1.5)]:
        if size_tag in m:
            return gb
    # embedding / small default
    if "embed" in m:
        return 0.5
    return 4.0  # safe default


async def _forward_to_node(node: GpuNode, ollama_payload: dict, timeout: float = 120.0) -> dict:
    """
    Forward an OpenAI-shaped request to a community node's node-agent.

    The node-agent exposes /v1/chat/completions (OpenAI-compatible) and
    internally talks to the local Ollama. We call that path so the
    response shape matches what the caller expects; the agent handles
    the Ollama <-> OpenAI translation. We then read the OpenAI-shaped
    response back.

    This is the HTTP-FALLBACK path used by the router when the node's
    WS is not connected. Phase 2 keeps it bit-identical to v1; Phase 3
    will remove it once the WS is the only transport.
    """
    import secrets as _secrets
    url = f"http://{node.tailscale_ip}:{node.port}/v1/chat/completions"
    # Build the OpenAI-shaped payload from the ollama_payload
    openai_payload = {
        "model": ollama_payload.get("model", ""),
        "messages": ollama_payload.get("messages", []),
        "temperature": (ollama_payload.get("options") or {}).get("temperature", 1.0),
        "max_tokens": (ollama_payload.get("options") or {}).get("num_predict"),
        "stream": False,
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(url, json=openai_payload)
        r.raise_for_status()
        data = r.json()
    # Normalize to the dict shape downstream expects (Ollama-style with
    # message.content). We pull from the OpenAI response.
    msg = (data.get("choices") or [{}])[0].get("message") or {}
    usage = data.get("usage") or {}
    return {
        "model": data.get("model", ollama_payload.get("model", "")),
        "message": {"role": msg.get("role", "assistant"), "content": msg.get("content", "")},
        "prompt_eval_count": usage.get("prompt_tokens", 0),
        "eval_count": usage.get("completion_tokens", 0),
    }


async def _forward_to_node_ws(node: GpuNode, ollama_payload: dict, timeout: float = 120.0) -> dict:
    """Forward a job to a community node over its WebSocket (Phase 2 path).

    Builds the OpenAI-shaped /v1/chat/completions body from the
    ollama_payload (same shape as the HTTP fallback) and dispatches it
    via `ws.send_job_via_ws`. The agent replies with a `job_result`
    whose `response` field is the same OpenAI-shaped dict the HTTP path
    would have returned. We then normalize it to the Ollama-style dict
    the caller expects.
    """
    from ws import send_job_via_ws  # late import: avoid circular at module load
    openai_payload = {
        "model": ollama_payload.get("model", ""),
        "messages": ollama_payload.get("messages", []),
        "temperature": (ollama_payload.get("options") or {}).get("temperature", 1.0),
        "max_tokens": (ollama_payload.get("options") or {}).get("num_predict"),
        "stream": False,  # Phase 2: non-streaming only
    }
    result = await send_job_via_ws(node.id, openai_payload, timeout=timeout)
    data = result.get("response") or {}
    msg = (data.get("choices") or [{}])[0].get("message") or {}
    usage = data.get("usage") or {}
    return {
        "model": data.get("model", ollama_payload.get("model", "")),
        "message": {"role": msg.get("role", "assistant"), "content": msg.get("content", "")},
        "prompt_eval_count": usage.get("prompt_tokens", 0),
        "eval_count": usage.get("completion_tokens", 0),
    }


def _ws_connected(node: GpuNode) -> bool:
    """True if the node has an active outbound WebSocket to the pool.

    Reads the DB column `connection_state` (Phase 1+) which is kept in
    sync by the WS endpoint. Single source of truth: the registry
    `_WS_REGISTRY` is process-local to the API worker, so we cannot
    trust it from inside the request handler if the WS connect happened
    on a different process — but the Single-Worker-Policy (see ws.py)
    guarantees that the request handler and the WS endpoint are in the
    same process, so this DB read is correct.
    """
    return (getattr(node, "connection_state", None) or "disconnected") == "connected"


def _ollama_to_openai_shape(ollama_resp: dict, model: str) -> dict:
    """Reshape Ollama's /api/chat response into OpenAI's /v1/chat/completions shape."""
    import secrets
    msg = ollama_resp.get("message", {}) or {}
    return {
        "id": f"chatcmpl-pool-{secrets.token_hex(8)}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": msg.get("role", "assistant"), "content": msg.get("content", "")},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": ollama_resp.get("prompt_eval_count", 0) or 0,
            "completion_tokens": ollama_resp.get("eval_count", 0) or 0,
            "total_tokens": (ollama_resp.get("prompt_eval_count", 0) or 0)
            + (ollama_resp.get("eval_count", 0) or 0),
        },
    }


async def route_request(
    db: Session,
    user: User,
    ollama_payload: dict,
    model: str,
) -> dict:
    """
    Main entry point used by main.py's /v1/chat/completions.

    Decision tree:
      1. Try local Ollama (ai-lanlibbi itself). If it works, source=local.
      2. If local fails or is busy, pick a community node and forward.
      3. If no community node is available, return 503.

    Returns a dict with the OpenAI-shaped response plus routing metadata:
      { "ok": True/False, "source": "local|community|cloud|none",
        "node_id": int|None, "response": {...}, "error": str|None }
    """
    from main import OLLAMA_URL  # late import to avoid circulars

    # --- 0. user whitelist gate ---
    # If the user has not opted in to the requested model (e.g. cloud models
    # are off by default), fail fast with a clear 403 message rather than
    # trying every node and returning a generic 502/503.
    if not _user_allows_model(user, model):
        from models import _is_cloud_model_name
        if _is_cloud_model_name(model):
            return {
                "ok": False,
                "source": "denied",
                "node_id": None,
                "response": None,
                "error": (
                    f"Cloud model '{model}' is not allowed for your account. "
                    "Enable it in your profile (Profil → Cloud-Modelle erlauben)."
                ),
            }
        return {
            "ok": False,
            "source": "denied",
            "node_id": None,
            "response": None,
            "error": f"Model '{model}' is not in your allowed-models list. Update your profile.",
        }

    # --- 1. try local ---
    # Only fall back to community on a *connection* failure. HTTP 4xx/5xx
    # from Ollama (e.g. model not found) should bubble up so the caller
    # sees a clear error rather than getting silently re-routed.
    import httpx as _hx
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(f"{OLLAMA_URL}/api/chat", json=ollama_payload)
            r.raise_for_status()
            local_resp = r.json()
        return {
            "ok": True,
            "source": "local",
            "node_id": None,
            "response": _ollama_to_openai_shape(local_resp, model),
            "error": None,
        }
    except _hx.HTTPStatusError as e:
        # 4xx/5xx from local — propagate as a real error
        log.info(f"Local Ollama HTTP {e.response.status_code}: {e.response.text[:120]}")
        return {
            "ok": False,
            "source": "local",
            "node_id": None,
            "response": None,
            "error": f"local Ollama HTTP {e.response.status_code}: {e.response.text[:200]}",
        }
    except (_hx.ConnectError, _hx.ReadTimeout, _hx.ConnectTimeout, _hx.PoolTimeout, OSError) as e:
        # Real connection failure — fall back to community
        log.info(f"Local Ollama unreachable ({e}); falling back to community pool")

    # --- 2. try community ---
    # Try the best node first, then the next-best, etc. up to 3 nodes.
    # We exclude nodes that have already failed in this attempt.
    #
    # Phase 2 transport selection (per node):
    #   - WS-connected   -> use the WebSocket job stream (no inbound port
    #                       needed at the agent; 0 inbound at the provider
    #                       in the steady state)
    #   - disconnected   -> HTTP fallback to /v1/chat/completions
    #                       (kept bit-identical to v1; removed in Phase 3)
    from ws import NodeOfflineError, JobTimeoutError, WSError as _WSError
    attempted: set = set()
    for _ in range(3):
        node = find_best_node(db, model, user=user, exclude_node_ids=list(attempted))
        if node is None:
            break
        attempted.add(node.id)
        # Per-node transport decision. Whitelist order is preserved by
        # find_best_node's score sort; we do NOT re-sort here.
        if _ws_connected(node):
            transport = "ws"
            try:
                ollama_resp = await _forward_to_node_ws(node, ollama_payload)
            except (NodeOfflineError, JobTimeoutError) as e:
                # Node went offline mid-call, or timed out. Fall back to
                # HTTP for THIS node, then continue to the next.
                log.warning(f"WS to node {node.id} ({node.name}) failed: {e}; trying HTTP fallback")
                try:
                    ollama_resp = await _forward_to_node(node, ollama_payload)
                    transport = "http"
                except Exception as e2:
                    log.warning(f"HTTP fallback to node {node.id} ({node.name}) also failed: {e2}")
                    continue
            except _WSError as e:
                # Agent reported an error (e.g. Ollama down). Try the
                # HTTP fallback in case the legacy agent path still works.
                log.warning(f"WS agent error on node {node.id}: {e}; trying HTTP fallback")
                try:
                    ollama_resp = await _forward_to_node(node, ollama_payload)
                    transport = "http"
                except Exception as e2:
                    log.warning(f"HTTP fallback to node {node.id} ({node.name}) also failed: {e2}")
                    continue
        else:
            transport = "http"
            try:
                ollama_resp = await _forward_to_node(node, ollama_payload)
            except Exception as e:
                log.warning(f"Community node {node.id} ({node.name}) failed: {e}")
                continue
        # PoolJob bookkeeping happens in main.py; here we just attach transport.
        result_payload = _ollama_to_openai_shape(ollama_resp, model)
        log.info(
            f"pool: job routed to node {node.id} ({node.name}) via {transport} model={model}"
        )
        return {
            "ok": True,
            "source": "community",
            "node_id": node.id,
            "response": result_payload,
            "error": None,
            "_transport": transport,  # internal audit flag, not part of OpenAI shape
        }

    # --- 3. overflow to cloud (stub for RunPod/Vast) ---
    # The POC intentionally returns 503 — wiring a real cloud provider
    # is out of scope for this milestone.
    return {
        "ok": False,
        "source": "cloud",
        "node_id": None,
        "response": None,
        "error": "no GPU available (local down, no community node reachable)",
    }


# ----------------------------------------------------------------------------
# Revenue distribution
# ----------------------------------------------------------------------------
def distribute_revenue(
    db: Session,
    node: GpuNode,
    job_cost: float,
    pool_job: Optional[PoolJob] = None,
) -> NodeEarning:
    """
    Split a job's revenue 70/20/10 and write a NodeEarning row.

    `job_cost` is in credits. We *also* bump GpuNode.earnings_total by
    the owner's share so the dashboard can show "Earned: 12.4 credits"
    without needing to sum NodeEarning rows on every read.
    """
    owner_share = round(job_cost * OWNER_SHARE, 6)
    platform_share = round(job_cost * PLATFORM_SHARE, 6)
    treasury_share = round(job_cost * TREASURY_SHARE, 6)

    earning = NodeEarning(
        node_id=node.id,
        owner_id=node.owner_id,
        pool_job_id=pool_job.id if pool_job else None,
        job_cost=round(job_cost, 6),
        owner_share=owner_share,
        platform_share=platform_share,
        treasury_share=treasury_share,
    )
    db.add(earning)
    node.earnings_total = round(node.earnings_total + owner_share, 6)
    # Platform/treasury totals would be summed via SQL for the admin
    # dashboard; we keep them on the row for now.
    db.commit()
    db.refresh(earning)
    return earning


# ----------------------------------------------------------------------------
# Endpoints
# ----------------------------------------------------------------------------
class RoutePreviewRequest(BaseModel):
    model: str
    tokens_needed: int = 1024


class RoutePreviewResponse(BaseModel):
    source: str           # local | community | cloud
    node_id: Optional[int]
    node_name: Optional[str]
    reason: str


@router.post("/route-preview", response_model=RoutePreviewResponse)
def route_preview(
    req: RoutePreviewRequest,
    db: Session = Depends(get_db),
):
    """Debug preview: where would a request land right now? (Auth: any user)"""
    from main import OLLAMA_URL
    # Cheap local-availability check (no model load):
    try:
        import httpx as _hx
        with _hx.Client(timeout=2.0) as c:
            r = c.get(f"{OLLAMA_URL}/api/tags")
            local_ok = r.status_code == 200
    except Exception:
        local_ok = False

    if local_ok:
        return RoutePreviewResponse(source="local", node_id=None, node_name=None, reason="local Ollama reachable")
    node = find_best_node(db, req.model, req.tokens_needed)
    if node:
        return RoutePreviewResponse(
            source="community", node_id=node.id, node_name=node.name,
            reason=f"cheapest score {node.hourly_rate}/h, util={node.current_utilization:.2f}"
        )
    return RoutePreviewResponse(
        source="cloud", node_id=None, node_name=None,
        reason="no local + no community node available (cloud overflow stub)"
    )


@router.get("/jobs")
def recent_jobs(
    limit: int = 20,
    db: Session = Depends(get_db),
):
    """Recent pool jobs across the community (used by admin dashboard)."""
    rows = (
        db.query(PoolJob)
        .order_by(PoolJob.started_at.desc())
        .limit(min(max(limit, 1), 200))
        .all()
    )
    return [
        {
            "id": r.id,
            "user_id": r.user_id,
            "node_id": r.node_id,
            "model": r.model,
            "source": r.source,
            "status": r.status,
            "total_tokens": r.total_tokens,
            "job_cost": r.job_cost,
            "latency_ms": r.latency_ms,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "error": r.error,
        }
        for r in rows
    ]


@router.get("/earnings/mine")
def my_earnings_real(
    db: Session = Depends(get_db),
    # We import get_current_user lazily to keep this file importable
    # without FastAPI in scope (helps the load-balancer unit tests).
    user: User = Depends(__import__("auth").get_current_user),
):
    """All earnings events for nodes owned by the caller."""
    my_nodes = db.query(GpuNode).filter(GpuNode.owner_id == user.id).all()
    node_ids = [n.id for n in my_nodes]
    if not node_ids:
        return {"total": 0.0, "by_node": [], "events": []}

    events = (
        db.query(NodeEarning)
        .filter(NodeEarning.node_id.in_(node_ids))
        .order_by(NodeEarning.created_at.desc())
        .limit(100)
        .all()
    )
    by_node: dict = {}
    for n in my_nodes:
        by_node[n.id] = {
            "node_id": n.id, "name": n.name, "earnings_total": n.earnings_total,
        }
    return {
        "total": round(sum(n.earnings_total for n in my_nodes), 6),
        "by_node": list(by_node.values()),
        "events": [
            {
                "id": e.id, "node_id": e.node_id, "job_cost": e.job_cost,
                "owner_share": e.owner_share, "platform_share": e.platform_share,
                "treasury_share": e.treasury_share, "created_at": e.created_at.isoformat(),
            }
            for e in events
        ],
    }
