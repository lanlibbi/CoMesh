"""
Admin API router — user management + cluster-wide node visibility.

Everything under `/admin` requires an admin role (`admin_auth.require_admin`),
i.e. a valid API key belonging to a user with `role == "admin"`.

Endpoint map
------------
  GET    /admin/whoami                                  caller identity + confirmation
  GET    /admin/overview                                platform-wide counters
  POST   /admin/users                                   create a user (idempotent by email)
  GET    /admin/users                                   list/filter users (paged)
  GET    /admin/users/{user_id}                         single user detail (+ key metadata)
  PATCH  /admin/users/{user_id}                         role / is_active / name / model whitelist
  POST   /admin/users/{user_id}/topup                   add credits (Idempotency-Key supported)
  POST   /admin/users/{user_id}/keys                    issue a fresh API key (old ones revoked)
  POST   /admin/users/{user_id}/keys/{key_id}/revoke    revoke a single API key
  POST   /admin/users/{user_id}/nodes/{node_id}/enable  enable/disable a node of any owner
  GET    /admin/nodes                                   every node, including offline/disabled
  GET    /admin/nodes/{node_id}                         node detail incl. WS state + last heartbeat

Idempotency
-----------
Mutating POSTs accept an `Idempotency-Key` header. The first call performs the
mutation and stores its (secret-free) result in `admin_audit_log`; a replay with
the same key returns the stored result with `"replayed": true` and performs no
second mutation. Raw API keys are never written to the audit log — a replayed
key rotation therefore returns the key metadata without the secret.

Audit trail
-----------
Every mutation writes an `admin_audit_log` row (admin, action, target, payload,
result) so state changes can be traced later.
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from admin_auth import require_admin
from auth import generate_api_key
from database import get_db
from config import credits_enabled
from netinfo import host_of as _host_of
from models import (
    ADMIN_ROLE,
    ADMIN_MANAGED_ROLES,
    ApiKey,
    AdminAuditLog,
    CreditTransaction,
    GpuNode,
    NodeEarning,
    NodeHeartbeat,
    Payment,
    PoolJob,
    SELF_SERVICE_ROLES,
    Usage,
    User,
    get_user_credits,
)
from usage_stats import AdminUsageOut, build_admin_usage

log = logging.getLogger("gpu-pool.admin")

router = APIRouter(prefix="/admin", tags=["admin"])

ONLINE_GRACE = timedelta(seconds=90)
MAX_PAGE = 500


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def _now() -> datetime:
    return datetime.utcnow()


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _is_online(node: GpuNode, now: Optional[datetime] = None) -> bool:
    """Heartbeat-based liveness. Mirrors nodes._is_online / pool._is_online."""
    now = now or _now()
    if not node.is_enabled or node.last_seen is None:
        return False
    if node.status not in ("online", "busy"):
        return False
    return (now - node.last_seen) < ONLINE_GRACE


def _effective_status(node: GpuNode, now: Optional[datetime] = None) -> str:
    """Status an operator should see: 'disabled' beats stale heartbeat state."""
    if not node.is_enabled:
        return "disabled"
    return node.status if _is_online(node, now) else "offline"


def _paging(limit: int, offset: int) -> tuple:
    return min(max(limit, 1), MAX_PAGE), max(offset, 0)


def _client_error(code: int, detail: str) -> HTTPException:
    return HTTPException(status_code=code, detail=detail)


def _parse_models_json(raw: Optional[str]) -> Optional[List[str]]:
    if raw is None:
        return None
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if isinstance(data, list):
        return [str(x) for x in data]
    return None


def _build(model_cls, result: Dict):
    """
    Instantiate a response model from an idempotency result.

    Keys the result does not carry (e.g. `replayed` on a first, non-replayed
    call) are simply absent, so the model's own defaults apply.
    """
    fields = set(model_cls.model_fields)
    return model_cls(**{k: v for k, v in result.items() if k in fields})


# ----------------------------------------------------------------------------
# Idempotent mutation wrapper
# ----------------------------------------------------------------------------
def run_idempotent(
    db: Session,
    admin: User,
    idempotency_key: Optional[str],
    action: str,
    target_type: str,
    target_id: Optional[int],
    payload: Dict,
    mutate,
    store_fields: Optional[List[str]] = None,
) -> Dict:
    """
    Execute `mutate()` exactly once per (admin, idempotency_key).

    `mutate()` receives no arguments, must only add/flush (never commit) and
    returns a JSON-serialisable dict. `store_fields` whitelists which result
    keys are persisted in the audit log (use it to keep secrets out).
    """
    if idempotency_key:
        key = idempotency_key.strip()
        if len(key) > 200:
            raise _client_error(422, "Idempotency-Key too long (max 200 chars).")
        existing = (
            db.query(AdminAuditLog)
            .filter(AdminAuditLog.idempotency_key == key)
            .first()
        )
        if existing:
            if existing.action != action:
                raise _client_error(
                    409,
                    "Idempotency-Key was already used for a different action "
                    f"('{existing.action}'). Use a fresh key.",
                )
            stored = json.loads(existing.result or "{}")
            stored["replayed"] = True
            stored["replayed_from_audit_id"] = existing.id
            return stored
    else:
        key = None

    result = mutate()

    stored = result
    if store_fields is not None:
        # Only the whitelisted keys are persisted (keeps secrets out of the audit
        # log); the caller still gets the full result back.
        stored = {k: result.get(k) for k in store_fields if k in result}

    db.add(AdminAuditLog(
        admin_user_id=admin.id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        idempotency_key=key,
        payload=json.dumps(payload or {}, default=str),
        result=json.dumps(stored, default=str),
    ))
    db.commit()
    return result

# ----------------------------------------------------------------------------
# Schemas
# ----------------------------------------------------------------------------
class AdminIdentity(BaseModel):
    id: int
    email: str
    name: str
    role: str
    company_hint: str = "gpu-pool"
    note: str = "Admin endpoints are role-gated and audited."


class UserAdminOut(BaseModel):
    id: int
    email: str
    name: str
    role: str
    is_active: bool
    registration_status: str = "approved"
    credits: float
    allowed_models: Optional[List[str]] = None
    allow_cloud: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    active_keys: int = 0
    nodes_total: int = 0
    nodes_online: int = 0
    usage_total_tokens: int = 0
    paid_total: float = 0.0


class UserListResponse(BaseModel):
    total: int
    returned: int
    limit: int
    offset: int
    users: List[UserAdminOut]


class ApiKeyOut(BaseModel):
    id: int
    key_prefix: str
    label: Optional[str] = None
    is_active: bool
    created_at: Optional[str] = None
    last_used_at: Optional[str] = None


class UserDetailOut(UserAdminOut):
    keys: List[ApiKeyOut] = []
    nodes: List[Dict] = []
    usage_events: int = 0


class CreateUserRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=200)
    name: str = Field(..., min_length=1, max_length=120)
    initial_credits: float = Field(100.0, ge=0.0, le=1_000_000.0)
    role: str = Field("both", description="admin | provider | consumer | both")
    password: Optional[str] = Field(None, min_length=1, max_length=200)


class CreateUserResponse(BaseModel):
    user_id: int
    email: str
    name: str
    role: str
    api_key: Optional[str] = None  # shown exactly once; None on idempotent replay
    key_prefix: str = ""
    credits: float
    created: bool = True
    replayed: bool = False


class UpdateUserRequest(BaseModel):
    """
    Partial update. Only the fields that are set are touched, so repeating the
    same request is a no-op (idempotent by construction).

    `allowed_models` semantics (mirrors /v1/me/allowed-models):
      None  -> leave untouched
      []    -> allow nothing
      [...] -> exact whitelist (cloud entries dropped unless allow_cloud=True)
    Set `allow_cloud` explicitly when the list contains cloud models.
    """
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    role: Optional[str] = None
    is_active: Optional[bool] = None
    allowed_models: Optional[List[str]] = None
    allow_cloud: bool = False
    expected_updated_at: Optional[str] = Field(
        None,
        description="Optimistic concurrency: if the stored users.updated_at "
                    "differs, the update is rejected with 409.",
    )


class TopupRequest(BaseModel):
    amount: float = Field(..., gt=-1_000_000.0, le=1_000_000.0,
                          description="Credits to add. Negative values are allowed (correction).")
    reason: str = Field("manual topup", max_length=200)


class TopupResponse(BaseModel):
    user_id: int
    credits: float
    balance_before: float
    added: float
    reason: str
    transaction_id: int
    replayed: bool = False


class KeyRotateResponse(BaseModel):
    user_id: int
    api_key: Optional[str] = None  # None on idempotent replay (never stored)
    key_prefix: str
    key_id: int
    revoked_key_ids: List[int] = []
    replayed: bool = False


class RevokeKeyResponse(BaseModel):
    user_id: int
    key_id: int
    revoked: bool
    already_inactive: bool
    replayed: bool = False


class EnableNodeResponse(BaseModel):
    node_id: int
    owner_id: int
    is_enabled: bool
    effective_status: str
    replayed: bool = False


class AdminNodeOut(BaseModel):
    id: int
    owner_id: int
    owner_email: Optional[str] = None
    name: str
    gpu_type: str
    vram_gb: int
    status: str                    # raw stored status
    effective_status: str          # online | offline | busy | disabled
    online: bool
    is_enabled: bool
    hourly_rate: float
    node_url: Optional[str] = None
    node_url_auto: bool = False
    # Deprecated mirror of the host part of `node_url`, kept for older clients.
    tailscale_ip: Optional[str] = None
    port: int
    backend: str = "ollama"
    last_seen: Optional[str] = None
    seconds_since_seen: Optional[float] = None
    total_hours: float = 0.0
    earnings_total: float = 0.0
    current_utilization: float = 0.0
    vram_used_gb: float = 0.0
    allowed_models: Optional[List[str]] = None
    connection_state: str = "disconnected"
    last_ws_seen: Optional[float] = None
    has_agent_key: bool = False
    created_at: Optional[str] = None


class NodeListResponse(BaseModel):
    total: int
    returned: int
    limit: int
    offset: int
    summary: Dict
    nodes: List[AdminNodeOut]


class AdminNodeDetail(AdminNodeOut):
    owner_name: Optional[str] = None
    description: Optional[str] = None
    nodes_jobs_total: int = 0
    nodes_jobs_failed: int = 0
    earnings_events: int = 0
    heartbeats_24h: int = 0
    last_heartbeat: Optional[Dict] = None
    updated_at: Optional[str] = None


class OverviewResponse(BaseModel):
    users_total: int
    users_active: int
    users_by_role: Dict
    admins_total: int
    credits_outstanding: float
    api_keys_active: int
    nodes_total: int
    nodes_online: int
    nodes_offline: int
    nodes_disabled: int
    nodes_vram_total_gb: int
    nodes_vram_online_gb: int
    nodes_with_agent_key: int
    nodes_ws_connected: int
    pool_jobs_total: int
    pool_jobs_failed: int
    pool_jobs_24h: int
    earnings_owner_total: float
    earnings_platform_total: float
    earnings_treasury_total: float
    payments_succeeded_total: float
    generated_at: str


# ----------------------------------------------------------------------------
# Serialisation helpers
# ----------------------------------------------------------------------------
def _user_out(db: Session, user: User, now: Optional[datetime] = None) -> UserAdminOut:
    now = now or _now()
    active_keys = db.query(func.count(ApiKey.id)).filter(
        ApiKey.user_id == user.id, ApiKey.is_active == True  # noqa: E712
    ).scalar() or 0
    nodes = db.query(GpuNode).filter(GpuNode.owner_id == user.id).all()
    usage_tokens = db.query(func.coalesce(func.sum(Usage.total_tokens), 0)).filter(
        Usage.user_id == user.id
    ).scalar() or 0
    paid = db.query(func.coalesce(func.sum(Payment.amount), 0.0)).filter(
        Payment.user_id == user.id, Payment.status == "succeeded"
    ).scalar() or 0.0
    role = (getattr(user, "role", None) or "both")
    return UserAdminOut(
        id=user.id,
        email=user.email,
        name=user.name,
        role=role,
        is_active=bool(user.is_active),
        registration_status=getattr(user, "registration_status", "approved") or "approved",
        credits=round(get_user_credits(db, user.id), 6),
        allowed_models=user.get_allowed_models(),
        allow_cloud=bool(user.allow_cloud),
        created_at=_iso(user.created_at),
        updated_at=_iso(getattr(user, "updated_at", None)),
        active_keys=int(active_keys),
        nodes_total=len(nodes),
        nodes_online=sum(1 for n in nodes if _is_online(n, now)),
        usage_total_tokens=int(usage_tokens),
        paid_total=round(float(paid), 6),
    )


def _node_out(db: Session, node: GpuNode, now: Optional[datetime] = None,
              owner_emails: Optional[Dict[int, str]] = None) -> AdminNodeOut:
    now = now or _now()
    online = _is_online(node, now)
    owner_email = None
    if owner_emails is not None:
        owner_email = owner_emails.get(node.owner_id)
    elif node.owner_id is not None:
        owner = db.query(User).filter(User.id == node.owner_id).first()
        owner_email = owner.email if owner else None
    return AdminNodeOut(
        id=node.id,
        owner_id=node.owner_id,
        owner_email=owner_email,
        name=node.name,
        gpu_type=node.gpu_type,
        vram_gb=node.vram_gb,
        status=node.status,
        effective_status=_effective_status(node, now),
        online=online,
        is_enabled=bool(node.is_enabled),
        hourly_rate=node.hourly_rate,
        node_url=node.node_url,
        node_url_auto=bool(node.node_url_auto),
        tailscale_ip=_host_of(node.node_url) or node.tailscale_ip,
        port=node.port,
        backend=node.backend,
        last_seen=_iso(node.last_seen),
        seconds_since_seen=(
            round((now - node.last_seen).total_seconds(), 1) if node.last_seen else None
        ),
        total_hours=node.total_hours,
        earnings_total=node.earnings_total,
        current_utilization=node.current_utilization if online else 0.0,
        vram_used_gb=node.vram_used_gb if online else 0.0,
        allowed_models=node.get_allowed_models(),
        connection_state=(getattr(node, "connection_state", None) or "disconnected"),
        last_ws_seen=getattr(node, "last_ws_seen", None),
        has_agent_key=bool(node.api_key),
        created_at=_iso(node.created_at),
    )


# ----------------------------------------------------------------------------
# Identity / overview
# ----------------------------------------------------------------------------
@router.get("/whoami", response_model=AdminIdentity)
def whoami(admin: User = Depends(require_admin)):
    """Cheap probe clients can use to verify an admin key before doing work."""
    return AdminIdentity(
        id=admin.id,
        email=admin.email,
        name=admin.name,
        role=getattr(admin, "role", ADMIN_ROLE) or ADMIN_ROLE,
    )


@router.get("/overview", response_model=OverviewResponse)
def overview(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Platform-wide counters — the numbers an operator wants at a glance."""
    now = _now()
    users = db.query(User).all()
    nodes = db.query(GpuNode).all()
    online = [n for n in nodes if _is_online(n, now)]

    role_counts: Dict[str, int] = {}
    for u in users:
        r = (getattr(u, "role", None) or "both")
        role_counts[r] = role_counts.get(r, 0) + 1

    earnings = db.query(
        func.coalesce(func.sum(NodeEarning.owner_share), 0.0),
        func.coalesce(func.sum(NodeEarning.platform_share), 0.0),
        func.coalesce(func.sum(NodeEarning.treasury_share), 0.0),
    ).first() or (0.0, 0.0, 0.0)

    jobs_total = db.query(func.count(PoolJob.id)).scalar() or 0
    jobs_failed = db.query(func.count(PoolJob.id)).filter(PoolJob.status == "failed").scalar() or 0
    jobs_24h = db.query(func.count(PoolJob.id)).filter(
        PoolJob.started_at >= now - timedelta(hours=24)
    ).scalar() or 0

    return OverviewResponse(
        users_total=len(users),
        users_active=sum(1 for u in users if u.is_active),
        users_by_role=role_counts,
        admins_total=role_counts.get(ADMIN_ROLE, 0),
        credits_outstanding=round(
            float(db.query(func.coalesce(func.sum(CreditTransaction.amount), 0.0)).scalar() or 0.0), 6
        ),
        api_keys_active=int(db.query(func.count(ApiKey.id)).filter(ApiKey.is_active == True).scalar() or 0),  # noqa: E712
        nodes_total=len(nodes),
        nodes_online=len(online),
        nodes_offline=sum(1 for n in nodes if n.is_enabled and not _is_online(n, now)),
        nodes_disabled=sum(1 for n in nodes if not n.is_enabled),
        nodes_vram_total_gb=int(sum(n.vram_gb for n in nodes)),
        nodes_vram_online_gb=int(sum(n.vram_gb for n in online)),
        nodes_with_agent_key=sum(1 for n in nodes if n.api_key),
        nodes_ws_connected=sum(
            1 for n in nodes if (getattr(n, "connection_state", None) == "connected")
        ),
        pool_jobs_total=int(jobs_total),
        pool_jobs_failed=int(jobs_failed),
        pool_jobs_24h=int(jobs_24h),
        earnings_owner_total=round(float(earnings[0]), 6),
        earnings_platform_total=round(float(earnings[1]), 6),
        earnings_treasury_total=round(float(earnings[2]), 6),
        payments_succeeded_total=round(float(
            db.query(func.coalesce(func.sum(Payment.amount), 0.0)).filter(
                Payment.status == "succeeded"
            ).scalar() or 0.0
        ), 6),
        generated_at=now.isoformat(),
    )


