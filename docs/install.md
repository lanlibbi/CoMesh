# Eine Provider-Node in einem Befehl

Diese Seite beschreibt den Installationsweg für **fremde Rechner**: ein Provider
soll eine Node beisteuern, ohne Python, ohne Docker, ohne das Repo zu klonen und
ohne einen Port in seiner Firewall zu öffnen. Ergebnis ist ein einzelnes Binary,
das als Dienst läuft und sich beim Portal meldet.

| System | Befehl |
|---|---|
| macOS, Linux | `curl -fsSL https://<portal>/downloads/install.sh \| sh` |
| Windows | `powershell -ExecutionPolicy Bypass -Command "irm https://<portal>/downloads/install.ps1 \| iex"` |

`<portal>` ist der Name, unter dem das Portal erreichbar ist (Beispiel:
`comesh.lanlibbilab.me`). Beide Skripte fragen den Account-Schlüssel **verdeckt**
ab, prüfen die Prüfsumme des Binaries und richten den Autostart ein — ohne
Administratorrechte.

Vorher braucht der Provider nur zweierlei:

1. ein **CoMesh-Konto mit der Rolle `provider` oder `both`** (ein `consumer`-Konto
   kann keine Node registrieren), freigegeben von der Administration,
2. ein **lokales Inferenz-Backend**, das läuft — Ollama (`127.0.0.1:11434`) oder
   ein OpenAI-kompatibler Server wie LM Studio (`127.0.0.1:1234`). Der Agent
   leitet Anfragen dorthin weiter; ohne Backend ist die Node online, bekommt aber
   nichts zu tun.

---

## Was der eine Befehl tut

1. **System erkennen** — macOS `arm64`/`x86_64`, Linux `arm64`/`x86_64`,
   Windows `x86_64`. Gibt es für die Kombination kein Binary, bricht das Skript
   ab, statt etwas Falsches zu installieren.
2. **Binary und Prüfsumme laden**, SHA-256 vergleichen. Ohne `.sha256`-Datei
   wird **nicht** installiert.
3. **Binary ablegen** und einmal starten (`--version`). Startet es nicht (falsche
   Architektur), bricht die Installation hier ab — vor dem Dienst.
4. **Account-Schlüssel** abfragen: verdeckte Eingabe, kein Argument in der
   Prozessliste, kein Eintrag in der Shell-History. Alternativ
   `COMESH_USER_KEY` (macOS/Linux) bzw. `$env:COMESH_USER_KEY` (Windows) oder
   `--key-file`. Der Schlüssel wird sofort gegen `/v1/me` geprüft — bei falschem
   Schlüssel oder falscher Portal-Adresse sieht man das hier und nicht erst im
   Dienstprotokoll.
5. **VRAM abfragen**, wenn keine NVIDIA-GPU erkannt wird (siehe unten).
6. **Konfiguration schreiben** und den Selbsttest `comesh-agent --check` mit
   genau dieser Datei laufen lassen.
7. **Dienst einrichten** (launchd / systemd --user / Aufgabenplanung) und starten.
8. **Status zeigen**: läuft der Dienst, antwortet das Portal, erscheint die Node
   in der Geräteliste. Bleibt etwas rot, stehen die letzten Protokollzeilen und
   die drei häufigsten Ursachen darunter.

### Wo was landet

| | macOS / Linux | Windows |
|---|---|---|
| Binary | `~/.local/bin/comesh-agent` | `%LOCALAPPDATA%\CoMesh\comesh-agent.exe` |
| Konfiguration | `~/.config/comesh/agent.env` (Rechte 600) | `%LOCALAPPDATA%\CoMesh\agent.env` (ACL: nur eigenes Konto) |
| Zustand (Node-Id + Node-Key) | `~/.config/comesh/node-state.json` | `%LOCALAPPDATA%\CoMesh\node-state.json` |
| Protokoll | `~/.config/comesh/agent.log` | `%LOCALAPPDATA%\CoMesh\agent.log` |
| Dienst (macOS) | `~/Library/LaunchAgents/de.comesh.agent.plist` | — |
| Dienst (Linux) | `~/.config/systemd/user/comesh-agent.service` | — |
| Dienst (Windows) | — | Aufgabe **CoMesh Agent**, Auslöser „Bei Anmeldung" |

