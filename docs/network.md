# CoMesh — Netzwerk einrichten (DHCP-tauglich)

CoMesh braucht **kein** bestimmtes Netz. Weder Portal noch Node-Agents haben
eine feste IP, und **Tailscale ist eine Option, keine Voraussetzung**. Dieses
Dokument beschreibt, was stattdessen gilt: wie sich beide Seiten finden, ohne
dass jemand eine Adresse einträgt.

## Die eine Regel

**Ein Node wird über `node_url` angesprochen, nicht über eine IP.**

| Feld | Inhalt | Beispiel |
|---|---|---|
| `node_url` | `http(s)://<host>[:port]` | `http://mein-gpu.local:11435` |
| `port` | Port des Node-Agents (wird angehängt, wenn `node_url` keinen hat) | `11435` |

Ist `node_url` leer, **leitet das Portal die Adresse ab** — aus dem ersten
Heartbeat des Agents. Das ist der Standardweg in einem DHCP-Netz: der Agent
meldet sich, das Portal lernt dabei, wo er steht. Ändert sich der Lease, meldet
sich der Agent mit einer neuen Adresse, und `node_url` wird neu gesetzt
(Spalte `node_url_auto = true`).

## Was wohin gehört

| Ort | Wert | Warum |
|---|---|---|
| Portal, `.env` → `APP_PUBLIC_URL` | z. B. `http://portal-host:8765` | Rückkehr-URLs der Zahlungsanbieter. Fehlt der Wert, leitet das Portal ihn aus dem Request ab — dann aber pro Anfrage. |
| Portal, `docker-compose.yml` | Port-Mappings über `COMESH_BIND_ADDRESS` (8767) und `COMESH_API_BIND_ADDRESS` (8765), Vorgabe `127.0.0.1` | Keine festen externen Adressen. Eine frische Installation antwortet nur auf dem eigenen Host; für Tunnel, vorgelagerten Proxy oder Clients im LAN auf `0.0.0.0` setzen. Container-Namen (`api`) gelten nur im Compose-Netz. |
| Node-Agent, `.env` → `PORTAL_URL` | Name oder IP des Portals | Der Agent geht **outbound** zum Portal; er braucht keinen offenen Inbound-Port. |
| Node-Agent, `.env` → `ADVERTISE_HOST` | optional, Name des Nodes | Pinnt den Namen, unter dem das Portal ihn anspricht. |
| Node-Agent, `NODE_ID` + `NODE_API_KEY` | optional | Werden durch die Selbst-Registrierung ersetzt. |

## Namensgebung: DNS/mDNS statt IP

Ein Name übersteht einen DHCP-Lease-Wechsel, eine IP nicht. Möglich sind alle
Varianten, solange **das Portal** die Adresse auflösen kann:

- **mDNS** (Linux: `avahi-daemon`, macOS/Windows eingebaut):
  `http://mein-gpu.local:11435` — funktioniert ohne DNS-Server im Wohn-LAN.
- **DNS** in Haushalten mit Router-DNS oder Pi-hole:
  `http://gpu-01.example.net`.
- **Mesh-VPN mit MagicDNS** (Tailscale, Headscale, NetBird, ZeroTier):
  der Name aus dem Overlay — die einfachste Variante, wenn die Hosts in
  verschiedenen Netzen stehen.
- **Feste IP** im DHCP-Server reservieren: funktioniert, ist aber die
  unflexibelste Option (Umzug ins andere Netz = Pool kaputt).

## Selbst-Registrierung des Node-Agents

Der Agent kann sich selbst anmelden und braucht dafür nur zwei Variablen:

```bash
# node-agent/.env
PORTAL_URL=http://portal-host:8765          # Name des Portal-Hosts
PORTAL_USER_KEY=gpu_...                     # API-Key eines Kontos mit Rolle provider/both
ADVERTISE_HOST=mein-gpu.local               # optional; sonst IP-Erkennung
```

Der Agent ruft dann `POST /nodes/register` auf, legt die zurückgegebenen
Zugangsdaten in `NODE_STATE_FILE` (Standard `/data/node-state.json`, Modus 0600)
ab und startet die Heartbeats. Ein Container-Rebuild ist damit unkritisch, solange
das Volume erhalten bleibt.

