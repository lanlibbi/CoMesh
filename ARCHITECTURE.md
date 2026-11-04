# Architektur

> **Abstract (EN).** CoMesh is a self-hosted GPU pool. A FastAPI portal on SQLite is
> the only fixed address: it authenticates accounts, gates models, picks a node,
> forwards the job and books the usage. A small Python agent on every provider host
> connects **outbound** over WebSocket (`/agent/connect`) and answers jobs as frames,
> so no node needs an open port; without that socket the portal falls back to HTTP.
> The portal also offers `/ws/chat` because a proxy cuts long HTTP requests. What
> follows describes the code as it is today — each claim names the file it comes
> from, valid for version 0.6.10.

Dieses Dokument beschreibt den Stand, der im Code steht, nicht den Plan. Belege
stehen als `datei:zeile` daneben.

## Rollen

**Portal** (`main.py`, `pool.py`, `nodes.py`, `ws.py`) — FastAPI + SQLAlchemy auf
SQLite. Es hält die OpenAI-kompatible API (`/v1/models`, `/v1/chat/completions`),
Konten und Rollen, Modellfreigaben, Abrechnung, die Pool-Logik und die
Web-Oberfläche. Das Portal ist die einzige Adresse, die ein Client kennt.

**Node-Agent** (`node-agent/agent.py`, ausgeliefert als ein PyInstaller-Binary) —
läuft auf jedem Provider-Rechner neben dem lokalen Backend, meldet GPU, VRAM und
Auslastung und reicht Aufträge an Ollama (`/api/chat`) oder einen
OpenAI-kompatiblen Server weiter (`BACKEND=openai`). Er lauscht auf **11435**
(`node-agent/agent.py:274`; `AGENT_PORT`, Vorgabe aus `netinfo.DEFAULT_AGENT_PORT`).
Die früher dokumentierten **8080** gehören nicht hierher — das ist der Port von
Open WebUI auf demselben Host, nicht der des Agenten.

**Nutzer und Provider** — beides sind Konten (`users`). Ein Provider besitzt eine
oder mehrere Nodes (`gpu_nodes.owner_id`); registrieren darf nur, wer die Rolle
`provider` oder `both` hat, `consumer` bekommt 403 (`nodes.py:306`).

## Transportwege

Drei Wege, klar getrennt:

| Weg | Wofür | Warum |
|---|---|---|
| HTTP | Steuerung (Registrierung, Heartbeat, Admin, `/v1/models`), Chat mit SSE | kurzlebig, durch jeden Proxy |
| WS `/agent/connect` | Portal → Agent, Aufträge | der Agent baut auf, kein Inbound-Port |
| WS `/ws/chat` | Browser → Portal, Chat | Proxys kappen lange HTTP-Requests |

**`/agent/connect`** (`ws.py:327`) ist die Gegenrichtung der naheliegenden
Annahme: nicht das Portal ruft die Node, sondern der Agent hält die Verbindung.
Das Portal schickt `{"type":"job","job_id":…,"payload":…}` (`ws.py:208`), der
Agent antwortet mit `job_result` beziehungsweise `job_result_chunk` für
Token-Deltas (`ws.py:430`, `ws.py:445`). Daraus folgt der wichtigste
Betriebsvorteil: keine Node braucht einen offenen Port, NAT, Firewall und
wechselnde Adressen sind gleichgültig. Fehlt die Verbindung, weicht der Router für
diese Node auf HTTP an `node_url` aus (`pool.py:581`).

**`/ws/chat`** (`ws.py:644`) existiert für den Betrieb hinter einem Proxy:
Cloudflare beendet einen HTTP-Request nach rund 100 s — und eine WebSocket-Sitzung
ohne Frames in *beide* Richtungen ebenso. Deshalb sendet das Portal, solange
`route_request` läuft, alle 15 s ein `keepalive`-Frame (`ws.py:585`,
`ws.py:599`). Der Key reist bevorzugt im Subprotocol `api-key.<raw>`, nicht in der
URL.