Der Agent liest seine Konfiguration über `COMESH_AGENT_ENV` (setzt der Dienst)
und findet sie sonst selbst unter dem Benutzer-Konfigurationsordner. Ein `.env`
im Arbeitsverzeichnis wird weiterhin gelesen — für Docker und Entwicklung.

**Kein `/data` mehr.** Der frühere Standardpfad `/data/node-state.json` existiert
nur im Container; das Dockerfile setzt ihn dort ausdrücklich. Auf einem normalen
Rechner läuft der Zustand ins Benutzerverzeichnis.

---

## WebSocket ist die Vorgabe — und warum das der Punkt ist

Der Agent baut die Verbindung **ausgehend** zum Portal auf
(`/agent/connect?node_id=…&node_key=…`). Damit gilt:

- **kein offener Port** auf dem Provider-Rechner,
- **keine Firewall-Regel**, keine Portweiterleitung, kein DynDNS,
- **keine vom Portal erreichbare Adresse** — der Provider darf hinter NAT sitzen.

`--transport http` gibt es weiterhin, aber nur als ausdrückliche Wahl: dann muss
das Portal die Node aktiv anrufen können (Port `11435` offen, `ADVERTISE_HOST`
gesetzt). Für fremde Provider ist das die Ausnahme, nicht der Weg.

Die Portal-Adresse dafür ist die **API-Basis**:

| Wo | `PORTAL_URL` |
|---|---|
| öffentlich (hinter nginx/Tunnel) | `https://<portal>/api` — die Vorgabe |
| im eigenen Netz direkt auf der API | `http://<host>:8765` |

Beides funktioniert mit demselben Binary, weil der Agent beim WebSocket ein
abschließendes `/api` abschneidet: die API liegt unter `/api/...`, der
WebSocket unter `/agent/connect` ohne Präfix. Wer das von Hand konfiguriert,
sollte es genauso halten — sonst landet der Handshake auf der HTML-Ersatzseite
und die Node bleibt still offline.

---

## VRAM: die Zeile, die über Aufträge entscheidet

Das Portal weist einer Node nur Aufträge zu, deren Modell in den gemeldeten
Speicher passt. Ohne NVIDIA-Treiber (macOS, Apple Silicon, reine CPU-Nodes) kann
der Agent nichts messen — dann meldet er **1 GB**, und die Node steht online,
bekommt aber nie etwas. Kein Fehler, keine Meldung, nur Stille.

Deshalb fragt der Installer in genau diesem Fall:

```
VRAM, den diese Node anbieten darf (GB) [12]:
```

- **Apple Silicon:** Unified Memory eintragen, aber nicht alles. Bei einem
  16-GB-Mac sind 8–12 realistisch; System, Backend und Modell teilen sich den
  Speicher. Vorgabe im Dialog: 75 % des Gesamtspeichers.
- **Linux/Windows ohne NVIDIA-Treiber:** dasselbe, mit dem Arbeitsspeicher als
  Anhaltspunkt.
- **Mit NVIDIA-GPU:** nichts eintragen. Der Agent misst selbst (`detected`).

Der Wert landet als `NODE_VRAM_GB` in der Konfiguration und ist im Portal als
`vram_source: "override"` sichtbar. Ein Heartbeat zieht ihn nach; die Geräteseite
muss man nicht bearbeiten.

---

## Prüfsumme: ohne sie wird nicht installiert

Neben jedem Binary liegt eine Datei `<binary>.sha256` mit
`<sha256>  <dateiname>`. Der Installer lädt beide, vergleicht und bricht bei
Abweichung ab. Fehlt die `.sha256`-Datei, bricht er ebenfalls ab — mit Absicht:

```sh
EXPECTED=$(cut -d' ' -f1 comesh-agent-linux-x86_64.sha256)
sha256sum comesh-agent-linux-x86_64    # muss denselben Wert zeigen
```

