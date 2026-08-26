"""
GPU-Node management router.

Endpoints (all require a valid API key except where noted):

  POST   /nodes/register          Register a new node. Returns the node + agent api_key.
  GET    /nodes/list              List all enabled, online community nodes (public stats).
  GET    /nodes/my                List nodes owned by the caller.
  GET    /nodes/{id}              Single node detail (owner-only or public if online).
  POST   /nodes/{id}/heartbeat    Node-agent pushes status (auth: node.api_key).
  POST   /nodes/{id}/enable       Pause/resume a node.
  DELETE /nodes/{id}              Remove a node (owner-only).

The heartbeat endpoint is the "inbox" for the node-agent running on each
contributor's machine. It does NOT use the user API key — the node has
its own dedicated key issued at registration time. This way the user's
account key is never exposed to the agent process.
"""
import logging
import secrets
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Header, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from models import GpuNode, NodeHeartbeat, User

log = logging.getLogger("gpu-pool.nodes")

router = APIRouter(prefix="/nodes", tags=["nodes"])


# ----------------------------------------------------------------------------
# Schemas
# ----------------------------------------------------------------------------
class RegisterNodeRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=80)
    gpu_type: str = Field(..., min_length=2, max_length=80)
    vram_gb: int = Field(..., ge=1, le=1024)
    hourly_rate: float = Field(0.05, ge=0.0, le=10.0)
    tailscale_ip: Optional[str] = Field(None, description="100.x.y.z — Tailscale IP of the node")
    port: int = Field(11434, ge=1, le=65535)
    backend: str = Field("ollama", pattern="^(ollama|openai)$", description="Inference backend: ollama (native /api/chat) or openai (OpenAI-compatible: LM Studio, LiteLLM, vLLM…)")
    description: Optional[str] = None
    allowed_models: Optional[List[str]] = Field(
        None,
        description="JSON list of model names this node will share. NULL = all local, no cloud.",
    )


class UpdateNodeRequest(BaseModel):
    """Partial update for an existing node (owner only)."""
    name: Optional[str] = Field(None, min_length=2, max_length=80)
    gpu_type: Optional[str] = Field(None, min_length=2, max_length=80)
    vram_gb: Optional[int] = Field(None, ge=1, le=1024)
    hourly_rate: Optional[float] = Field(None, ge=0.0, le=10.0)
    tailscale_ip: Optional[str] = None
    port: Optional[int] = Field(None, ge=1, le=65535)
    backend: Optional[str] = Field(None, pattern="^(ollama|openai)$")
    description: Optional[str] = None
    allowed_models: Optional[List[str]] = None  # NULL clears the whitelist


class HeartbeatRequest(BaseModel):
    status: str = Field("online", pattern="^(online|busy|offline)$")
    gpu_util: float = Field(0.0, ge=0.0, le=1.0)
    vram_used_gb: float = Field(0.0, ge=0.0, le=1024)
    vram_total_gb: Optional[float] = None
    active_jobs: int = Field(0, ge=0, le=64)
    raw: Optional[dict] = None  # arbitrary agent-side stats


class NodeOut(BaseModel):
    id: int
    owner_id: int
    name: str
    gpu_type: str
    vram_gb: int
    status: str
    hourly_rate: float
    tailscale_ip: Optional[str]
    port: int
    backend: str = "ollama"
    last_seen: Optional[str]
    total_hours: float
    earnings_total: float
    current_utilization: float
    vram_used_gb: float
    is_enabled: bool
    description: Optional[str]
    allowed_models: Optional[List[str]] = None
    created_at: str

    class Config:
        from_attributes = True


class NodeRegistered(NodeOut):
    """Registration response — includes the agent API key (shown once)."""
    agent_api_key: str


class PoolStats(BaseModel):
    total_nodes: int
    online_nodes: int
    total_vram_gb: int
    available_vram_gb: int
    avg_utilization: float
    lowest_rate: Optional[float]
    highest_rate: Optional[float]


# ----------------------------------------------------------------------------
# Auth: node-agent uses its own key in `X-Node-Key`
# ----------------------------------------------------------------------------
def _get_node_from_header(
    node_id: int,
    x_node_key: Optional[str] = Header(default=None, alias="X-Node-Key"),
    db: Session = Depends(get_db),
) -> GpuNode:
    if not x_node_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Node-Key header (issued at /nodes/register).",
        )
    node = db.query(GpuNode).filter(GpuNode.id == node_id).first()
    if not node or node.api_key != x_node_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid node credentials.",
        )
    return node


# ----------------------------------------------------------------------------
# Online-detection helpers
# ----------------------------------------------------------------------------
ONLINE_GRACE = timedelta(seconds=90)  # last_seen within 90s => online


def _is_online(node: GpuNode) -> bool:
    return (
        node.is_enabled
        and node.last_seen is not None
        and (datetime.utcnow() - node.last_seen) < ONLINE_GRACE
        and node.status in ("online", "busy")
    )