# ----------------------------------------------------------------------------
# Users
# ----------------------------------------------------------------------------
@router.post("/users", response_model=CreateUserResponse, status_code=201)
def admin_create_user(
    req: CreateUserRequest,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Create a user. Idempotent by email: a second call for an existing email
    returns the existing user (no duplicate, no new key, no extra credits).
    """
    email = req.email.strip().lower()
    role = req.role if req.role in ADMIN_MANAGED_ROLES else "both"

    def mutate() -> Dict:
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            return {
                "user_id": existing.id,
                "email": existing.email,
                "name": existing.name,
                "role": existing.role,
                "key_prefix": (
                    db.query(ApiKey).filter(ApiKey.user_id == existing.id)
                    .order_by(ApiKey.id.desc()).first().key_prefix
                    if db.query(ApiKey).filter(ApiKey.user_id == existing.id).first() else ""
                ),
                "credits": round(get_user_credits(db, existing.id), 6),
                "created": False,
                "api_key": None,
            }

        user = User(email=email, name=req.name, is_active=True, role=role)
        if req.password:
            user.password_hash = __import__("hashlib").sha256(
                req.password.encode("utf-8")
            ).hexdigest()
        db.add(user)
        db.flush()
        db.add(CreditTransaction(
            user_id=user.id,
            amount=req.initial_credits,
            balance_after=req.initial_credits,
            reason="initial credit (admin)",
        ))
        raw_key, key_hash, key_prefix = generate_api_key()
        db.add(ApiKey(
            user_id=user.id,
            key_hash=key_hash,
            key_prefix=key_prefix,
            label="admin-created",
            is_active=True,
        ))
        return {
            "user_id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role,
            "api_key": raw_key,
            "key_prefix": key_prefix,
            "credits": req.initial_credits,
            "created": True,
        }

    result = run_idempotent(
        db, admin, idempotency_key, "user.create", "user",
        None, req.model_dump(), mutate,
        store_fields=["user_id", "email", "name", "role", "key_prefix", "credits", "created"],
    )
    log.info(f"admin {admin.email}: create user {email} (id={result.get('user_id')}, created={result.get('created')})")
    return _build(CreateUserResponse, result)


@router.get("/users", response_model=UserListResponse)
def admin_list_users(
    q: Optional[str] = Query(None, description="Substring match on email or name"),
    role: Optional[str] = Query(None, description="admin | provider | consumer | both"),
    is_active: Optional[bool] = Query(None),
    include_inactive: bool = Query(True, description="False = only active users"),
    limit: int = Query(50, ge=1, le=MAX_PAGE),
    offset: int = Query(0, ge=0),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """List users with filters + paging. Active and inactive users are both listed."""
    limit, offset = _paging(limit, offset)
    query = db.query(User)
    if role:
        if role not in ADMIN_MANAGED_ROLES:
            raise _client_error(422, f"Unknown role '{role}'. Valid: {', '.join(ADMIN_MANAGED_ROLES)}")
        query = query.filter(User.role == role)
    if is_active is not None:
        query = query.filter(User.is_active == is_active)
    elif not include_inactive:
        query = query.filter(User.is_active == True)  # noqa: E712
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(func.lower(User.email).like(like.lower()) | func.lower(User.name).like(like.lower()))

    total = query.count()
    rows = query.order_by(User.id.asc()).limit(limit).offset(offset).all()
    now = _now()
    return UserListResponse(
        total=int(total),
        returned=len(rows),
        limit=limit,
        offset=offset,
        users=[_user_out(db, u, now) for u in rows],
    )


# ---------------------------------------------------------------------------
# Registrations (manual approval of new public sign-ups)
# ---------------------------------------------------------------------------


@router.get("/registrations")
def admin_list_registrations(
    q: Optional[str] = Query(None, description="Substring match on email or name"),
    search: Optional[str] = Query(None, description="Alias for q"),
    status: Optional[str] = Query(None, description="pending | approved | rejected"),
    registration_status: Optional[str] = Query(None, description="Alias for status"),
    limit: int = Query(50, ge=1, le=MAX_PAGE),
    offset: int = Query(0, ge=0),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """List registration requests with server-side search + status filter + paging."""
    query_text = q if q is not None else search
    status_filter = status if status is not None else registration_status
    limit, offset = _paging(limit, offset)
    query = db.query(User)
    if status_filter:
        s = status_filter.strip().lower()
        if s not in ("pending", "approved", "rejected"):
            raise _client_error(422, f"Unknown status '{status_filter}'. Valid: pending, approved, rejected")
        query = query.filter(User.registration_status == s)
    if query_text:
        like = f"%{query_text.strip()}%"
        query = query.filter(func.lower(User.email).like(like.lower()) | func.lower(User.name).like(like.lower()))

    total = query.count()
    rows = query.order_by(User.id.asc()).limit(limit).offset(offset).all()
    items = []
    for u in rows:
        credits = round(get_user_credits(db, u.id), 6)
        rs = getattr(u, "registration_status", "approved") or "approved"
        created = _iso(u.created_at)
        items.append({
            "id": u.id,
            "user_id": u.id,
            "email": u.email,
            "name": u.name,
            "role": getattr(u, "role", "both") or "both",
            "status": rs,
            "registration_status": rs,
            "is_active": bool(u.is_active),
            "credits": credits,
            "created_at": created,
            "date": created,
            "registered_at": created,
            "signup_credits": getattr(u, "signup_credits", None),
        })
    return {
        "total": int(total),
        "returned": len(items),
        "limit": limit,
        "offset": offset,
        "registrations": items,
        "users": items,
        "items": items,
    }


@router.post("/registrations/{registration_id}/approve")
def admin_approve_registration(
    registration_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == registration_id).first()
    if not user:
        raise _client_error(404, "Registration not found")
    rs = getattr(user, "registration_status", "approved") or "approved"
    if rs == "approved":
        return {
            "id": user.id,
            "user_id": user.id,
            "email": user.email,
            "status": "approved",
            "registration_status": "approved",
            "credits": round(get_user_credits(db, user.id), 6),
            "replayed": True,
        }
    credits_to_add = getattr(user, "signup_credits", None)
    if credits_to_add is None:
        credits_to_add = 100.0
    try:
        credits_to_add = float(credits_to_add)
    except (TypeError, ValueError):
        credits_to_add = 100.0
    if credits_enabled() and credits_to_add > 0:
        balance_before = get_user_credits(db, user.id)
        db.add(CreditTransaction(
            user_id=user.id,
            amount=credits_to_add,
            balance_after=balance_before + credits_to_add,
            reason="signup credit (approved)",
        ))
    for k in db.query(ApiKey).filter(ApiKey.user_id == user.id).all():
        k.is_active = True
    user.is_active = True
    user.registration_status = "approved"
    user.updated_at = __import__("datetime").datetime.utcnow()
    db.commit()
    log.info(f"admin {admin.email}: approved registration {user.id} ({user.email})")
    return {
        "id": user.id,
        "user_id": user.id,
        "email": user.email,
        "name": user.name,
        "status": "approved",
        "registration_status": "approved",
        "credits": round(get_user_credits(db, user.id), 6),
        "replayed": False,
    }


@router.post("/registrations/{registration_id}/reject")
def admin_reject_registration(
    registration_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == registration_id).first()
    if not user:
        raise _client_error(404, "Registration not found")
    rs = getattr(user, "registration_status", "approved") or "approved"
    if rs == "rejected":
        return {
            "id": user.id,
            "user_id": user.id,
            "email": user.email,
            "status": "rejected",
            "registration_status": "rejected",
            "replayed": True,
        }
    for k in db.query(ApiKey).filter(ApiKey.user_id == user.id).all():
        k.is_active = False
    user.is_active = False
    user.registration_status = "rejected"
    user.updated_at = __import__("datetime").datetime.utcnow()
    db.commit()
    log.info(f"admin {admin.email}: rejected registration {user.id} ({user.email})")
    return {
        "id": user.id,
        "user_id": user.id,
        "email": user.email,
        "name": user.name,
        "status": "rejected",
        "registration_status": "rejected",
        "replayed": False,
    }


@router.get("/users/{user_id}", response_model=UserDetailOut)
def admin_get_user(
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise _client_error(404, "User not found")

    now = _now()
    base = _user_out(db, user, now)
    keys = db.query(ApiKey).filter(ApiKey.user_id == user.id).order_by(ApiKey.id.asc()).all()
    nodes = db.query(GpuNode).filter(GpuNode.owner_id == user.id).all()
    usage_events = db.query(func.count(Usage.id)).filter(Usage.user_id == user.id).scalar() or 0

    return UserDetailOut(
        **base.model_dump(),
        keys=[
            ApiKeyOut(
                id=k.id,
                key_prefix=k.key_prefix,
                label=k.label,
                is_active=bool(k.is_active),
                created_at=_iso(k.created_at),
                last_used_at=_iso(k.last_used_at),
            )
            for k in keys
        ],
        nodes=[
            {
                "id": n.id,
                "name": n.name,
                "gpu_type": n.gpu_type,
                "effective_status": _effective_status(n, now),
                "is_enabled": bool(n.is_enabled),
                "earnings_total": n.earnings_total,
                "connection_state": getattr(n, "connection_state", "disconnected"),
            }
            for n in nodes
        ],
        usage_events=int(usage_events),
    )


@router.patch("/users/{user_id}", response_model=UserAdminOut)
def admin_update_user(
    user_id: int,
    req: UpdateUserRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Partial user update: role, is_active, name, model whitelist.

    * Role changes are validated against ADMIN_MANAGED_ROLES (admins can be
      created/promoted here — users cannot do this for themselves).
    * Setting is_active=false immediately invalidates the user's keys
      (auth.get_current_user requires an active user).
    * An admin cannot deactivate or demote their own account (lockout guard).
    * Repeating the identical request changes nothing (idempotent).
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise _client_error(404, "User not found")

    if req.expected_updated_at is not None:
        stored = getattr(user, "updated_at", None)
        if stored is not None and stored.isoformat() != req.expected_updated_at:
            raise _client_error(
                409,
                "users.updated_at changed since it was read "
                f"(expected {req.expected_updated_at}, found {stored.isoformat()}). Re-read and retry.",
            )

    changes: Dict[str, object] = {}

    if req.role is not None:
        if req.role not in ADMIN_MANAGED_ROLES:
            raise _client_error(422, f"Invalid role '{req.role}'. Valid: {', '.join(ADMIN_MANAGED_ROLES)}")
        if user.id == admin.id and req.role != ADMIN_ROLE:
            raise _client_error(409, "Refusing to remove your own admin role (lockout guard).")
        if user.role != req.role:
            changes["role"] = {"from": user.role, "to": req.role}
            user.role = req.role

    if req.is_active is not None:
        if user.id == admin.id and req.is_active is False:
            raise _client_error(409, "Refusing to deactivate your own admin account (lockout guard).")
        if bool(user.is_active) != bool(req.is_active):
            changes["is_active"] = {"from": bool(user.is_active), "to": bool(req.is_active)}
            user.is_active = bool(req.is_active)
            if not req.is_active:
                for k in db.query(ApiKey).filter(ApiKey.user_id == user.id, ApiKey.is_active == True).all():  # noqa: E712
                    k.is_active = False

    if req.name is not None and req.name != user.name:
        changes["name"] = {"from": user.name, "to": req.name}
        user.name = req.name

    if req.allowed_models is not None:
        target: Optional[List[str]]
        if req.allow_cloud:
            target = list(req.allowed_models)
        else:
            target = [m for m in req.allowed_models if "cloud" not in m.lower()]
        if user.get_allowed_models() != target:
            changes["allowed_models"] = {"from": user.get_allowed_models(), "to": target}
            user.set_allowed_models(target)
        elif user.get_allowed_models() is None and target == []:
            user.set_allowed_models(target)
            changes["allowed_models"] = {"from": None, "to": target}

    user.updated_at = _now()
    db.commit()
    db.refresh(user)

    try:
        db.add(AdminAuditLog(
            admin_user_id=admin.id,
            action="user.update",
            target_type="user",
            target_id=user.id,
            idempotency_key=None,
            payload=json.dumps(req.model_dump(), default=str),
            result=json.dumps({"changed": changes}, default=str),
        ))
        db.commit()
    except Exception as e:  # audit must never break the mutation
        db.rollback()
        log.warning(f"audit write failed for user.update/{user.id}: {e}")

    log.info(f"admin {admin.email}: update user {user.email} changes={list(changes.keys())}")
    return _user_out(db, user)


@router.post("/users/{user_id}/topup", response_model=TopupResponse)
def admin_topup_user(
    user_id: int,
    req: TopupRequest,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Add (or correct) credits for a user. Replays with the same Idempotency-Key do not double-book."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise _client_error(404, "User not found")

    def mutate() -> Dict:
        before = round(get_user_credits(db, user.id), 6)
        after = round(before + req.amount, 6)
        tx = CreditTransaction(
            user_id=user.id,
            amount=req.amount,
            balance_after=after,
            reason=req.reason,
        )
        db.add(tx)
        db.flush()
        return {
            "user_id": user.id,
            "credits": after,
            "balance_before": before,
            "added": req.amount,
            "reason": req.reason,
            "transaction_id": tx.id,
            "replayed": False,
        }

    result = run_idempotent(
        db, admin, idempotency_key, "user.topup", "user", user.id,
        {"amount": req.amount, "reason": req.reason}, mutate,
    )
    log.info(f"admin {admin.email}: topup user {user.email} +{req.amount} -> {result['credits']}")
    return _build(TopupResponse, result)


@router.post("/users/{user_id}/keys", response_model=KeyRotateResponse)
def admin_rotate_user_key(
    user_id: int,
    label: Optional[str] = Query(None, max_length=120),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Issue a fresh API key and revoke the user's other active keys.

    The raw key is returned exactly once and is deliberately NOT stored in the
    audit log: an idempotent replay returns the key metadata with
    `api_key: null` and `replayed: true` (state unchanged, no new key issued).
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise _client_error(404, "User not found")
    if not user.is_active:
        raise _client_error(409, "User is inactive — reactivate the account before issuing a key.")

    def mutate() -> Dict:
        revoked = []
        for k in db.query(ApiKey).filter(ApiKey.user_id == user.id, ApiKey.is_active == True).all():  # noqa: E712
            k.is_active = False
            revoked.append(k.id)
        raw, key_hash, key_prefix = generate_api_key()
        new_key = ApiKey(
            user_id=user.id,
            key_hash=key_hash,
            key_prefix=key_prefix,
            label=label or "admin-rotated",
            is_active=True,
        )
        db.add(new_key)
        db.flush()
        return {
            "user_id": user.id,
            "api_key": raw,
            "key_prefix": key_prefix,
            "key_id": new_key.id,
            "revoked_key_ids": revoked,
            "replayed": False,
        }

    result = run_idempotent(
        db, admin, idempotency_key, "user.key.rotate", "user", user.id,
        {"label": label}, mutate,
        store_fields=["user_id", "key_prefix", "key_id", "revoked_key_ids"],
    )
    log.info(f"admin {admin.email}: rotated key for {user.email} (new key id={result.get('key_id')}, replayed={result.get('replayed', False)})")
    return _build(KeyRotateResponse, result)


@router.post("/users/{user_id}/keys/{key_id}/revoke", response_model=RevokeKeyResponse)
def admin_revoke_user_key(
    user_id: int,
    key_id: int,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Revoke a single API key. Revoking an already-inactive key is a successful no-op."""
    key = db.query(ApiKey).filter(ApiKey.id == key_id, ApiKey.user_id == user_id).first()
    if not key:
        raise _client_error(404, "API key not found for that user")

    def mutate() -> Dict:
        already = not bool(key.is_active)
        key.is_active = False
        db.flush()
        return {
            "user_id": user_id,
            "key_id": key.id,
            "revoked": True,
            "already_inactive": already,
            "replayed": False,
        }

    result = run_idempotent(
        db, admin, idempotency_key, "user.key.revoke", "api_key", key.id,
        {}, mutate,
    )
    log.info(f"admin {admin.email}: revoked key {key_id} of user {user_id}")
    return _build(RevokeKeyResponse, result)


# ----------------------------------------------------------------------------
# Nodes (all owners, including offline/disabled)
# ----------------------------------------------------------------------------
@router.get("/nodes", response_model=NodeListResponse)
def admin_list_nodes(
    q: Optional[str] = Query(None, description="Substring match on node name, gpu_type or node address"),
    status_filter: Optional[str] = Query(
        None, alias="status",
        description="all | online | offline | busy | disabled (default: all)",
    ),
    owner_id: Optional[int] = Query(None),
    backend: Optional[str] = Query(None, description="ollama | openai"),
    include_disabled: bool = Query(True, description="False = hide nodes the owner paused"),
    limit: int = Query(100, ge=1, le=MAX_PAGE),
    offset: int = Query(0, ge=0),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Every node on the platform — the point of this endpoint is that offline and
    disabled nodes show up too (the public /nodes/list hides them by default).
    """
    limit, offset = _paging(limit, offset)
    now = _now()

    query = db.query(GpuNode)
    if owner_id is not None:
        query = query.filter(GpuNode.owner_id == owner_id)
    if backend:
        query = query.filter(GpuNode.backend == backend)
    if not include_disabled:
        query = query.filter(GpuNode.is_enabled == True)  # noqa: E712
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            func.lower(GpuNode.name).like(like.lower())
            | func.lower(GpuNode.gpu_type).like(like.lower())
            | func.coalesce(GpuNode.node_url, "").like(like)
            | func.coalesce(GpuNode.tailscale_ip, "").like(like)
        )

    rows = query.order_by(GpuNode.id.asc()).all()

    if status_filter and status_filter != "all":
        if status_filter not in ("online", "offline", "busy", "disabled"):
            raise _client_error(422, "status must be one of: all, online, offline, busy, disabled")
        if status_filter == "online":
            rows = [n for n in rows if _is_online(n, now)]
        elif status_filter == "disabled":
            rows = [n for n in rows if not n.is_enabled]
        elif status_filter == "offline":
            rows = [n for n in rows if n.is_enabled and not _is_online(n, now)]
        elif status_filter == "busy":
            rows = [n for n in rows if _is_online(n, now) and n.status == "busy"]

    total = len(rows)
    page = rows[offset:offset + limit]

    owner_ids = {n.owner_id for n in page if n.owner_id is not None}
    owners = {}
    if owner_ids:
        owners = {
            u.id: u.email
            for u in db.query(User).filter(User.id.in_(owner_ids)).all()
        }

    all_nodes = db.query(GpuNode).all()
    all_online = [n for n in all_nodes if _is_online(n, now)]
    summary = {
        "nodes_total": len(all_nodes),
        "nodes_online": len(all_online),
        "nodes_offline": sum(1 for n in all_nodes if n.is_enabled and not _is_online(n, now)),
        "nodes_disabled": sum(1 for n in all_nodes if not n.is_enabled),
        "nodes_ws_connected": sum(
            1 for n in all_nodes if (getattr(n, "connection_state", None) == "connected")
        ),
        "vram_total_gb": int(sum(n.vram_gb for n in all_nodes)),
        "vram_online_gb": int(sum(n.vram_gb for n in all_online)),
        "filtered_total": total,
    }
    return NodeListResponse(
        total=total,
        returned=len(page),
        limit=limit,
        offset=offset,
        summary=summary,
        nodes=[_node_out(db, n, now, owners) for n in page],
    )


@router.get("/nodes/{node_id}", response_model=AdminNodeDetail)
def admin_get_node(
    node_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Node detail, including the pieces the public view hides (WS state, last heartbeat, failures)."""
    node = db.query(GpuNode).filter(GpuNode.id == node_id).first()
    if not node:
        raise _client_error(404, "Node not found")
    now = _now()
    owner = db.query(User).filter(User.id == node.owner_id).first()

    hb = (
        db.query(NodeHeartbeat)
        .filter(NodeHeartbeat.node_id == node.id)
        .order_by(NodeHeartbeat.received_at.desc())
        .first()
    )
    hb_24h = db.query(func.count(NodeHeartbeat.id)).filter(
        NodeHeartbeat.node_id == node.id,
        NodeHeartbeat.received_at >= now - timedelta(hours=24),
    ).scalar() or 0
    jobs_total = db.query(func.count(PoolJob.id)).filter(PoolJob.node_id == node.id).scalar() or 0
    jobs_failed = db.query(func.count(PoolJob.id)).filter(
        PoolJob.node_id == node.id, PoolJob.status == "failed"
    ).scalar() or 0
    earnings_events = db.query(func.count(NodeEarning.id)).filter(
        NodeEarning.node_id == node.id
    ).scalar() or 0

    base = _node_out(db, node, now)
    return AdminNodeDetail(
        **base.model_dump(),
        owner_name=owner.name if owner else None,
        description=node.description,
        nodes_jobs_total=int(jobs_total),
        nodes_jobs_failed=int(jobs_failed),
        earnings_events=int(earnings_events),
        heartbeats_24h=int(hb_24h),
        last_heartbeat=(
            {
                "received_at": _iso(hb.received_at),
                "status": hb.status,
                "gpu_util": hb.gpu_util,
                "vram_used_gb": hb.vram_used_gb,
                "vram_total_gb": hb.vram_total_gb,
                "active_jobs": hb.active_jobs,
            }
            if hb else None
        ),
        updated_at=_iso(getattr(node, "updated_at", None)),
    )


@router.post("/users/{user_id}/nodes/{node_id}/enable", response_model=EnableNodeResponse)
def admin_enable_node(
    user_id: int,
    node_id: int,
    enabled: bool = Query(True),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Pause/resume a node belonging to any user (owner-scoped /nodes/{id}/enable
    cannot do this). Idempotent: setting the same value again is a no-op.
    """
    node = db.query(GpuNode).filter(GpuNode.id == node_id, GpuNode.owner_id == user_id).first()
    if not node:
        raise _client_error(404, "Node not found for that user")

    def mutate() -> Dict:
        node.is_enabled = bool(enabled)
        db.flush()
        return {
            "node_id": node.id,
            "owner_id": node.owner_id,
            "is_enabled": bool(node.is_enabled),
            "effective_status": _effective_status(node),
            "replayed": False,
        }

    result = run_idempotent(
        db, admin, idempotency_key, "node.enable", "gpu_node", node.id,
        {"enabled": bool(enabled)}, mutate,
    )
    log.info(f"admin {admin.email}: node {node.id} is_enabled -> {result.get('is_enabled')} (owner {user_id})")
    return _build(EnableNodeResponse, result)


# ----------------------------------------------------------------------------
# Usage analytics (platform-wide)
# ----------------------------------------------------------------------------
@router.get("/usage", response_model=AdminUsageOut)
def admin_usage(
    window: str = Query("7d", description="24h | 7d | 30d | all"),
    limit: int = Query(50, ge=1, le=MAX_PAGE, description="Max users returned, heaviest first"),
    include_inactive: bool = Query(True, description="False = only active accounts"),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Token/credit usage of every user, per model — the admin counterpart to
    GET /v1/me/usage. Same aggregation, no user filter.
    """
    result = build_admin_usage(db, window=window, limit=limit, include_inactive=include_inactive)
    log.info(
        f"admin {admin.email}: usage window={result.window} users={len(result.users)} "
        f"tokens={result.totals.total_tokens}"
    )
    return result
