# API-Referenz

Komplette Referenz aller HTTP-Endpoints des GPU-Pool-Portals.

**Base-URL:** `http://portal-host:8765` (oder via Tailscale-MagicDNS)
**Content-Type:** `application/json` (außer bei File-Uploads)

> **Auth-Hardening (LANA-46):** Token-Modell, Rate-Limits, Brute-Force-Schutz
> und Admin-Authentifizierung sind in **[auth.md](auth.md)** dokumentiert.
> Kurzfassung: alle geschützten Endpoints nehmen `Authorization: Bearer <token>`,
> wobei `/auth/register` + `POST /admin/users` einen langen API-Key (`gpu_…`)
> und `/auth/login` ein Session-Token mit TTL (`sess_…`) ausgeben. Die
> OpenAI-kompatible Oberfläche ist unverändert.

---

## Health

### `GET /health`

Liveness-Check.

**Response 200:**
```json
{
  "status": "ok",
  "nodes_online": 3,
  "local_ollama": "ok"
}
```

---

## Chat Completions (OpenAI-kompatibel)

### `POST /v1/chat/completions`

OpenAI-kompatibler Endpoint. Wird automatisch an den besten Node verteilt.

**Request-Body:** Standard-OpenAI-Schema.

```json
{
  "model": "qwen2.5-coder:14b",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Explain Tailscale in one sentence."}
  ],
  "temperature": 0.7,
  "max_tokens": 500,
  "stream": false
}
```

**Response-Header:**
- `x-pool-node: node-ip` — IP des gewählten Nodes (oder `local`)
- `x-pool-tokens-in: 42` — Input-Token-Count
- `x-pool-tokens-out: 128` — Output-Token-Count
- `x-pool-cost-usd: 0.0001` — Geschätzte Kosten
- `x-pool-duration-ms: 1234` — Verarbeitungsdauer

**Response 200:** Standard-OpenAI-Schema.
```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "created": 1718,
  "model": "qwen2.5-coder:14b",
  "choices": [{
    "index": 0,
    "message": {"role": "assistant", "content": "Tailscale creates a WireGuard-based mesh VPN..."},
    "finish_reason": "stop"
  }],
  "usage": {
    "prompt_tokens": 42,
    "completion_tokens": 128,
    "total_tokens": 170
  }
}
```

**Errors:**
- `503` — Keine Nodes online
- `504` — Node hat nicht rechtzeitig geantwortet
- `502` — Node hat Fehler zurückgegeben

---

## Nodes

### `GET /nodes/`

Liste aller registrierten Nodes.

**Response 200:** reduzierte Projektion (öffentlich). `tailscale_ip`, `port`,
`owner_id`, `earnings_total` und `total_hours` sind **nicht** enthalten; der
volle Datensatz kommt über die authentifizierten Endpoints (`GET /nodes/my`,
`GET /nodes/{id}` als Owner/Admin).

```json
[
  {
    "id": 1,
    "name": "ai-lanlibbi (RTX 3080 + RTX 3060)",
    "gpu_type": "NVIDIA RTX 3080 + RTX 3060",
    "vram_gb": 22,
    "status": "online",
    "hourly_rate": 0.0,
    "backend": "ollama",
    "last_seen": "2026-06-11T21:30:15",
    "current_utilization": 0.12,
    "vram_used_gb": 3.4,
    "description": null,
    "allowed_models": null,
    "created_at": "2026-06-01T10:00:00"
  },
  ...
]
```

### `GET /nodes/{node_id}`

Details zu einem Node. Owner/Admin erhalten den vollen Datensatz (inkl.
`tailscale_ip`, `port`, `earnings_total`), alle anderen die reduzierte
Projektion; offline Nodes liefern für Nicht-Owner `404`.

**Response 404:** Node nicht gefunden.

### `POST /nodes/register`

Manuelle Registrierung. Normalerweise macht das der Agent automatisch.

**Request-Body:**
```json
{
  "tailscale_ip": "node-ip",
  "port": 8080,
  "gpu_model": "RTX 4090",
  "vram_gb": 24,
  "price_per_1k_tokens": 0.0005
}
```

**Response 201:**
```json
{
  "id": 3,
  "tailscale_ip": "node-ip",
  "...": "..."
}
```

**Errors:**
- `409` — Node mit dieser Tailscale-IP existiert bereits

### `POST /nodes/heartbeat`

Wird vom Node-Agent alle 5s aufgerufen. Erstellt automatisch einen Node, falls noch nicht vorhanden.

**Request-Body:**
```json
{
  "tailscale_ip": "node-ip",
  "cpu_pct": 23.4,
  "ram_pct": 41.2,
  "gpu_util_pct": 78.5,
  "vram_used_gb": 12.3
}
```

**Response 204:** No Content.

