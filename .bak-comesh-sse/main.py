"""
GPU-Sharing POC - FastAPI backend.

OpenAI-compatible /v1/chat/completions that proxies to:
  1. Local Ollama on the portal host itself - default path
  2. Community pool nodes - picked by pool.find_best_node()
  3. Cloud overflow (RunPod/Vast) - stub for now

Includes user management, API key issuance, credit accounting,
payments (Stripe, PayPal, Alipay, Apple Pay - all in test/mock mode
for the POC), and Community GPU-Pool (node registration, heartbeat,
load-balancing, revenue distribution).

Feature flags live in config.yaml (see config.py). `credits_enabled: false`
puts the portal in free mode: no HTTP 402 balance gate and no credit
deduction on /v1/chat/completions. The credit tables themselves are never
dropped, so the flag can be flipped back on without a migration.
"""
import hashlib
import json
import logging
import os
import secrets
import time
from contextlib import asynccontextmanager
from typing import List, Optional

import httpx
from fastapi import Depends, FastAPI, HTTPException, Header, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth import (generate_api_key, get_current_user, hash_api_key, hash_password,
    verify_password, revoke_tokens, parse_bearer_header, resolve_token, is_admin,
    issue_token, require_admin, API_KEY_TTL_DAYS, SESSION_TOKEN_TTL_HOURS)
from ratelimit import (limit_register, limit_login, limit_chat, client_ip, enforce, limit_node,
    LOGIN_GUARD, login_keys)
from database import SessionLocal, engine, get_db, init_db, DATA_DIR
from netinfo import DEFAULT_AGENT_PORT
from payments import APP_PUBLIC_URL
from models import (
    ApiKey,
    CreditTransaction,
    SystemSetting,
    GpuNode,
    NodeEarning,
    Payment,
    PoolJob,
    Usage,
    User,
    VALID_ROLES,
    ADMIN_ROLE,
    get_user_credits,
    _is_cloud_model_name,
)
from payments import router as payments_router
from frontend import router as frontend_router
from nodes import router as nodes_router
from pool import router as pool_router, distribute_revenue
from auth import require_admin
from admin import router as admin_router  # /admin/* — whoami, overview, users, nodes, usage
from config import credits_enabled
from ws import router as ws_router  # Phase 1: WebSocket outbound layer
from usage_stats import router as usage_stats_router  # /v1/me/usage

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://host.docker.internal:11434")
# When running on the host directly (not in Docker), default to localhost
if not os.path.exists("/.dockerenv") and os.environ.get("DOCKER_ENV") != "1":
    if OLLAMA_URL == "http://host.docker.internal:11434":
        OLLAMA_URL = "http://localhost:11434"

DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", "qwen2.5-coder:7b")
COST_PER_1K_TOKENS = float(os.environ.get("COST_PER_1K_TOKENS", "0.001"))  # 1 credit = 0.001 EUR-ish

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("gpu-pool")


# ----------------------------------------------------------------------------
# Lifespan: init DB on startup
# ----------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    _ensure_payments_table()
    _ensure_node_tables()
    _ensure_password_column()
    _ensure_user_settings()
    _ensure_system_settings()
    _ensure_registration_columns()
    _ensure_api_key_and_node_columns()
    _ensure_node_allowed_models()
    _ensure_node_ws_columns()
    _ensure_node_address_columns()
    await seed_test_user_if_empty()
    await seed_admin_if_configured()
    log.info(f"GPU-Pool POC started. Ollama URL: {OLLAMA_URL}, default model: {DEFAULT_MODEL}")
    yield


app = FastAPI(
    title="CoMesh Portal",
    description=(
        "CoMesh — a community GPU pool. Contribute GPUs and use the whole pool "
        "through one OpenAI-compatible API. Includes node registration, "
        "load-balancing, usage accounting, credits, and a role-gated admin "
        "console with an audit log."
    ),
    version="0.4.0",
    lifespan=lifespan,
)

# CORS — open for the POC. The existing frontend lives on :3000 (separate dev server).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount sub-routers
app.include_router(payments_router)
app.include_router(frontend_router)
app.include_router(nodes_router)
app.include_router(pool_router)
app.include_router(ws_router)  # Phase 1: WebSocket /agent/connect + /nodes/{id}/connection
# /admin/* — must come AFTER the app-level routes above so nothing shadows it; the
# POC create-user/topup handlers that used to live here were removed in favour of
# the authenticated, idempotent versions in admin.py.
app.include_router(admin_router)
app.include_router(usage_stats_router)  # /v1/me/usage — lost in the same merge; the frontend and its tests call it


# ----------------------------------------------------------------------------
# Schemas
# ----------------------------------------------------------------------------
class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: Optional[str] = None
    messages: List[ChatMessage]
    temperature: Optional[float] = 1.0
    max_tokens: Optional[int] = None
    stream: Optional[bool] = False


class ChatCompletionChoice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: str = "stop"


