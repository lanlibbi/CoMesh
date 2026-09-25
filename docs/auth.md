# Auth & Rate Limiting (Hardening)

Stand: Auth-Hardening-Pass (LANA-46). Diese Datei beschreibt das *harte*
Token-Modell, die Schwellwerte und die Migrationspfade. Die OpenAI-kompatible
API (`POST /v1/chat/completions`, `GET /v1/models`, `GET /v1/me`, …) ist
**unverändert**: dieselben Pfade, dieselbe Response-Form, derselbe
`Authorization: Bearer <token>`-Header.

---

## 1. Token-Model

Es gibt zwei Typen, beide opak und beide über den gleichen Header genutzt:

| Typ | Präfix | Ausgestellt von | Lebensdauer | Default |
|---|---|---|---|---|
| API-Key | `gpu_…` | `/auth/register`, `POST /admin/users` | lang (kein Ablauf per Default) | `API_KEY_TTL_DAYS=0` |
| Session-Token | `sess_…` | `/auth/login` | kurz, rotierend | `SESSION_TOKEN_TTL_HOURS=24` |

Beide werden **nur gehasht** (SHA-256) in `api_keys.key_hash` gespeichert; der
Rohwert wird genau einmal ausgeliefert. Zusätzlich: `token_type`, `expires_at`
(NULL = läuft nicht ab), `is_active` (Revocation), `last_used_at` (Audit).

Neu gegenüber dem POC:

- `/auth/login` gibt ein **Session-Token mit TTL** aus (vorher: unbegrenzter Key).
- Ein Login **rotiert** die vorherigen Session-Tokens desselben Accounts.
- `POST /auth/logout` widerruft alle Session-Tokens des Aufrufers.
- Abgelaufene/widerrufene Tokens werden zentral in `auth.resolve_token()`
  abgewiesen (`401 API key expired.` / `API key is revoked or inactive.`) —
  kein Handler kann sie umgehen.

### Warum opake Tokens statt JWT

Die Clients sind OpenAI-kompatible Konsumenten, die ein Bearer-Token schicken.
Ein DB-gestütztes opakes Token erfüllt denselben Vertrag **plus** Revocation,
Ablauf und Audit. Ein JWT würde ein zweites Signing-Secret zum Rotieren
einführen und Statelessness erkaufen, die ein Single-Worker-Deployment
(`--workers 1`, siehe `docker-compose.yml`) nicht braucht. Wenn der Pool später
horizontal skaliert, ist der Umstieg auf JWT + `kid`-Rotation in `auth.py`
isoliert möglich (nur `resolve_token` und `issue_token` betroffen).

## 2. Passwörter

- PBKDF2-HMAC-SHA256, 16-Byte-Zufallssalt pro Nutzer, ≥ 240 000 Iterationen
  (`AUTH_PBKDF2_ITERATIONS`). Format: `pbkdf2_sha256$<iters>$<salt_b64>$<hash_b64>`.
- **Legacy-Kompatibilität:** die alte unsalted SHA-256-Variante aus dem POC wird
  beim Login weiter akzeptiert und im selben Request transparent auf PBKDF2
  hochgezogen. Kein Passwort-Reset, kein Aussperren bestehender Accounts.
- **Keine User-Enumeration:** existiert der Account nicht, wird eine
  Dummy-PBKDF2-Rechnung (`verify_password_dummy`) ausgeführt, damit die
  Antwortzeit nicht verrät, ob die E-Mail registriert ist. Die Fehlermeldung
  ist in beiden Fällen identisch (`401 Invalid credentials`).
- `MIN_PASSWORD_LENGTH` (default 8) wird bei `/auth/register` erzwungen.
- Der Seed-Account (`test@example.com`) wird mit PBKDF2 gehasht; sein Key steht
  **nicht mehr im Log**, sondern in `SEED_KEY_PATH` (Mode `0600`).

## 3. Brute-Force-Schutz am Login

Zwei Mechanismen, beide pro IP **und** pro Account:

1. **Token-Bucket**: `RATE_LIMIT_LOGIN_PER_MIN` (default 10) / `…_BURST` (5).
2. **Lockout mit exponentiellem Backoff** (`ratelimit.LoginGuard`):
   nach `LOGIN_MAX_FAILURES` (5) Fehlversuchen innerhalb
   `LOGIN_FAILURE_WINDOW_SECONDS` (900) wird der Key für
   `LOGIN_LOCK_SECONDS` (300) gesperrt, danach verdoppelt sich die Sperre pro
   weiterem Fehlversuch bis `LOGIN_LOCK_MAX_SECONDS` (3600).
   Ein gesperrter Account wird **auch mit korrektem Passwort** abgewiesen (429).

   Die Sperre greift bewusst auch pro IP: ein Angreifer, der viele Accounts von
   einer Quelle durchprobiert (Credential Stuffing), wird ebenfalls gebremst.
   Erfolgreicher Login löscht die Zähler.

## 4. Rate-Limits (Auswahl)

Alle Limits sind Umgebungsvariablen; `429` antwortet immer mit `Retry-After`.

| Scope | Key | ENV (per min / burst) |
|---|---|---|
| Chat | pro User | `RATE_LIMIT_CHAT_PER_MIN` 60 / `RATE_LIMIT_CHAT_BURST` 20 |
| Chat | pro Client-IP | `RATE_LIMIT_CHAT_IP_PER_MIN` 120 / `…_BURST` 40 |
| Login | pro IP **und** pro Account | `RATE_LIMIT_LOGIN_PER_MIN` 10 / `…_BURST` 5 |
| Register | pro IP | `RATE_LIMIT_REGISTER_PER_MIN` 30 / `…_BURST` 10 |
| Nodes | pro Node (Heartbeat) | `RATE_LIMIT_NODE_PER_MIN` 240 / `…_BURST` 60 |
| Admin | pro IP | `RATE_LIMIT_ADMIN_PER_MIN` 30 / `…_BURST` 5 |