Wer die Dateien selbst hostet (`--base-url https://…`), muss **beide** Dateien
zusammen ausliefern. `build.sh`/`build.ps1` erzeugen sie; sie gehören in dasselbe
Verzeichnis.

**Die Prüfsumme steht seit 04.11.2026 auch in der Download-Adresse.** Cloudflare
liefert Dateien mit der Endung `.exe` aus dem eigenen Edge-Cache und hielt nach
einem Release weiter die alte Datei: gemessen `cf-cache-status: HIT`, `age:
6508`, `cache-control: max-age=14400` (4 h), während die `.sha256` daneben
schon die neue Summe trug — die Installation brach dann an der Prüfsumme ab,
obwohl am Ursprung alles stimmte. Deshalb holt der Installer **zuerst** die
`.sha256` und lädt das Binary unter
`<base>/<binary>?sha=<erste 12 Zeichen der Summe>`. Der Query ändert sich mit
dem Inhalt, eine Cache-Kopie kann also nicht mehr greifen. Wer von Hand lädt,
nimmt denselben Query — oder lädt ohne Query und rechnet die Summe nach; beides
führt zum selben Ergebnis, nur der erste Weg ist schnell.

---

## Warum `curl` und nicht der Browser (macOS)

Ein Binary, das über den Browser heruntergeladen wurde, bekommt von macOS das
Quarantäne-Attribut (`com.apple.quarantine`). Beim Start prüft Gatekeeper dann
die Signatur; das Binary ist **nicht signiert und nicht notarisiert** (es gibt
kein Apple-Entwicklerkonto dafür), also erscheint „cannot be opened because the
developer cannot be verified" — und für einen Provider, der nur einen Befehl
kopieren wollte, ist das das Ende.

`curl` setzt dieses Attribut nicht. Deshalb ist der Einzeiler nicht nur bequemer,
sondern der Grund, warum die Installation ohne Dialog und ohne Klick auf
„Trotzdem öffnen" durchläuft. Wird die Datei doch einmal per Browser geladen:

```bash
xattr -d com.apple.quarantine ~/.local/bin/comesh-agent
```

Dasselbe gilt für `install.sh` selbst — auch das Skript wird über `curl` geholt.

Windows und SmartScreen: eine unsignierte `.exe` kann beim **manuellen** Start
eine Warnung zeigen. Der Installer startet sie aus einer Aufgabe heraus; das
Attribut „aus dem Internet" (`Zone.Identifier`) trägt eine per `Invoke-WebRequest`
geladene Datei nicht in derselben Form wie ein Browser-Download.

---

## Wo die Binaries liegen

Vorgabe ist `<portal>/downloads/` (die Dateien liegen im Deploy-Baum unter
`frontend-alpine/downloads/` und werden vom Frontend-Container ausgeliefert).
Die Binaries selbst sind **nicht versioniert** (`downloads/.gitignore`), die
beiden Installer dagegen schon. Erwartete Namen:

```
comesh-agent-darwin-arm64          comesh-agent-darwin-arm64.sha256
comesh-agent-darwin-x86_64         comesh-agent-darwin-x86_64.sha256
comesh-agent-linux-arm64           comesh-agent-linux-arm64.sha256
comesh-agent-linux-x86_64          comesh-agent-linux-x86_64.sha256
comesh-agent-windows-x86_64.exe    comesh-agent-windows-x86_64.exe.sha256
```

### Was derzeit tatsächlich ausgeliefert wird (Stand 04.11.2026)

| Datei | Zustand |
|---|---|
| `install.sh`, `install.ps1` | **vorhanden** (versioniert) |
| `comesh-agent-linux-x86_64` + `.sha256` | **vorhanden** — 0.6.10, 14.609.000 B, `--version` geprüft (`comesh-agent 0.6.10`), Prüfsumme gegengeprüft |
| `comesh-agent-windows-x86_64.exe` + `.sha256` | **vorhanden** — 0.6.10, 14.058.581 B, `--version` geprüft (`comesh-agent 0.6.10`), Prüfsumme gegengeprüft (gebaut mit `build.ps1` auf Windows Server 2019 / x64, Python 3.12) |
| `comesh-agent-darwin-arm64` + `.sha256` | **vorhanden** — 0.6.10, 14.044.992 B, in GitHub Actions auf `macos-latest` gebaut (04.11.2026), `file` meldet `Mach-O 64-bit arm64`, `--version` geprüft (`comesh-agent 0.6.10`), Prüfsumme gegengeprüft |
| `comesh-agent-darwin-x86_64` | **fehlt** — `macos-latest` ist Apple Silicon; ein Intel-Binary bräuchte einen Lauf auf `macos-13` |
| `comesh-agent-linux-arm64` | **fehlt** — PyInstaller baut nur für die Architektur, auf der es läuft; ein x86_64-Host kann kein ARM-Binary einfrieren |

