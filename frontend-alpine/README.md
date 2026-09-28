# GPU-Pool Frontend — Alpine.js (Single-File, kein Build-Step)

Statisches Frontend für den GPU-Pool POC, ausgeliefert von nginx in einem
eigenen Container auf **Port 3000**.

## Tech-Stack

- **HTML/CSS/JS** — vanilla, kein Bundler, kein Build-Step
- **Alpine.js 3** (CDN, gepinnt, `defer`) — Reaktivität
- **nginx 1.27-alpine** — Static Serving + Reverse-Proxy

> Tailwind wurde bewusst entfernt. Es waren nach dem Redesign **0**
> Utility-Klassen im Markup; die CDN war nur noch toter Ballast. Das komplette
> Design steckt in `style.css`. Neue Seiten brauchen kein Tailwind — nur
> `style.css` und `app.js`.

## Designsystem (Anthrazit / Messing)

`style.css` ist das Designsystem. Die Tokens stehen oben als CSS-Custom-Properties,
die Abschnitte sind kommentiert.

| Rolle | Token | Wert |
|---|---|---|
| Grundfläche | `--bg` | `#0e1013` |
| Karten/Panels | `--surface` | `#171b20` |
| Hairline | `--line` | `rgba(255,255,255,.07)` |
| Text / Sekundär | `--text` / `--text-dim` | `#e8ebee` / `#98a1ac` |
| Akzent (Geld, Primäraktion) | `--brass` | `#c9a24a` |
| Status | `--ok` / `--warn` / `--err` | `#5cb87a` / `#d9a441` / `#d1584f` |

Regeln beim Erweitern:

- **Messing ist der einzige Akzent** — nur für Geld/Credits und die Primäraktion.
  Keine bunten Verläufe, keine Neon-Statusfarben, kein Gradient-Purple.
- **Layout über 1px-Hairlines**, nicht über Schatten. Flächen bekommen ihren
  Metall-Charakter über einen 1px-Top-Highlight.
- **Zahlen immer in Mono mit `tabular-nums`** (`.num` / `.mono`), damit Werte in
  Spalten ruhig stehen.
- **Kein `backdrop-filter` auf animierten Ebenen** — kostet auf schwacher GPU
  mehr als die Animation selbst.
- `.grid` ist ein 12-Spalten-Raster mit `.span-1`…`.span-12`. `.g2`…`.g5` sind
  eigenständige Raster — **nicht** mit `.span-N` kombinieren.
- Karten mit unten ausgerichtetem Abschluss (Preis-Packs): `.card.col` + `.fill`.

## Hintergrund-Animation (app-weit)

Drei Ebenen, jede ausschließlich über `transform`/`opacity` — GPU-Kompositor,
**kein Canvas**:

| Klasse | Effekt |
|---|---|
| `.bg-grid` | 64px-Raster, driftet 72 s linear, radial ausgefadet |
| `.bg-glow` | zwei langsame Stahl-/Messing-Blobs, 96 s `alternate` |
| `.bg-grain` | statisches SVG-Filmkorn, `overlay` |

Darüber liegt ein **statischer Scrim** (`body::before`), der den Kontrast
garantiert. `prefers-reduced-motion: reduce` friert die Ebenen ein, das Design
bleibt intakt.

Eingehängt wird das per `mountBackground()` in `app.js`. **Nie** eine neue Seite
mit handgeschriebenem `<canvas>`- oder Div-Block bauen — das Feld kommt
automatisch und identisch auf jeder View.

## Chrome

Topbar und Footer kommen ebenfalls aus `app.js` (`navHTML()`, `footerHTML()`),
damit die Navigation nicht zwischen Seiten auseinanderläuft.

- `navHTML(activeKey)` — `activeKey` ist `dashboard` | `chat` | `credits` |
  `pool` | `nodes` | `earnings` | `agent` | `profile`. Einträge mit
  `providerOnly: true` erscheinen nur für Provider-Rollen.
- Der Footer wird beim Laden angehängt; Seiten brauchen keinen Platzhalter.
- Mobile: die Nav bekommt eine eigene Zeile und scrollt den aktiven Link
  automatisch ins Bild (`revealActiveNav()`).

## Seiten

| Pfad | Zweck |
|---|---|
| `/` (index.html) | Dashboard: Guthaben, API-Key, letzte Aufrufe |
| `/login.html` | Anmeldung |
| `/register.html` | Registrierung (100 Credits zum Start) |
| `/credits.html` | Credits kaufen (Starter/Pro/Business) |
| `/chat.html` | Chat mit Modell-Auswahl |
| `/pool.html` | Community-Pool, Live-Auto-Refresh alle 10 s |
| `/nodes.html` | Eigene GPUs registrieren/verwalten (Provider) |
| `/earnings.html` | Einnahmen pro Node/Event (Provider) |
| `/profile.html` | Rolle + Modell-Whitelist |
| `/agent.html` | Node-Agent-Setup |

## Architektur

- Alle API-Calls gehen über `/api/*`; nginx strippt das Präfix und proxyt auf
  den `api`-Service (FastAPI, Port 8000).
- Auth ist sessionlos: das Backend liefert bei Register/Login einen rohen
  API-Key, der Client legt ihn in `localStorage` und schickt ihn als
  `Authorization: Bearer <key>`.
- `app.js` exportiert global: `API`, `Auth`, `LS`, `toast`, `fmtCredits`,
  `fmtNumber`, `fmtDate`, `timeAgo`, `navHTML`, `footerHTML`,
  `mountBackground`, `renderUsageChart`, `refreshUser`.

## Starten

```bash
# Aus dem Projekt-Root (eine Ebene höher)
docker compose build frontend
docker compose up -d frontend
# erreichbar auf http://<host>:3000/
```

## Backend-Endpunkte, die das Frontend nutzt

- `POST /api/auth/register` · `POST /api/auth/login`
- `GET  /api/v1/me` · `PUT /api/v1/me/role` · `PUT /api/v1/me/allowed-models`
- `GET  /api/v1/models` · `GET /api/v1/available-models`
- `POST /api/v1/chat/completions`
- `GET  /api/nodes/list?only_online=true` · `GET /api/nodes/my`
- `POST /api/nodes/register` · `POST /api/nodes/{id}/heartbeat`
- `GET  /api/nodes/stats/summary` · `POST /api/nodes/{id}/enable`
- `GET  /api/pool/earnings/mine`

## POC-Grenzen

- Kein echtes Stripe: die Kauf-Buttons legen nur einen Aufladewunsch an
  (localStorage), den ein Admin bestätigt.
- Das Nutzungsdiagramm im Dashboard zeigt 7 leere Tage — es gibt noch keinen
  `/v1/stats`-Endpunkt.
- Passwörter liegen als SHA-256 im Backend — für den POC okay, produktiv
  bcrypt/argon2.
