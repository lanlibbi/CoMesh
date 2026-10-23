<p align="center">
  <img src="docs/brand/comesh-banner.svg" alt="CoMesh — your compute, meshed" width="100%">
</p>

> **Your compute, meshed.**
>
> Contribute GPUs to the pool, use the whole pool through one OpenAI-compatible API — free and powered by your community.

CoMesh joins local and remote self-hosted inference servers into one shared
inference layer. Users send requests to a **Portal**,
which routes them to the most suitable **Node-Agent** in the pool.

> **Status:** Proof of Concept (POC), running end-to-end: Portal, Node-Agents,
> load-balancing, credits-based billing and a role-gated **admin console** with an
> audit log. This repo contains **code + docs**.
>
> **Version:** `0.4.0` — Portal and Node-Agent share one version from here on.
> See [CHANGELOG.md](CHANGELOG.md).

> **Network:** no fixed addresses anywhere. The portal and its nodes find each
> other over a plain LAN, Docker network or mesh VPN — DHCP is fine. Nothing has
> to be configured beyond `.env` variables. See [docs/network.md](docs/network.md).

---

Admin console and portal, real captures (1440×900, dark and light theme):

| | |
|---|---|
| **Dashboard** — pool status, credits, own usage | **Admin · Accounts** — approve, roles, passwords, credits, keys |
| **Admin · Audit log** — who changed what, when | **Sign in** — brand, theme and language switch |
| **Light theme** — same UI, brass accents follow the theme | |

The header animation is a small canvas (`frontend-alpine/brand-mesh.js`): a miniature of
the pool — nodes, links, packets travelling along them. It follows the theme colours,
stops when the tab is hidden, and renders a single static frame under
`prefers-reduced-motion`.

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

## Who needs what

| Role | What it takes |
|---|---|
| **User** (send requests) | **nothing.** A browser on `http://<portal>:8767`, or any
OpenAI-compatible client against `http://<portal>:8765/v1` with an API key. |
| **Provider** (contribute a GPU) | a local inference backend (Ollama, LM Studio, vLLM …)
**plus** the node-agent in front of it. The portal only ever calls the agent (`node_url`
→ port `11435`), never the backend directly. |
| **Operator** (run the portal) | Docker Compose (Linux, or Docker Desktop with WSL2), or
Python natively. |

On Windows a provider needs Python (or the planned `comesh-agent.exe`) — a plain
LM Studio install alone does not make a node. See [docs/windows.md](docs/windows.md).

## Components

| Component | Stack | Port | Description |
|---|---|---|---|
| Portal backend | FastAPI + SQLAlchemy | `8765` | API, pool logic, DB |
| Portal UI (Alpine) | Alpine.js + canvas, no build step | `8767` | Node/pool/usage/admin dashboard |
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

### Admin console (UI)

Everything below is available in the web UI as well — no curl needed. Three pages,
all gated on `role = admin` server-side, every mutation lands in the audit log:

| Page | Menu | What it does |
|---|---|---|
| `admin-registrations.html` | **Freigaben** | approve / reject sign-ups, status filter, search, paging; per account: role, **set password**, **top up credits**, **issue a new API key** (the old one dies, the new one is shown once), activate / deactivate; **create an account** by hand |
| `admin-usage.html` | **Verbrauch (alle)** | tokens, requests and credits per account and model over 24h / 7d / 30d / all; quota per account; credits system on/off |
| `admin-audit.html` | **Protokoll** | every change with timestamp, acting admin, target and a readable diff (`role: both → admin`); filter by action. Passwords and key values are never stored |

`usage.html` (**Mein Verbrauch**) is the non-admin view of your own consumption.

What an operator can do via the API:

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

## Anleitung für Einsteiger

