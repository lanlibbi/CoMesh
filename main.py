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

Feature flags live in config.yaml (see config.py). `credits_enabled: false`
puts the portal in free mode: no HTTP 402 balance gate and no credit
deduction on /v1/chat/completions. The credit tables themselves are never
dropped, so the flag can be flipped back on without a migration.
"""
import hashlib
import logging
import os
import secrets
import time
from contextlib import asynccontextmanager
from typing import List, Optional

import httpx
from fastapi import Depends, FastAPI, HTTPException, Header, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth import generate_api_key, get_current_user
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
from config import credits_enabled
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
        "credits_enabled": credits_enabled(),
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
    model = request.model or DEFAULT_MODEL

    # Credits are behind a feature flag (config.yaml: credits_enabled).
    # When the flag is off the portal is free to use: no balance floor and no
    # HTTP 402. When it is on we keep the legacy behaviour.
    billing = credits_enabled()
    balance = get_user_credits(db, user.id)
    if billing and balance < 0.01:
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
# Admin: create users (POC - in production this would be behind admin auth)
# ----------------------------------------------------------------------------
@app.post("/admin/users", response_model=CreateUserResponse)
def create_user(req: CreateUserRequest, db: Session = Depends(get_db)):
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
    raw_key, key_hash, key_prefix = generate_api_key()
    db.add(ApiKey(
        user_id=user.id,
        key_hash=key_hash,
        key_prefix=key_prefix,
        label="default",
        is_active=True,
    ))
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
def topup_user(user_id: int, amount: float, db: Session = Depends(get_db)):
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
# Public auth: register + login (POC). Login = "I own this API key" proof.
# Production: replace with proper password hashing (bcrypt/argon2) + JWT.
# ----------------------------------------------------------------------------
def _hash_pw(pw: str) -> str:
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
    credits_enabled: bool = True


@app.post("/auth/register", response_model=AuthResponse)
def auth_register(req: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == req.email).first():
        raise HTTPException(status_code=409, detail="Email already registered")

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
        email=req.email,
        name=req.name,
        is_active=True,
        password_hash=_hash_pw(req.password),
        role=role,
    )
    db.add(user)
    db.flush()
    if allowed_models_value is not None:
        user.set_allowed_models(allowed_models_value)
    if credits_enabled():
        # Signup grants stay tied to the billing system: with credits off they
        # would be meaningless (and the user gets unlimited usage anyway).
        db.add(CreditTransaction(
            user_id=user.id,
            amount=req.initial_credits,
            balance_after=req.initial_credits,
            reason="signup credit",
        ))

    raw_key, key_hash, key_prefix = generate_api_key()
    db.add(ApiKey(
        user_id=user.id,
        key_hash=key_hash,
        key_prefix=key_prefix,
        label="default",
        is_active=True,
    ))
    db.commit()

    log.info(f"Public register: {user.email} (id={user.id}) with {req.initial_credits} credits")
    return AuthResponse(
        user_id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        allowed_models=user.get_allowed_models(),
        api_key=raw_key,
        key_prefix=key_prefix,
        credits=req.initial_credits,
        credits_enabled=credits_enabled(),
    )


@app.post("/auth/login", response_model=AuthResponse)
def auth_login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.password_hash or user.password_hash != _hash_pw(req.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    raw_key, key_hash, key_prefix = generate_api_key()
    for k in db.query(ApiKey).filter(ApiKey.user_id == user.id, ApiKey.is_active == True).all():
        k.is_active = False
    db.add(ApiKey(
        user_id=user.id,
        key_hash=key_hash,
        key_prefix=key_prefix,
        label="login-issued",
        is_active=True,
    ))
    db.commit()

    balance = get_user_credits(db, user.id)
    return AuthResponse(
        user_id=user.id,
        email=user.email,
        name=user.name,
        role=getattr(user, "role", "both") or "both",
        allowed_models=user.get_allowed_models(),
        api_key=raw_key,
        key_prefix=key_prefix,
        credits=balance,
        credits_enabled=credits_enabled(),
    )


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