Ohne `ADVERTISE_HOST` erkennt der Agent seine Adresse selbst:
Outbound-IP über einen UDP-Probe (es fließt kein Paket), sonst der Hostname.
Bei NAT ist die Outbound-IP von außen nicht erreichbar — dann `ADVERTISE_HOST`
auf einen Namen setzen.

## Setup-Check

Zwei Kommandos, beide ohne API-Key und ohne Seiteneffekte:

```bash
# Portal-Seite: erreichbar? Welche Adresse sieht es vom Aufrufer, welche würde es ableiten?
scripts/check_setup.sh http://portal-host:8765

# Node-Seite: erkannter Name/IP, Backend, Portal-Erreichbarkeit
python agent.py --check
```

Der Portal-Endpunkt dahinter ist `GET /net/echo` (offen, ohne Auth). Er nennt
`portal.public_url`, die vom Aufrufer sichtbaren Header und die
`derived_node_url` — also genau die Adresse, die der Pool später anspricht.
Zeigt der Check keine brauchbare Adresse, ist das die Ursache: nicht an den
Heartbeats drehen, sondern `ADVERTISE_HOST` setzen.

## Firewall

- **Portal → Node-Agent**: der Agent muss auf seinem Port (`11435` bzw.
  `AGENT_PORT`) erreichbar sein. Ohne offenen Inbound-Port stattdessen
  `AGENT_TRANSPORT=ws` verwenden: dann baut der Agent die Verbindung auf, und
  nur das Portal muss erreichbar sein.
- **Node-Agent → Portal**: `PORTAL_URL` muss erreichbar sein (Port-Mapping im
  Compose reicht).
- Keine der beiden Seiten gehört ins offene Internet. Ein privates Netz
  (LAN oder Mesh-VPN) genügt.

## Tailscale (optional)

Wer schon ein Tailnet hat, kann die Namen daraus unverändert verwenden — die
Konfiguration ist identisch, es ändert sich nur der Wert:

```bash
PORTAL_URL=http://portal-host:8765     # MagicDNS-Name statt LAN-Name
ADVERTISE_HOST=node-host               # MagicDNS-Name des Nodes
```

Kein CoMesh-Bestandteil setzt Tailscale voraus, und keine Datei im Repo nennt
mehr eine konkrete Tailnet-Adresse. Details zu ACLs und Betrieb eines Tailnets
stehen bewusst nicht mehr in diesem Repo — dafür ist die Tailscale-Doku
zuständig. Wer ein anderes Overlay (Headscale, NetBird, ZeroTier) nutzt: gleiches
Prinzip, nur andere Namen.

## Internet-Exposure via Cloudflare Tunnel (LANA-110)

Wenn das Portal übers Internet erreichbar sein soll (z.B. via Cloudflare Tunnel oder
einen anderen Reverse-Proxy), gilt:

- **Control-Plane** (Portal-UI, Registrierung, Heartbeats, Admin) läuft problemlos
  über HTTP durch den Tunnel — Requests sind kurzlebig.
- **Chat/Inference NICHT über lange HTTP-Requests**: Cloudflare beantwortet HTTP mit
  einer ~100s-Obergrenze (Error 524). Lange LLM-Läufe brechen ab.
- **Lösung: WS-Chat.** Der Endpunkt `/ws/chat` (LANA-110, gehärtet in LANA-112)
  führt Chat-Completions über eine ausdauernde WebSocket-Verbindung aus.
  Framing/Beispiel im Docstring von `ws.py`.

### Cloudflare-Realität bei WebSockets (LANA-112)

„WebSockets laufen uneingeschränkt durch Cloudflare" stimmt **nicht**:

- **Idle-Timeout in beide Richtungen:** Cloudflare trennt eine WS-Verbindung,
  wenn für ~100 s keine Frames fließen — in *beiden* Richtungen. Ein lange
  laufender LLM-Job, der während `route_request` nichts sendet, wird
  abgebrochen. Deshalb sendet der Server während des Routings alle 15 s ein
  App-Level-Frame `{"type": "keepalive"}` (Keepalive-Task in `ws.py`,
  Intervall via `WS_KEEPALIVE_INTERVAL_S` einstellbar). Nachweis:
  `tests/test_ws_chat.py::test_ws_keepalive_frames_close_gap` —
  `max(frame_gap) < 25 s` bei einem 3-s-Upstream-Stub.
