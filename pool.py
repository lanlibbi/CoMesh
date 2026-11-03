"""
Community GPU-Pool load-balancing + revenue distribution.

Two layers:

  * `PoolRouter` (class) — picks the best node for a given request.
    Scoring weights: online > enough free VRAM > low utilization > low rate
    > reachability (a registered node is expected to be dialable).
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
import json
import logging
import os
import time
from datetime import datetime
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from netinfo import node_base_url

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


def node_request_headers() -> dict:
    """Header fuer jede Anfrage an einen Node-Agenten.

    `X-Node-Secret` ist das gemeinsame Geheimnis (NODE_SHARED_SECRET beider
    Seiten). Ist es nicht gesetzt, bleibt das Verhalten wie bisher — ein Agent
    ohne Sperre erwartet dann auch keinen Kopf.
    """
    secret = (os.environ.get("NODE_SHARED_SECRET") or "").strip()
    return {"X-Node-Secret": secret} if secret else {}


def _node_allows_model(node: GpuNode, model: str) -> bool:
    """True if the node's whitelist (or default) admits the model."""
    return node.can_serve_model(model)


def _is_admin_user(user: User) -> bool:
    """Local copy of the admin check."""
    import os
    if getattr(user, "role", None) == "admin":
        return True
    admins = [e.strip().lower() for e in (os.environ.get("ADMIN_EMAILS") or "").split(",") if e.strip()]
    return (getattr(user, "email", None) or "").lower() in admins


def _user_allows_model(user: User, model: str) -> bool:
    """True if the user's whitelist (or default) admits the model."""
    return user.can_use_model(model)


def angebotene_cloud_modelle(db: Session) -> set:
    """Cloud-Modelle, die mindestens ein aktiver Node anbietet.

    Ein Node mit `allowed_models = None` bietet alle **lokalen** Modelle an und keine Cloud —
    Cloud muss der Betreiber ausdrücklich in die Liste schreiben. Damit entscheidet der
    Provider, welche Cloud-Modelle überhaupt zur Verfügung stehen.
    """
    from models import _is_cloud_model_name

    namen: set = set()
    for node in db.query(GpuNode).filter(GpuNode.is_enabled == True).all():  # noqa: E712
        for modell in (node.get_allowed_models() or []):
            if _is_cloud_model_name(modell):
                namen.add(modell)
    return namen


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

        # Lower is better. We weight price more heavily than utilization:
        # in the POC the bottleneck is willingness to be cheap, not network
        # latency (all nodes are reached directly, whatever the network is).
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


async def _forward_to_node(node: GpuNode, ollama_payload: dict, timeout: float = 300.0) -> dict:
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
    base = node_base_url(node.node_url, node.port)
    if not base:
        # Legacy rows written before LANA-89 still carry only `tailscale_ip`.
        legacy_host = (node.tailscale_ip or "").strip()
        if legacy_host:
            base = node_base_url(
                legacy_host if "://" in legacy_host else f"http://{legacy_host}",
                node.port,
            )
    if not base:
        raise RuntimeError(
            f"Node {node.id} has no reachable address yet. It gets one from its first "
            "heartbeat (or set node_url at registration / in the node's ADVERTISE_HOST)."
        )
    url = f"{base}/v1/chat/completions"
    # Build the OpenAI-shaped payload from the ollama_payload
    openai_payload = {
        "model": ollama_payload.get("model", ""),
        "messages": ollama_payload.get("messages", []),
        "temperature": (ollama_payload.get("options") or {}).get("temperature", 1.0),
        "max_tokens": (ollama_payload.get("options") or {}).get("num_predict"),
        "stream": False,
    }
    # Werkzeuge mitgeben — sonst kann der Node nichts aufrufen.
    if ollama_payload.get("tools"):
        openai_payload["tools"] = ollama_payload["tools"]
        if ollama_payload.get("tool_choice") is not None:
            openai_payload["tool_choice"] = ollama_payload["tool_choice"]
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(url, json=openai_payload, headers=node_request_headers())
        r.raise_for_status()
        data = r.json()
    # Normalize to the dict shape downstream expects (Ollama-style with
    # message.content). We pull from the OpenAI response.
    msg = (data.get("choices") or [{}])[0].get("message") or {}
    usage = data.get("usage") or {}
    return {
        "model": data.get("model", ollama_payload.get("model", "")),
        "message": {
            "role": msg.get("role", "assistant"),
            "content": msg.get("content", ""),
            "tool_calls": msg.get("tool_calls"),
        },
        "prompt_eval_count": usage.get("prompt_tokens", 0),
        "eval_count": usage.get("completion_tokens", 0),
    }


