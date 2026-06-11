# Portal

Das Portal ist die zentrale API- und UI-Instanz des GPU-Pool-POC. Es läuft im POC auf `ai-lanlibbi` (Tailscale-IP `100.126.79.111`).

## Setup

### Voraussetzungen

- Python 3.11+
- Docker + Docker Compose
- Tailscale (siehe [tailscale.md](tailscale.md))

### Installation

```bash
cd portal/
cp .env.example .env

# .env anpassen
cat .env
PORTAL_PORT=8765
DB_URL=sqlite:///./gpu_pool.db
LOCAL_OLLAMA_URL=http://localhost:11434
NODE_TIMEOUT_SECONDS=30
HEARTBEAT_INTERVAL_SECONDS=5

docker compose up -d
```

### Health-Check

```bash
curl http://ai-lanlibbi:8765/health
# {"status": "ok", "nodes_online": 3, "local_ollama": "ok"}
```

### Logs

```bash
docker compose logs -f portal
```

## Konfiguration

Alle Optionen via `.env`:

| Variable | Default | Beschreibung |
|---|---|---|
| `PORTAL_PORT` | `8765` | HTTP-Port |
| `DB_URL` | `sqlite:///./gpu_pool.db` | SQLAlchemy-URL |
| `LOCAL_OLLAMA_URL` | `http://localhost:11434` | Lokales Ollama als Fallback |
| `NODE_TIMEOUT_SECONDS` | `30` | Nach dieser Zeit ohne Heartbeat → Node als offline markieren |
| `HEARTBEAT_INTERVAL_SECONDS` | `5` | Erwartetes Heartbeat-Intervall (für Stats) |
| `LOG_LEVEL` | `INFO` | DEBUG/INFO/WARNING/ERROR |

## Datenmodell (DB)

Siehe [architecture.md](architecture.md#datenmodell) für Details. Tabellen:

- `gpu_nodes` — Stammdaten der Nodes
- `node_heartbeats` — Metrik-Historie (alle 5s)
- `node_earnings` — Aggregierte Earnings pro Job
- `pool_jobs` — Job-Historie mit Status

### DB-Reset (POC)

```bash
docker compose down
rm -f gpu_pool.db
docker compose up -d
```

## API

Komplette Referenz: [api.md](api.md). Die wichtigsten Endpoints:

### `POST /v1/chat/completions`

OpenAI-kompatibel. Verteilt automatisch an den besten Node.

**Response-Header:**
- `x-pool-node` — IP des gewählten Nodes (oder `local`)
- `x-pool-tokens-in` / `x-pool-tokens-out` — Token-Counts

**Beispiel:**
```bash
curl -X POST http://ai-lanlibbi:8765/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2.5-coder:14b",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

### `GET /nodes/`

Liste aller registrierten Nodes.

```bash
curl http://ai-lanlibbi:8765/nodes/
```

### `POST /nodes/register`

Manuelle Registrierung (normalerweise macht das der Agent).

```bash
curl -X POST http://ai-lanlibbi:8765/nodes/register \
  -H "Content-Type: application/json" \
  -d '{
    "tailscale_ip": "100.120.250.36",
    "port": 8080,
    "gpu_model": "RTX 4090",
    "vram_gb": 24,
    "price_per_1k_tokens": 0.0005
  }'
```

### `POST /nodes/heartbeat`

Wird vom Node-Agent alle 5s aufgerufen.

```bash
curl -X POST http://ai-lanlibbi:8765/nodes/heartbeat \
  -H "Content-Type: application/json" \
  -d '{
    "tailscale_ip": "100.120.250.36",
    "cpu_pct": 23.4,
    "ram_pct": 41.2,
    "gpu_util_pct": 78.5,
    "vram_used_gb": 12.3
  }'
```

### `GET /pool/`

Aktueller Pool-Status.

```bash
curl http://ai-lanlibbi:8765/pool/
# {"total_nodes": 5, "online_nodes": 4, "avg_load_pct": 45.2, "cheapest_node": "..."}
```

### `GET /earnings/`

Earnings pro Node (default letzte 24h).

```bash
curl http://ai-lanlibbi:8765/earnings/?hours=24
```

## UI

Das Portal bringt zwei UIs mit (gleiche Daten, anderes Stack):

### FastAPI-UI (`:8765`)

Server-side gerendert mit Jinja2 + Alpine.js. URLs:

- `http://ai-lanlibbi:8765/ui/nodes` — Node-Übersicht
- `http://ai-lanlibbi:8765/ui/pool` — Pool-Status
- `http://ai-lanlibbi:8765/ui/earnings` — Earnings-Charts
- `http://ai-lanlibbi:8765/ui/agent` — Agent-Setup-Anleitung

### Alpine-UI (`:3000`)

Client-side, Tailwind + Alpine. Identische Seiten, modernes Look-and-Feel. Separater Container, gleiche Backend-API.

## Troubleshooting

### Portal antwortet nicht

```bash
docker compose ps
docker compose logs portal
```

### DB locked (SQLite)

```bash
# Alle Prozesse mit offenem DB-File?
lsof gpu_pool.db
# Im Notfall:
docker compose restart portal
```

### Nodes werden als offline angezeigt

- Tailscale verbunden? `tailscale status` auf dem Contributor-Host
- Firewall: Portal muss `:8765` von Tailscale-Netz erreichen können
- Heartbeats kommen an? `tail -f logs/portal.log | grep heartbeat`

### Load-Balancing wählt immer denselben Node

- Hat der andere Node `enabled: true`?
- Letzter Heartbeat: `/nodes/{id}` → `last_seen`
- Preis/Auslastung checken: `/pool/`