**Ein Prozess.** Die WS-Registry und die Futures laufender Aufträge liegen im
Prozess (`ws.py:125`); das Portal startet deshalb mit `--workers 1`
(`docker-compose.yml:65`). Mehrere Worker würden Agent-Verbindung und
Request-Handler voneinander trennen.

## Anfrageweg einer Modellanfrage

`POST /v1/chat/completions` (`main.py:1076`):

1. **Auth** — `Authorization: Bearer gpu_…`; der Schlüssel wird als SHA-256 gegen
   `api_keys.key_hash` geprüft, das Konto muss aktiv sein (`auth.py:151`).
   `quota_mode=blocked` → 403, bei `balance` und Guthaben unter 0,01 → 402
   (`main.py:1100`).
2. **Rate-Limit** — Token-Bucket je Nutzer und je Client-IP, Antwort 429 mit
   `Retry-After` (`ratelimit.py:217`).
3. **Modell-Gate** — `user.can_use_model()` (`models.py:95`): ohne Liste alle
   lokalen Modelle, mit Liste genau diese; Cloud-Modelle zusätzlich nur mit
   `allow_cloud` und nur, wenn ein aktiver Node sie anbietet (`pool.py:479`).
4. **Routing** (`pool.route_request`, `pool.py:447`):
   1. lokales Ollama auf dem Portal-Host. Nur ein *Verbindungs*fehler fällt weiter;
      ein HTTP-Fehler von Ollama wird durchgereicht (`pool.py:548`).
   2. `find_best_node` (`pool.py:126`) filtert in dieser Reihenfolge: online,
      Node-Whitelist, Konto-Whitelist, **VRAM-Gate** — danach entscheidet die
      Auswahl. Online heißt: WS-Ping jünger als 90 s **oder** HTTP-Heartbeat jünger
      als 90 s (`models.py:293`, `pool.py:67`). Das VRAM-Gate vergleicht
      `vram_gb − vram_used_gb` mit einer Schätzung aus dem Modellnamen (`:7b` →
      5 GB, `:13b` → 9 GB, `70b` → 40 GB, sonst 4 GB; `pool.py:183`) und verwirft
      die Node, wenn der Speicher nicht reicht (`pool.py:163`).

      **Lastverteilung (seit 0.6.11).** Unter den Kandidaten gilt:
      1. **wenigste laufende Anfragen** (`pool.node_inflight`, ein Zähler im
         Prozess, um jede Weiterleitung herum erhöht und im `finally` wieder
         verringert — Erfolg, Fehler, Timeout, Abbruch),
      2. dann der **Score** `hourly_rate + 0,5 · current_utilization`
         (+ 0,2 für `status != online`),
      3. bei vollständigem Gleichstand **reihum** (`itertools.count`, Modulo über
         die Gleichstandsgruppe).

      Vorher entschied **nur** der Score. Damit war die Auswahl deterministisch:
      zwei gleichwertige Nodes mit demselben Modell, dieselbe Sortierreihenfolge —
      der zweite Eintrag bekam nie einen Auftrag, und zwei gleichzeitige Anfragen
      liefen beide auf dieselbe Maschine. Der Preis entscheidet weiterhin, aber
      nur unter gleich belasteten Nodes.
   3. Transport je Node: `connection_state == "connected"` → WS, sonst HTTP. Bis zu
      drei Nodes werden versucht, ein Fehlschlag führt zum nächsten (`pool.py:574`).
   4. Bleibt nichts übrig → 503; der Cloud-Overflow ist ein Stub (`pool.py:634`).
5. **Buchung** — `Usage` immer, `CreditTransaction` nur bei `credits_enabled` und
   `quota_mode=balance`, `PoolJob` mit Quelle, Node, Tokens und Latenz; bei einer
   Community-Node zusätzlich `NodeEarning` im Verhältnis 70/20/10
   (`main.py:1152`, `pool.py:49`).
6. **Antwort** — OpenAI-Form inklusive `usage`; `stream: true` liefert
   Server-Sent Events (`main.py:1117`).

## Zugangssperren

