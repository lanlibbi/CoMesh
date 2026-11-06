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
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth import get_current_user, generate_node_key, verify_node_key, hash_api_key
from ratelimit import limit_node
from database import get_db
from models import GpuNode, NodeHeartbeat, User
from netinfo import (
    DEFAULT_AGENT_PORT,
    derive_node_url,
    is_auto_url,
    node_base_url,
    normalize_node_url,
    source_host,
)

log = logging.getLogger("gpu-pool.nodes")

router = APIRouter(prefix="/nodes", tags=["nodes"])


# ----------------------------------------------------------------------------
# Schemas
# ----------------------------------------------------------------------------
class RegisterNodeRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=80)
    gpu_type: str = Field(..., min_length=2, max_length=80)
    vram_gb: int = Field(..., ge=1, le=1024)
    # Herkunft der VRAM-Zahl, wie der Agent sie meldet. "assumed" = keine GPU
    # erkannt und NODE_VRAM_GB nicht gesetzt; das Portal zeigt das als Hinweis
    # an, weil genau dieser Fall die Node stumm auftragslos macht.
    vram_source: Optional[str] = Field(
        None, pattern="^(detected|override|assumed)$",
        description="detected | override (NODE_VRAM_GB) | assumed (1 GB angenommen)",
    )
    hourly_rate: float = Field(0.05, ge=0.0, le=10.0)
    # Reachability of the agent. Optional on purpose: an agent on DHCP can
    # register without knowing its own address — the portal derives it from the
    # first heartbeat (see netinfo.derive_node_url) and stores it back.
    node_url: Optional[str] = Field(
        None,
        description="http(s)://<host|ip>[:port] of the node-agent. Prefer a DNS/mDNS name; "
                    "leave empty to let the portal auto-detect it from the heartbeat.",
    )
    # Deprecated alias kept so existing scripts/UI builds keep working. It is
    # folded into `node_url` at registration time.
    tailscale_ip: Optional[str] = Field(None, description="Deprecated — use node_url")
    port: int = Field(DEFAULT_AGENT_PORT, ge=1, le=65535)
    backend: str = Field("ollama", pattern="^(ollama|openai)$", description="Inference backend: ollama (native /api/chat) or openai (OpenAI-compatible: LM Studio, LiteLLM, vLLM…)")
    description: Optional[str] = None
    allowed_models: Optional[List[str]] = Field(
        None,
        description="JSON list of model names this node will share. NULL = all local, no cloud.",
    )


class UpdateNodeRequest(BaseModel):
    """Partial update for an existing node (owner or admin)."""
    name: Optional[str] = Field(None, min_length=2, max_length=80)
    gpu_type: Optional[str] = Field(None, min_length=2, max_length=80)
    vram_gb: Optional[int] = Field(None, ge=1, le=1024)
    hourly_rate: Optional[float] = Field(None, ge=0.0, le=10.0)
    node_url: Optional[str] = None
    tailscale_ip: Optional[str] = Field(None, description="Deprecated — use node_url")
    port: Optional[int] = Field(None, ge=1, le=65535)
    backend: Optional[str] = Field(None, pattern="^(ollama|openai)$")
    description: Optional[str] = None
    allowed_models: Optional[List[str]] = None  # [] = nothing; see clear_allowed_models
    # NULL (= alle lokalen Modelle, keine Cloud) ist kein gueltiger JSON-Wert in
    # einer Liste. Ohne dieses Kennzeichen kaeme ein Formular nie von einer
    # Freigabeliste zurueck auf "Standard".
    clear_allowed_models: bool = Field(
        False, description="Setzt allowed_models auf NULL: alle lokalen Modelle, keine Cloud."
    )
    hide_owner: Optional[bool] = Field(
        None, description="Besitzer im Adminbereich anonymisieren"
    )
    availability: Optional[str] = Field(
        None, pattern="^(always|partial)$",
        description="always = Dauerbetrieb, partial = nur zeitweise verfügbar",
    )


