# GPU-Pool Frontend (Alpine.js + Tailwind)

A lightweight single-page frontend for the GPU-Pool POC, served by nginx
in a separate Docker container on **port 3000**.

## Tech stack
- **HTML/CSS/JavaScript** (vanilla, no framework)
- **Alpine.js 3** (CDN) — for reactivity
- **Tailwind CSS** (CDN) — for styling
- **nginx 1.27-alpine** — static file serving + reverse proxy

## Pages
| Path | Purpose |
|------|---------|
| `/` (index.html) | Dashboard: credit balance, API key management, recent calls |
| `/login.html` | Login form |
| `/register.html` | Registration form (gives 100 free credits) |
| `/credits.html` | Buy credits (3 packs: Starter/Pro/Business) + manual top-up requests |
| `/chat.html` | Chat interface with model selector |

## Architecture
- All API calls go through `/api/*` which nginx proxies to the `api` service
  (the FastAPI backend on port 8000) with the `/api` prefix stripped.
- Auth is session-less: the backend returns a raw API key on
  register/login; the client stores it in `localStorage` and sends it as
  `Authorization: Bearer <key>` on every request.

## Files
- `index.html`, `login.html`, `register.html`, `credits.html`, `chat.html`
- `app.js` — shared client (API wrapper, auth helpers, formatting, nav)
- `style.css` — project-specific styling on top of Tailwind
- `nginx.conf` — reverse proxy + static file serving
- `Dockerfile` — copies everything into `nginx:1.27-alpine`

## How to run
```bash
# From the project root (one level up)
docker compose build frontend
docker compose up -d frontend

# Frontend is now reachable on:
http://<host>:3000/
```

## Backend integration
The frontend talks to these endpoints (proxied through `/api`):
- `POST /api/auth/register` — public registration (returns API key + 100 credits)
- `POST /api/auth/login` — public login (returns a fresh API key, deactivates old ones)
- `GET  /api/v1/me` — current user + credit balance (requires `Authorization: Bearer <key>`)
- `GET  /api/v1/models` — list Ollama models
- `POST /api/v1/chat/completions` — OpenAI-compatible chat (deducts credits)

## Notes / POC limitations
- No real Stripe: the "Buy now" buttons simulate a checkout confirmation;
  credits are NOT actually added. The "manual top-up" form stores requests
  in `localStorage` only.
- The usage chart on the dashboard shows 7 empty days (no `/v1/stats` endpoint
  yet); the rest of the dashboard pulls live data from `/v1/me`.
- Passwords are stored as SHA-256 hashes in the backend — fine for a POC,
  use bcrypt/argon2 in production.