# ----------------------------------------------------------------------------
# Endpoints
# ----------------------------------------------------------------------------
@router.post("/register", response_model=NodeRegistered, status_code=201)
def register_node(
    req: RegisterNodeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Register a new GPU node. The caller becomes the owner."""
    if user.role == "consumer":
        raise HTTPException(
            status_code=403,
            detail="Your role is 'consumer' — switch to 'provider' or 'both' in your profile to register nodes.",
        )
    agent_key = f"node_{secrets.token_urlsafe(24)}"
    node = GpuNode(
        owner_id=user.id,
        name=req.name,
        gpu_type=req.gpu_type,
        vram_gb=req.vram_gb,
        hourly_rate=req.hourly_rate,
        tailscale_ip=req.tailscale_ip,
        port=req.port,
        backend=req.backend,
        description=req.description,
        api_key=agent_key,
        status="offline",
    )
    if req.allowed_models is not None:
        node.set_allowed_models(req.allowed_models)
    db.add(node)
    db.commit()
    db.refresh(node)
    log.info(f"User {user.email} registered node '{node.name}' id={node.id} (gpu={node.gpu_type}, vram={node.vram_gb}GB, models={node.get_allowed_models()})")
    return NodeRegistered(
        id=node.id,
        owner_id=node.owner_id,
        name=node.name,
        gpu_type=node.gpu_type,
        vram_gb=node.vram_gb,
        status=node.status,
        hourly_rate=node.hourly_rate,
        tailscale_ip=node.tailscale_ip,
        port=node.port,
        last_seen=node.last_seen.isoformat() if node.last_seen else None,
        total_hours=node.total_hours,
        earnings_total=node.earnings_total,
        current_utilization=node.current_utilization,
        vram_used_gb=node.vram_used_gb,
        is_enabled=node.is_enabled,
        description=node.description,
        allowed_models=node.get_allowed_models(),
        created_at=node.created_at.isoformat(),
        agent_api_key=agent_key,
    )


@router.put("/{node_id}", response_model=NodeOut)
def update_node(
    node_id: int,
    req: UpdateNodeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Partial update of a node's metadata + model whitelist (owner only)."""
    node = db.query(GpuNode).filter(GpuNode.id == node_id, GpuNode.owner_id == user.id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found or not owned by you")
    if req.name is not None:
        node.name = req.name
    if req.gpu_type is not None:
        node.gpu_type = req.gpu_type
    if req.vram_gb is not None:
        node.vram_gb = req.vram_gb
    if req.hourly_rate is not None:
        node.hourly_rate = req.hourly_rate
    if req.tailscale_ip is not None:
        node.tailscale_ip = req.tailscale_ip
    if req.port is not None:
        node.port = req.port
    if req.backend is not None:
        node.backend = req.backend
    if req.description is not None:
        node.description = req.description
    if req.allowed_models is not None:
        node.set_allowed_models(req.allowed_models)
    db.commit()
    db.refresh(node)
    log.info(f"User {user.email} updated node {node.id}: models={node.get_allowed_models()}")
    return NodeOut(
        id=node.id, owner_id=node.owner_id, name=node.name, gpu_type=node.gpu_type,
        vram_gb=node.vram_gb, status=node.status if _is_online(node) else "offline",
        hourly_rate=node.hourly_rate, tailscale_ip=node.tailscale_ip, port=node.port,
        backend=node.backend,
        last_seen=node.last_seen.isoformat() if node.last_seen else None,
        total_hours=node.total_hours, earnings_total=node.earnings_total,
        current_utilization=node.current_utilization, vram_used_gb=node.vram_used_gb,
        is_enabled=node.is_enabled, description=node.description,
        allowed_models=node.get_allowed_models(),
        created_at=node.created_at.isoformat(),
    )


@router.get("/list", response_model=List[NodeOut])
def list_nodes(
    only_online: bool = True,
    db: Session = Depends(get_db),
):
    """Public list of community nodes. `only_online=true` filters by recent heartbeat."""
    q = db.query(GpuNode).filter(GpuNode.is_enabled == True)
    nodes = q.all()
    out: List[NodeOut] = []
    for n in nodes:
        online = _is_online(n)
        if only_online and not online:
            continue
        out.append(NodeOut(
            id=n.id,
            owner_id=n.owner_id,
            name=n.name,
            gpu_type=n.gpu_type,
            vram_gb=n.vram_gb,
            status="online" if online else n.status,
            hourly_rate=n.hourly_rate,
            tailscale_ip=n.tailscale_ip,
            port=n.port,
            backend=n.backend,
            last_seen=n.last_seen.isoformat() if n.last_seen else None,
            total_hours=n.total_hours,
            earnings_total=n.earnings_total,
            current_utilization=n.current_utilization if online else 0.0,
            vram_used_gb=n.vram_used_gb if online else 0.0,
            is_enabled=n.is_enabled,
            description=n.description,
            allowed_models=n.get_allowed_models(),
            created_at=n.created_at.isoformat(),
        ))
    return out


@router.get("/my", response_model=List[NodeOut])
def my_nodes(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    nodes = db.query(GpuNode).filter(GpuNode.owner_id == user.id).all()
    return [
        NodeOut(
            id=n.id,
            owner_id=n.owner_id,
            name=n.name,
            gpu_type=n.gpu_type,
            vram_gb=n.vram_gb,
            status=n.status if _is_online(n) else "offline",
            hourly_rate=n.hourly_rate,
            tailscale_ip=n.tailscale_ip,
            port=n.port,
            backend=n.backend,
            last_seen=n.last_seen.isoformat() if n.last_seen else None,
            total_hours=n.total_hours,
            earnings_total=n.earnings_total,
            current_utilization=n.current_utilization,
            vram_used_gb=n.vram_used_gb,
            is_enabled=n.is_enabled,
            description=n.description,
            allowed_models=n.get_allowed_models(),
            created_at=n.created_at.isoformat(),
        )
        for n in nodes
    ]


@router.get("/{node_id}", response_model=NodeOut)
def get_node(node_id: int, db: Session = Depends(get_db)):
    node = db.query(GpuNode).filter(GpuNode.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return NodeOut(
        id=node.id,
        owner_id=node.owner_id,
        name=node.name,
        gpu_type=node.gpu_type,
        vram_gb=node.vram_gb,
        status=node.status if _is_online(node) else "offline",
        hourly_rate=node.hourly_rate,
        tailscale_ip=node.tailscale_ip,
        port=node.port,
        backend=node.backend,
        last_seen=node.last_seen.isoformat() if node.last_seen else None,
        total_hours=node.total_hours,
        earnings_total=node.earnings_total,
        current_utilization=node.current_utilization,
        vram_used_gb=node.vram_used_gb,
        is_enabled=node.is_enabled,
        description=node.description,
        allowed_models=node.get_allowed_models(),
        created_at=node.created_at.isoformat(),
    )


@router.post("/{node_id}/heartbeat", status_code=204)
def heartbeat(
    node_id: int,
    req: HeartbeatRequest,
    node: GpuNode = Depends(_get_node_from_header),
    db: Session = Depends(get_db),
):
    """Node-agent pushes a status update. Authenticated via X-Node-Key."""
    if node.id != node_id:
        raise HTTPException(status_code=404, detail="Node id mismatch")

    # Update live state
    node.status = req.status
    node.current_utilization = req.gpu_util
    node.vram_used_gb = req.vram_used_gb
    node.last_seen = datetime.utcnow()

    # Persist a history row
    import json
    db.add(NodeHeartbeat(
        node_id=node.id,
        status=req.status,
        gpu_util=req.gpu_util,
        vram_used_gb=req.vram_used_gb,
        vram_total_gb=req.vram_total_gb or float(node.vram_gb),
        active_jobs=req.active_jobs,
        raw_payload=json.dumps(req.raw) if req.raw else None,
    ))
    db.commit()
    # 204 No Content — agent should not need a body
    return


@router.post("/{node_id}/enable")
def enable_node(
    node_id: int,
    enabled: bool = True,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    node = db.query(GpuNode).filter(GpuNode.id == node_id, GpuNode.owner_id == user.id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found or not owned by you")
    node.is_enabled = enabled
    db.commit()
    return {"id": node.id, "is_enabled": node.is_enabled}


@router.delete("/{node_id}", status_code=204)
def delete_node(
    node_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    node = db.query(GpuNode).filter(GpuNode.id == node_id, GpuNode.owner_id == user.id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found or not owned by you")
    db.delete(node)
    db.commit()
    return


# ----------------------------------------------------------------------------
# Community pool stats (used by /pool dashboard)
# ----------------------------------------------------------------------------
@router.get("/stats/summary", response_model=PoolStats)
def pool_stats(db: Session = Depends(get_db)):
    nodes = db.query(GpuNode).filter(GpuNode.is_enabled == True).all()
    online = [n for n in nodes if _is_online(n)]
    total_vram = sum(n.vram_gb for n in online)
    avail_vram = sum(max(0.0, n.vram_gb - n.vram_used_gb) for n in online)
    avg_util = (
        sum(n.current_utilization for n in online) / len(online) if online else 0.0
    )
    rates = [n.hourly_rate for n in online]
    return PoolStats(
        total_nodes=len(nodes),
        online_nodes=len(online),
        total_vram_gb=total_vram,
        available_vram_gb=int(avail_vram),
        avg_utilization=round(avg_util, 3),
        lowest_rate=min(rates) if rates else None,
        highest_rate=max(rates) if rates else None,
    )