class HeartbeatRequest(BaseModel):
    status: str = Field("online", pattern="^(online|offline|busy)$")
    gpu_util: float = Field(0.0, ge=0.0, le=1.0)
    vram_used_gb: float = Field(0.0, ge=0.0, le=1024)
    vram_total_gb: Optional[float] = None
    # Der Agent wiederholt hier seine gemeldete VRAM-Zahl samt Herkunft. Ein
    # gesetztes NODE_VRAM_GB (source=override) ueberschreibt den Portalwert —
    # sonst bliebe eine Node auf 1 GB stehen, auch nachdem der Betreiber den
    # Wert nachgetragen hat.
    vram_gb: Optional[int] = Field(None, ge=1, le=1024)
    vram_source: Optional[str] = Field(None, pattern="^(detected|override|assumed)$")
    active_jobs: int = Field(0, ge=0, le=64)
    # Address the agent believes it is reachable under (ADVERTISE_HOST, else its
    # detected outbound IP/hostname). The portal adopts it only while the node
    # has no explicitly configured URL — that is the DHCP-friendly path.
    advertise_host: Optional[str] = Field(
        None, description="Host (name or IP) the agent is reachable under; usually auto-detected."
    )
    agent_port: Optional[int] = Field(None, ge=1, le=65535, description="Port the agent serves on")
    # Modelle, die der Agent in **seinem** Backend gefunden hat. Damit kann ein
    # Provider Modelle anbieten, die der zentrale Katalog des Portals nicht kennt.
    # `null` heisst: Abfrage fehlgeschlagen — dann bleibt die zuletzt gemeldete
    # Liste stehen, statt eine Node faelschlich auf "kann nichts" zu setzen.
    models: Optional[List[str]] = Field(
        None, description="Modelle, die das Backend dieser Node anbietet (Agent-Sicht)."
    )
    raw: Optional[dict] = None  # arbitrary agent-side stats


class NodeOut(BaseModel):
    id: int
    owner_id: int
    name: str
    gpu_type: str
    vram_gb: int
    vram_source: str = ""
    status: str
    hourly_rate: float
    node_url: Optional[str]
    node_url_auto: bool = False
    # Deprecated mirror of the host part of `node_url`, kept for older UI builds.
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
    # Was die Node selbst als vorhanden gemeldet hat (Agent-Sicht). NULL = unbekannt.
    reported_models: Optional[List[str]] = None
    reported_models_at: Optional[str] = None
    hide_owner: bool = False
    availability: str = "always"
    created_at: str

    class Config:
        from_attributes = True


class NodePublicOut(BaseModel):
    id: int
    name: str
    gpu_type: str
    vram_gb: int
    vram_source: str = ""
    status: str
    hourly_rate: float
    backend: str = "ollama"
    last_seen: Optional[str]
    current_utilization: float
    vram_used_gb: float
    description: Optional[str]
    allowed_models: Optional[List[str]] = None
    availability: str = "always"
    created_at: str



def node_out_fields(node: GpuNode) -> dict:
    """Serialize a node for the API.

    ``tailscale_ip`` stays in the payload as a deprecated mirror of the host
    part of ``node_url``: older frontend builds render it, and the legacy
    pool-dispatch fallback still reads it. Nothing writes it any more.
    """
    from netinfo import host_of

    return {
        "id": node.id,
        "owner_id": node.owner_id,
        "name": node.name,
        "gpu_type": node.gpu_type,
        "vram_gb": node.vram_gb,
        "vram_source": getattr(node, "vram_source", None) or "",
        "status": node.status,
        "hourly_rate": node.hourly_rate,
        "node_url": node.node_url,
        "node_url_auto": bool(node.node_url_auto),
        "tailscale_ip": host_of(node.node_url or "") or node.tailscale_ip,
        "port": node.port,
        "backend": node.backend or "ollama",
        "last_seen": node.last_seen.isoformat() if node.last_seen else None,
        "total_hours": node.total_hours,
        "earnings_total": node.earnings_total,
        "current_utilization": node.current_utilization,
        "vram_used_gb": node.vram_used_gb,
        "is_enabled": bool(node.is_enabled),
        "description": node.description,
        "allowed_models": node.get_allowed_models(),
    # getattr: alte Zeilen aus der Zeit vor der Migration haben die Spalten noch nicht.
    "hide_owner": bool(getattr(node, "hide_owner", False)),
    "availability": getattr(node, "availability", None) or "always",
    "reported_models": node.get_reported_models(),
    "reported_models_at": (
        node.reported_models_at.isoformat()
        if getattr(node, "reported_models_at", None) else None
    ),
    "created_at": node.created_at.isoformat(),
    }