| Sperre | Richtung | Wo |
|---|---|---|
| Account-Schlüssel `gpu_…` | Client → Portal | Bearer-Header, SHA-256 in `api_keys.key_hash`, Klartext nur einmal (`auth.py:86`) |
| `X-Node-Key` | Agent → Portal | eigener Schlüssel je Node, gehasht in `gpu_nodes.api_key_hash` (`nodes.py:248`) |
| `X-Node-Secret` | Portal → Agent | gemeinsames `NODE_SHARED_SECRET`, sonst 401 (`pool.py:79`, `node-agent/agent.py:650`) |
| `X-Admin-Token` | Admin → Portal | `ADMIN_API_KEY` oder Bearer eines Admin-Kontos (`auth.py:349`) |

- **Rollen** — `provider`, `consumer`, `both`, `admin` (`models.py:48`). Modelle
  werden doppelt freigegeben: am Konto (`users.allowed_models`) und an der Node
  (`gpu_nodes.allowed_models`), Cloud zusätzlich über `allow_cloud`.
- **Rate-Limits** (`ratelimit.py:215`) — Chat 60/min + 20 Burst je Nutzer und
  120/min je IP, Login 10/min mit wachsender Sperre nach Fehlversuchen
  (`LOGIN_GUARD`), Node-Endpunkte 240/min (der Heartbeat läuft alle 30 s), Admin
  30/min. Der Limiter zählt im Prozess, nicht verteilt — passend zu `--workers 1`.
- **Agent** — jeder Endpunkt außer `/health` verlangt `X-Node-Secret`
  (`node-agent/agent.py:650`). Fehlt die Variable, bleibt der Agent offen und warnt beim
  Start (`node-agent/agent.py:1266`): Rückweg, nicht Normalzustand.
- **Protokoll** — Rollen-, Freigabe- und Passwortänderungen landen in
  `admin_audit_log`, das Passwort nur als „gesetzt" (`admin.py:1006`).

## Datenhaltung

SQLite unter `/data/gpu_pool.db`, Tabellen per `create_all` beim Start
(`database.py`).

| Tabelle | Rolle |
|---|---|
| `users`, `api_keys` | Konten, Rollen, Freigaben, Schlüssel (nur Hash und Präfix) |
| `usages`, `credit_transactions`, `payments` | Verbrauch, Guthabenbewegungen, Zahlungen |
| `gpu_nodes`, `node_heartbeats` | Knoten samt `connection_state`/`last_ws_seen`, dazu die Zeitreihe der Meldungen |
| `pool_jobs`, `node_earnings` | Ergebnis eines Routings und die Anteile je Node |
| `system_settings`, `admin_audit_log` | Laufzeit-Schalter (`credits_enabled`), Änderungsprotokoll |

## Was bewusst nicht existiert

- **Kein Model-Catalog-Sync.** Das Portal fragt keine Node, welche Modelle dort
  installiert sind. `GET /v1/models` liest Ollama auf dem Portal-Host und filtert
  nach den Freigaben (`main.py:586`); ein Node-Modell erscheint nur, weil der
  Provider es in die Liste schreibt. Eine falsche Liste fällt erst beim Auftrag
  auf — es gibt keinen Abgleich.
- **Keine Reproduzierbarkeit der Binaries.** Die Builds entstehen per PyInstaller
  auf gehosteten Runnern (`macos-latest`); derselbe Quellstand ergibt nicht
  denselben Hash.
- **Keine Signatur.** Weder Notarisierung noch Authenticode. Die SHA-256-Summe
  liegt neben dem Binary auf demselben Server — sie schützt gegen
  Übertragungsfehler, nicht gegen einen kompromittierten Server.
- **Kein Cloud-Overflow, keine verteilte Skalierung.** 503 statt Ausweichen
  (`pool.py:634`); die WS-Registry ist prozesslokal.

## Adressierung

Kein Bestandteil braucht eine feste IP. Angesprochen wird eine Node über
`node_url`; bleibt das Feld leer, übernimmt das Portal die Adresse aus dem ersten
Heartbeat und markiert sie als automatisch erkannt (`nodes.py:491`). Details:
[docs/network.md](docs/network.md), Betrieb des Agenten:
[docs/node-agent.md](docs/node-agent.md).