### `PATCH /nodes/{node_id}`

Update von Node-Feldern (z. B. `enabled` zum Pausieren).

**Request-Body (alle Felder optional):**
```json
{
  "enabled": false,
  "price_per_1k_tokens": 0.0003
}
```

**Response 200:** Updated node object.

### `DELETE /nodes/{node_id}`

Node entfernen. Heartbeats dieses Nodes werden ignoriert.

**Response 204:** No Content.

### `GET /nodes/{node_id}/heartbeats`

Letzte Heartbeats eines Nodes.

**Query-Parameter:**
- `limit` (default: 100)
- `since_minutes` (default: 60)

**Response 200:**
```json
[
  {
    "id": 1234,
    "node_id": 3,
    "timestamp": "2026-06-11T21:30:15",
    "cpu_pct": 23.4,
    "ram_pct": 41.2,
    "gpu_util_pct": 78.5,
    "vram_used_gb": 12.3
  },
  ...
]
```

---

## Pool

### `GET /pool/`

Aktueller Pool-Status.

**Response 200:**
```json
{
  "total_nodes": 5,
  "online_nodes": 4,
  "avg_load_pct": 45.2,
  "cheapest_node": {
    "id": 1,
    "tailscale_ip": "portal-ip",
    "price_per_1k_tokens": 0.0003,
    "load_pct": 12.1
  },
  "best_node": {
    "id": 1,
    "tailscale_ip": "portal-ip",
    "score": [12.1, 0.0003]
  }
}
```

### `GET /pool/jobs`

Liste der letzten Jobs. **Auth:** Token erforderlich; die Liste ist auf die
eigenen Jobs gescoped (eigene Requests **und** Jobs auf den eigenen Nodes).
Admins sehen weiterhin alles (`ADMIN_EMAILS` / `role=admin`).

**Query-Parameter:**
- `limit` (default: 50)
- `status` (`running` | `success` | `error` | `timeout`)
- `node_id`

**Response 200:**
```json
[
  {
    "id": "uuid-v4",
    "request_id": "req-abc123",
    "node_id": 3,
    "model": "qwen2.5-coder:14b",
    "started_at": "2026-06-11T21:30:15",
    "finished_at": "2026-06-11T21:30:18",
    "status": "success",
    "tokens_in": 42,
    "tokens_out": 128,
    "duration_ms": 3215
  },
  ...
]
```

### `GET /pool/jobs/{request_id}`

Details zu einem einzelnen Job.

---

## Earnings

### `GET /earnings/`

Aggregierte Earnings pro Node.

**Query-Parameter:**
- `hours` (default: 24) — Zeitfenster
- `node_id` — Optional, alle wenn weggelassen

**Response 200:**
```json
[
  {
    "node_id": 1,
    "tailscale_ip": "portal-ip",
    "total_tokens": 1234567,
    "total_jobs": 234,
    "total_usd": 0.6173
  },
  ...
]
```

### `GET /earnings/timeline`

Earnings über Zeit (für Charts).

**Query-Parameter:**
- `hours` (default: 24)
- `bucket` (`minute` | `hour` | `day`, default: `hour`)

**Response 200:**
```json
[
  {
    "timestamp": "2026-06-11T20:00:00",
    "node_id": 1,
    "tokens": 5678,
    "usd": 0.0028
  },
  ...
]
```

---

## UI-Endpoints (HTML)

| Endpoint | Beschreibung |
|---|---|
| `GET /ui/nodes` | Node-Übersicht mit Live-Metriken |
| `GET /ui/pool` | Pool-Status + Last-Verteilung |
| `GET /ui/earnings` | Earnings-Charts (pro Node, kumulativ) |
| `GET /ui/agent` | Setup-Anleitung für Node-Agents |
| `GET /ui/jobs/{id}` | Job-Detail mit Token-Usage |

---

## Fehler-Codes

| Code | Bedeutung |
|---|---|
| `400` | Bad Request (fehlende Felder, ungültiges JSON) |
| `404` | Not Found (Node/Job existiert nicht) |
| `409` | Conflict (z. B. doppelte Registrierung) |
| `500` | Internal Server Error |
| `502` | Bad Gateway (Node-Fehler weitergereicht) |
| `503` | Service Unavailable (keine Nodes online) |
| `504` | Gateway Timeout (Node antwortet nicht) |

Alle Fehler-Responses haben das Format:
```json
{
  "detail": "Human-readable error message",
  "code": "MACHINE_READABLE_CODE"
}
```

---

## Rate-Limits (TODO)

Im POC nicht implementiert. Für Produktion:
- Pro Tailscale-IP: 1000 req/min
- Pro Model: 100 req/min
- Burst: 50 req/s

Mit `429 Too Many Requests` + `Retry-After` Header.
