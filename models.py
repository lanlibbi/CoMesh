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


VALID_ROLES = ("provider", "consumer", "both")


class User(Base):
    """A platform user."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    password_hash = Column(String, nullable=True)  # PBKDF2-SHA256 (legacy sha256 accepted once, then upgraded)
    is_active = Column(Boolean, default=True, nullable=False)
    role = Column(String, default="both", nullable=False)        # provider | consumer | both | admin
    allowed_models = Column(Text, nullable=True)                 # JSON list or NULL = "all local, no cloud"
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

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
        Authorization check for a single model. Cloud models are blocked
        by default (None whitelist + cloud model = no).
        """
        if not model:
            return True
        m = model.lower()
        is_cloud = _is_cloud_model_name(model)
        allowed = self.get_allowed_models()
        if allowed is None:
            # Default: all local allowed, no cloud.
            return not is_cloud
        return model in allowed

    @property
    def allow_cloud(self) -> bool:
        """True if the user's whitelist explicitly contains at least one cloud model."""
        allowed = self.get_allowed_models()
        if not allowed:
            return False
        return any(_is_cloud_model_name(m) for m in allowed)


def _is_cloud_model_name(name: str) -> bool:
    """Heuristic: a model is 'cloud' if the name contains 'cloud'."""
    return "cloud" in (name or "").lower()


class ApiKey(Base):
    """An API key or session token for a user.

    Keys are stored hashed (`key_hash`); the raw value is shown once at
    creation. `token_type` separates long-lived API keys ("api_key") from
    short-lived login tokens ("session"). `expires_at` is NULL for tokens
    that do not expire (the default for API keys; see API_KEY_TTL_DAYS).
    """
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

    The owner is a User. The node exposes its Ollama-compatible API on
    a Tailscale-reachable IP:port. Heartbeats refresh `last_seen`;
    the pool router reads `status` to decide where to forward jobs.
    """
    __tablename__ = "gpu_nodes"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)                # "Living Room RTX 4090"
    gpu_type = Column(String, nullable=False)            # "RTX 4090", "A100 80GB", ...
    vram_gb = Column(Integer, nullable=False)            # total VRAM
    status = Column(String, default="offline", nullable=False)  # online | offline | busy
    hourly_rate = Column(Float, default=0.05, nullable=False)   # credits/hour charged to the user
    tailscale_ip = Column(String, nullable=True)         # 100.x.y.z
    port = Column(Integer, default=11434, nullable=False)
    # Inference backend this node exposes. "ollama" (default) talks Ollama's
    # /api/chat; "openai" talks any OpenAI-compatible server (LM Studio, LiteLLM, vLLM…).
    backend = Column(String, default="ollama", nullable=False)
    # Node-agent credential. `api_key_hash` is the SHA-256 of the raw key and is
    # authoritative; `api_key` is the legacy plaintext column kept only so
    # pre-existing deployments keep working until the agent is restarted with a
    # rotated key (see /nodes/{id}/rotate-key).
    api_key = Column(String, nullable=True)              # legacy plaintext (deprecated)
    api_key_hash = Column(String, nullable=True)         # SHA-256 of the agent key
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
    (local = ai-lanlibbi, community = GpuNode, cloud = RunPod/Vast stub).
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


def get_user_credits(db, user_id: int) -> float:
    """Sum of all credit transactions for a user."""
    from sqlalchemy import func
    total = db.query(func.coalesce(func.sum(CreditTransaction.amount), 0.0)).filter(
        CreditTransaction.user_id == user_id
    ).scalar()
    return float(total or 0.0)
