# Portal

Das Portal ist die zentrale API- und UI-Instanz des CoMesh-POC. Es läuft auf dem
Portal-Host — erreichbar unter einem Namen deiner Wahl (DNS/mDNS im LAN oder ein
Name aus einem Mesh-VPN). Eine feste IP braucht es nicht.

## Setup

### Voraussetzungen

- Python 3.11+
- Docker + Docker Compose
- Ein Netz, in dem die Nodes das Portal und das Portal die Nodes erreichen
  (siehe [network.md](network.md))

### Installation

```bash
cp .env.example .env

# .env anpassen
cat .env
# APP_PUBLIC_URL=http://portal-host:8765   # nur noetig, wenn Zahlungen konfiguriert sind
PORTAL_PORT=8765
DB_URL=sqlite:///./gpu_pool.db
LOCAL_OLLAMA_URL=http://localhost:11434
NODE_TIMEOUT_SECONDS=30

docker compose up -d
```

### Health-Check

```bash
curl http://portal-host:8765/health
# {"status": "ok", "nodes_online": 3, "local_ollama": "ok"}
# Netz-Check (offen, ohne API-Key):
curl http://portal-host:8765/net/echo
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
| `APP_PUBLIC_URL` | (leer) | Öffentliche Basis-URL für Zahlungs-Rückkehrlinks. Leer = wird aus dem Request abgeleitet |
| `DB_URL` | `sqlite:///./gpu_pool.db` | SQLAlchemy-URL |
| `LOCAL_OLLAMA_URL` | `http://localhost:11434` | Lokales Ollama als Fallback |
| `NODE_TIMEOUT_SECONDS` | `30` | Nach dieser Zeit ohne Heartbeat → Node als offline markieren |
| `LOG_LEVEL` | `INFO` | DEBUG/INFO/WARNING/ERROR |

**Das Heartbeat-Intervall stellt der Agent, nicht das Portal.** `HEARTBEAT_SEC`
(HTTP-Betrieb, Vorgabe 30 s) und `WS_HEARTBEAT_SEC` (WebSocket-Betrieb, Vorgabe
15 s) stehen in der Konfiguration des Node-Agenten; das Portal liest sie nicht.
Es zählt nur die Gegenrichtung: eine Node gilt als online, solange sie sich
innerhalb von **90 s** gemeldet hat (`ONLINE_GRACE` in `nodes.py`/`pool.py`, per
WS-Ping oder HTTP-Heartbeat). Eine frühere Variable `HEARTBEAT_INTERVAL_SECONDS`
hat nie existiert — sie stand nur in dieser Doku.

## Datenmodell (DB)

Siehe [architecture.md](architecture.md#datenmodell) für Details. Tabellen:

- `gpu_nodes` — Stammdaten der Nodes
- `node_heartbeats` — Metrik-Historie (je Heartbeat, im WS-Betrieb je Ping)
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
curl -X POST http://portal-host:8765/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2.5-coder:14b",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

### `GET /nodes/`

Liste aller registrierten Nodes.

```bash
curl http://portal-host:8765/nodes/
```

### `POST /nodes/register`

Manuelle Registrierung (normalerweise macht das der Agent).

```bash
curl -X POST http://portal-host:8765/nodes/register \
  -H "Content-Type: application/json" \
  -d '{
    "node_url": "http://node-host:11435",
    "port": 11435,
    "gpu_model": "RTX 4090",
    "vram_gb": 24,
    "price_per_1k_tokens": 0.0005
  }'
```

### `POST /nodes/heartbeat`

Wird vom Node-Agent alle 5s aufgerufen.

```bash
curl -X POST http://portal-host:8765/nodes/heartbeat \
  -H "Content-Type: application/json" \
  -d '{
    "advertise_host": "node-host",
    "agent_port": 11435,
    "cpu_pct": 23.4,
    "ram_pct": 41.2,
    "gpu_util_pct": 78.5,
    "vram_used_gb": 12.3
  }'
```

### `GET /pool/`

Aktueller Pool-Status.

```bash
curl http://portal-host:8765/pool/
# {"total_nodes": 5, "online_nodes": 4, "avg_load_pct": 45.2, "cheapest_node": "..."}
```

### `GET /earnings/`

Earnings pro Node (default letzte 24h).

```bash
curl http://portal-host:8765/earnings/?hours=24
```

## UI

Das Portal bringt zwei UIs mit (gleiche Daten, anderes Stack):

### FastAPI-UI (`:8765`)

Server-side gerendert mit Jinja2 + Alpine.js. URLs:

- `http://portal-host:8765/ui/nodes` — Node-Übersicht
- `http://portal-host:8765/ui/pool` — Pool-Status
- `http://portal-host:8765/ui/earnings` — Earnings-Charts
- `http://portal-host:8765/ui/agent` — Agent-Setup-Anleitung

### Alpine-UI (`:8767`)

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

- Erreicht die Node das Portal? `curl $PORTAL_URL/net/echo`
- Erreicht das Portal die Node? `curl http://node-host:11435/health`
  (Adresse steht in `/nodes/my` im Feld `node_url`)
- Firewall: der Agent-Port muss für das Portal offen sein — oder
  `AGENT_TRANSPORT=ws` verwenden, dann entfällt der Inbound-Port
- Heartbeats kommen an? `docker compose logs -f api | grep heartbeat`

### Load-Balancing wählt immer denselben Node

- Hat der andere Node `enabled: true`?
- Letzter Heartbeat: `/nodes/{id}` → `last_seen`
- Preis/Auslastung checken: `/pool/`