Die drei Zahlen sind am 04.11.2026 **über HTTPS nachgemessen** (Größe des
Downloads == Größe der Datei im Deploy-Baum, SHA-256 der geladenen Datei ==
`.sha256`-Datei daneben):

| Binary | Bytes | SHA-256 (Stand 04.11.2026) |
|---|---|---|
| `comesh-agent-linux-x86_64` | 14.609.000 | `8879d46c494f16d4a5dccb2e6b547aa393005e82322c5bf76ad786b782e47b1c` |
| `comesh-agent-windows-x86_64.exe` | 14.058.581 | `e601a962e82ea201821bbd31f1d6b43763be30024bc579063b86d63c746f048d` |
| `comesh-agent-darwin-arm64` | 14.044.992 | `3881a74dece11fe11c297f0abaa4e44fea96c573ba5358ff4bfead0303c95eb1` |

Fehlt die Datei zu einer Systemkombination, antwortet `/downloads/` mit **404**
(bewusst kein SPA-Fallback, sonst käme HTML mit 200 zurück) und der Installer
bricht mit `Download fehlgeschlagen: <url>` ab, statt etwas Falsches zu
installieren — für einen **Intel-Mac** und **Linux ARM64** geht der Einzeiler
also noch nicht.

**Für Macs mit Apple Silicon ist der Einzeiler der Weg.** Das Binary entsteht in
`.github/workflows/build-node-agent.yml`: Der Workflow läuft auf `macos-latest`,
misst die Architektur mit `uname -m` (nicht angenommen — der Dateiname wird
daraus gebildet), prüft `comesh-agent --version` gegen die `VERSION`-Datei und
lädt Binary plus `.sha256` als Artefakt hoch. Er committet nichts: das Artefakt
wird heruntergeladen und nach `frontend-alpine/downloads/` gelegt (siehe
`frontend-alpine/downloads/README.md`). Wer keinen Mac zur Hand hat, braucht
also keinen mehr.

Wer lieber lokal baut (Intel-Mac, Linux ARM, oder um die CI zu umgehen):

```bash
cd node-agent && ./build.sh          # macOS/Linux -> dist/
cd node-agent && .\build.ps1         # Windows     -> dist\
```

Anderer Ort, gleiche Dateien:

```bash
curl -fsSL https://example.net/comesh/install.sh | sh -s -- --base-url https://example.net/comesh
```

---

## Die Node taucht im Portal nicht auf

Der Installer zeigt am Ende drei Zeilen — Dienst, Portal, Node. Welche zuerst
nachzusehen ist, hängt davon ab, welche nicht stimmt:

| Beobachtung | Ursache | Abhilfe |
|---|---|---|
| Dienst „läuft NICHT" | Binary startet nicht oder wurde beendet | `~/.config/comesh/agent.log` bzw. `%LOCALAPPDATA%\CoMesh\agent.log` lesen; Linux: `systemctl --user status comesh-agent` |
| Portal `HTTP 000` | Name/Port nicht erreichbar | `curl -sS https://<portal>/api/health` von Hand; Firmware-Firewall, Proxy, falscher Name |
| Portal `HTTP 200`, Node fehlt | Registrierung abgelehnt | Protokoll: `Self-registration failed (403)` → Rolle `consumer` oder Konto nicht freigegeben |
| Node fehlt, Protokoll sagt `WS disconnected: 403` | WebSocket am Proxy abgewiesen | nginx braucht `location = /agent/connect` mit Upgrade-Kopfzeilen (siehe `frontend-alpine/nginx.conf`) |
| Node „online", aber nie Aufträge | VRAM zu klein gemeldet | `NODE_VRAM_GB` setzen; im Portal steht dann `vram_source: override` statt `assumed` |
| Node online, Aufträge scheitern mit 502 | Backend läuft nicht | `curl -s http://127.0.0.1:11434/api/tags` bzw. `…:1234/v1/models` |
| Logins/Registrierung scheitern | Schlüssel ist eine Sitzungsmarke (`sess_…`) | im Profil einen echten Schlüssel ausstellen (`gpu_…`, einmal sichtbar) |

