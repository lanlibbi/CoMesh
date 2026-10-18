# CoMesh

> **Your compute, meshed.**
>
> Contribute GPUs to the pool, use the whole pool through one OpenAI-compatible API — free and powered by your community.

CoMesh joins local and remote self-hosted inference servers into one shared
inference layer. Users send requests to a **Portal**,
which routes them to the most suitable **Node-Agent** in the pool.

> **Status:** Proof of Concept (POC). Works end-to-end with Portal, Node-Agents,
> load-balancing and credits-based billing. This repo contains **code + docs**.

> **Network:** no fixed addresses anywhere. The portal and its nodes find each
> other over a plain LAN, Docker network or mesh VPN — DHCP is fine. Nothing has
> to be configured beyond `.env` variables. See [docs/network.md](docs/network.md).

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
├── netinfo.py            # address detection + node_url helpers (no fixed IPs)
├── docs/                 # Architecture / API / Node-Agent / Network
├── scripts/check_setup.sh # portal-side setup check (no API key needed)
└── examples/             # Example client + node-agent compose
```

## Architecture (overview)

```
┌──────────┐    OpenAI-API     ┌──────────┐  HTTP/WS to      ┌──────────────┐
│  Client  │ ────────────────► │  Portal  │  node_url        │  Node-Agent  │
│ (Python) │                  │ (FastAPI)│ ────────────────►│   (Docker)   │
└───────────                  └──────────┘                  └──────┬───────┘
                                   │                              │
                                   │ Heartbeats (carry the        │ HTTP (local)
                                   │ node's own address)          ▼
                                   ▼                        ┌──────────┐
                              ┌─────────┐                   │  Ollama  │
                              │  Nodes  │                   │  :11434  │
                              │  DB     │                   └──────────┘
                              └─────────┘
```

- **Portal** (FastAPI): receives requests, picks the best node, dispatches jobs, books credits against the caller's balance.
- **Node-Agent** (Python container): runs on contributor hosts, reports heartbeats (CPU/GPU/RAM/price), proxies requests to the local backend.
- **Network**: portal → node-agent over `node_url` (DNS/mDNS name, LAN IP, or a
  mesh-VPN name — e.g. Tailscale, optionally). No public ports, no fixed IPs.

See [ARCHITECTURE.md](ARCHITECTURE.md) and [docs/architecture.md](docs/architecture.md).

---

## Quickstart

### 1. Start the portal

```bash
cp .env.example .env
docker compose up -d --build
# Portal: http://localhost:8765
# Setup check (no API key): scripts/check_setup.sh http://localhost:8765
```

### 2. Deploy a node-agent (on the contributor host)

```bash
cd node-agent/
python3 setup.py            # interactive: backend, portal URL, optional own name
python agent.py --check     # which address will the portal dial?
docker compose up -d
```

All it needs is the portal's address; the agent registers itself and reports the
address it is reachable under:

```bash
# node-agent/.env — the whole network configuration
PORTAL_URL=http://portal-host:8765   # name of the portal host (your LAN / mDNS / VPN)
PORTAL_USER_KEY=gpu_...              # API key of an account with role provider/both
ADVERTISE_HOST=my-node.local         # optional; omit to auto-detect
```

The agent registers with the portal automatically and becomes available after ~5 seconds.
Both sides work on DHCP: nothing in this setup has to know an IP in advance, and a
lease change re-registers the address by itself ([docs/network.md](docs/network.md)).

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
| Portal UI (Alpine) | Tailwind + Alpine | `8767` | Node/pool/usage/admin dashboard |
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
- [docs/node-agent.md](docs/node-agent.md) — node-agent setup and deployment
- [docs/api.md](docs/api.md) — full API reference
- [docs/network.md](docs/network.md) — addressing, DHCP, mDNS, optional mesh VPN

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
cp .env.example .env
docker compose up -d --build
# Portal: http://localhost:8765
# Setup-Check (ohne API-Key): scripts/check_setup.sh http://localhost:8765
```

### 2. Node-Agent deployen (auf dem Contributor-Host)

```bash
cd node-agent/
python3 setup.py          # interaktiv: Backend, Portal-URL, optional eigener Name
python agent.py --check   # welche Adresse spricht das Portal an?
docker compose up -d
```

Nötig ist nur die Adresse des Portals; der Agent registriert sich selbst und
meldet die Adresse, unter der er erreichbar ist:

```bash
# node-agent/.env — die komplette Netz-Konfiguration
PORTAL_URL=http://portal-host:8765   # Name des Portal-Hosts (LAN / mDNS / VPN)
PORTAL_USER_KEY=gpu_...              # API-Key eines Kontos mit Rolle provider/both
ADVERTISE_HOST=mein-node.local       # optional; ohne Angabe: automatische Erkennung
```

Der Agent meldet sich automatisch beim Portal an und ist nach ~5 Sekunden verfügbar.
Beide Seiten laufen auf DHCP: hier muss nichts eine IP vorher kennen, und ein
Lease-Wechsel trägt die neue Adresse selbst nach ([docs/network.md](docs/network.md)).

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
- [docs/node-agent.md](docs/node-agent.md) — Node-Agent-Setup und Deployment
- [docs/api.md](docs/api.md) — komplette API-Referenz
- [docs/network.md](docs/network.md) — Adressierung, DHCP, mDNS, optionales Mesh-VPN

## Lizenz

POC, interne Nutzung. TBD.
