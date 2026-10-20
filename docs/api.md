# API-Referenz

Komplette Referenz aller HTTP-Endpoints des CoMesh-Portals.

**Base-URL:** `https://<portal>/v1` — ueber einen oeffentlichen Namen **ohne Port** (TLS auf 443).
Im eigenen Netz stattdessen `http://<host>:8765/v1`: dort ist die API der Port **8765**, die
Oberflaeche hoert auf **8767**. `<portal>` ist der Name, unter dem DU das Portal erreichst
(oeffentlicher Name, DNS-/mDNS-Name, LAN-IP, Name im Mesh-VPN; ein Name ueberlebt einen
DHCP-Lease-Wechsel). Beide Wege sprechen dieselbe API.

**Schluessel:** in der HTTP-Kopfzeile `Authorization: Bearer <api-key>` — das Wort `Bearer`
gehoert dazu. In einer Konfigurationsdatei oder im SDK (`api_key="…"`, `api_key: …`) steht
**nur der Schluessel**; die Bibliothek setzt `Bearer` selbst davor. Wer dort `Bearer …`
eintraegt, schickt es doppelt und bekommt 401.
**Content-Type:** `application/json` (außer bei File-Uploads)

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
    {"role": "user", "content": "What does a load balancer do?"}
  ],
  "temperature": 0.7,
  "max_tokens": 500,
  "stream": false
}
```

**Response-Header:**
- `x-pool-node: node-host` — Adresse des gewählten Nodes (oder `local`)
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
    "message": {"role": "assistant", "content": "A load balancer spreads requests across..."},
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

**Response 200:**
```json
[
  {
    "id": 1,
    "node_url": "http://node-host:11435",
    "port": 8080,
    "gpu_model": "RTX 4090",
    "vram_gb": 24,
    "price_per_1k_tokens": 0.0005,
    "enabled": true,
    "last_seen": "2026-06-11T21:30:15",
    "created_at": "2026-06-01T10:00:00"
  },
  ...
]
```

### `GET /nodes/{node_id}`

Details zu einem Node.

**Response 404:** Node nicht gefunden.

### `POST /nodes/register`

Manuelle Registrierung. Normalerweise macht das der Agent automatisch.

**Request-Body:**
```json
{
  "node_url": "http://node-host:11435",
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
  "node_url": "http://node-host:11435",
  "...": "..."
}
```

**Errors:**
- `409` — Node mit dieser Adresse existiert bereits

### `POST /nodes/heartbeat`

Wird vom Node-Agent alle 5s aufgerufen. Erstellt automatisch einen Node, falls noch nicht vorhanden.

**Request-Body:**
```json
{
  "node_url": "http://node-host:11435",
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
    "node_url": "http://node-host:11435",
    "price_per_1k_tokens": 0.0003,
    "load_pct": 12.1
  },
  "best_node": {
    "id": 1,
    "node_url": "http://node-host:11435",
    "score": [12.1, 0.0003]
  }
}
```

### `GET /pool/jobs`

Liste der letzten Jobs.

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

## Earnings — entfernt

Das Earnings-/Payout-Modell (Node-Betreiber verdienen Coins) ist vom Tisch. Die
Earnings-Seite (`/earnings`), ihre UI-Route und der Navigationseintrag wurden entfernt;
die Verdienstanzeige in der Node-Liste ebenfalls.

Geblieben ist allein die **Abrechnung über Credits**, und die ist im Admin-Bereich
schaltbar (`PUT /admin/settings` -> `credits_enabled`). Die früher hier dokumentierten
Endpunkte `GET /earnings/` und `GET /earnings/timeline` gibt es im Code nicht (mehr);
tatsächlich vorhanden ist nur `GET /pool/earnings/mine` (Node-Sicht des Owners).

## Admin

Alle `/admin`-Endpoints sind **rollen-gated**: sie verlangen einen gültigen API-Key
eines Users mit `role = "admin"`. Ohne Key → `401`, mit Nicht-Admin-Key → `403`.
Jeder schreibende Aufruf landet im Audit-Log (`admin_audit_log`).

Admin-Rechte vergibt nur ein bestehender Admin (`PATCH /admin/users/{id}` mit
`{"role":"admin"}`). Über `PUT /v1/me/role` kann sich ein User **nicht** selbst
zum Admin machen — erlaubt bleiben dort `provider | consumer | both`.

### Idempotenz

Alle schreibenden `POST`-Endpoints akzeptieren einen `Idempotency-Key`-Header.
Der erste Aufruf mutiert und speichert das Ergebnis im Audit-Log; ein Replay mit
demselben Key liefert das gespeicherte Ergebnis mit `"replayed": true` zurück und
mutiert **nicht** erneut. Roh-Keys werden nie im Audit-Log gespeichert: bei einem
Replay einer Key-Rotation kommt `api_key: null` zurück.

```bash
curl -X POST http://portal-host:8765/admin/users/12/topup \
  -H "Authorization: Bearer gpu_admin..." \
  -H "Idempotency-Key: topup-2026-09-25-12-25eur" \
  -H "Content-Type: application/json" \
  -d '{"amount": 25.0, "reason": "manual topup"}'