- **Edge-Deploys:** Cloudflare Workers/Edge-Runtimes unterstützen keine
  frei dauerhaften Client-Sockets; klassische Tunnel-CSWs-Proxys schon.
  Der Portal-Betrieb läuft bewusst als normaler `cloudflared`-Tunnel, nicht
  als Worker.
- **Netzweite Code-Rollouts (Cloudflare "Technical note"):** Cloudflare kann
  WebSocket-Verbindungen auch ohne Idle-Timeout beenden — z. B. beim Deploy
  neuer Edge-Software im Netz (Close Code 1012 "service restart"). Das ist
  kein Fehlerfall im eigenen Code und lässt sich nicht verhindern. Genau
  deshalb muss der Client (LANA-113 A) `onclose` ohne `onerror` sofort
  behandeln und auf den HTTP-Fallback wechseln, statt das 300-s-Timeout
  auszusitzen.

### Streaming-Entscheid (LANA-112 Fix 2; Phase 3 via LANA-114)

Seit Phase 3 (LANA-114) sind `chunk`-Frames bei `stream=true` **echte
Upstream-Token-Deltas**: der Node-Agent streamt die ND-JSON-Antwort seines
Ollama und schickt sie als `job_result_chunk`-Frames über den
Node-Job-Stream (`ws.py`), das Portal reicht sie unverzüglich als
`chunk` an `/ws/chat` weiter. Damit stimmt auch der TTFT: das erste
`chunk`-Frame kommt mit dem ersten Token, nicht erst mit der fertigen
Antwort.

Verbindlich bleibt in jedem Fall der `final`-Frame: sein `content` ist die
exakte Aggregation aller Deltas. Fallback-Szenarien ohne echtes Streaming
(HTTP-Fallback-Pfad, Agent mit `BACKEND=openai`, ältere Agent-Versionen)
liefern weiterhin das 24-Zeichen-Progress-Chunking der fertigen Antwort —
Clients behandeln `chunk` als Anzeige, `final` als Wahrheit.

Agent-Vertrag (Phase 3):

- Job mit `stream: true` im Payload → Agent streamt Ollama
  `/api/chat` (NDJSON), sendet pro Delta
  `{"type": "job_result_chunk", "job_id": ..., "delta": "..."}` und danach
  das bindende `job_result` mit aggregiertem Content.
- `BACKEND=openai`-Agenten antworten Phase-2-mäßig non-streaming — das
  Portal erkennt das am Fehlen von Deltas und nutzt den Fallback-Chunking.
- Bricht der Stream nach bereits gesendeten Deltas ab, folgt ein
  `job_result` mit `ok: false`; Clients müssen die Partial-Content dann
  verwerfen (final/error ist bindend).

### Key-Transport (LANA-112, Fix 6)

Der API-Key wird standardmäßig über das WS-Subprotocol
`Sec-WebSocket-Protocol: api-key.<raw>` transportiert — der Server akzeptiert
das angebotene Subprotocol explizit zurück (RFC 6455 §4.1, sonst brechen
Browser den Handshake ab). Der Query-Parameter `?api_key=` bleibt als
dokumentierter Fallback (z.B. Clients, die keine Subprotocols setzen können),
landet aber in Cloudflare-HTTP-Request-Logs (CF protokolliert die
Upgrade-Request-URL) und sollte im Internet-Exposure vermieden werden.
Das Frontend nutzt beide Pfade: Subprotocol zuerst, Query nur als Fallback.

### Frontend-Nutzung (LANA-112, Fix 5)

`chat.html` (plain und Alpine) **bevorzugt WS** (`API.chatCompletion` bzw.
`apiChatCompletion`): Key per Subprotocol, `keepalive` wird ignoriert,
`chunk` wird inkrementell gerendert, bei Handshake-Fehler fällt der Client
automatisch auf HTTP (`POST /v1/chat/completions`) zurück — z.B. bei
strikten Corporate-Proxies, die WS nicht durchlassen.
