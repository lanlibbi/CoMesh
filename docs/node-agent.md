# Node-Agent

Der Node-Agent ist der leichte Worker, der auf jedem Contributor-Host läuft. Er meldet Hardware-Metriken ans Portal und leitet Inference-Requests an lokales Ollama weiter.

## Was der Agent tut

```
┌──────────────────────────────────┐
│  Node-Agent (Python-Container)   │
│                                  │
│  1. Beim Start:                  │
│     - Hardware erkennen (GPU)    │
│     - Beim Portal registrieren   │
│                                  │
│  2. Heartbeat-Loop (alle 5s):    │
│     - CPU/RAM/GPU/VRAM messen    │
│     - An Portal senden           │
│                                  │
│  3. Inference-Proxy (Port 8080): │
│     - Empfängt POST /v1/chat/..  │
│     - Leitet an lokales Ollama   │
└──────────────────────────────────┘
```

## Voraussetzungen

Auf dem Contributor-Host:

- Docker + Docker Compose
- NVIDIA-GPU mit funktionierenden Treibern
- NVIDIA Container Toolkit (`nvidia-docker2`)
- Ollama (lokal, Port 11434) — mit gewünschtem Modell geladen
- Tailscale, im selben Netz wie das Portal
- Erreichbarkeit: Portal → Agent (Tailscale-IP:8080)

### Ollama prüfen

```bash
ollama --version
ollama list  # zeigt geladene Modelle
curl http://localhost:11434/api/tags
```

Falls noch nicht installiert: `curl -fsSL https://ollama.com/install.sh | sh`

### GPU-Passthrough für Docker testen

```bash
docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi
```

Wenn das funktioniert, ist alles bereit.

## Installation

```bash
cd node-agent/

# .env erstellen
cp .env.example .env
```

### `.env`

```bash
# Welche Tailscale-IP hat dieser Host?
# tailscale ip -4
TAILSCALE_IP=node-ip

# Auf welchem Port lauscht der Agent?
AGENT_PORT=8080

# Portal-URL (Tailscale-IP oder MagicDNS)
PORTAL_URL=http://portal-ip:8765

# Wie oft senden wir Heartbeats?
HEARTBEAT_INTERVAL_SECONDS=5

# Preis in USD pro 1k Tokens (auch Output)
PRICE_PER_1K_TOKENS=0.0005

# Lokales Ollama
OLLAMA_URL=http://host.docker.internal:11434
```

> **Hinweis zu `host.docker.internal`:** Auf Linux muss Docker mit `--add-host=host.docker.internal:host-gateway` gestartet werden. Beispiel im mitgelieferten `docker-compose.yml`.

### Starten

```bash
docker compose up -d
docker compose logs -f agent
```

Erwartete Ausgabe:
```
[agent] Starting GPU-Pool Node-Agent
[agent] Detected GPU: NVIDIA GeForce RTX 4090 (24 GB)
[agent] Registering with portal at http://portal-ip:8765
[agent] Registered as node_id=3
[agent] Starting heartbeat loop (interval=5s)
[agent] Inference proxy listening on :8080
```

## Verifizierung

### Agent läuft

```bash
curl http://node-ip:8080/health
# {"status": "ok", "agent": "running", "ollama": "ok", "gpu": "RTX 4090"}
```

### Portal sieht den Node

```bash
curl http://portal-ip:8765/nodes/ | jq '.[] | select(.tailscale_ip=="node-ip")'
```

### End-to-End-Test

```bash
# Direkt zum Agent
curl -X POST http://node-ip:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen2.5-coder:14b","messages":[{"role":"user","content":"Hi"}]}'

# Über das Portal (Load-Balancing)
curl -X POST http://portal-ip:8765/v1/chat/completions \
  -H "Content-Type: application/json" \
  -D - \
  -d '{"model":"qwen2.5-coder:14b","messages":[{"role":"user","content":"Hi"}]}'
# Header x-pool-node: node-ip
```

## Hardware-Anforderungen

| GPU | VRAM | Empfohlene Modelle | Preis/1k Tokens (Vorschlag) |
|---|---|---|---|
| RTX 3060 | 12 GB | llama3.1:8b, qwen2.5:7b | $0.0003 |
| RTX 3080 | 10/12 GB | llama3.1:8b, qwen2.5:14b (q4) | $0.0004 |
| RTX 4090 | 24 GB | qwen2.5-coder:14b, llama3.1:70b (q4) | $0.0005 |
| A100 | 40/80 GB | llama3.1:70b fp16, mixtral:8x22b | $0.0010 |

> Preise sind nur Vorschläge für den POC. In Produktion würde das ein dynamischer Auktions-Marketplace regeln.

## Monitoring

### Metriken, die der Agent sammelt

- `cpu_pct` — CPU-Auslastung in Prozent
- `ram_pct` — RAM-Auslastung in Prozent
- `gpu_util_pct` — GPU-SM-Auslastung (von `nvidia-smi`)
- `vram_used_gb` — Belegter VRAM in GB
- `vram_total_gb` — Gesamter VRAM (einmalig bei Registrierung)
- `gpu_temp_c` — GPU-Temperatur (TODO)
- `power_w` — GPU-Power-Draw (TODO)

Anzeige im Portal-UI: `http://portal-host:8765/ui/nodes`

### Eigener Node-Status

```bash
# Letzte Heartbeats
curl http://portal-ip:8765/nodes/3/heartbeats?limit=20

# Earnings (letzte 24h)
curl "http://portal-ip:8765/earnings/?node_id=3&hours=24"
```

## Troubleshooting

### Agent registriert sich nicht

**Symptom:** `Registration failed: Connection refused` in den Logs.

**Lösung:**
```bash
# Tailscale aktiv?
tailscale status
# Portal erreichbar?
curl http://portal-ip:8765/health
```

### GPU wird nicht erkannt

**Symptom:** `gpu_util_pct: null` in Heartbeats.

**Lösung:**
```bash
# Im Container prüfen
docker compose exec agent nvidia-smi
# Falls nvidia-smi fehlt: NVIDIA Container Toolkit installieren
```

### Ollama vom Container aus nicht erreichbar

**Symptom:** `Inference proxy error: Connection refused` auf Port 11434.

**Lösung Linux:**
- `host.docker.internal` muss via `--add-host` gemappt sein (siehe `docker-compose.yml`)
- Alternativ: `network_mode: host` im Compose-File (verliert Isolation)

**Lösung macOS/Windows:** `host.docker.internal` funktioniert out-of-the-box.

### Heartbeats kommen durch, aber kein Inference

- Firewall auf Contributor-Host? `sudo ufw status` (Ubuntu)
- Agent lauscht auf 0.0.0.0:8080? `docker compose logs agent | grep "listening"`

## Wartung

### Update

```bash
git pull
docker compose pull
docker compose up -d
```

### Agent pausieren (ohne Datenverlust)

```bash
# Im Portal-UI: Node auf "disabled" setzen
curl -X PATCH http://portal-ip:8765/nodes/3 \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

### Komplett entfernen

```bash
docker compose down -v
# Im Portal: Node löschen
curl -X DELETE http://portal-ip:8765/nodes/3
```
