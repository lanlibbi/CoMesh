# CoMesh

> **Your compute, meshed.**
>
> Contribute GPUs to the pool, use the whole pool through one OpenAI-compatible API — free and powered by your community.

CoMesh joins local and remote self-hosted inference servers into one shared
inference layer. Users send requests to a **Portal**,
which routes them to the most suitable **Node-Agent** in the pool.

> **Status:** Proof of Concept (POC). Works end-to-end with Portal, Node-Agents,
> load-balancing and earnings tracking. This repo contains **code + docs**.

---

## Repository layout

```
├── main.py               # FastAPI portal (API, pool logic, auth)
├── models.py             # SQLAlchemy models (User, GpuNode, Earnings…)
├── nodes.py              # Node registration / heartbeats / CRUD
├── pool.py               # Load balancing + node selection
├── ws.py                 # WebSocket transport (phase 1/2)
├── payments.py           # Stripe/PayPal (mock mode)
├── frontend/             # Legacy Jinja2 UI
├── frontend-alpine/      # Alpine.js + Tailwind UI (particle effect, recommended)
├── node-agent/           # Contributor agent (backend-agnostic: Ollama/OpenAI-compatible)
│   └── setup.py          # Interactive installer with backend selection
├── docker-compose.yml    # Portal + frontend stack
├── docs/                 # Architecture / API / Node-Agent / Tailscale
└── examples/             # Example client + node-agent compose
```

## Architecture (overview)

```
┌──────────┐    OpenAI-API     ┌──────────┐    Tailscale     ┌──────────────┐
│  Client  │ ────────────────► │  Portal  │ ────────────────►│  Node-Agent  │
│ (Python) │                  │ (FastAPI)│                  │   (Docker)   │
└───────────                  └──────────┘                  └──────┬───────┘
                                   │                              │
                                   │ Heartbeats                   │ HTTP (local)
                                   │                              ▼
                                   ▼                        ┌──────────┐
                              ┌─────────┐                   │  Ollama  │
                              │  Nodes  │                   │  :11434  │
                              │  DB     │                   └──────────┘
                              └─────────┘
```

- **Portal** (FastAPI): receives requests, picks the best node, dispatches jobs, tracks earnings.
- **Node-Agent** (Python container): runs on contributor hosts, reports heartbeats (CPU/GPU/RAM/price), proxies requests to the local backend.
- **Tailscale**: private overlay network, portal → node-agents directly, no public IPs.

See [ARCHITECTURE.md](ARCHITECTURE.md) and [docs/architecture.md](docs/architecture.md).

---

## Quickstart

### 1. Start the portal

```bash
docker compose up -d --build
# Portal: http://localhost:8765
```

### 2. Deploy a node-agent (on the contributor host)

```bash
cd node-agent/
python3 setup.py          # interactive: pick backend (Ollama / LM Studio / LiteLLM / OpenAI-compatible)
# fill in NODE_ID + NODE_API_KEY from the portal in .env
docker compose up -d
```

The agent registers with the portal automatically and becomes available after ~5 seconds.

**Backend selection:** the setup installer generates the matching `.env` + `docker-compose.yml` for your self-hosted backend:

| Backend | Protocol | Notes |
|---------|----------|-------|
| **Ollama** | `/api/chat` (native) | Default, local |
| **LM Studio** | `/v1/chat/completions` (OpenAI) | Enable the server flag |
| **LiteLLM** | `/v1/chat/completions` (OpenAI) | Proxy in front of any model |
| **Other OpenAI-compatible servers** | `/v1/chat/completions` | vLLM, llama.cpp, … |

The node-agent translates as needed: `BACKEND=ollama` speaks native Ollama, `BACKEND=openai` speaks any OpenAI-compatible backend.

### 3. Send your first request

```bash
curl -X POST http://localhost:8765/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2.5-coder:14b",
    "messages": [{"role": "user", "content": "Hello GPU pool!"}]
  }'
```

The portal automatically picks the cheapest node with the lowest current load. The response includes an `x-pool-node` header with the selected node's address.

Example client: [examples/client.py](examples/client.py)

---

## Components

| Component | Stack | Port | Description |
|---|---|---|---|
| Portal backend | FastAPI + SQLAlchemy | `8765` | API, pool logic, DB |
| Portal UI (Alpine) | Tailwind + Alpine | `8767` | Node/pool/earnings dashboard |
| Node-Agent | Python + psutil + pynvml | `8080` | Heartbeat + inference proxy |

