"""
GPU-Sharing POC - FastAPI backend.

OpenAI-compatible /v1/chat/completions that proxies to:
  1. Local Ollama (ai-lanlibbi itself) - default path
  2. Community pool nodes - picked by pool.find_best_node()
  3. Cloud overflow (RunPod/Vast) - stub for now

Includes user management, API key issuance, credit accounting,
payments (Stripe, PayPal, Alipay, Apple Pay - all in test/mock mode
for the POC), and Community GPU-Pool (node registration, heartbeat,
load-balancing, revenue distribution).
"""
import hashlib
import logging
import os
import secrets
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import List, Optional

import httpx
from fastapi import Depends, FastAPI, HTTPException, Header, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth import (
    SESSION_TOKEN_TTL_HOURS,
    API_KEY_TTL_DAYS,
    generate_api_key,
    get_current_user,
    hash_password,
    issue_token,
    require_admin,
    upgrade_password_if_needed,
    verify_password,
    verify_password_dummy,
)
from ratelimit import (
    LOGIN_GUARD,
    client_ip,
    limit_admin,
    limit_chat,
    limit_login,
    limit_register,
    login_keys,
)
from database import SessionLocal, engine, get_db, init_db
from models import (
    ApiKey,
    CreditTransaction,
    GpuNode,
    NodeEarning,
    Payment,
    PoolJob,
    Usage,
    User,
    VALID_ROLES,
    get_user_credits,
    _is_cloud_model_name,
)
from payments import router as payments_router
from frontend import router as frontend_router
from nodes import router as nodes_router
from pool import router as pool_router, distribute_revenue
from ws import router as ws_router  # Phase 1: WebSocket outbound layer

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

# --- Auth hardening ---------------------------------------------------------
# Minimum accepted password length at register (login is unaffected).
MIN_PASSWORD_LENGTH = int(os.environ.get("MIN_PASSWORD_LENGTH", "8") or 8)
# The seed account only exists to make a fresh DB usable. It is created with a
# random password unless the operator pins one via SEED_PASSWORD.
SEED_PASSWORD = os.environ.get("SEED_PASSWORD") or ""
DEFAULT_SEED_PASSWORD = "password123"  # only used when SEED_PASSWORD is unset


def _seed_password() -> str:
    """Password for the seed test account (deterministic in the POC)."""
    return SEED_PASSWORD or DEFAULT_SEED_PASSWORD

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
    _ensure_node_allowed_models()
    _ensure_node_ws_columns()
    _ensure_token_columns()
    _ensure_node_key_hash_column()
    await seed_test_user_if_empty()
    log.info(f"GPU-Pool POC started. Ollama URL: {OLLAMA_URL}, default model: {DEFAULT_MODEL}")
    yield


