# Architektur

Dieses Dokument beschreibt die Architektur des CoMesh-POC im Detail: Komponenten, Datenmodell, Entscheidungen und Trade-offs.

## Design-Prinzipien

1. **OpenAI-API-kompatibel** — Clients sollen den Pool wie jeden anderen OpenAI-Endpoint ansprechen können.
2. **Dezentral, aber zentral koordiniert** — Node-Agents laufen unabhängig, das Portal kennt aber alle Nodes und verteilt.
3. **Stateless Portal** — Load-Balancing-Logik und State nur in der DB, Portal selbst ist horizontal skalierbar.
4. **Kein festes Netz** — Kein Port-Forwarding, keine Public-IPs, keine
   Annahme über IP-Bereiche. Ein Node wird über `node_url` angesprochen
   (DNS/mDNS-Name, LAN-IP oder Mesh-VPN-Name); ein DHCP-Netz genügt.

## Komponenten

### Portal

Das Portal ist die zentrale API-Instanz. Es hat drei Hauptaufgaben:

1. **Inference-Proxying** (`/v1/chat/completions`)
2. **Pool-Management** (`/pool/*`) — Node-Auswahl, Load-Balancing, Earnings
3. **Node-Management** (`/nodes/*`) — Registrierung, Heartbeats, CRUD

**Tech:** Python 3.11, FastAPI, SQLAlchemy, Uvicorn, Jinja2.

**Verzeichnisstruktur (im POC):**
```
portal/
├── main.py             # FastAPI-App, Routes
├── models.py           # SQLAlchemy Models
├── pool.py             # Load-Balancing-Logik
├── nodes.py            # Node-Management-Endpoints
├── earnings.py         # Earnings-Tracking
├── db.py               # DB-Setup
├── templates/          # Jinja2-Templates
│   ├── nodes.html
│   ├── pool.html
│   ├── earnings.html
│   └── agent.html
└── docker-compose.yml
```

### Node-Agent

Leichtgewichtiger Python-Container, der auf Contributors-Hosts läuft.

**Verantwortlichkeiten:**
- Hardware-Metriken sammeln (CPU, RAM, GPU-Auslastung, VRAM)
- Heartbeats ans Portal senden
- Inference-Requests vom Portal entgegennehmen und an lokales Ollama weiterleiten

**Tech:** Python 3.11, `psutil` (System-Metriken), `pynvml` (NVIDIA-GPU), `httpx` (Async-HTTP).

**Verzeichnisstruktur:**
```
node-agent/
├── agent.py            # Main loop
├── requirements.txt
├── Dockerfile
├── .env.example
└── docker-compose.yml
```

## Datenmodell

```python
# models.py (Auszug)

class GpuNode(Base):
    __tablename__ = "gpu_nodes"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    node_url: Mapped[Optional[str]]        # http(s)://host[:port]; NULL = noch unbekannt
    node_url_auto: Mapped[bool]            # true = aus dem Heartbeat abgeleitet
    port: Mapped[int] = mapped_column(default=8080)
    gpu_model: Mapped[Optional[str]]
    vram_gb: Mapped[Optional[int]]
    price_per_1k_tokens: Mapped[float] = mapped_column(default=0.001)
    enabled: Mapped[bool] = mapped_column(default=True)
    last_seen: Mapped[Optional[datetime]]
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

class NodeHeartbeat(Base):
    __tablename__ = "node_heartbeats"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("gpu_nodes.id"), index=True)
    timestamp: Mapped[datetime] = mapped_column(default=datetime.utcnow, index=True)
    cpu_pct: Mapped[float]
    ram_pct: Mapped[float]
    gpu_util_pct: Mapped[Optional[float]]
    vram_used_gb: Mapped[Optional[float]]

class NodeEarning(Base):
    __tablename__ = "node_earnings"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("gpu_nodes.id"), index=True)
    timestamp: Mapped[datetime] = mapped_column(default=datetime.utcnow, index=True)
    tokens_in: Mapped[int]
    tokens_out: Mapped[int]
    amount_usd: Mapped[float]

class PoolJob(Base):
    __tablename__ = "pool_jobs"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[str] = mapped_column(unique=True, index=True)
    node_id: Mapped[Optional[int]] = mapped_column(ForeignKey("gpu_nodes.id"))
    model: Mapped[str]
    started_at: Mapped[datetime]
    finished_at: Mapped[Optional[datetime]]
    status: Mapped[str]  # "running" | "success" | "error" | "timeout"
    error: Mapped[Optional[str]]
```

