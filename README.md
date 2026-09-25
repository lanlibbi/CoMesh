# GPU-Pool

A decentralized GPU pool that joins local and remote self-hosted inference
servers into one shared inference layer. Users send requests to a **Portal**,
which routes them to the most suitable **Node-Agent** in the pool.

> **Status:** Proof of Concept (POC). Works end-to-end with Portal, Node-Agents,
> load-balancing and earnings tracking. This repo contains **code + docs**.

---

## Repository layout

```
├── main.py               # FastAPI portal (API, pool logic, auth)
├── auth.py               # Token handling: API keys, session tokens, passwords
├── ratelimit.py          # Rate limiting + login brute-force guard
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
├── tests/                # Feature, WS and auth-hardening suites
├── docs/                 # Architecture / API / Auth / Node-Agent / Tailscale
└── examples/             # Example client + node-agent compose
```

## Auth & security

Token handling, rate limits and brute-force protection are documented in
**[docs/auth.md](docs/auth.md)**. Short version:

- `/auth/register` and `POST /admin/users` issue a long-lived API key (`gpu_…`);
  `/auth/login` issues a short-lived session token (`sess_…`, TTL via
  `SESSION_TOKEN_TTL_HOURS`) and rotates previous sessions. `POST /auth/logout`
  revokes them.
- Tokens are stored hashed (SHA-256), passwords are PBKDF2-HMAC-SHA256 with a
  per-user salt; legacy POC hashes are upgraded transparently on login.
- `/auth/login` is protected by a token bucket **and** a failure-based lockout
  with exponential backoff, per account and per IP.
- Per-user/per-node/per-IP rate limits return `429` with `Retry-After`.
- `/admin/*` is default-deny: set `ADMIN_TOKEN` or `ADMIN_EMAILS` (see
  `.env.example`).
- The OpenAI-compatible surface is unchanged — same paths, same
  `Authorization: Bearer <token>` contract.

```bash
python3 tests/test_auth_hardening.py   # self-contained: starts its own server + throwaway DB
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

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) — ASCII diagram and data flows
- [docs/architecture.md](docs/architecture.md) — deep-dive architecture
- [docs/portal.md](docs/portal.md) — portal setup, config, API
- [docs/auth.md](docs/auth.md) — token model, rate limits, brute-force protection, admin auth
- [docs/node-agent.md](docs/node-agent.md) — node-agent setup, deployment, Tailscale
- [docs/api.md](docs/api.md) — full API reference
- [docs/tailscale.md](docs/tailscale.md) — network setup

---

## License

POC, internal use. TBD.

---

# GPU-Pool (Deutsch)

Ein dezentraler GPU-Pool, der lokale und entfernte Ollama- und OpenAI-kompatible
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
    "messages": [{"role": "user", "content": "Hallo GPU-Pool!"}]
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
- [docs/auth.md](docs/auth.md) — Token-Modell, Rate-Limits, Brute-Force-Schutz, Admin-Auth
- [docs/node-agent.md](docs/node-agent.md) — Node-Agent-Setup, Deployment, Tailscale
- [docs/api.md](docs/api.md) — komplette API-Referenz
- [docs/tailscale.md](docs/tailscale.md) — Netzwerk-Setup

## Lizenz

POC, interne Nutzung. TBD.
