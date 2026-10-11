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
| Portal, `docker-compose.yml` | nur Port-Mappings (`8765:8000`, `8767:80`) | Keine festen externen Adressen. Container-Namen (`api`) gelten nur im Compose-Netz. |
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