Nützliche Befehle:

```bash
# macOS
launchctl print gui/$(id -u)/de.comesh.agent | head -20
tail -f ~/.config/comesh/agent.log

# Linux
systemctl --user status comesh-agent
journalctl --user -u comesh-agent -n 50 --no-pager
tail -f ~/.config/comesh/agent.log

# Windows (PowerShell)
schtasks /Query /TN "CoMesh Agent" /V /FO LIST
Get-Content "$env:LOCALAPPDATA\CoMesh\agent.log" -Tail 30 -Wait
```

Im Protokoll ist `WS welcome received` das entscheidende Lebenszeichen: das
Portal hat die Node authentifiziert und die Verbindung angenommen. `Self-registered
as node_id=…` davor heißt, die Registrierung hat geklappt.

---

## Neu installieren, aktualisieren, entfernen

Beide Skripte sind **idempotent**: ein zweiter Lauf ersetzt Binary und
Konfiguration, lädt den Dienst neu und legt keine zweite Node an. Der vorhandene
Account-Schlüssel wird beibehalten, wenn kein neuer angegeben wird.

```bash
# Aktualisieren (neue Version, gleiche Konfiguration)
curl -fsSL https://<portal>/downloads/install.sh | sh

# Anderen Schlüssel einspielen
COMESH_USER_KEY=gpu_… curl -fsSL https://<portal>/downloads/install.sh | sh
```

```powershell
.\install.ps1 -Uninstall     # Windows: Aufgabe und Dateien entfernen
```

```bash
curl -fsSL https://<portal>/downloads/install.sh | sh -s -- --uninstall
```

- `--name` gilt bei der **ersten** Registrierung; danach ist der Name eine
  Eigenschaft der Node im Portal und wird dort geändert (die Konfigurationsdatei
  umbenennen hilft nicht, weil die Zugangsdaten schon in `node-state.json`
  stehen).

`--uninstall` entfernt Dienst, Binary, Konfiguration, Protokoll und
Zustandsdatei. **Die Node bleibt im Portal in der Geräteliste stehen** — dort
löschen, sonst sieht sie für die Administration wie eine ausgefallene Node aus.
Die Deinstallation braucht keine Adminrechte.

Nach einer Neuinstallation ohne Zustandsdatei registriert sich der Agent als
**neue** Node; die alte Leiche gehört gelöscht.

---

## Selbst prüfen, ohne das Portal anzufassen

Für Tests gibt es ein Testportal, das die Wege des echten nachbildet (API unter
`/api`, WebSocket unter `/agent/connect`):

```bash
cd node-agent
. .venv-build/bin/activate            # aus build.sh; oder eigenes venv
pip install fastapi uvicorn
MOCK_DOWNLOADS=$PWD/dist python -m uvicorn test.mock_portal:app --port 8799 &

COMESH_BASE_URL=http://127.0.0.1:8799/downloads \
COMESH_PORTAL_URL=http://127.0.0.1:8799/api \
COMESH_USER_KEY=gpu_test_wegwerf \
COMESH_VRAM_GB=8 \
sh install.sh
```

Danach zeigt `/api/__state` (Testportal), welche Nodes, Heartbeats und
WS-Sitzungen angekommen sind — und der Agent lässt sich mit `--uninstall`
wieder entfernen.

---

## Stand und Grenzen