Wer CoMesh nicht kennt: die Seite **`/hilfe.html`** im Portal erklärt in einfacher Sprache,
was das Werkzeug ist, wofür es gebaut wurde, wie der erste Aufruf aussieht, was Credits sind
und was die Fehlercodes bedeuten. Sie funktioniert ohne Anmeldung und ist aus dem Menü
verlinkt („Anleitung"). Sie lässt sich zwischen **Deutsch und Englisch** umschalten. Quelle: `frontend-alpine/hilfe.html`, Langfassung für die
Projektarbeit in `docs/anleitung.md`.

## Eigene API-Schlüssel und Modellfreigabe

Ein Client braucht einen Schlüssel, der mit `gpu_` beginnt. Ausgestellt wird er im Portal
(Profil → **API-Schlüssel ausstellen**, Passwort bestätigt, einmal sichtbar) oder per
`POST /v1/me/keys`. Die Browser-Sitzung (`sess_…`) ist **kein** API-Schlüssel.

`GET /v1/models` liefert nur die Modelle, die für das Konto freigegeben sind. Cloud-Modelle sind
kostenpflichtig und werden über `users.allow_cloud` getrennt zugeschaltet — ohne die Freigabeliste
anzutasten. Details: [docs/api.md](docs/api.md).

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) — ASCII diagram and data flows
- [docs/architecture.md](docs/architecture.md) — deep-dive architecture
- [docs/portal.md](docs/portal.md) — portal setup, config, API
- [docs/node-agent.md](docs/node-agent.md) — node-agent setup and deployment
- [docs/agent-api.md](docs/agent-api.md) — **agent account**: full-access account for automation (approvals, reports, usage); what it can and cannot do
- [docs/anleitung.md](docs/anleitung.md) — **user guide**: what CoMesh is, first request, credits, error codes (German long form; the in-portal page `/hilfe.html` switches between German and English)
- [docs/api.md](docs/api.md) — full API reference
- [docs/network.md](docs/network.md) — addressing, DHCP, mDNS, optional mesh VPN
- [docs/windows.md](docs/windows.md) — running a **provider** on Windows (LM Studio or
  Ollama, native or Docker, autostart via Task Scheduler)

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

## Adminbereich (Deutsch)

Alles unter `/admin` verlangt einen Schlüssel eines Kontos mit `role = admin`.
Im Browser gibt es dafür drei Seiten (Menü **Freigaben**, **Verbrauch (alle)**,
**Protokoll**): Registrierungen freigeben und ablehnen, Rollen vergeben, Passwörter
setzen, Credits buchen, Schlüssel ausstellen, Konten deaktivieren und anlegen — jede
Änderung landet im Protokoll. Screenshots oben im Abschnitt *Screenshots*.

Der erste Admin entsteht beim Start aus `ADMIN_API_KEY` / `ADMIN_EMAIL` (siehe
`.env.example`); weitere Admins ernennt ein bestehender Admin. Die API schützt sich
selbst: ein Admin kann sich weder degradieren noch deaktivieren.

## Wer braucht was (Deutsch)

| Rolle | Was nötig ist |
|---|---|
| **Nutzer** | **nichts.** Browser auf `http://<portal>:8767` oder ein OpenAI-kompatibler
Client auf `http://<portal>:8765/v1` mit einem API-Schlüssel. |
| **Provider** | ein lokales Backend (Ollama, LM Studio, vLLM …) **und** der Node-Agent
davor. Das Portal ruft ausschließlich den Agenten an (`node_url` → Port `11435`). |
| **Betreiber** | Docker Compose oder Python nativ. |

Unter Windows braucht ein Provider Python (oder die geplante `comesh-agent.exe`) —
LM Studio allein macht noch keinen Node. Details, inklusive der Streaming-Grenze bei
`BACKEND=openai`, in [docs/windows.md](docs/windows.md).

## Dokumentation (Deutsch)

- [ARCHITECTURE.md](ARCHITECTURE.md) — ASCII-Diagramm und Datenflüsse
- [docs/architecture.md](docs/architecture.md) — tiefer Architektur-Einblick
- [docs/portal.md](docs/portal.md) — Portal-Setup, Konfiguration, API
- [docs/node-agent.md](docs/node-agent.md) — Node-Agent-Setup und Deployment
- [docs/api.md](docs/api.md) — komplette API-Referenz
- [docs/network.md](docs/network.md) — Adressierung, DHCP, mDNS, optionales Mesh-VPN

## Lizenz

POC, interne Nutzung. TBD.

## Own API keys and model permissions

A client needs a key starting with `gpu_`. Issue one in the portal (profile → **Issue API key**,
password confirmed, shown once) or via `POST /v1/me/keys`. The browser session (`sess_…`) is **not**
an API key.

`GET /v1/models` returns only the models released for the account. Cloud models cost money and are
enabled separately via `users.allow_cloud`, leaving the release list untouched. Details:
[docs/api.md](docs/api.md).