class UsageInfo(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    id: str = Field(default_factory=lambda: f"chatcmpl-{secrets.token_hex(12)}")
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[ChatCompletionChoice]
    usage: UsageInfo
    # Routing metadata (only when load-balanced)
    source: Optional[str] = None        # local | community | cloud
    node_id: Optional[int] = None


class CreateUserRequest(BaseModel):
    email: str
    name: str
    initial_credits: float = 100.0


class AdminSettingsUpdate(BaseModel):
    credits_enabled: bool

class AdminSettingsResponse(BaseModel):
    credits_enabled: bool

class AdminQuotaUpdate(BaseModel):
    quota_mode: str

class AdminQuotaResponse(BaseModel):
    user_id: int
    quota_mode: str

class CreateUserResponse(BaseModel):
    user_id: int
    email: str
    api_key: str  # Only shown once
    key_prefix: str
    credits: float


class UserInfo(BaseModel):
    id: int
    email: str
    name: str
    credits: float
    is_active: bool
    role: str = "both"
    allowed_models: Optional[List[str]] = None
    created_at: str
    # Feature flag (config.yaml: credits_enabled). False = unlimited usage:
    # the UI must not show balances, prices or top-up flows.
    credits_enabled: bool = True


class UpdateRoleRequest(BaseModel):
    role: str  # provider | consumer | both


class UpdateAllowedModelsRequest(BaseModel):
    """
    Persist the user's model whitelist.

    Semantics (intentionally explicit):
      - models=None and allow_cloud=False -> reset to default: all local, no cloud.
      - models=None and allow_cloud=True  -> not allowed via this endpoint; the caller
        should set models=[] and add specific cloud models. We accept it and treat
        it as 'all local' (cloud toggle is encoded by the presence of cloud models
        in the explicit list).
      - models=[] (empty list)            -> allow nothing.
      - models=[...] (list)               -> exact whitelist.
    """
    models: Optional[List[str]] = None
    allow_cloud: bool = False


class UserSettingsResponse(BaseModel):
    role: str
    allowed_models: Optional[List[str]] = None
    allow_cloud: bool = False
    warnings: List[str] = []


# ----------------------------------------------------------------------------
# DB migrations (idempotent ALTERs for the POC)
# ----------------------------------------------------------------------------
def _ensure_password_column():
    """Add users.password_hash column if it doesn't exist (idempotent)."""
    with engine.begin() as conn:
        cols = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(users)").fetchall()]
        if "password_hash" not in cols:
            conn.exec_driver_sql("ALTER TABLE users ADD COLUMN password_hash VARCHAR")
            log.info("Added users.password_hash column")


def _ensure_user_settings():
    """Add users.role and users.allowed_models columns if missing (idempotent)."""
    with engine.begin() as conn:
        cols = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(users)").fetchall()]
        if "role" not in cols:
            conn.exec_driver_sql("ALTER TABLE users ADD COLUMN role VARCHAR DEFAULT 'both' NOT NULL")
            log.info("Added users.role column (default 'both')")
        if "allowed_models" not in cols:
            conn.exec_driver_sql("ALTER TABLE users ADD COLUMN allowed_models TEXT")
            log.info("Added users.allowed_models column")
        if "quota_mode" not in cols:
            conn.exec_driver_sql("ALTER TABLE users ADD COLUMN quota_mode VARCHAR DEFAULT 'unlimited' NOT NULL")
            log.info("Added users.quota_mode column (default 'unlimited')")


def _ensure_system_settings():
    """Create the system_settings table if missing (idempotent) — DB-backed
    runtime settings editable by admins (e.g. the credits_enabled flag)."""
    from models import Base
    Base.metadata.create_all(bind=engine, tables=[SystemSetting.__table__])



def _ensure_api_key_and_node_columns():
    """Add api_keys.token_type/expires_at and gpu_nodes.api_key_hash if missing.

    These columns belong to the auth-hardening work (session tokens, hashed agent
    keys). They were added to models.py but never migrated into a live database,
    so every query touching ApiKey failed with "no such column" until the schema
    caught up. Idempotent, runs on every start.
    """
    with engine.begin() as conn:
        cols = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(api_keys)").fetchall()]
        if "token_type" not in cols:
            conn.exec_driver_sql(
                "ALTER TABLE api_keys ADD COLUMN token_type VARCHAR DEFAULT 'api_key' NOT NULL"
            )
            log.info("Added api_keys.token_type column (default 'api_key')")
        if "expires_at" not in cols:
            conn.exec_driver_sql("ALTER TABLE api_keys ADD COLUMN expires_at DATETIME")
            log.info("Added api_keys.expires_at column (NULL = never expires)")

        node_cols = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(gpu_nodes)").fetchall()]
        if node_cols and "api_key_hash" not in node_cols:
            conn.exec_driver_sql("ALTER TABLE gpu_nodes ADD COLUMN api_key_hash VARCHAR")
            log.info("Added gpu_nodes.api_key_hash column")


def _ensure_registration_columns():
    """Add registration_status and signup_credits columns if missing (idempotent)."""
    with engine.begin() as conn:
        cols = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(users)").fetchall()]
        if "registration_status" not in cols:
            conn.exec_driver_sql("ALTER TABLE users ADD COLUMN registration_status VARCHAR DEFAULT 'approved' NOT NULL")
            log.info("Added users.registration_status column (default 'approved')")
        if "signup_credits" not in cols:
            conn.exec_driver_sql("ALTER TABLE users ADD COLUMN signup_credits REAL DEFAULT 100.0 NOT NULL")
            log.info("Added users.signup_credits column (default 100.0)")


def _ensure_node_allowed_models():
    """Add gpu_nodes.allowed_models column if missing (idempotent)."""
    with engine.begin() as conn:
        cols = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(gpu_nodes)").fetchall()]
        if "allowed_models" not in cols:
            conn.exec_driver_sql("ALTER TABLE gpu_nodes ADD COLUMN allowed_models TEXT")
            log.info("Added gpu_nodes.allowed_models column")


def _ensure_node_ws_columns():
    """Add WebSocket-tracking columns to gpu_nodes (idempotent, Phase 1).

    Added columns:
      - connection_state: 'disconnected' | 'connecting' | 'connected'
      - last_ws_seen:     Unix timestamp of last WS ping (float, nullable)
      - ws_session_id:    UUID identifying the current WS connection
    """
    with engine.begin() as conn:
        cols = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(gpu_nodes)").fetchall()]
        if "connection_state" not in cols:
            conn.exec_driver_sql(
                "ALTER TABLE gpu_nodes ADD COLUMN connection_state VARCHAR DEFAULT 'disconnected' NOT NULL"
            )
            log.info("Added gpu_nodes.connection_state column (default 'disconnected')")
        if "last_ws_seen" not in cols:
            conn.exec_driver_sql("ALTER TABLE gpu_nodes ADD COLUMN last_ws_seen REAL")
            log.info("Added gpu_nodes.last_ws_seen column")
        if "ws_session_id" not in cols:
            conn.exec_driver_sql("ALTER TABLE gpu_nodes ADD COLUMN ws_session_id VARCHAR")
            log.info("Added gpu_nodes.ws_session_id column")


def _ensure_node_address_columns():
    """Add gpu_nodes.node_url / node_url_auto if missing (idempotent, LANA-89).

    `node_url` supersedes `tailscale_ip`: the pool no longer assumes a mesh VPN,
    so a node is addressed by whatever URL reaches it (DNS/mDNS name, LAN IP,
    tailnet name, reverse proxy). The legacy column stays in place — old rows
    keep working through the fallback in pool._forward_to_node.
    """
    with engine.begin() as conn:
        cols = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(gpu_nodes)").fetchall()]
        if "node_url" not in cols:
            conn.exec_driver_sql("ALTER TABLE gpu_nodes ADD COLUMN node_url VARCHAR")
            log.info("Added gpu_nodes.node_url column")
        if "node_url_auto" not in cols:
            conn.exec_driver_sql(
                "ALTER TABLE gpu_nodes ADD COLUMN node_url_auto BOOLEAN DEFAULT 0 NOT NULL"
            )
            log.info("Added gpu_nodes.node_url_auto column")


def _ensure_payments_table():
    """Create the payments table if it doesn't exist (idempotent)."""
    Payment.__table__.create(bind=engine, checkfirst=True)
    log.info("Payments table ready.")


def _ensure_node_tables():
    """Create the community-pool tables if they don't exist (idempotent)."""
    for model in (GpuNode, NodeEarning, PoolJob):
        try:
            model.__table__.create(bind=engine, checkfirst=True)
        except Exception as e:
            log.warning(f"Could not ensure table for {model.__name__}: {e}")
    log.info("Community pool tables ready.")


# ----------------------------------------------------------------------------
# Endpoints
# ----------------------------------------------------------------------------
NODE_AGENT_VERSION = "0.4.0"
VERSION = "0.4.0"


@app.get("/version")
def version_info():
    """Portal-, Vertrags- und Agent-Version an einer Stelle."""
    return {
        "product": "CoMesh",
        "portal_version": VERSION,
        "api_contract": "v1",
        "node_agent_version": NODE_AGENT_VERSION,
    }


@app.get("/health")
async def health():
    """Liveness + Ollama reachability + community-pool summary."""
    from nodes import _is_online
    ollama_ok = False
    ollama_error = None
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{OLLAMA_URL}/api/tags")
            ollama_ok = r.status_code == 200
    except Exception as e:
        ollama_error = str(e)

    # Pool summary
    db = SessionLocal()
    try:
        nodes = db.query(GpuNode).filter(GpuNode.is_enabled == True).all()
        online = [n for n in nodes if _is_online(n)]
        community_vram = sum(n.vram_gb for n in online)
    finally:
        db.close()

    return {
        "status": "ok",
        "ollama_reachable": ollama_ok,
        "ollama_error": ollama_error,
        "credits_enabled": credits_enabled(),
        "community": {
            "nodes_total": len(nodes) if 'nodes' in dir() else 0,
            "nodes_online": len(online) if 'online' in dir() else 0,
            "total_vram_gb": community_vram,
        },
    }


@app.get("/net/echo")
async def net_echo(request: Request):
    """Setup check (LANA-89): what the portal sees of the caller, and what it is.

    Open, unauthenticated, no side effects. `scripts/check_setup.sh` and the
    node-agent's `--check` use it to answer the two questions that decide whether
    a fresh DHCP installation can work at all:

      * which address/host does this portal believe it is reachable under?
      * what address does it derive for *this* caller?

    A node whose `advertise_host`/source address lands in `derived_node_url` is
    what the pool will dial — if that URL is not reachable from here, no
    heartbeat tuning will help.
    """
    import socket

    from netinfo import detect_outbound_ip, local_hostname, request_base_url, source_host

    peer = source_host(request)
    derived = None
    if peer and not peer.startswith(("10.", "172.", "192.168.", "169.254.", "127.")):
        try:
            from netinfo import derive_node_url
            derived = derive_node_url(peer, DEFAULT_AGENT_PORT,
                                      scheme=request.headers.get("x-forwarded-proto", "http"))
        except Exception:
            derived = None

    return {
        "portal": {
            "advertise_host": os.environ.get("ADVERTISE_HOST") or local_hostname(),
            "detected_ip": detect_outbound_ip(),
            "hostname": local_hostname(),
            "public_url": APP_PUBLIC_URL or request_base_url(request),
            "base_url_seen_by_caller": request_base_url(request),
        },
        "caller": {
            "peer_host": peer,
            "x_forwarded_for": request.headers.get("x-forwarded-for"),
            "x_real_ip": request.headers.get("x-real-ip"),
            "forwarded_proto": request.headers.get("x-forwarded-proto"),
        },
        "derived_node_url": derived,
        "hints": [
            "Clients and nodes must be able to reach each other directly for /v1/chat/completions.",
            "Use a DNS or mDNS name instead of an IP so a DHCP lease change cannot break the pool.",
            "A mesh VPN (e.g. Tailscale MagicDNS) works too — it is one option, not a requirement.",
        ],
        "socket": {"fqdn": socket.getfqdn(), "hostname": socket.gethostname()},
    }


@app.get("/v1/models")
async def list_models(_user: User = Depends(get_current_user)):
    """List models from Ollama (auth required)."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{OLLAMA_URL}/api/tags")
            r.raise_for_status()
            return r.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Upstream Ollama error: {e}")


@app.get("/v1/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Current user info + credit balance (+ the credits feature flag)."""
    return UserInfo(
        id=user.id,
        email=user.email,
        name=user.name,
        credits=get_user_credits(db, user.id),
        is_active=user.is_active,
        role=getattr(user, "role", "both") or "both",
        allowed_models=user.get_allowed_models(),
        created_at=user.created_at.isoformat(),
        credits_enabled=credits_enabled(),
    )


@app.put("/v1/me/role", response_model=UserSettingsResponse)
def update_my_role(
    req: UpdateRoleRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change the caller's role. Adds a warning if downgrading to consumer while still owning nodes."""
    if req.role not in VALID_ROLES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid role. Must be one of: {', '.join(VALID_ROLES)}",
        )
    warnings: List[str] = []
    if req.role == "consumer":
        owned = db.query(GpuNode).filter(GpuNode.owner_id == user.id).count()
        if owned > 0:
            warnings.append(
                f"Du hast noch {owned} registrierte Node(s) — diese werden nicht mehr für andere User verfügbar sein, solange deine Rolle 'consumer' ist."
            )

    # RiegelAdminRolle: ein Admin, der sein Profil speichert, darf sich nicht
    # selbst degradieren. Rollen werden fuer Admins ausschliesslich ueber
    # /admin/users verwaltet (siehe admin.py).
    if getattr(user, "role", "") == ADMIN_ROLE:
        raise HTTPException(
            status_code=409,
            detail="Die Admin-Rolle wird von der Administration verwaltet (/admin/users) "
                   "und kann hier nicht geaendert werden.",
        )
    user.role = req.role
    db.commit()
    db.refresh(user)
    log.info(f"User {user.email} changed role -> {req.role}")
    return UserSettingsResponse(
        role=user.role,
        allowed_models=user.get_allowed_models(),
        allow_cloud=user.allow_cloud,
        warnings=warnings,
    )


@app.put("/v1/me/allowed-models", response_model=UserSettingsResponse)
def update_my_allowed_models(
    req: UpdateAllowedModelsRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Persist the caller's model whitelist.

    Rules:
      - If `models` is None, we reset to the safe default (no whitelist, no cloud).
      - If `allow_cloud` is True AND `models` is None, we accept it but set
        `models = []` (caller didn't pick anything) — the user must explicitly
        list at least the cloud model they want. We don't auto-fill all cloud
        models because that would defeat the purpose of the toggle.
      - Cloud models in `models` are kept as-is (the user explicitly opted in).
    """
    warnings: List[str] = []
    if req.models is None:
        if req.allow_cloud:
            warnings.append(
                "Cloud-Modelle wurden freigeschaltet, aber du hast keine Modelle ausgewählt. "
                "Wähle unten mindestens ein Cloud-Modell aus der Liste."
            )
            user.set_allowed_models([])  # explicit empty
        else:
            user.set_allowed_models(None)  # default
    else:
        # Caller provided an explicit list. If allow_cloud is False but the list
        # contains cloud models, drop them and warn.
        if not req.allow_cloud:
            kept = [m for m in req.models if not _is_cloud_model_name(m)]
            dropped = [m for m in req.models if _is_cloud_model_name(m) and m not in kept]
            if dropped:
                warnings.append(
                    f"Cloud-Modelle {dropped} wurden entfernt, weil 'Cloud erlauben' nicht aktiv ist."
                )
            user.set_allowed_models(kept)
        else:
            user.set_allowed_models(req.models)
    db.commit()
    db.refresh(user)
    return UserSettingsResponse(
        role=user.role,
        allowed_models=user.get_allowed_models(),
        allow_cloud=user.allow_cloud,
        warnings=warnings,
    )


@app.get("/v1/available-models")
async def list_available_models(_user: User = Depends(get_current_user)):
    """
    Classified list of models available in the local Ollama instance.

    The frontend uses this to render the model multi-select on the
    registration and profile pages. Cloud classification is a
    name-based heuristic (any model whose name contains 'cloud').

    On upstream failure we return an empty list rather than 500-ing
    — the UI should still be usable for picking from a hardcoded
    fallback list.
    """
    import httpx
    out: List[dict] = []
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{OLLAMA_URL}/api/tags")
            r.raise_for_status()
            data = r.json()
        for m in (data.get("models") or []):
            name = m.get("name") or m.get("model") or ""
            size_bytes = int(m.get("size") or 0)
            size_gb = round(size_bytes / (1024 ** 3), 2)
            is_cloud = _is_cloud_model_name(name)
            out.append({
                "name": name,
                "size_gb": size_gb,
                "is_cloud": is_cloud,
                "is_local": not is_cloud,
            })
    except Exception as e:
        log.warning(f"/v1/available-models: upstream error: {e}")
    # Always include a hardcoded fallback so the UI is never empty.
    if not out:
        out = [
            {"name": "qwen2.5-coder:7b", "size_gb": 4.5, "is_cloud": False, "is_local": True},
            {"name": "llama3.1:8b", "size_gb": 4.9, "is_cloud": False, "is_local": True},
        ]
    return {"models": out}


# ---------------------------------------------------------------------------
# SSE (Phase 4) — /v1/chat/completions mit stream=true
#
# Ohne Streaming ist eine lange Antwort ein einziger HTTP-Request; ein
# Cloudflare-Tunnel kappt den bei rund 100 s mit 524. Mit SSE fliessen sofort
# Bytes und die Kappung greift nicht. Der Delta-Kanal (`on_delta`) existierte
# bereits fuer /ws/chat — hier wird er auf SSE abgebildet.
# ---------------------------------------------------------------------------
def _sse_pack(obj: dict) -> str:
    return "data: " + json.dumps(obj, ensure_ascii=False) + "\n\n"


def _sse_chunk(model: str, delta: str = "", finish=None, role=None) -> str:
    d = {}
    if role:
        d["role"] = role
    if delta:
        d["content"] = delta
    return _sse_pack({
        "id": f"chatcmpl-sse-{int(time.time() * 1000)}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": d, "finish_reason": finish}],
    })


async def _stream_chat_completion(db, user, model, ollama_payload, balance, billing, t0, req_ip):
    """SSE-Generator: routet, streamt Deltas, bucht danach ab."""
    import asyncio as _asyncio

    from pool import route_request
    from fastapi.responses import StreamingResponse

    queue: "_asyncio.Queue[str]" = _asyncio.Queue()
    state: dict = {}

    async def on_delta(delta: str) -> None:
        await queue.put(delta)

    payload = dict(ollama_payload)
    payload["stream"] = True

    async def runner() -> None:
        try:
            state.update(await route_request(db, user, payload, model, on_delta=on_delta))
        except Exception as e:  # noqa: BLE001 - Fehler gehoert in den Stream
            log.exception("stream routing failed")
            state.update({"ok": False, "error": str(e), "source": "error", "node_id": None})

    async def gen():
        task = _asyncio.create_task(runner())
        yield _sse_chunk(model, role="assistant")
        try:
            while True:
                getter = _asyncio.create_task(queue.get())
                fertig, _ = await _asyncio.wait({getter, task}, return_when=_asyncio.FIRST_COMPLETED)
                if getter in fertig:
                    yield _sse_chunk(model, delta=getter.result())
                    continue
                getter.cancel()
                while not queue.empty():
                    yield _sse_chunk(model, delta=queue.get_nowait())
                break

            if not state.get("ok"):
                yield _sse_pack({"error": {"message": state.get("error") or "routing failed",
                                           "type": state.get("source") or "error"}})
                yield "data: [DONE]\n\n"
                return

            resp = state.get("response") or {}
            usage = resp.get("usage") or {}
            prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
            completion_tokens = int(usage.get("completion_tokens", 0) or 0)
            total_tokens = int(usage.get("total_tokens", prompt_tokens + completion_tokens) or 0)
            latency_ms = int((time.time() - t0) * 1000)

            # Abschluss-Rahmen mit Nutzung, wie OpenAI-Clients es erwarten
            abschluss = json.loads(_sse_chunk(model, finish="stop")[len("data: "):].strip())
            abschluss["usage"] = {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            }
            yield _sse_pack(abschluss)
            yield "data: [DONE]\n\n"

            # --- Buchhaltung wie im blockierenden Weg ---
            credits_used = round((total_tokens / 1000.0) * COST_PER_1K_TOKENS, 6)
            new_balance = round(balance - credits_used, 6)
            api_key = db.query(ApiKey).filter(ApiKey.user_id == user.id, ApiKey.is_active == True).first()  # noqa: E712
            db.add(Usage(
                user_id=user.id,
                api_key_id=api_key.id if api_key else None,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                credits_charged=credits_used,
            ))
            if billing:
                db.add(CreditTransaction(
                    user_id=user.id,
                    amount=-credits_used,
                    balance_after=new_balance,
                    reason=f"chat(sse): {model} ({total_tokens} tokens, src={state.get('source')})",
                ))
            pool_job = PoolJob(
                user_id=user.id,
                node_id=state.get("node_id"),
                model=model,
                source=state.get("source"),
                status="succeeded",
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                job_cost=credits_used,
                latency_ms=latency_ms,
                finished_at=__import__("datetime").datetime.utcnow(),
            )
            db.add(pool_job)
            db.flush()
            if state.get("source") == "community" and state.get("node_id"):
                node = db.query(GpuNode).filter(GpuNode.id == state["node_id"]).first()
                if node is not None:
                    distribute_revenue(db, node, credits_used, pool_job=pool_job)
            db.commit()
            log.info(
                f"User {user.email} -> {model} src={state.get('source')} node={state.get('node_id')} "
                f"| SSE in:{prompt_tokens} out:{completion_tokens} | {latency_ms}ms"
            )
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    body: ChatCompletionRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    OpenAI-compatible chat completions with community-pool load balancing.

    Routing:
      1. Try local Ollama.
      2. If local fails, pick the best community node and forward.
      3. If community is unavailable, return 503 (cloud overflow is stubbed).
    """
    from pool import route_request
    model = body.model or DEFAULT_MODEL
    limit_chat(user.id, client_ip(request))

    # Credits are behind a feature flag (config.yaml: credits_enabled).
    # When the flag is off the portal is free to use: no balance floor and no
    # HTTP 402. When it is on we keep the legacy behaviour.
    billing = credits_enabled(db) and (getattr(user, "quota_mode", "unlimited") or "unlimited") != "unlimited"
    quota = (getattr(user, "quota_mode", "unlimited") or "unlimited")
    if quota == "blocked":
        raise HTTPException(
            status_code=403,
            detail="Your account is blocked from using this pool by the administrator.",
        )
    balance = get_user_credits(db, user.id)
    if billing and balance < 0.01:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Insufficient credits. Current balance: {balance:.4f}",
        )

    ollama_payload = {
        "model": model,
        "messages": [m.model_dump() for m in body.messages],
        "stream": False,
        "options": {"temperature": body.temperature},
    }
    if body.max_tokens is not None:
        ollama_payload["options"]["num_predict"] = body.max_tokens

    t0 = time.time()

    # Phase 4: streamender Weg. Gleiche Pruefungen, nur andere Auslieferung.
    if body.stream:
        return await _stream_chat_completion(
            db, user, model, ollama_payload, balance, billing, t0, client_ip(request)
        )

    routed = await route_request(db, user, ollama_payload, model)
    latency_ms = int((time.time() - t0) * 1000)

    if not routed["ok"]:
        # Whitelist denial -> 403 with the helpful message
        if routed["source"] == "denied":
            raise HTTPException(status_code=403, detail=routed.get("error") or "Model not allowed")
        # No GPU available anywhere — surface a clean 503
        if routed["source"] == "cloud":
            raise HTTPException(
                status_code=503,
                detail="No GPU available: local Ollama is down and no community node is reachable. Cloud overflow not yet wired.",
            )
        raise HTTPException(status_code=502, detail=f"Routing failed: {routed.get('error')}")

    ollama_resp = routed["response"]  # already in OpenAI shape from pool.py
    msg_content = (ollama_resp.get("choices", [{}])[0].get("message", {}) or {}).get("content", "")
    usage = ollama_resp.get("usage", {}) or {}
    prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
    completion_tokens = int(usage.get("completion_tokens", 0) or 0)
    total_tokens = int(usage.get("total_tokens", prompt_tokens + completion_tokens) or 0)

    credits_used = round((total_tokens / 1000.0) * COST_PER_1K_TOKENS, 6)
    new_balance = round(balance - credits_used, 6)

    api_key = db.query(ApiKey).filter(ApiKey.user_id == user.id, ApiKey.is_active == True).first()
    db.add(Usage(
        user_id=user.id,
        api_key_id=api_key.id if api_key else None,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        credits_charged=credits_used,
    ))
    if billing:
        # Charge the request. With the flag off we deliberately skip this: no
        # balance floor means a deduction would just drive balances negative.
        # The Usage row above still records the token count.
        db.add(CreditTransaction(
            user_id=user.id,
            amount=-credits_used,
            balance_after=new_balance,
            reason=f"chat: {model} ({total_tokens} tokens, src={routed['source']})",
        ))

    # Pool job record + revenue distribution when running on a community node
    pool_job = PoolJob(
        user_id=user.id,
        node_id=routed.get("node_id"),
        model=model,
        source=routed["source"],
        status="succeeded",
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        job_cost=credits_used,
        latency_ms=latency_ms,
        finished_at=__import__("datetime").datetime.utcnow(),
    )
    db.add(pool_job)
    db.flush()  # so pool_job.id exists for the earning row

    if routed["source"] == "community" and routed.get("node_id"):
        node = db.query(GpuNode).filter(GpuNode.id == routed["node_id"]).first()
        if node is not None:
            distribute_revenue(db, node, credits_used, pool_job=pool_job)

    db.commit()

    cost_note = (f"-{credits_used} credits (balance: {new_balance:.4f})"
                 if billing else f"credits off (informational: {credits_used})")
    log.info(
        f"User {user.email} -> {model} src={routed['source']} "
        f"node={routed.get('node_id')} | in:{prompt_tokens} out:{completion_tokens} "
        f"| {cost_note} | {latency_ms}ms"
    )

    return ChatCompletionResponse(
        created=int(time.time()),
        model=model,
        choices=[ChatCompletionChoice(message=ChatMessage(role="assistant", content=msg_content))],
        usage=UsageInfo(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        ),
        source=routed["source"],
        node_id=routed.get("node_id"),
    )


# ----------------------------------------------------------------------------
# Admin user management moved to admin.py (router, prefix /admin, all routes
# behind require_admin + Idempotency-Key). The POC handlers that lived here were
# unauthenticated — anyone could create a user or mint credits. Do not reintroduce
# local /admin/* routes: app-level routes are matched before the router and would
# shadow the protected versions.
# ----------------------------------------------------------------------------


# ----------------------------------------------------------------------------
# Global runtime settings (admin-only) — credits_enabled and friends
# ----------------------------------------------------------------------------


# ----------------------------------------------------------------------------
# Public auth: register + login (POC). Login = "I own this API key" proof.
# Production: replace with proper password hashing (bcrypt/argon2) + JWT.
# ----------------------------------------------------------------------------
MIN_PASSWORD_LENGTH = 8


def _hash_pw(pw: str) -> str:
    # Back-compat shim: new code should use auth.hash_password.
    return hash_password(pw)


class RegisterRequest(BaseModel):
    email: str
    name: str
    password: str
    role: str = "both"
    allowed_models: Optional[List[str]] = None
    allow_cloud: bool = False
    initial_credits: float = 100.0


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    user_id: int
    email: str
    name: str
    role: str = "both"
    allowed_models: Optional[List[str]] = None
    api_key: str
    key_prefix: str
    credits: float
    credits_enabled: bool = True
    registration_status: str = "approved"
    status: Optional[str] = None
    token_type: str = "api_key"
    expires_at: Optional[str] = None
    expires_in: Optional[int] = None



@app.put("/admin/settings", response_model=AdminSettingsResponse)
def admin_update_settings(body: AdminSettingsUpdate, db: Session = Depends(get_db), user = Depends(require_admin)):
    """Global runtime settings (admin-only). Currently: credits_enabled."""
    row = db.query(SystemSetting).filter(SystemSetting.key == "credits_enabled").first()
    if row is None:
        row = SystemSetting(key="credits_enabled", value="true" if body.credits_enabled else "false")
        db.add(row)
    else:
        row.value = "true" if body.credits_enabled else "false"
        row.updated_at = __import__("datetime").datetime.utcnow()
    db.commit()
    return AdminSettingsResponse(credits_enabled=credits_enabled(db))


@app.get("/admin/settings", response_model=AdminSettingsResponse)
def admin_get_settings(db: Session = Depends(get_db), user = Depends(require_admin)):
    return AdminSettingsResponse(credits_enabled=credits_enabled(db))


@app.patch("/admin/users/{user_id}/quota", response_model=AdminQuotaResponse)
def admin_set_user_quota(user_id: int, body: AdminQuotaUpdate, db: Session = Depends(get_db), user = Depends(require_admin)):
    """Set a user's quota mode when credits are enabled: unlimited | balance | blocked."""
    mode = (body.quota_mode or "").strip().lower()
    if mode not in ("unlimited", "balance", "blocked"):
        raise HTTPException(status_code=422, detail="quota_mode must be unlimited | balance | blocked")
    target = db.query(User).filter(User.id == user_id).first()
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    target.quota_mode = mode
    target.updated_at = __import__("datetime").datetime.utcnow()
    db.commit()
    return AdminQuotaResponse(user_id=target.id, quota_mode=target.quota_mode)


def _auth_response(user, raw_token, key_prefix, credits,
                    *, token_type: str, expires_at=None) -> AuthResponse:
    return AuthResponse(
        user_id=user.id,
        email=user.email,
        name=user.name,
        role=getattr(user, "role", "both") or "both",
        allowed_models=user.get_allowed_models(),
        api_key=raw_token,
        key_prefix=key_prefix,
        credits=credits,
        token_type=token_type,
        expires_at=expires_at.isoformat() if expires_at else None,
        expires_in=(int((expires_at - __import__("datetime").datetime.utcnow()).total_seconds()) if expires_at else None),
    )


@app.post("/auth/register", response_model=AuthResponse)
def auth_register(req: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    limit_register(client_ip(request))

    email = (req.email or "").strip().lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="Email already registered")
    if len(req.password or "") < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters.",
        )

    allowed_models_value = None
    role = req.role if req.role in VALID_ROLES else "both"
    if req.allowed_models is not None:
        if req.allow_cloud:
            allowed_models_value = list(req.allowed_models)
        else:
            allowed_models_value = [m for m in req.allowed_models if not _is_cloud_model_name(m)]
    elif req.allow_cloud:
        allowed_models_value = []

    user = User(
        email=email,
        name=req.name,
        is_active=True,
        registration_status="approved",
        password_hash=hash_password(req.password),
        role=role,
        signup_credits=req.initial_credits,
    )
    db.add(user)
    db.flush()
    if allowed_models_value is not None:
        user.set_allowed_models(allowed_models_value)
    from datetime import datetime as _dt, timedelta as _td
    db.add(CreditTransaction(
        user_id=user.id,
        amount=req.initial_credits,
        balance_after=req.initial_credits,
        reason="signup credit",
    ))
    raw_key, key_hash, key_prefix = issue_token(
        db, user, token_type="api_key", ttl_days=API_KEY_TTL_DAYS, label="default"
    )
    db.commit()
    db.refresh(user)

    expires = (_dt.utcnow() + _td(days=API_KEY_TTL_DAYS)) if API_KEY_TTL_DAYS > 0 else None
    return _auth_response(user, raw_key, key_prefix, req.initial_credits,
                          token_type="api_key", expires_at=expires)


@app.post("/auth/login", response_model=AuthResponse)
def auth_login(req: LoginRequest, request: Request, db: Session = Depends(get_db)):
    limit_login(client_ip(request), (req.email or "").strip().lower())

    email = (req.email or "").strip().lower()
    user = db.query(User).filter(User.email == email).first()

    # Empty-ish record for timing protection even when user unknown.
    if not user:
        verify_password_dummy(req.password or "")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    ok, needs_upgrade = verify_password(req.password or "", user.password_hash)
    if not ok:
        LOGIN_GUARD.record_failure(*login_keys(client_ip(request), email))
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if getattr(user, "registration_status", "approved") != "approved" or not getattr(user, "is_active", True):
        raise HTTPException(status_code=403, detail="Registration pending manual approval")

    # Brute-force guard: per account + per IP.
    guard_keys = login_keys(client_ip(request), email)
    LOGIN_GUARD.check(*guard_keys)

    # Consume failures? record success clears.
    LOGIN_GUARD.record_success(*guard_keys)

    if needs_upgrade:
        user.password_hash = hash_password(req.password or "")
        db.commit()

    # Rotate old sessions, issue a new session token.
    revoke_tokens(db, user, token_type="session")
    raw_key, key_hash, key_prefix = issue_token(
        db, user, token_type="session", ttl_hours=SESSION_TOKEN_TTL_HOURS, label="login"
    )
    # Rotate pointer stored separately? issue_token already creates row.
    db.commit()

    # unlock path? not needed.

    balance = get_user_credits(db, user.id)
    from datetime import datetime as _dt, timedelta as _td
    expires = _dt.utcnow() + _td(hours=SESSION_TOKEN_TTL_HOURS)
    return _auth_response(user, raw_key, key_prefix, balance,
                          token_type="session", expires_at=expires)


@app.post("/auth/logout")
def auth_logout(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    revoked = revoke_tokens(db, user, token_type="session")
    return {"revoked": revoked}


# ----------------------------------------------------------------------------
# Seed: test user on startup
# ----------------------------------------------------------------------------
async def seed_test_user_if_empty():
    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            user = User(email="test@example.com", name="Test User", is_active=True)
            db.add(user)
            db.flush()
            db.add(CreditTransaction(
                user_id=user.id,
                amount=100.0,
                balance_after=100.0,
                reason="initial credit (seed)",
            ))
            raw_key, key_hash, key_prefix = generate_api_key()
            user.password_hash = _hash_pw("password123")
            db.add(ApiKey(
                user_id=user.id,
                key_hash=key_hash,
                key_prefix=key_prefix,
                label="seed-test-key",
                is_active=True,
            ))
            db.commit()

            seed_path = os.environ.get("SEED_KEY_PATH", "/data/seed_api_key.txt")
            with open(seed_path, "w") as f:
                f.write(f"email: test@example.com\npassword: password123\nkey: {raw_key}\nkey_prefix: {key_prefix}\n")
            log.info(f"=== SEED USER CREATED ===\n  email: test@example.com\n  password: password123\n  api_key: {raw_key}\n  (also written to {seed_path})")
        else:
            log.info("DB already populated, skipping seed.")
            # Make sure the test user has a password set (idempotent)
            user = db.query(User).filter(User.email == "test@example.com").first()
            if user:
                if not user.password_hash:
                    user.password_hash = _hash_pw("password123")
                    db.commit()
                    log.info("Set password_hash=password123 for seed user")
    finally:
        db.close()


ADMIN_KEY_FILE = os.path.join(DATA_DIR, "admin_api_key.txt")
ADMIN_PW_FILE = os.path.join(DATA_DIR, "admin_password.txt")


def _load_or_create_secret(path: str, make, what: str) -> str:
    """Reuse the secret stored in `path`, else generate it there (mode 0600).

    Called at install time so a fresh deployment ends up with working admin
    credentials without anyone hand-crafting them. The file lives next to the
    database, so the secret survives restarts and the one you noted down keeps
    working. O_CREAT with mode in the same call: the value is never world-readable,
    not even briefly.
    """
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as fh:
                existing = fh.read().strip()
            if existing:
                log.info(f"Admin bootstrap: reusing the {what} in {path}")
                return existing

        value = make()
        os.makedirs(DATA_DIR, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(value + "\n")
        log.warning(
            f"Admin bootstrap: no {what} configured - generated one at install time, "
            f"stored in {path} (chmod 600)."
        )
        return value
    except Exception as exc:
        log.error(f"Admin bootstrap: cannot read/create {path}: {exc}")
        return ""


def _load_or_create_admin_key() -> str:
    """The admin API key: read the persisted one, else generate it."""
    return _load_or_create_secret(
        ADMIN_KEY_FILE, lambda: "gpu_admin_" + secrets.token_urlsafe(32), "API key"
    )


def _load_or_create_admin_password() -> str:
    """The admin account password — /auth/login only accepts email + password.

    Without this the generated admin could not sign in to the UI at all: it would
    hold an API key but no usable password. The file is the source of truth, so the
    documented credentials always work; treat it as the place to change them.
    """
    return _load_or_create_secret(
        ADMIN_PW_FILE, lambda: secrets.token_urlsafe(18), "admin password"
    )



async def seed_admin_if_configured():
    """Bootstrap the admin identity (see docs/api.md -> Admin-Bootstrap).

    Without this every /admin/* route answers 403 for everyone and the admin UI is
    unreachable no matter how correct it is.

      1. ADMIN_API_KEY set -> create/promote the admin account and install that key
         as its ONLY active key (the documented, recommended path).
      2. otherwise PROMOTE_ADMIN_EMAIL -> promote that existing account. Off by
         default on purpose: a deployment must not silently grant admin to a
         seeded/POC account.
      3. neither of the two -> generate the key at install time and persist it
         (see _load_or_create_admin_key), so a fresh install has a working admin
         console without anyone hand-crafting a secret.
    """
    admin_key = (os.environ.get("ADMIN_API_KEY") or "").strip()
    promote_email = (os.environ.get("PROMOTE_ADMIN_EMAIL") or "").strip().lower()
    if not admin_key and not promote_email:
        admin_key = _load_or_create_admin_key()
        if not admin_key:
            log.info("Admin bootstrap: no key available - /admin/* stays unreachable.")
            return

    email = (os.environ.get("ADMIN_EMAIL") or "admin@gpu-pool.local").strip().lower()
    name = (os.environ.get("ADMIN_NAME") or "Platform Admin").strip()

    db = SessionLocal()
    try:
        if admin_key:
            admin_password = _load_or_create_admin_password()
            user = db.query(User).filter(User.email == email).first()
            if user is None:
                user = User(email=email, name=name, role=ADMIN_ROLE, is_active=True)
                user.password_hash = _hash_pw(admin_password) if admin_password else None
                db.add(user)
                db.flush()
                log.info(f"Admin bootstrap: created {email}")
            else:
                user.role = ADMIN_ROLE
                user.is_active = True
                if admin_password:
                    # The password file is the source of truth for /auth/login, not
                    # whatever a previous start happened to leave in the column.
                    user.password_hash = _hash_pw(admin_password)
                log.info(f"Admin bootstrap: promoted existing {email} to admin")

            key_hash = hash_api_key(admin_key)
            # That key is the admin's only active key: rotate any other away.
            for other in (
                db.query(ApiKey)
                .filter(ApiKey.user_id == user.id, ApiKey.is_active == True)  # noqa: E712
                .all()
            ):
                if other.key_hash != key_hash:
                    other.is_active = False

            existing = db.query(ApiKey).filter(ApiKey.key_hash == key_hash).first()
            if existing is None:
                db.add(ApiKey(
                    user_id=user.id,
                    key_hash=key_hash,
                    key_prefix=admin_key[:12],
                    label="admin-bootstrap",
                    is_active=True,
                ))
            else:
                existing.user_id = user.id
                existing.is_active = True
                existing.label = "admin-bootstrap"
            db.commit()
            log.info(f"Admin bootstrap: key installed for {email}")

        elif promote_email:
            user = db.query(User).filter(User.email == promote_email).first()
            if user is None:
                log.warning(
                    f"PROMOTE_ADMIN_EMAIL={promote_email} matches no user - nothing promoted."
                )
            elif user.role != ADMIN_ROLE:
                user.role = ADMIN_ROLE
                db.commit()
                log.warning(
                    f"Admin bootstrap: promoted EXISTING account {promote_email} to admin "
                    "via PROMOTE_ADMIN_EMAIL"
                )
    except Exception as e:  # a broken bootstrap must not take the portal down
        db.rollback()
        log.error(f"Admin bootstrap failed: {e}")
    finally:
        db.close()