async def _forward_to_node_stream(node: GpuNode, ollama_payload: dict, on_delta, timeout: float = 300.0) -> dict:
    """Weiterleitung an einen Node mit SSE: liefert Deltas weiter und sammelt die Antwort.

    Gegenstueck zu `_forward_to_node`, aber streamend. Der Agent antwortet mit
    OpenAI-konformen SSE-Rahmen; jedes `choices[0].delta.content` geht sofort an
    `on_delta`, sodass ein Client die Antwort mitliest, statt auf das Ende zu
    warten. Am Ende steht dieselbe OpenAI-foermige Antwort wie beim blockierenden
    Weg, inklusive `usage` aus dem Schluss-Rahmen des Agenten.
    """
    import httpx as _hx

    from netinfo import node_base_url

    base = node_base_url(getattr(node, "node_url", None), getattr(node, "port", None) or 11435,
                         fallback_scheme="http") or f"http://{node.tailscale_ip}:{node.port or 11435}"
    payload = dict(ollama_payload)
    payload["stream"] = True

    content_parts: list = []
    usage: dict = {}
    prompt_tokens = 0
    completion_tokens = 0

    async with _hx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST", f"{base.rstrip('/')}/v1/chat/completions",
                                 json=payload, headers=node_request_headers()) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                body = line[len("data:"):].strip()
                if body == "[DONE]":
                    break
                try:
                    obj = json.loads(body)
                except ValueError:
                    continue
                if "error" in obj:
                    raise RuntimeError((obj.get("error") or {}).get("message") or "node stream error")
                for ch in obj.get("choices") or []:
                    delta = ((ch.get("delta") or {}).get("content")) or ""
                    if delta:
                        content_parts.append(delta)
                        if on_delta is not None:
                            await on_delta(delta)
                if obj.get("usage"):
                    usage = obj["usage"] or {}
                    prompt_tokens = int(usage.get("prompt_tokens") or prompt_tokens or 0)
                    completion_tokens = int(usage.get("completion_tokens") or completion_tokens or 0)

    text = "".join(content_parts)
    return {
        "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


async def _forward_to_node_ws(node: GpuNode, ollama_payload: dict, timeout: float = 120.0,
                              on_delta=None) -> dict:
    """Forward a job to a community node over its WebSocket (Phase 2 path).

    Builds the OpenAI-shaped /v1/chat/completions body from the
    ollama_payload (same shape as the HTTP fallback) and dispatches it
    via `ws.send_job_via_ws`. The agent replies with a `job_result`
    whose `response` field is the same OpenAI-shaped dict the HTTP path
    would have returned. We then normalize it to the Ollama-style dict
    the caller expects.

    Phase 3 (LANA-114): with on_delta set, the payload requests
    stream=true and the agent may emit job_result_chunk frames; they are
    forwarded to on_delta as they arrive. The binding job_result is then
    the source of truth for content/usage (its content equals the deltas
    the Ollama agent emitted). If the agent cannot stream (old agent
    version, BACKEND=openai), it answers Phase-2 style with the full
    response — callers can detect that by comparing on-delta count.
    """
    from ws import send_job_via_ws  # late import: avoid circular at module load
    openai_payload = {
        "model": ollama_payload.get("model", ""),
        "messages": ollama_payload.get("messages", []),
        "temperature": (ollama_payload.get("options") or {}).get("temperature", 1.0),
        "max_tokens": (ollama_payload.get("options") or {}).get("num_predict"),
        "stream": bool(ollama_payload.get("stream")) and on_delta is not None,
    }
    result = await send_job_via_ws(node.id, openai_payload, timeout=timeout,
                                   on_delta=on_delta)
    data = result.get("response") or {}
    msg = (data.get("choices") or [{}])[0].get("message") or {}
    usage = data.get("usage") or {}
    return {
        "model": data.get("model", ollama_payload.get("model", "")),
        "message": {
            "role": msg.get("role", "assistant"),
            "content": msg.get("content", ""),
            "tool_calls": msg.get("tool_calls"),
        },
        "prompt_eval_count": usage.get("prompt_tokens", 0),
        "eval_count": usage.get("completion_tokens", 0),
    }


async def _local_ollama_streaming(ollama_payload: dict, on_delta) -> dict:
    """Phase 3 (LANA-114): local Ollama ND-JSON streaming.

    Streams /api/chat from the local backend, forwards every content delta
    via on_delta and returns the same normalized Ollama-style dict the
    non-streaming local path produces (content aggregated from deltas).
    Raises httpx errors like the non-streaming path so callers keep their
    existing fallback semantics.
    """
    from main import OLLAMA_URL  # late import to avoid circulars
    prompt_tokens = 0
    completion_tokens = 0
    parts: list = []
    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream("POST", f"{OLLAMA_URL}/api/chat", json=ollama_payload) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if not line.strip():
                    continue
                data = json.loads(line)
                delta = (data.get("message") or {}).get("content") or ""
                if delta:
                    parts.append(delta)
                    await on_delta(delta)
                if data.get("done"):
                    prompt_tokens = data.get("prompt_eval_count") or 0
                    completion_tokens = data.get("eval_count") or 0
    return {
        "model": ollama_payload.get("model", ""),
        "message": {"role": "assistant", "content": "".join(parts)},
        "prompt_eval_count": prompt_tokens,
        "eval_count": completion_tokens,
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
                "message": {
                    "role": msg.get("role", "assistant"),
                    "content": msg.get("content", ""),
                    # Werkzeugaufrufe durchreichen; ohne sie kann kein Agent arbeiten.
                    "tool_calls": msg.get("tool_calls"),
                },
                # Ein Aufruf gewinnt: Ollama meldet "stop", auch wenn Werkzeuge gefordert
                # sind — Clients entscheiden aber an finish_reason == "tool_calls".
                "finish_reason": "tool_calls" if msg.get("tool_calls")
                else (ollama_resp.get("done_reason") or "stop"),
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
    on_delta=None,
) -> dict:
    """
    Main entry point used by main.py's /v1/chat/completions.

    Decision tree:
      1. Try local Ollama on the portal host. If it works, source=local.
      2. If local fails or is busy, pick a community node and forward.
      3. If no community node is available, return 503.

    Returns a dict with the OpenAI-shaped response plus routing metadata:
      { "ok": True/False, "source": "local|community|cloud|none",
        "node_id": int|None, "response": {...}, "error": str|None }

    Phase 3 (LANA-114): on_delta (optional async callable receiving str
    deltas) is forwarded to the WS community path. The local path streams
    Ollama ND-JSON directly when on_delta is set.
    """
    from main import OLLAMA_URL  # late import to avoid circulars

    # --- 0. user whitelist gate ---
    # If the user has not opted in to the requested model (e.g. cloud models
    # are off by default), fail fast with a clear 403 message rather than
    # trying every node and returning a generic 502/503.
    # Cloud-Modelle brauchen zusätzlich eine Freigabe auf der Anbieterseite: irgendein
    # aktiver Node muss das Modell in seiner Liste führen.
    from models import _is_cloud_model_name
    if _is_cloud_model_name(model) and model not in angebotene_cloud_modelle(db):
        return {
            "ok": False,
            "source": "denied",
            "node_id": None,
            "response": None,
            "error": (
                f"Cloud model '{model}' is not offered by any node. "
                "A provider must release it for their node (Geräte → Modelle)."
            ),
        }

    if not _user_allows_model(user, model):
        from models import _is_cloud_model_name
        if _is_cloud_model_name(model):
            # Ein Consumer kann Cloud-Modelle nicht selbst freischalten — die Auswahl
            # im Profil gibt es nur fuer Provider und "beides". Fuer ihn ist der Weg
            # ueber die Administration der einzige.
            rolle = (getattr(user, "role", "") or "").lower()
            if rolle == "consumer":
                hinweis = (
                    "Ask an administrator to release it for your account "
                    "(Freigaben → Konto → Modelle)."
                )
            else:
                hinweis = "Enable it in your profile (Profil → Cloud-Modelle erlauben)."
            return {
                "ok": False,
                "source": "denied",
                "node_id": None,
                "response": None,
                "error": f"Cloud model '{model}' is not allowed for your account. {hinweis}",
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
        if on_delta is not None and ollama_payload.get("stream"):
            # Phase 3 (LANA-114): local streaming — forward Ollama ND-JSON
            # deltas immediately, then return the aggregated response.
            local_resp = await _local_ollama_streaming(ollama_payload, on_delta)
            return {
                "ok": True,
                "source": "local",
                "node_id": None,
                "response": _ollama_to_openai_shape(local_resp, model),
                "error": None,
            }
        async with httpx.AsyncClient(timeout=300.0) as client:
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
                ollama_resp = await _forward_to_node_ws(node, ollama_payload, on_delta=on_delta)
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
                if on_delta is not None and ollama_payload.get("stream"):
                    # Phase 4: streamend zum Agenten, Deltas sofort weiterreichen
                    ollama_resp = await _forward_to_node_stream(node, ollama_payload, on_delta)
                    transport = "http+stream"
                else:
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
    user: User = Depends(__import__("auth").get_current_user),
    db: Session = Depends(get_db),
):
    """Recent pool jobs for the caller; admins see everything."""
    q = db.query(PoolJob)
    if not _is_admin_user(user):
        my_node_ids = [n.id for n in db.query(GpuNode).filter(GpuNode.owner_id == user.id).all()]
        from sqlalchemy import or_ as _or
        q = q.filter(_or(PoolJob.user_id == user.id, PoolJob.node_id.in_(my_node_ids or [-1])))

    rows = (
        q.order_by(PoolJob.started_at.desc())
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
