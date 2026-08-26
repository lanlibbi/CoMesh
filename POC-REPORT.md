# GPU-Pool POC - Build Report

**Date:** 2026-06-05 22:58 - 23:05 (Europe/Berlin)
**Host:** `ai-lanlibbi` (100.126.79.111)
**Status:** ✅ RUNNING — all tests pass

## What was built

A FastAPI-based GPU-sharing POC at `/home/christian/projects/opencode-poc/`
on `ai-lanlibbi`, exposing an **OpenAI-compatible** `/v1/chat/completions`
endpoint that proxies to the host's existing Ollama instance.

### Files created (all 8)

| File | Size | Purpose |
|------|------|---------|
| `main.py` | 12 KB | FastAPI app, routes, lifespan/seed |
| `auth.py` | 2.3 KB | API-key auth (SHA-256 hashed) |
| `models.py` | 3.3 KB | SQLAlchemy: User, ApiKey, CreditTransaction, Usage |
| `database.py` | 868 B | SQLite engine + session |
| `Dockerfile` | 361 B | python:3.11-slim, uvicorn entrypoint |
| `docker-compose.yml` | 458 B | API service + named volume, host.docker.internal |
| `requirements.txt` | 113 B | fastapi, uvicorn, sqlalchemy, pydantic, httpx |
| `README.md` | 3.4 KB | Setup + API docs |

## Deployment

- **Container:** `gpu-pool-api` (image: `opencode-poc-api:latest`)
- **Port mapping:** `8765:8000` (host 8000 is taken by Portainer on this box)
- **Volume:** `opencode-poc_sqlite_data` → `/data` (SQLite + seed key)
- **Ollama:** runs on host (not in compose), reached via `host.docker.internal:11434`
- **Env:** `OLLAMA_URL=http://host.docker.internal:11434`, `DEFAULT_MODEL=qwen2.5-coder:7b`, `DOCKER_ENV=1`

## Test user (seeded on first start)

- **email:** `test@example.com`
- **name:** `Test User`
- **initial credits:** 100.0
- **API key:** `gpu_ScOgpgvZWQDh2OgPY_XmsRI2uELsUud8tWQyEvPn2bs`
  - Also persisted to `/data/seed_api_key.txt` on the Docker volume
  - Key prefix shown in DB: `gpu_ScOgpgvZ`

> ⚠️ The raw key is only visible in the container log / seed file on first
> start. Subsequent restarts won't show it again. If lost, create a new user
> via `POST /admin/users` or `topup` the existing one.

## Verification (all passed)

| # | Test | Result |
|---|------|--------|
| 1 | `GET /health` | `{ollama_reachable: true}` |
| 2 | `GET /` | service info |
| 3 | `GET /v1/me` (with key) | user 1, 100 credits |
| 4 | `GET /v1/models` | lists 9 Ollama models |
| 5 | `POST /v1/chat/completions` | **"Hallo"** — 38 prompt + 2 completion tokens, model `qwen2.5-coder:7b` |
| 6 | `GET /v1/me` after chat | 100 → 99.99996 credits (charged 4e-05 = 0.00004) |
| 7 | `GET /v1/me` (no key) | HTTP 401 |
| 8 | `GET /v1/me` (bad key) | HTTP 401 |

### DB state after the smoke test

```
users:                [(1, 'test@example.com', 'Test User')]
api_keys:             [(1, 1, 'gpu_ScOgpgvZ', 'seed-test-key')]
credit_transactions:  [
  (1, 1, 100.0,    100.0,    'initial credit (seed)'),
  (2, 1, -0.00004, 99.99996, 'chat: qwen2.5-coder:7b (40 tokens)')
]
usages:               [(1, 1, 'qwen2.5-coder:7b', 38, 2, 0.00004)]
```

All on the named Docker volume `opencode-poc_sqlite_data` — survives restarts.

## How to use

```bash
# Health
curl http://100.126.79.111:8765/health

# Chat
curl -X POST http://100.126.79.111:8765/v1/chat/completions \
  -H "Authorization: Bearer gpu_ScOgpgvZWQDh2OgPY_XmsRI2uELsUud8tWQyEvPn2bs" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2.5-coder:7b",
    "messages": [{"role":"user","content":"Hello!"}]
  }'

# Create more users
curl -X POST http://100.126.79.111:8765/admin/users \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@example.com","name":"Alice","initial_credits":50}'

# Top up existing user
curl -X POST 'http://100.126.79.111:8765/admin/users/1/topup?amount=25.0'
```

## Caveats / next steps

1. **`/admin/*` endpoints are unauthenticated.** Acceptable for POC on a
   trusted LAN; must be gated before any external exposure.
2. **Credit cost is flat** (`0.001` credits per 1K tokens). Could be made
   per-model to reflect real GPU cost.
3. **No streaming yet** — `stream: true` is accepted in the request schema
   but ignored; `/v1/chat/completions` always returns a complete response.
4. **No rate limiting** — would be a sensible next addition.
5. **OpenCode** is not installed on `ai-lanlibbi` (only `docker`, `docker-compose`,
   `python3.12` confirmed). The POC was built by hand-written code; for future
   iterations we could install OpenCode and use it for code generation.

## Payments (v0.2)

Added a payment layer in test/mock mode. All four providers are wired
through a unified `POST /payments/{provider}/checkout` endpoint, with
webhook + return-URL handlers for fulfilment. In test mode (no SDK
configured) the endpoints return a mock URL that, when opened, marks
the payment succeeded and credits the user.

### Credit packages

| Paket       | Credits | Preis  | Bonus   | Total   |
|-------------|--------:|-------:|--------:|--------:|
| Starter     |  1 000  | 10 €   |     -   |  1 000  |
| Pro         |  5 000  | 45 €   |   500   |  5 500  |
| Business    | 20 000  | 160 €  |  4 000  | 24 000  |
| Enterprise  |100 000  | 700 €  | 25 000  |125 000  |

### Endpoints

- `GET  /payments/config`               — package + provider availability
- `POST /payments/{stripe|paypal|alipay|applepay}/checkout`
- `POST /payments/stripe/webhook`       — Stripe events (`checkout.session.completed`, `payment_intent.succeeded`)
- `GET  /payments/stripe/success`       — return URL after Stripe Checkout
- `POST /payments/paypal/ipn`           — PayPal IPN
- `GET  /payments/paypal/capture`       — return URL after PayPal approval
- `GET  /payments/alipay/success`       — return URL after Alipay (via Stripe)
- `GET  /payments/applepay/success`     — return URL after Apple Pay (via Stripe)
- `POST /payments/stripe/simulate-success` — dev helper
- `GET  /payments/history`              — current user's payment history
- `GET  /payments/{id}`                 — single payment

### Going live

1. Set `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`
   in `.env` (or compose `environment:`). The Stripe SDK is **not** installed
   in the POC image; uncomment the line in `requirements.txt` and rebuild.
2. Set `PAYPAL_CLIENT_ID` + `PAYPAL_CLIENT_SECRET` and uncomment
   `paypalrestsdk` for live PayPal.
3. For Apple Pay, register your domain with Stripe and use the returned
   `client_secret` with the Stripe.js `paymentRequest` button on the frontend.
4. Set `APP_PUBLIC_URL` to the public HTTPS URL so the return URLs work
   for real customers.

### Frontend

Three HTML pages served by FastAPI itself:

- `/`         — login / register
- `/chat`     — chat UI
- `/credits`  — buy credit packages (4 buttons per package, transaction history)

Open http://100.126.79.111:8765/credits in a browser, log in with
`test@example.com` / `password123`, and click any payment button to test
the full flow.