## Load-Balancing-Algorithmus

```python
# pool.py (Kern-Logik)

def find_best_node(model: str) -> Optional[GpuNode]:
    """
    Wählt den besten Node für ein Model.
    
    Scoring:
      1. Node muss enabled sein und last_seen < 30s
      2. Node muss das Model lokal haben (POC: alle Nodes haben alles)
      3. Niedrigster aktueller Load (avg GPU util der letzten Heartbeats)
      4. Tiebreak: niedrigster Preis
    """
    candidates = (
        session.query(GpuNode)
        .filter(
            GpuNode.enabled == True,
            GpuNode.last_seen > datetime.utcnow() - timedelta(seconds=30)
        )
        .all()
    )
    
    if not candidates:
        return None
    
    # Load jedes Nodes berechnen
    scored = []
    for node in candidates:
        recent = session.query(NodeHeartbeat)\
            .filter(NodeHeartbeat.node_id == node.id)\
            .filter(NodeHeartbeat.timestamp > datetime.utcnow() - timedelta(seconds=30))\
            .all()
        
        if not recent:
            continue
        
        avg_gpu_util = mean(h.gpu_util_pct for h in recent if h.gpu_util_pct is not None)
        score = (avg_gpu_util, node.price_per_1k_tokens)
        scored.append((score, node))
    
    if not scored:
        return None
    
    scored.sort(key=lambda x: x[0])
    return scored[0][1]
```

## Trade-offs & Entscheidungen

### SQLite statt Postgres (POC)

- ✅ Null-Setup, eine Datei, perfekt für POC
- ❌ Nicht horizontal skalierbar
- **Migration zu Postgres:** SQLAlchemy abstrahiert, Connection-String reicht.

### Polling-Heartbeats (5s) statt WebSocket

- ✅ Einfach, keine Connection-Verwaltung
- ✅ Funktioniert über alle Firewalls
- ❌ 5s Latenz für "Node down"-Erkennung
- **Migration:** WebSocket/SSE für Echtzeit-Metriken, falls nötig.

### Lokales Ollama als Fallback im Portal

- ✅ Portal kann auf dem Portal-Host selbst laufen und antworten, wenn keine externen Nodes verfügbar sind
- ❌ Verhalten inkonsistent (manchmal lokal, manchmal remote)
- **Beibehalten:** Funktioniert als "Garantie-Verfügbarkeit" für kleine Workloads.

### Keine Authentifizierung (POC)

- ❌ Offen für jeden, der das Netz erreicht
- **TODO für Prod:** API-Keys, OAuth oder mTLS.

### Model-Catalog nicht synchronisiert

- Im POC wird angenommen, dass jeder Node jedes Model hat.
- **TODO:** `/nodes/{id}/models` Endpoint, Model-Match in `find_best_node()`.

## Skalierung

| Metrik | POC | Ziel (Prod) |
|---|---|---|
| Nodes | 1–5 | 50–500 |
| Requests/s | <10 | 1000+ |
| DB | SQLite | Postgres + Read-Replicas |
| Portal | Single | Multi-Instance hinter Load-Balancer |
| Auth | keine | API-Keys + Netz-ACLs (Mesh-VPN oder Firewall) |
| Earnings | tracked | echte Abrechnung (Stripe o.ä.) |