- **Linux ist gemessen** (arm64, Python 3.13, PyInstaller 6.22): Binary gebaut
  (15 MB, Version aus `VERSION`), über `curl … | sh` installiert, Rechte 600 auf
  `agent.env`, systemd-`--user`-Dienst `enabled` + `active`, WebSocket-Handshake
  (`WS welcome received`), Selbstregistrierung und Heartbeat im Portal sichtbar.
- **Dauerbetrieb**: 100 s nach der Installation weiter Heartbeats (7 → 10) und
  Pings (9 → 16), `NRestarts=0` — die Node fällt nicht nach 90 s aus dem Routing.
- **Auch `--transport http` ist gemessen**: in diesem Betrieb startet der
  eingefrorene uvicorn-Server, `/health` und `/` antworten (das prüft die
  Hidden Imports in `comesh-agent.spec`).
- **Fehlerwege gemessen**: fehlende `.sha256` → Abbruch ohne Installation,
  falsche Prüfsumme → Abbruch mit beiden Werten, unerreichbares Portal →
  Statuszeilen, Protokollauszug und Exitcode 1.
- **Idempotenz und Rückweg gemessen**: zweiter Lauf ersetzt statt zu duplizieren
  (keine zweite Node), `--uninstall` hinterlässt weder Dienst noch Dateien.
- **Das macOS-Binary ist in CI gebaut und geprüft, aber nicht auf einem Mac
  gestartet.** GitHub Actions, `macos-latest` (arm64, Darwin 25.6, Python 3.12.10,
  PyInstaller 6.22.3, ohne Codesignatur): Bau in 32 s, `comesh-agent --version`
  meldet `comesh-agent 0.6.10`, `file` sagt `Mach-O 64-bit executable arm64`,
  Größe 14.044.992 B, SHA-256
  `3881a74dece11fe11c297f0abaa4e44fea96c573ba5358ff4bfead0303c95eb1`. Das
  Artefakt ist über HTTPS geladen und die Prüfsumme gegen die ausgelieferte
  `.sha256` gerechnet. **Nicht** ausgeführt: der Start des Binaries auf echter
  Apple-Hardware, `launchctl`, der Gatekeeper-Weg und der Quarantäne-Hinweis.
- **macOS und Windows sind vorbereitet, aber nicht auf echter Hardware
  ausgeführt**: `install.ps1`/`build.ps1` sind über den PowerShell-AST und
  PSScriptAnalyzer geprüft (0 Befunde außer Stilhinweisen), `install.sh` über
  `sh -n` und shellcheck; das erzeugte launchd-Plist ist als XML validiert
  (auch mit `&` im Pfad). **Nicht** ausgeführt: `launchctl`,
  `schtasks`, `icacls` — und damit die Dienstwege selbst, die
  Gatekeeper-/SmartScreen-Frage und der Windows-Neustart nach einem Update.
  Wer dort installiert, sollte mit `bash -x` bzw. `Set-PSDebug -Trace 1`
  arbeiten und den Bericht hier ergänzen.
- **Die Binaries sind unsigniert** (weder Apple-Notarisierung noch
  Windows-Codesignatur). Das ist der Grund für die `curl`-Installation; für eine
  breite Verteilung wäre eine Signatur der nächste Schritt.
- **Modelle melden Nodes nicht.** Was eine Node anbieten darf, steht in
  `gpu_nodes.allowed_models` und wird im Portal gepflegt. Ein Modell, das nur
  lokal auf der Node liegt, macht sie nicht sichtbar.

## Woher die Skripte die Adresse kennen

`install.sh` und `install.ps1` werden vom Portal **mit der Adresse dieser Instanz** ausgeliefert
(nginx ersetzt beim Ausliefern einen Platzhalter). Wer die Installationszeile aus dem Guide dieser
Instanz kopiert, holt Agent, Prüfsumme und API-Adresse also immer von hier — nicht vom
Referenzserver. Abweichende Ziele lassen sich weiterhin setzen: `COMESH_ORIGIN` (Umgebung),
`--base-url` und `--portal-url` (Argumente). Wird ein Skript am Portal vorbei geholt, bricht es mit
einer Erklärung ab, statt still auf eine fremde Adresse zu zeigen.
