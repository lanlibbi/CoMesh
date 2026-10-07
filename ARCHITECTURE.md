# ARCHITECTURE

Visuelle Übersicht der CoMesh-Komponenten und Datenflüsse.

## Komponenten-Diagramm

```
                ┌───────────────────────────────────────────────┐
                │              CoMesh Portal                    │
                │              (portal-host)                    │
                │                                               │
                │   ┌─────────┐   ┌─────────┐   ┌─────────┐    │
                │   │  /v1/   │   │  /pool/ │   │ /nodes/ │    │
                │   │ chat/   │   │  (LB)   │   │  (CRUD) │    │
                │   │ compl.  │   │         │   │         │    │
                │   └────┬────┘   └────┬────┘   └────┬────┘    │
                │        │             │              │         │
                │        └─────────────┴──────────────┘         │
                │                      │                       │
                │                      ▼                       │
                │               ┌────────────┐                 │
                │               │  SQLAlchemy│                 │
                │               │     DB     │                 │
                │               └────────────┘                 │
                │                                               │
                │   ┌─────────┐  ┌─────────┐  ┌─────────┐      │
                │   │nodes.   │  │pool.    │  │earnings.│      │
                │   │  html   │  │  html   │  │  html   │      │
                │   └─────────┘  └─────────┘  └─────────┘      │
                └──────────────────────┬────────────────────────┘
                                       │
    HTTP/WS to node_url │ (DNS, mDNS, LAN or mesh VPN)
                                       │
       ┌───────────────────┬───────────┼───────────┬───────────────────┐
       │                   │           │           │                   │
       ▼                   ▼           ▼           ▼                   ▼
  ┌─────────┐         ┌─────────┐ ┌─────────┐ ┌─────────┐         ┌─────────┐
  │Node 1   │         │Node 2   │ │Node 3   │ │Node 4   │  ...    │Node N   │
  │(Node 1) │         │(Desktop)│ │(Gaming) │ │(Workstn)│         │(Laptop) │
  │         │         │         │ │         │ │         │         │         │
  │ Agent   │         │ Agent   │ │ Agent   │ │ Agent   │         │ Agent   │
  │ :8080   │         │ :8080   │ │ :8080   │ │ :8080   │         │ :8080   │
  └────┬────┘         └────┬────┘ └────┬────┘ └────┬────┘         └────┬────┘
       │                   │           │           │                   │
       ▼                   ▼           ▼           ▼                   ▼
  ┌─────────┐         ┌─────────┐ ┌─────────┐ ┌─────────┐         ┌─────────┐
  │ Ollama  │         │ Ollama  │ │ Ollama  │ │ Ollama  │         │ Ollama  │
  │ :11434  │         │ :11434  │ │ :11434  │ │ :11434  │         │ :11434  │
  └─────────┘         └─────────┘ └─────────┘ └─────────┘         └─────────┘
```

## Datenflüsse

### 1. Inference-Request

```
Client
  │ POST /v1/chat/completions
  ▼
Portal (/v1/chat/completions)
  │ 1. Versuche lokales Ollama (:11434)
  │    → Erfolg? Antwort zurück
  │
  │ 2. Fehler → pool.find_best_node()
  │    Kriterien: niedrigster Preis, niedrigste Auslastung
  │    → Gewählter Node-Agent (über sein node_url)
  │
  │ 3. POST {node_url}/v1/chat/completions
  ▼
Node-Agent
  │ Proxy zu lokalem Ollama (:11434)
  │ Antwort zurück ans Portal
  ▼
Portal
  │ Header: x-pool-node: {ip}
  │ DB: PoolJob (start, end, tokens, node_id)
  │ DB: NodeEarning (tokens * price)
  ▼
Client
```

### 2. Heartbeat

```
Node-Agent (alle 5s)
  │ POST /nodes/heartbeat
  │ Body: {status, gpu_util, advertise_host, agent_port, raw}
  │ (advertise_host: eigene Adresse — das Portal übernimmt sie,
  │  solange keine node_url fest eingetragen ist)
  ▼
Portal
  │ DB: NodeHeartbeat (timestamp, metrics)
  │ Update: GpuNode.last_seen
  ▼
(kein Response-Body nötig)
```

### 3. Node-Registrierung

```
Node-Agent (beim Start)
  │ POST /nodes/register
  │ Body: {name, gpu_type, vram_gb, port, node_url?, ...}
  │ (node_url darf leer bleiben → Auto-Erkennung beim Heartbeat)
  ▼
Portal
  │ DB: GpuNode (CREATE)
  │ → HTTP 201 mit node_id
  ▼
Node-Agent
  │ Startet Heartbeat-Loop
```

## Tech-Stack

| Layer | Technologie | Warum |
|---|---|---|
| API-Protokoll | OpenAI-kompatibel | Beste Client-Kompatibilität |
| Portal | Python 3.11 + FastAPI | Async, schnell, Type-Hints |
| ORM | SQLAlchemy | DB-agnostisch, Migrations-fähig |
| DB | SQLite (POC) / Postgres (Prod) | Einfach, später skalierbar |
| Frontend | Alpine.js + Tailwind | Keine Build-Pipeline nötig |
| Node-Agent | Python + psutil + pynvml | Minimaler Footprint |
| Containerisierung | Docker | Reproduzierbar, plattformunabhängig |
| Netzwerk | DNS/mDNS, LAN oder Mesh-VPN | Keine Public-IPs, keine feste Adresse |

## Nicht-Ziele (POC)

- Authentifizierung (kein API-Key, kein Rate-Limit)
- Abrechnung (Earnings werden getrackt, aber nicht ausgezahlt)
- Multi-Tenancy
- Model-Catalog-Sync über Nodes hinweg
- Streaming-Responses (geplant, nicht implementiert)

## Adressierung

Kein Bestandteil kennt eine feste IP. Ein Node wird über `node_url` angesprochen;
bleibt das Feld leer, leitet das Portal die Adresse aus dem ersten Heartbeat ab
(Details: [docs/network.md](docs/network.md)).