```

### `GET /admin/whoami`

Billiger Probe-Call: bestätigt, dass der Key admin-berechtigt ist.

**Response 200:** `{"id":1,"email":"admin@…","name":"Platform Admin","role":"admin",…}`

### `GET /admin/overview`

Plattform-Kennzahlen: User (gesamt/aktiv/pro Rolle), Credits, Keys, Nodes
(gesamt/online/offline/disabled, VRAM), Pool-Jobs, Earnings-Splits, Payments.

### `GET /admin/users`

| Parameter | Beschreibung |
|---|---|
| `q` | Substring auf `email` oder `name` |
| `role` | `admin` \| `provider` \| `consumer` \| `both` |
| `is_active` | `true` / `false` |
| `include_inactive` | Default `true` — inaktive User werden mitgelistet |
| `limit` / `offset` | Default 50 / 0, max 500 |

Jeder Eintrag enthält `credits`, `role`, `is_active`, `active_keys`,
`nodes_total`, `nodes_online`, `usage_total_tokens`, `paid_total`.

### `POST /admin/users`

Legt einen User an. **Idempotent per E-Mail**: ein zweiter Aufruf mit derselben
E-Mail liefert `"created": false` und den bestehenden User — kein Duplikat, kein
zweiter Key, keine zusätzlichen Credits.

```json
{"email":"alice@example.com","name":"Alice","initial_credits":50,"role":"both"}
```
**Response 201:** `{"user_id":3,"email":"…","role":"both","api_key":"gpu_… (einmalig)","key_prefix":"gpu_abc1234","credits":50.0,"created":true}`

### `GET /admin/users/{user_id}`

Detail inkl. Key-Metadaten (`key_prefix`, `last_used_at` — nie der Roh-Key),
Node-Kurzliste und Usage-Zähler.

### `PATCH /admin/users/{user_id}`

Partielle Änderung: `name`, `role` (inkl. `admin`), `is_active`,
`allowed_models` (+ `allow_cloud`), optional `expected_updated_at` für
Optimistic Concurrency. Nicht gesetzte Felder bleiben unangetastet, ein
identischer Aufruf ändert nichts.

* `is_active: false` entwertet sofort alle Keys des Users.
* Ein Admin kann sein **eigenes** Konto weder deaktivieren noch degradieren
  (`409`, Lockout-Guard).

### `POST /admin/users/{user_id}/topup`

```json
{"amount": 25.0, "reason": "manual topup"}
```
**Response:** `{"user_id":12,"credits":37.5,"balance_before":12.5,"added":25.0,"reason":"manual topup","transaction_id":88}`

### `POST /admin/users/{user_id}/keys`

Rotiert den Key: entwertet alle aktiven Keys des Users und gibt einen neuen aus
(`?label=` optional). Der Roh-Key wird **einmal** zurückgegeben und nie
gespeichert.

### `POST /admin/users/{user_id}/keys/{key_id}/revoke`

Entwertet genau einen Key. Ein bereits inaktiver Key ist ein erfolgreicher
No-Op (`already_inactive: true`).

### `GET /admin/nodes`

Alle Nodes des Clusters — **inklusive offline und disabled**. Der öffentliche
`/nodes/list` verbirgt diese per Default, das ist der Unterschied.

| Parameter | Beschreibung |
|---|---|
| `q` | Substring auf `name`, `gpu_type`, `node_url` oder dem Alt-Feld `tailscale_ip` |
| `status` | `all` (Default) \| `online` \| `offline` \| `busy` \| `disabled` |
| `owner_id` / `backend` | Filter |
| `include_disabled` | Default `true` — `false` blendet pausierte Nodes aus |
| `limit` / `offset` | Default 100 / 0, max 500 |

Jeder Eintrag enthält `effective_status` (`online | offline | busy | disabled`),
`online`, `seconds_since_seen`, `owner_email`, `connection_state` (WebSocket),
`has_agent_key`, Auslastung und VRAM. Die Response enthält zusätzlich
`summary` (Cluster-Zähler über alle Nodes, unabhängig vom Filter).

### `GET /admin/nodes/{node_id}`

Node-Detail inkl. Besitzer, Job-Statistik (`nodes_jobs_total`,
`nodes_jobs_failed`), Earnings-Events, Heartbeats der letzten 24 h und dem
letzten Heartbeat-Payload.

### `POST /admin/users/{user_id}/nodes/{node_id}/enable?enabled=false`

Pausiert/aktiviert einen Node **jedes** Besitzers — `PATCH /nodes/{id}/enable`
kann das nur owner-scoped. Idempotent (identischer Wert = No-Op).

### Admin-Bootstrap

Ohne Admin-User wäre die Oberfläche nicht erreichbar. Zwei Wege:

1. `ADMIN_API_KEY` (+ optional `ADMIN_EMAIL`, `ADMIN_NAME`) in der Umgebung
   setzen. Beim Start wird der User angelegt/promotet und dieser Key als
   sein einziger aktiver Key installiert. **Empfohlen.**
2. Kein `ADMIN_API_KEY` gesetzt, aber `PROMOTE_ADMIN_EMAIL=<email>` zeigt auf
   einen existierenden User → dieser wird beim Start zum Admin promovet
   (Warnung im Log). **Default ist leer / aus** — ein Deployment soll nicht
   stillschweigend einem Seed-/POC-Konto Adminrechte geben.
3. Weder noch: beim Install wird ein Key erzeugt und in
   `$DATA_DIR/admin_api_key.txt` (chmod 600) abgelegt; jeder weitere Start
   verwendet denselben. Das ist der **Default** — eine frische Installation hat
   damit einen erreichbaren Admin-Bereich, ohne dass jemand ein Secret
   erfinden muss.

> Der frühere Caveat „`/admin/*` ist unauthentifiziert" ist damit erledigt:
> die alten offenen Routen (`POST /admin/users`, `POST /admin/users/{id}/topup`)
> wurden entfernt. `POST /admin/users/legacy-create` antwortet nur noch mit
> `308` und verweist auf die authentifizierte Route.

---

## UI-Endpoints (HTML)

| Endpoint | Beschreibung |
|---|---|
| `GET /ui/nodes` | Node-Übersicht mit Live-Metriken |
| `GET /ui/pool` | Pool-Status + Last-Verteilung |
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
- Pro Quell-Adresse: 1000 req/min
- Pro Model: 100 req/min
- Burst: 50 req/s

Mit `429 Too Many Requests` + `Retry-After` Header.
