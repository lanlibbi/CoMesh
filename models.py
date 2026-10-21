"""
SQLAlchemy models for users, API keys, credit accounting, payments,
and the Community GPU-Pool (GpuNode, NodeHeartbeat, NodeEarnings, PoolJob).
"""
import json
import secrets
from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Text
)
from sqlalchemy.orm import relationship

from database import Base


def _generate_api_key() -> str:
    """Generate a secure API key with prefix."""
    return f"gpu_{secrets.token_urlsafe(32)}"


# ----------------------------------------------------------------------------
# Roles
# ----------------------------------------------------------------------------
# self-service roles: a user may set these for themselves (PUT /v1/me/role).
SELF_SERVICE_ROLES = ("provider", "consumer", "both")
# privileged role: only an existing admin can grant it (PATCH /admin/users/{id}).
ADMIN_ROLE = "admin"
# full set accepted by admin-managed writes and admin-side filters.
ADMIN_MANAGED_ROLES = SELF_SERVICE_ROLES + (ADMIN_ROLE,)
# legacy alias — the OpenAI/self-service surface (main.py) keeps using this name.
VALID_ROLES = SELF_SERVICE_ROLES


class User(Base):
    """A platform user."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    password_hash = Column(String, nullable=True)  # SHA-256 hash; POC: use bcrypt/argon2 in prod
    is_active = Column(Boolean, default=True, nullable=False)
    registration_status = Column(String, default="approved", nullable=False)  # pending | approved | rejected
    signup_credits = Column(Float, default=100.0, nullable=False)              # credits granted on approval
    role = Column(String, default="both", nullable=False)        # provider | consumer | both
    allowed_models = Column(Text, nullable=True)                 # JSON list or NULL = "all local, no cloud"
    # Cloud-Modelle sind kostenpflichtig und werden bewusst zugeschaltet. Getrennt von
    # `allowed_models`, damit eine gezielte Freigabe erhalten bleibt.
    allow_cloud = Column(Boolean, default=False, nullable=False)
    # Quota mode when the credits system is enabled (admin-controlled):
    #   "unlimited" -> no credit checks for this user (default, free usage)
    #   "balance"   -> legacy behaviour: balance floor + deduction apply
    #   "blocked"   -> requests are refused (HTTP 403), independent of balance
    quota_mode = Column(String, default="unlimited", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)

    api_keys = relationship("ApiKey", back_populates="user", cascade="all, delete-orphan")
    usages = relationship("Usage", back_populates="user", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="user", cascade="all, delete-orphan")
    nodes = relationship("GpuNode", back_populates="owner", cascade="all, delete-orphan")
    node_earnings = relationship("NodeEarning", back_populates="owner", cascade="all, delete-orphan")

    # ---------- Model-whitelist helpers ----------
    def get_allowed_models(self) -> Optional[List[str]]:
        """
        Returns the parsed whitelist, or None (= all local, no cloud by default).
        Empty list [] is distinct from None and means "allow nothing".
        """
        if self.allowed_models is None:
            return None
        try:
            data = json.loads(self.allowed_models)
            if data is None:
                return None
            if isinstance(data, list):
                return [str(x) for x in data]
            return None
        except (json.JSONDecodeError, TypeError):
            return None

    def set_allowed_models(self, models: Optional[List[str]]) -> None:
        """
        Persist the whitelist. None -> NULL (= all local, no cloud default).
        Empty list -> '[]' (allow nothing).
        """
        if models is None:
            self.allowed_models = None
        else:
            self.allowed_models = json.dumps(list(models))

    def can_use_model(self, model: str) -> bool:
        """
        Authorization check for a single model.

        Zwei getrennte Entscheidungen:
          * `allowed_models` sagt, welche lokalen Modelle freigegeben sind
            (None = alle lokalen, Liste = genau diese, [] = nichts),
          * `allow_cloud` schaltet Cloud-Modelle zusätzlich frei, ohne die lokale
            Freigabe zu verändern.
        """
        if not model:
            return True
        is_cloud = _is_cloud_model_name(model)
        allowed = self.get_allowed_models()
        rolle = (self.role or "").lower()

        if allowed is None:
            # Ohne Liste gilt:
            #   Consumer           -> nichts freigegeben (er bekommt Modelle zugeteilt),
            #   Provider/both/admin -> alle lokalen, Cloud nur wenn zugeschaltet.
            if rolle == "consumer":
                return is_cloud and bool(self.allow_cloud)
            return (not is_cloud) or bool(self.allow_cloud)

        if model in allowed:
            return True
        return is_cloud and bool(self.allow_cloud)


def _is_cloud_model_name(name: str) -> bool:
    """Heuristic: a model is 'cloud' if the name contains 'cloud'."""
    return "cloud" in (name or "").lower()


class ApiKey(Base):
    """An API key for a user. Keys are stored hashed; raw key shown once at creation."""
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    key_hash = Column(String, unique=True, index=True, nullable=False)
    key_prefix = Column(String, nullable=False)  # First 12 chars for display
    label = Column(String, nullable=True)
    token_type = Column(String, default="api_key", nullable=False)  # api_key | session
    expires_at = Column(DateTime, nullable=True)                   # NULL = never expires
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_used_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="api_keys")

    @property
    def is_expired(self) -> bool:
        return self.expires_at is not None and self.expires_at <= datetime.utcnow()

    @property
    def expires_in_seconds(self) -> Optional[int]:
        if self.expires_at is None:
            return None
        return int((self.expires_at - datetime.utcnow()).total_seconds())


class CreditTransaction(Base):
    """Credit movements (top-ups, deductions)."""
    __tablename__ = "credit_transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    amount = Column(Float, nullable=False)  # positive = top-up, negative = usage
    balance_after = Column(Float, nullable=False)
    reason = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class SystemSetting(Base):
    """Key/value runtime settings editable by admins (e.g. credits_enabled).

    Values are stored as strings and parsed on read. Absence of a key means
    "not overridden" -> callers fall back to config.yaml defaults.
    """
    __tablename__ = "system_settings"

    key = Column(String, primary_key=True)
    value = Column(String, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)


class Usage(Base):
    """Logged usage of the /v1/chat/completions endpoint."""
    __tablename__ = "usages"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    api_key_id = Column(Integer, ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True)
    model = Column(String, nullable=False)
    prompt_tokens = Column(Integer, default=0, nullable=False)
    completion_tokens = Column(Integer, default=0, nullable=False)
    total_tokens = Column(Integer, default=0, nullable=False)
    credits_charged = Column(Float, default=0.0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="usages")


class Payment(Base):
    """A payment attempt (Stripe / PayPal / Alipay / Apple Pay)."""
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider = Column(String, nullable=False)            # stripe | paypal | alipay | applepay
    amount = Column(Float, nullable=False)               # EUR
    currency = Column(String, default="EUR", nullable=False)
    status = Column(String, default="pending", nullable=False)  # pending | succeeded | failed | cancelled
    credits_added = Column(Integer, default=0, nullable=False)
    transaction_id = Column(String, nullable=True, index=True)  # gateway-side id
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="payments")


# ----------------------------------------------------------------------------
# Community GPU-Pool models
# ----------------------------------------------------------------------------
class GpuNode(Base):
    """A community-contributed GPU node.

    The owner is a User. The node exposes its Ollama-compatible API on a
    `node_url` (scheme + host + port). The host may be a DNS name, an mDNS
    name (``*.local``), a name from a mesh VPN (e.g. Tailscale MagicDNS) or a
    plain LAN IP — whatever the portal can reach. Nodes on DHCP keep an
    *empty* ``node_url``; the portal then auto-detects the address from the
    source IP of each heartbeat, so no address has to be configured or kept
    in sync. Heartbeats refresh `last_seen`; the pool router reads `status`
    to decide where to forward jobs.
    """
    __tablename__ = "gpu_nodes"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)                # "Living Room RTX 4090"
    gpu_type = Column(String, nullable=False)            # "RTX 4090", "A100 80GB", ...
    vram_gb = Column(Integer, nullable=False)            # total VRAM
    status = Column(String, default="offline", nullable=False)  # online | offline | busy
    hourly_rate = Column(Float, default=0.05, nullable=False)   # credits/hour charged to the user
    # Deprecated (LANA-89): use `node_url`. Kept so existing SQLite databases
    # keep loading; it is no longer written or read by the application.
    tailscale_ip = Column(String, nullable=True)
    # Canonical reachability address of the agent, e.g.
    #   http://node-host:11435   (DNS / mDNS name, preferred)
    #   http://10.0.0.42:11435   (plain IP — breaks on DHCP lease changes)
    #   https://gpu-01.example.net  (reverse proxy / TLS terminator)
    # May be empty: the portal then derives the host from the heartbeat's
    # source address and stores the result back here.
    node_url = Column(String, nullable=True)
    # True when `node_url` was derived automatically from the heartbeat source
    # address (DHCP-friendly) rather than configured explicitly.
    node_url_auto = Column(Boolean, default=False, nullable=False)
    port = Column(Integer, default=11434, nullable=False)
    # Inference backend this node exposes. "ollama" (default) talks Ollama's
    # /api/chat; "openai" talks any OpenAI-compatible server (LM Studio, LiteLLM, vLLM…).
    backend = Column(String, default="ollama", nullable=False)
    api_key = Column(String, nullable=True)              # legacy raw key (deprecated, no longer written)
    api_key_hash = Column(String, nullable=True)             # SHA-256 of agent key; preferred
    last_seen = Column(DateTime, nullable=True)
    total_hours = Column(Float, default=0.0, nullable=False)
    earnings_total = Column(Float, default=0.0, nullable=False)
    current_utilization = Column(Float, default=0.0, nullable=False)  # 0..1
    vram_used_gb = Column(Float, default=0.0, nullable=False)
    is_enabled = Column(Boolean, default=True, nullable=False)        # owner can pause
    description = Column(Text, nullable=True)
    allowed_models = Column(Text, nullable=True)                  # JSON whitelist; NULL = "all local, no cloud"
    # --- Phase 1: WebSocket connectivity tracking ------------------------
    connection_state = Column(String, default="disconnected", nullable=False)  # disconnected | connecting | connected
    last_ws_seen = Column(Float, nullable=True)                    # Unix timestamp; updated on every WS ping
    ws_session_id = Column(String, nullable=True)                  # UUID; one per active WS connection
    # --------------------------------------------------------------------
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    owner = relationship("User", back_populates="nodes")
    earnings = relationship("NodeEarning", back_populates="node", cascade="all, delete-orphan")
    jobs = relationship("PoolJob", back_populates="node", cascade="all, delete-orphan")

    # ---------- Model-whitelist helpers (mirror of User) ----------
    def get_allowed_models(self) -> Optional[List[str]]:
        if self.allowed_models is None:
            return None
        try:
            data = json.loads(self.allowed_models)
            if data is None:
                return None
            if isinstance(data, list):
                return [str(x) for x in data]
            return None
        except (json.JSONDecodeError, TypeError):
            return None

    def set_allowed_models(self, models: Optional[List[str]]) -> None:
        if models is None:
            self.allowed_models = None
        else:
            self.allowed_models = json.dumps(list(models))

    def can_serve_model(self, model: str) -> bool:
        """Authorization check for routing a job to this node."""
        if not model:
            return True
        is_cloud = _is_cloud_model_name(model)
        allowed = self.get_allowed_models()
        if allowed is None:
            return not is_cloud
        return model in allowed


class NodeHeartbeat(Base):
    """A single heartbeat sample from a node-agent.

    Kept for historical analysis (uptime, utilization charts) and to
    drive Prometheus-style exports. The router only looks at the
    most recent sample (via GpuNode.last_seen + current_utilization).
    """
    __tablename__ = "node_heartbeats"

    id = Column(Integer, primary_key=True, index=True)
    node_id = Column(Integer, ForeignKey("gpu_nodes.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String, nullable=False)              # online | busy | offline
    gpu_util = Column(Float, default=0.0, nullable=False)  # 0..1
    vram_used_gb = Column(Float, default=0.0, nullable=False)
    vram_total_gb = Column(Float, default=0.0, nullable=False)
    active_jobs = Column(Integer, default=0, nullable=False)
    raw_payload = Column(Text, nullable=True)            # JSON dump from the agent
    received_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    node = relationship("GpuNode")


class NodeEarning(Base):
    """One credit-distribution event for a job that ran on a community node.

    Splits the user-charged amount into three buckets:
      70% -> node owner
      20% -> platform (the User with email PLATFORM_OWNER_EMAIL, or a
             PlatformEarnings table; here we keep it simple: track on
             the node and expose via admin endpoints)
      10% -> community treasury (tracked as a global PlatformAccount row)

    The user is always charged the gross amount; the bookkeeping here
    is internal. The owner's `earnings_total` is the sum of these rows.
    """
    __tablename__ = "node_earnings"

    id = Column(Integer, primary_key=True, index=True)
    node_id = Column(Integer, ForeignKey("gpu_nodes.id", ondelete="CASCADE"), nullable=False, index=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    pool_job_id = Column(Integer, ForeignKey("pool_jobs.id", ondelete="SET NULL"), nullable=True)
    job_cost = Column(Float, nullable=False)             # what the requester paid
    owner_share = Column(Float, nullable=False)          # 0.70 * job_cost
    platform_share = Column(Float, nullable=False)       # 0.20 * job_cost
    treasury_share = Column(Float, nullable=False)       # 0.10 * job_cost
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    node = relationship("GpuNode", back_populates="earnings")
    owner = relationship("User", back_populates="node_earnings")


class PoolJob(Base):
    """A single request that the load-balancer routed to a community node.

    Stored for observability + fair-use analytics. We always record the
    final outcome (forwarded / overflowed / failed) and the source
    (local = the portal host, community = GpuNode, cloud = RunPod/Vast stub).
    """
    __tablename__ = "pool_jobs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    node_id = Column(Integer, ForeignKey("gpu_nodes.id", ondelete="SET NULL"), nullable=True, index=True)
    model = Column(String, nullable=False)
    source = Column(String, default="community", nullable=False)  # local | community | cloud
    status = Column(String, default="pending", nullable=False)    # pending | running | succeeded | failed
    prompt_tokens = Column(Integer, default=0, nullable=False)
    completion_tokens = Column(Integer, default=0, nullable=False)
    total_tokens = Column(Integer, default=0, nullable=False)
    job_cost = Column(Float, default=0.0, nullable=False)
    latency_ms = Column(Integer, default=0, nullable=False)
    error = Column(Text, nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    finished_at = Column(DateTime, nullable=True)

    node = relationship("GpuNode", back_populates="jobs")
    user = relationship("User")


class AdminAuditLog(Base):
    """Audit + idempotency record for admin-triggered mutations.

    One row per successful admin mutation. `idempotency_key` is unique when
    present, which is what makes admin POSTs replay-safe: a second request with
    the same key returns the stored `result` instead of mutating again.

    Secrets are never stored here: key-rotation results are whitelisted down to
    metadata before they are persisted (see admin.run_idempotent).
    """
    __tablename__ = "admin_audit_log"

    id = Column(Integer, primary_key=True, index=True)
    admin_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action = Column(String, nullable=False, index=True)       # user.create | user.update | user.topup | node.enable | ...
    target_type = Column(String, nullable=True)               # user | api_key | gpu_node
    target_id = Column(Integer, nullable=True, index=True)
    idempotency_key = Column(String, unique=True, nullable=True, index=True)
    payload = Column(Text, nullable=True)                     # JSON: request body (no secrets)
    result = Column(Text, nullable=True)                      # JSON: response echo (no secrets)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


def get_user_credits(db, user_id: int) -> float:
    """Sum of all credit transactions for a user."""
    from sqlalchemy import func
    total = db.query(func.coalesce(func.sum(CreditTransaction.amount), 0.0)).filter(
        CreditTransaction.user_id == user_id
    ).scalar()
    return float(total or 0.0)