- Chat-Limits greifen **nach** der Authentifizierung → der Bucket hängt am
  Nutzer, nicht an der IP (NAT-freundlich). Die IP ist eine zweite Schranke.
- `RATE_LIMITS_DISABLED=1` schaltet alles ab (nur Tests/Benchmarks).
- **Implementierung:** In-Process-Token-Buckets mit Lock
  (`ratelimit.RateLimiter`). Das ist für dieses Deployment exakt (Single
  Worker, dokumentiert in `docker-compose.yml`). Für Multi-Worker später auf
  Redis `INCR`/`EXPIRE` umstellen — nur `Bucket.consume` betroffen.
- `client_ip()` vertraut `X-Forwarded-For` **nicht** per Default (Spoofing);
  hinter einem Proxy `TRUST_PROXY_HEADERS=1` setzen.

## 5. Admin-Endpoints

`POST /admin/users` und `POST /admin/users/{id}/topup` waren im POC **ohne
jede Authentifizierung** erreichbar (jeder konnte Nutzer + API-Keys anlegen und
Credits verteilen). Jetzt gilt `auth.require_admin`:

- `ADMIN_TOKEN` (Statik-Token des Operators) über
  `Authorization: Bearer <token>` **oder** `X-Admin-Token: <token>`, oder
- ein Bearer-Token eines Admin-Accounts (`ADMIN_EMAILS`, kommasepariert) bzw.
  `role == "admin"`.
- **Default-deny:** ist weder `ADMIN_TOKEN` noch `ADMIN_EMAILS` gesetzt, wird
  jeder Admin-Call mit `401` abgewiesen. `ADMIN_AUTH_DISABLED=1` ist die
  ausdrückliche POC-Notluke und loggt eine Warnung pro Request.
- Zusätzlich `RATE_LIMIT_ADMIN_*` pro IP.

## 6. Node-Agent-Keys

- `agent_api_key` wird wie Tokens behandelt: nur `gpu_nodes.api_key_hash`
  (SHA-256) wird gespeichert. Antwort von `/nodes/register` und
  `POST /nodes/{id}/rotate-key` zeigen den Rohwert **einmal**.
- **Migration ohne Ausfall:** beim ersten authentifizierten Request eines
  Alt-Agents wird der Klartext-Key verifiziert und sofort in die Hash-Form
  überführt (`api_key = NULL`). Bestehende Agents laufen also weiter.
- `POST /nodes/{id}/rotate-key` (Owner/Admin) ist der unterstützte Weg zum
  Schlüsselwechsel; der alte Key ist sofort ungültig.
- Vergleiche laufen über `hmac.compare_digest` (kein Timing-Leak).

## 7. Sichtbarkeit (Datenminimierung)

- `GET /nodes/list` (öffentlich) liefert eine reduzierte Projektion:
  **kein** `tailscale_ip`, **kein** `owner_id`, **kein** `earnings_total`,
  **kein** `port`. Ein unauthentifizierter Aufrufer hat keinen Anspruch auf die
  private Overlay-Adresse eines Contributors oder dessen laufende Einnahmen.
- `GET /nodes/{id}`: voller Datensatz für Owner/Admin, sonst die reduzierte
  Projektion (und `404` für offline Nodes).
- `GET /nodes/{id}/connection`: `state` ist öffentlich (Liveness fürs
  Dashboard), `ws_session_id`/`last_ws_seen` nur für Owner/Admin.
- `GET /pool/jobs` verlangt jetzt ein Token und ist auf die eigenen Jobs
  gescoped (vorher: global für jeden gültigen Key). Admins sehen weiter alles.

**Frontend-Hinweis:** `frontend-alpine/pool.js` nutzt `/nodes/list` +
`/nodes/stats/summary` und rendert `name`, `gpu_type`, `vram_gb`,
`current_utilization`, `vram_used_gb`, `status`, `hourly_rate` — alles Felder,
die die öffentliche Projektion weiterhin enthält. Kein Frontend-Change nötig.

## 8. Migrations-Verhalten

`main.py` führt beim Start idempotente SQLite-ALTERs aus:

- `api_keys.token_type` (Default `'api_key'`), `api_keys.expires_at` (NULL)
- `gpu_nodes.api_key_hash` + Backfill aus `gpu_nodes.api_key`

Bestehende Keys und Nodes bleiben damit gültig; nichts muss neu ausgestellt
werden.

## 9. Tests

```bash
# Auth-Hardening (in-process, eigene Wegwerf-DB, keine laufende Portal-Instanz nötig)
python3 tests/test_auth_hardening.py

# Gegen ein laufendes Portal (API-Oberfläche; DB-Assertions werden übersprungen)
GPU_POOL_API=http://localhost:8765 ADMIN_TOKEN=... python3 tests/test_auth_hardening.py
```

Abgedeckt (72 Checks): Hash-Verfahren + Legacy-Upgrade, Session-TTL, Rotation,
Ablauf, Logout-Revocation, Lockout inkl. `Retry-After` und Unabhängigkeit
zwischen Accounts, Rate-Limits pro User/Node/IP, Admin-Default-Deny,
Node-Key-Hashing + Rotation, öffentliche Projektion, `/pool/jobs`-Scoping,
Passwort-Mindestlänge, unauthentifizierte Chat-Abweisung.

Zusätzlich laufen die reaktivierten Suites weiter grün:
`tests/test_features.py` (23/23), `tests/test_ws_connectivity.py` (23/23),
`tests/test_ws_job_stream.py` (29/29).