app = FastAPI(
    title="GPU-Pool POC",
    description=(
        "GPU-Sharing Platform POC - OpenAI-compatible API on top of Ollama. "
        "Includes payments, community GPU-pool (node registration, "
        "load-balancing, revenue distribution)."
    ),
    version="0.3.0",
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


def _ensure_token_columns():
    """Add api_keys.token_type/expires_at columns (idempotent, auth hardening).

    Existing rows get token_type='api_key' (the POC issued only long-lived
    keys) and expires_at=NULL (never expires) - so pre-existing keys keep
    working after the upgrade.
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


def _ensure_node_key_hash_column():
    """Add gpu_nodes.api_key_hash and backfill it from the legacy plaintext key.

    The backfill means existing node-agents survive the upgrade: their raw key
    keeps working (verified against the new hash), while `api_key` can be
    cleared by rotating the key.
    """
    with engine.begin() as conn:
        cols = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(gpu_nodes)").fetchall()]
        if "api_key_hash" not in cols:
            conn.exec_driver_sql("ALTER TABLE gpu_nodes ADD COLUMN api_key_hash VARCHAR")
            log.info("Added gpu_nodes.api_key_hash column")
    # Backfill outside the DDL transaction (idempotent: only NULL hashes).
    db = SessionLocal()
    try:
        rows = db.query(GpuNode).filter(GpuNode.api_key_hash.is_(None), GpuNode.api_key.isnot(None)).all()
        for node in rows:
            node.api_key_hash = hashlib.sha256(node.api_key.encode("utf-8")).hexdigest()
        if rows:
            db.commit()
            log.info(f"Backfilled api_key_hash for {len(rows)} existing node(s)")
    except Exception as e:
        log.warning(f"could not backfill node key hashes: {e}")
        db.rollback()
    finally:
        db.close()


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
        "community": {
            "nodes_total": len(nodes) if 'nodes' in dir() else 0,
            "nodes_online": len(online) if 'online' in dir() else 0,
            "total_vram_gb": community_vram,
        },
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
    """Current user info + credit balance."""
    return UserInfo(
        id=user.id,
        email=user.email,
        name=user.name,
        credits=get_user_credits(db, user.id),
        is_active=user.is_active,
        role=getattr(user, "role", "both") or "both",
        allowed_models=user.get_allowed_models(),
        created_at=user.created_at.isoformat(),
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


@app.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    http_request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    OpenAI-compatible chat completions with community-pool load balancing.

    Routing:
      1. Try local Ollama.
      2. If local fails, pick the best community node and forward.
      3. If community is unavailable, return 503 (cloud overflow is stubbed).

    Rate limiting (429 + Retry-After, after authentication so it is per user):
      * per user:   RATE_LIMIT_CHAT_PER_MIN / RATE_LIMIT_CHAT_BURST
      * per client IP (secondary guard against one noisy host)
    The response body stays in OpenAI shape; a 429 surfaces as a normal HTTP
    error, which OpenAI-compatible clients already handle.
    """
    limit_chat(user.id, client_ip(http_request))

    from pool import route_request
    model = request.model or DEFAULT_MODEL

    balance = get_user_credits(db, user.id)
    if balance < 0.01:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Insufficient credits. Current balance: {balance:.4f}",
        )

    ollama_payload = {
        "model": model,
        "messages": [m.model_dump() for m in request.messages],
        "stream": False,
        "options": {"temperature": request.temperature},
    }
    if request.max_tokens is not None:
        ollama_payload["options"]["num_predict"] = request.max_tokens

    t0 = time.time()
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

    log.info(
        f"User {user.email} -> {model} src={routed['source']} "
        f"node={routed.get('node_id')} | in:{prompt_tokens} out:{completion_tokens} "
        f"| -{credits_used} credits (balance: {new_balance:.4f}) | {latency_ms}ms"
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
# Admin: create users (admin-authenticated; see auth.require_admin)
# ----------------------------------------------------------------------------
@app.post("/admin/users", response_model=CreateUserResponse)
def create_user(
    req: CreateUserRequest,
    request: Request,
    _admin: Optional[User] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Create a user + API key.

    Hardened: was previously unauthenticated. Now requires the operator token
    (ADMIN_TOKEN) or an admin account (ADMIN_EMAILS / role=admin). Default-deny
    when neither is configured.
    """
    limit_admin(client_ip(request))
    if db.query(User).filter(User.email == req.email).first():
        raise HTTPException(status_code=409, detail="User with that email already exists")

    user = User(email=req.email, name=req.name, is_active=True)
    db.add(user)
    db.flush()
    db.add(CreditTransaction(
        user_id=user.id,
        amount=req.initial_credits,
        balance_after=req.initial_credits,
        reason="initial credit",
    ))
    raw_key, key_hash, key_prefix = issue_token(
        db, user, token_type="api_key", ttl_days=API_KEY_TTL_DAYS, label="default"
    )
    db.commit()

    log.info(f"Created user {user.email} (id={user.id}) with {req.initial_credits} credits")
    return CreateUserResponse(
        user_id=user.id,
        email=user.email,
        api_key=raw_key,
        key_prefix=key_prefix,
        credits=req.initial_credits,
    )


@app.post("/admin/users/{user_id}/topup")
def topup_user(
    user_id: int,
    amount: float,
    request: Request,
    _admin: Optional[User] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Add credits to a user. Hardened: admin authentication required."""
    limit_admin(client_ip(request))
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    current = get_user_credits(db, user.id)
    new_balance = round(current + amount, 6)
    db.add(CreditTransaction(
        user_id=user.id,
        amount=amount,
        balance_after=new_balance,
        reason="manual topup",
    ))
    db.commit()
    return {"user_id": user.id, "credits": new_balance, "added": amount}


# ----------------------------------------------------------------------------
# Public auth: register + login.
#
# Token model (hardened — see auth.py for the full rationale):
#   register -> long-lived API key  ("gpu_...", no expiry by default)
#   login    -> short-lived session ("sess_...", expires after
#               SESSION_TOKEN_TTL_HOURS; a new login rotates old sessions)
#   both     -> presented as `Authorization: Bearer <token>` (unchanged contract)
#
# Passwords are PBKDF2-HMAC-SHA256 with a per-user salt. The helper below is
# kept only for legacy-hash compatibility tests.
# ----------------------------------------------------------------------------
def _hash_pw(pw: str) -> str:
    """Legacy POC password hash (unsalted sha256). Do not use for new records."""
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()


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
    # Auth-hardening additions (additive: existing clients ignore them)
    token_type: str = "api_key"          # api_key | session
    expires_at: Optional[str] = None     # ISO-8601, None = does not expire
    expires_in: Optional[int] = None     # seconds until expiry, None = never


def _auth_response(user: User, raw_token: str, key_prefix: str, credits: float,
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
        expires_in=(int((expires_at - datetime.utcnow()).total_seconds()) if expires_at else None),
    )


@app.post("/auth/register", response_model=AuthResponse)
def auth_register(req: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    """Public signup.

    Hardening: per-IP rate limit (RATE_LIMIT_REGISTER_*), PBKDF2 password
    hashing, response shape unchanged apart from additive token metadata.
    """
    limit_register(client_ip(request))

    email = (req.email or "").strip().lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="Email already registered")
    if len(req.password or "") < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters.",
        )

    # Build the user (with optional role + allowed_models).
    allowed_models_value: Optional[List[str]] = None
    role = req.role if req.role in VALID_ROLES else "both"
    if req.allowed_models is not None:
        # Same cloud-stripping logic as PUT /v1/me/allowed-models.
        if req.allow_cloud:
            allowed_models_value = list(req.allowed_models)
        else:
            allowed_models_value = [m for m in req.allowed_models if not _is_cloud_model_name(m)]
    elif req.allow_cloud:
        # allow_cloud=True but no explicit list -> empty list (must pick at least one).
        allowed_models_value = []

    user = User(
        email=email,
        name=req.name,
        is_active=True,
        password_hash=hash_password(req.password),
        role=role,
    )
    db.add(user)
    db.flush()
    if allowed_models_value is not None:
        user.set_allowed_models(allowed_models_value)
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

    log.info(f"Public register: {user.email} (id={user.id}) with {req.initial_credits} credits")
    return _auth_response(
        user, raw_key, key_prefix, req.initial_credits,
        token_type="api_key", expires_at=(datetime.utcnow() + timedelta(days=API_KEY_TTL_DAYS)) if API_KEY_TTL_DAYS > 0 else None,
    )


@app.post("/auth/login", response_model=AuthResponse)
def auth_login(req: LoginRequest, request: Request, db: Session = Depends(get_db)):
    """Public login: exchanges email+password for a short-lived session token.

    Hardening:
      * per-IP and per-account rate limit (RATE_LIMIT_LOGIN_*)
      * brute-force lockout with exponential backoff (LOGIN_GUARD)
      * constant-time password verification, PBKDF2 with per-user salt
      * dummy hash when the account does not exist (no user enumeration)
      * issues a "sess_..." token with TTL (SESSION_TOKEN_TTL_HOURS), not an
        unlimited key; the client contract (Authorization: Bearer) is unchanged
      * failures are logged for the audit trail
    """
    ip = client_ip(request)
    email = (req.email or "").strip().lower()
    ip_key, email_key = login_keys(ip, email)

    limit_login(ip, email)      # token bucket: 10/min, burst 5
    LOGIN_GUARD.check(ip_key, email_key)  # lockout from previous failures

    user = db.query(User).filter(User.email == email).first()
    if not user:
        # Burn comparable CPU so timing does not leak account existence.
        verify_password_dummy(req.password)
        LOGIN_GUARD.record_failure(ip_key, email_key)
        log.warning(f"login failed: unknown account email={email} ip={ip}")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    ok, needs_upgrade = verify_password(req.password, user.password_hash)
    if not ok or not user.is_active:
        LOGIN_GUARD.record_failure(ip_key, email_key)
        log.warning(
            f"login failed: user_id={user.id} email={email} ip={ip} "
            f"active={user.is_active} reason={'inactive' if not user.is_active else 'bad password'}"
        )
        raise HTTPException(status_code=401, detail="Invalid credentials")

    LOGIN_GUARD.record_success(ip_key, email_key)
    if needs_upgrade:
        # Legacy POC sha256 hash - re-hash on the way in (idempotent migration).
        upgrade_password_if_needed(db, user, req.password, needs_upgrade)

    ttl_hours = SESSION_TOKEN_TTL_HOURS
    raw_token, key_hash, key_prefix = issue_token(
        db, user,
        token_type="session",
        ttl_hours=ttl_hours,
        label="login-issued",
        rotate=True,  # a login invalidates the user's previous session tokens
    )
    db.commit()

    balance = get_user_credits(db, user.id)
    expires_at = datetime.utcnow() + timedelta(hours=ttl_hours) if ttl_hours > 0 else None
    log.info(f"login ok: user_id={user.id} email={email} ip={ip} session_ttl_h={ttl_hours}")
    return _auth_response(user, raw_token, key_prefix, balance,
                          token_type="session", expires_at=expires_at)


@app.post("/auth/logout")
def auth_logout(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Revoke the caller's session tokens (all of them, not just this one).

    Additive endpoint: nothing existing depends on it, and it gives clients a
    real way to end a session now that login tokens expire and are revocable.
    """
    from auth import revoke_tokens
    revoked = revoke_tokens(db, user, token_type="session")
    db.commit()
    log.info(f"logout: user_id={user.id} revoked_sessions={revoked}")
    return {"ok": True, "revoked": revoked}


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
            user.password_hash = hash_password(_seed_password())
            db.add(ApiKey(
                user_id=user.id,
                key_hash=key_hash,
                key_prefix=key_prefix,
                label="seed-test-key",
                token_type="api_key",
                expires_at=None,
                is_active=True,
            ))
            db.commit()

            # Never log the seeded credential: write it to a 0600 file the
            # operator can read, and keep the log line free of secrets.
            seed_path = os.environ.get("SEED_KEY_PATH", "/data/seed_api_key.txt")
            try:
                fd = os.open(seed_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(fd, "w") as f:
                    f.write(
                        f"email: test@example.com\n"
                        f"password: {_seed_password()}\n"
                        f"key: {raw_key}\n"
                        f"key_prefix: {key_prefix}\n"
                    )
            except Exception as e:
                log.warning(f"could not write seed credentials to {seed_path}: {e}")
            log.info(
                f"=== SEED USER CREATED === email=test@example.com "
                f"key_prefix={key_prefix} credentials written to {seed_path} (mode 0600). "
                f"Rotate or delete this account before any public deployment."
            )
        else:
            log.info("DB already populated, skipping seed.")
    finally:
        db.close()
