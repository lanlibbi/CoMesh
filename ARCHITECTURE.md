# ARCHITECTURE

Visuelle Übersicht der GPU-Pool-Komponenten und Datenflüsse.

## Komponenten-Diagramm

```
                ┌───────────────────────────────────────────────┐
                │              GPU-Pool Portal                  │
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
                            Tailscale │ (WireGuard)
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
  │    → Gewählter Node-Agent (Tailscale-IP)
  │
  │ 3. POST {tailscale_ip}:8080/v1/chat/completions
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
  │ Body: {tailscale_ip, cpu_pct, ram_pct, gpu_util, price_per_1k_tokens}
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
  │ Body: {tailscale_ip, port, gpu_model, vram_gb, ...}
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
| Netzwerk | Tailscale | Keine Public-IPs, Zero-Config |

## Nicht-Ziele (POC)

- Authentifizierung (kein API-Key, kein Rate-Limit)
- Abrechnung (Earnings werden getrackt, aber nicht ausgezahlt)
- Multi-Tenancy
- Model-Catalog-Sync über Nodes hinweg
- Streaming-Responses (geplant, nicht implementiert)