def resolve_node_url(req_url: Optional[str], legacy_ip: Optional[str], port: int) -> Optional[str]:
    """Explicit URL wins; otherwise a legacy `tailscale_ip` is promoted to one."""
    explicit = normalize_node_url(req_url, default_port=None)
    if explicit:
        return explicit
    legacy = (legacy_ip or "").strip()
    if legacy:
        return normalize_node_url(legacy, default_port=None)
    return None


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


def _node_is_owner_or_admin(node: GpuNode, user: Optional[User]) -> bool:
    if user is None:
        return False
    if getattr(user, "role", None) == "admin":
        return True
    return node.owner_id == user.id

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
    if not node or not verify_node_key(x_node_key, node.api_key_hash, node.api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid node credentials.",
        )
    if not node.is_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Node is disabled by its owner.",
        )
    # one-time migration of legacy plaintext keys
    if not node.api_key_hash and node.api_key:
        node.api_key_hash = hash_api_key(x_node_key)
        node.api_key = None
        db.commit()
    return node


# ----------------------------------------------------------------------------
# Online-detection helpers
# ----------------------------------------------------------------------------
ONLINE_GRACE = timedelta(seconds=90)  # last_seen within 90s => online


def _is_online(node: GpuNode) -> bool:
    if not node.is_enabled:
        return False
    # WS-Verbindung zaehlt wie ein HTTP-Heartbeat (models.ws_is_alive).
    if node.ws_is_alive():
        return True
    return (
        node.last_seen is not None
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
    limit_node(user.id)
    agent_key, agent_key_hash, _prefix = generate_node_key()
    node = GpuNode(
        owner_id=user.id,
        name=req.name,
        gpu_type=req.gpu_type,
        vram_gb=req.vram_gb,
        vram_source=req.vram_source,
        hourly_rate=req.hourly_rate,
        node_url=resolve_node_url(req.node_url, req.tailscale_ip, req.port),
        node_url_auto=False,
        port=req.port,
        backend=req.backend,
        description=req.description,
        api_key=None,
        api_key_hash=agent_key_hash,
        status="offline",
    )
    if req.allowed_models is not None:
        node.set_allowed_models(req.allowed_models)
    db.add(node)
    db.commit()
    db.refresh(node)
    log.info(f"User {user.email} registered node '{node.name}' id={node.id} (gpu={node.gpu_type}, vram={node.vram_gb}GB, addr={node.node_url or 'auto'}, models={node.get_allowed_models()})")
    return NodeRegistered(**node_out_fields(node), agent_api_key=agent_key)


@router.put("/{node_id}", response_model=NodeOut)
def update_node(
    node_id: int,
    req: UpdateNodeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Partial update of a node's metadata + model whitelist.

    Berechtigt sind **der Eigentümer der Node und Administratoren**. Der
    Eigentümer pflegt damit selbst, welche Modelle seine Maschine anderen
    anbietet (`allowed_models`) — das ist eine Entscheidung des Providers, nicht
    der Administration. Ein Fremder bekommt 404 (nicht 403: die Node geht ihn
    nichts an, und die Antwort soll nicht verraten, dass es sie gibt).

    Die Rechte bleiben auf **diese eine Node** beschränkt: Freischalten
    (`/enable`), Löschen und Schlüsselwechsel haben eigene Endpunkte mit eigener
    Prüfung; `owner_id` ist nicht Teil der Anfrage und lässt sich hier nicht
    umhängen.
    """
    node = db.query(GpuNode).filter(GpuNode.id == node_id).first()
    if not node or not _node_is_owner_or_admin(node, user):
        raise HTTPException(status_code=404, detail="Node not found or not owned by you")
    if req.name is not None:
        node.name = req.name
    if req.gpu_type is not None:
        node.gpu_type = req.gpu_type
    if req.vram_gb is not None:
        node.vram_gb = req.vram_gb
    if req.hourly_rate is not None:
        node.hourly_rate = req.hourly_rate
    # An explicit address (or the deprecated tailscale_ip alias) clears the
    # auto-detected flag; leaving both empty switches the node back to
    # auto-detect on the next heartbeat.
    if req.node_url is not None or req.tailscale_ip is not None:
        resolved = resolve_node_url(req.node_url, req.tailscale_ip, req.port or node.port)
        node.node_url = resolved
        node.node_url_auto = False
    if req.port is not None:
        node.port = req.port
    if req.backend is not None:
        node.backend = req.backend
    if req.description is not None:
        node.description = req.description
    if req.allowed_models is not None:
        # Leere Liste heisst "nichts freigeben" und wird bewusst geschrieben;
        # "alle lokalen" ist NULL und laesst sich nur ueber `clear_allowed_models`
        # setzen (sonst käme man mit einem Formular nie dorthin zurück).
        node.set_allowed_models(req.allowed_models)
    if req.clear_allowed_models:
        node.allowed_models = None
    if req.hide_owner is not None:
        node.hide_owner = bool(req.hide_owner)
    if req.availability is not None:
        node.availability = req.availability
    db.commit()
    db.refresh(node)
    log.info(
        f"User {user.email} (role={user.role}) updated node {node.id}: "
        f"addr={node.node_url or 'auto'}, models={node.get_allowed_models()}"
    )
    fields = node_out_fields(node)
    if not _is_online(node):
        fields["status"] = "offline"
    return NodeOut(**fields)


@router.post("/{node_id}/rotate-key")
def rotate_node_key(
    node_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    node = db.query(GpuNode).filter(GpuNode.id == node_id).first()
    if not node or not _node_is_owner_or_admin(node, user):
        raise HTTPException(status_code=404, detail="Node not found or not owned by you")

    raw_key, key_hash, key_prefix = generate_node_key()
    node.api_key_hash = key_hash
    node.api_key = None
    db.commit()
    log.info(f"Node {node.id} agent key rotated by user {user.id} (prefix {key_prefix})")
    return {
        "id": node.id,
        "agent_api_key": raw_key,
        "key_prefix": key_prefix,
        "note": "Restart the node-agent with this key; the previous key is now invalid.",
    }


@router.get("/list", response_model=List[NodePublicOut])
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
        out.append(NodePublicOut(
            id=n.id,
            name=n.name,
            gpu_type=n.gpu_type,
            vram_gb=n.vram_gb,
            vram_source=getattr(n, "vram_source", None) or "",
            status="online" if online else n.status,
            hourly_rate=n.hourly_rate,
            backend=n.backend or "ollama",
            last_seen=n.last_seen.isoformat() if n.last_seen else None,
            current_utilization=n.current_utilization if online else 0.0,
            vram_used_gb=n.vram_used_gb if online else 0.0,
            description=n.description,
            allowed_models=n.get_allowed_models(),
            # Betriebsart gehört in den öffentlichen Katalog: sie sagt, ob die Maschine
            # im Dauerbetrieb läuft oder nur zeitweise erreichbar ist.
            availability=getattr(n, "availability", None) or "always",
            created_at=n.created_at.isoformat(),
        ))
    return out


@router.get("/my", response_model=List[NodeOut])
def my_nodes(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    nodes = db.query(GpuNode).filter(GpuNode.owner_id == user.id).all()
    out: List[NodeOut] = []
    for n in nodes:
        fields = node_out_fields(n)
        if not _is_online(n):
            fields["status"] = "offline"
        out.append(NodeOut(**fields))
    return out


@router.get("/{node_id}", response_model=NodeOut)
def get_node(node_id: int, db: Session = Depends(get_db)):
    node = db.query(GpuNode).filter(GpuNode.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    fields = node_out_fields(node)
    if not _is_online(node):
        fields["status"] = "offline"
    return NodeOut(**fields)


@router.post("/{node_id}/heartbeat", status_code=204)
def heartbeat(
    node_id: int,
    req: HeartbeatRequest,
    request: Request,
    node: GpuNode = Depends(_get_node_from_header),
    db: Session = Depends(get_db),
):
    """Node-agent pushes a status update. Authenticated via X-Node-Key.

    Also the point where the portal learns a *node address* it was never told:
    when the node has no explicitly configured ``node_url``, the address is
    taken from the request (X-Real-IP / X-Forwarded-For from the reverse proxy,
    else the socket peer) and stored as an auto-detected URL. A DHCP lease change
    therefore fixes itself — the agent does not need to know its own address and
    nothing has to be kept in sync by hand.
    """
    if node.id != node_id:
        raise HTTPException(status_code=404, detail="Node id mismatch")

    # --- address auto-detection (LANA-89) ---------------------------------
    if not node.node_url or node.node_url_auto:
        scheme = request.headers.get("x-forwarded-proto", "http").split(",")[0].strip() or "http"
        advertised = (req.advertise_host or "").strip()
        if advertised:
            # The agent says how it can be reached (ADVERTISE_HOST, else the
            # outbound IP it detected). Preferred over the packet source, which
            # is a NAT/proxy address on many home setups.
            candidate = normalize_node_url(
                advertised, default_scheme=scheme, default_port=req.agent_port or node.port
            )
        else:
            peer = source_host(request)
            if peer and peer.startswith(("10.", "172.", "192.168.", "169.254.", "127.")):
                # A private/loopback peer address is a dead end for the portal:
                # the agent sits behind NAT, or the portal is being called from
                # the same host. Keep whatever we have and wait for an
                # advertise_host from the agent.
                candidate = None
            else:
                candidate = derive_node_url(peer or "", req.agent_port or node.port, scheme=scheme)
        if candidate:
            node.node_url = candidate
            node.node_url_auto = True
    if req.agent_port:
        node.port = req.agent_port

    # VRAM-Herkunft mitschreiben. Ein ausdrueckliches NODE_VRAM_GB (override)
    # gewinnt gegen den gespeicherten Wert: so kommt eine Node aus der
    # 1-GB-Falle, ohne dass jemand die Geräteseite bearbeiten muss.
    if req.vram_source:
        node.vram_source = req.vram_source
        if req.vram_source == "override" and req.vram_gb:
            node.vram_gb = int(req.vram_gb)

    # Update live state
    node.status = req.status
    node.current_utilization = req.gpu_util
    node.vram_used_gb = req.vram_used_gb
    node.last_seen = datetime.utcnow()

    # Modelle, die der Agent in seinem eigenen Backend gefunden hat. Sie sind die
    # einzige Quelle fuer Modelle, die der zentrale Katalog nicht fuehrt. Ein
    # `null` (Abfrage beim Agenten fehlgeschlagen) laesst die letzte Meldung stehen;
    # eine leere Liste bedeutet "nichts gefunden" und wird als solche gespeichert.
    if req.models is not None:
        sauber: List[str] = []
        for eintrag in req.models[:200]:
            name = str(eintrag).strip()[:200]
            if name and name not in sauber:
                sauber.append(name)
        node.set_reported_models(sauber)
        node.reported_models_at = datetime.utcnow()

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