---

## Admin operations

Everything under `/admin` requires an API key of a user with `role = "admin"`.

Bootstrap the first admin by setting `ADMIN_API_KEY` in the environment (see
`.env.example`). The account named by `ADMIN_EMAIL` is created and that value
becomes its only active key:

```bash
export ADMIN_API_KEY="gpu_$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')"
docker compose up -d --build

curl -H "Authorization: Bearer $ADMIN_API_KEY" http://localhost:8765/admin/whoami
curl -H "Authorization: Bearer $ADMIN_API_KEY" "http://localhost:8765/admin/nodes?status=all"
curl -H "Authorization: Bearer $ADMIN_API_KEY" http://localhost:8765/admin/overview
```

What an operator can do:

- **Users** — list (including deactivated ones), create, change role/state/model
  whitelist, top up credits, rotate or revoke API keys. Admins can only be
  created by another admin; `PUT /v1/me/role` never accepts `admin`.
- **Nodes** — see **every** node including offline and disabled ones, with owner,
  WebSocket state, last heartbeat and job/failure counters; pause or resume a
  node of any owner.
- **Auditing** — every mutation writes an `admin_audit_log` row. Mutating POSTs
  accept an `Idempotency-Key` header, so a retried request replays the stored
  result instead of repeating the effect (raw API keys are never stored).

### Tests

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest tests -q          # 15 admin tests, in-process TestClient
bash scripts/smoke_admin.sh http://localhost:8765 "$ADMIN_API_KEY"   # live HTTP smoke check
```

---

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) — ASCII diagram and data flows
- [docs/architecture.md](docs/architecture.md) — deep-dive architecture
- [docs/portal.md](docs/portal.md) — portal setup, config, API
- [docs/node-agent.md](docs/node-agent.md) — node-agent setup, deployment, Tailscale
- [docs/api.md](docs/api.md) — full API reference
- [docs/tailscale.md](docs/tailscale.md) — network setup

---

## License

POC, internal use. TBD.

---

# CoMesh (Deutsch)

> **Your compute, meshed.**
>
> Stelle GPUs für den Pool bereit und nutze den ganzen Pool über eine einzige OpenAI-kompatible API — kostenlos und von deiner Community getragen.

CoMesh führt lokale und entfernte Ollama- und OpenAI-kompatible
Instanzen (LM Studio, LiteLLM, vLLM, llama.cpp) zu einer gemeinsamen
Inference-Schicht zusammenführt. Nutzer schicken ihre Anfragen an ein **Portal**,
das Portal verteilt sie an den am besten geeigneten **Node-Agent** im Netz.

> **Status:** Proof of Concept (POC). Funktioniert end-to-end mit Portal,
> Node-Agents, Load-Balancing und Earnings-Tracking. Dieses Repo enthält
> **Code + Doku**.

---

## Quickstart (Deutsch)

### 1. Portal starten

```bash
docker compose up -d --build
# Portal: http://localhost:8765
```

### 2. Node-Agent deployen (auf dem Contributor-Host)

```bash
cd node-agent/
python3 setup.py          # interaktiv: Backend wählen (Ollama / LM Studio / LiteLLM / OpenAI-kompatibel)
# .env mit NODE_ID + NODE_API_KEY aus dem Portal setzen
docker compose up -d
```

Der Agent meldet sich automatisch beim Portal an und ist nach ~5 Sekunden verfügbar.

### 3. Erste Anfrage schicken

```bash
curl -X POST http://localhost:8765/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2.5-coder:14b",
    "messages": [{"role": "user", "content": "Hallo CoMesh!"}]
  }'
```

Das Portal wählt automatisch den billigsten Node mit der niedrigsten aktuellen
Auslastung. Die Antwort enthält den `x-pool-node`-Header mit der Adresse des
gewählten Nodes.

---

## Dokumentation (Deutsch)

- [ARCHITECTURE.md](ARCHITECTURE.md) — ASCII-Diagramm und Datenflüsse
- [docs/architecture.md](docs/architecture.md) — tiefer Architektur-Einblick
- [docs/portal.md](docs/portal.md) — Portal-Setup, Konfiguration, API
- [docs/node-agent.md](docs/node-agent.md) — Node-Agent-Setup, Deployment, Tailscale
- [docs/api.md](docs/api.md) — komplette API-Referenz
- [docs/tailscale.md](docs/tailscale.md) — Netzwerk-Setup

## Lizenz

POC, interne Nutzung. TBD.
