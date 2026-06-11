# GPU-Pool

Ein dezentraler GPU-Pool, der lokale und entfernte Ollama-Instanzen zu einer gemeinsamen Inference-Schicht zusammenführt. User schicken ihre Anfragen an ein **Portal**, das Portal verteilt sie an den am besten geeigneten **Node-Agent** im Pool.

> **Status:** Proof of Concept (POC). Funktioniert end-to-end mit Portal, Node-Agents, Load-Balancing und Earnings-Tracking.

---

## Architektur (Überblick)

```
┌──────────┐    OpenAI-API     ┌──────────┐    Tailscale     ┌──────────────┐
│  Client  │ ────────────────► │  Portal  │ ────────────────►│  Node-Agent  │
│ (Python) │                  │ (FastAPI)│                  │   (Docker)   │
└───────────                  └──────────┘                  └──────┬───────┘
                                   │                              │
                                   │ Heartbeats                   │ HTTP (lokal)
                                   │                              ▼
                                   ▼                        ┌──────────┐
                              ┌─────────┐                   │  Ollama  │
                              │  Nodes  │                   │  :11434  │
                              │  DB     │                   └──────────┘
                              └─────────┘
```

- **Portal** (FastAPI auf `ai-lanlibbi`): Empfängt Requests, wählt den besten Node, verteilt Jobs, sammelt Earnings.
- **Node-Agent** (Python-Container): Läuft auf Contributors-Hosts, meldet Heartbeats (CPU/GPU/RAM/Preis), proxied Anfragen an lokales Ollama.
- **Tailscale**: Privates Overlay-Netz, Portal → Node-Agents direkt, ohne Public-IPs.

Mehr Details: [ARCHITECTURE.md](ARCHITECTURE.md) und [docs/architecture.md](docs/architecture.md).

---

## Quickstart

### 1. Portal starten (auf `ai-lanlibbi`)

```bash
cd portal/
docker compose up -d
# Portal: http://ai-lanlibbi:8765
```

### 2. Node-Agent deployen (auf Contributor-Host)

```bash
cd node-agent/
cp .env.example .env
# TAILSCE_IP, PRICE_PER_1K_TOKENS etc. setzen
docker compose up -d
```

Der Agent meldet sich automatisch beim Portal an und ist nach ~5 Sekunden verfügbar.

### 3. Erste Anfrage schicken

```bash
curl -X POST http://ai-lanlibbi:8765/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2.5-coder:14b",
    "messages": [{"role": "user", "content": "Hello GPU pool!"}]
  }'
```

Das Portal wählt automatisch den billigsten Node mit der niedrigsten aktuellen Auslastung. Antwort enthält `x-pool-node` Header mit der IP des gewählten Nodes.

Beispiel-Client: [examples/client.py](examples/client.py)

---

## Komponenten

| Komponente | Stack | Port | Beschreibung |
|---|---|---|---|
| Portal Backend | FastAPI + SQLAlchemy | `8765` | API, Pool-Logik, DB |
| Portal UI (FastAPI) | Jinja2 + Alpine.js | `8765` | Admin-UI für Nodes/Pool/Earnings |
| Portal UI (Alpine) | Tailwind + Alpine | `3000` | Alternative UI (gleiche Daten) |
| Node-Agent | Python + psutil + pynvml | `8080` | Heartbeat + Ollama-Proxy |

---

## Dokumentation

- [ARCHITECTURE.md](ARCHITECTURE.md) — ASCII-Diagramm und Datenflüsse
- [docs/architecture.md](docs/architecture.md) — Tiefer Architektur-Einblick
- [docs/portal.md](docs/portal.md) — Portal-Setup, Konfiguration, API
- [docs/node-agent.md](docs/node-agent.md) — Node-Agent-Setup, Deployment, Tailscale
- [docs/api.md](docs/api.md) — Komplette API-Referenz
- [docs/tailscale.md](docs/tailscale.md) — Netzwerk-Setup

---

## Lizenz

POC, interne Nutzung. TBD.
