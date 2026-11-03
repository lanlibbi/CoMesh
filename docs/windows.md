# CoMesh unter Windows

**Kurzfassung**

| Rolle | Was braucht Windows? |
|---|---|
| **Nutzer** (Anfragen stellen) | **nichts.** Browser auf `http://<portal>:8767`, oder einen beliebigen OpenAI-kompatiblen Client auf `http://<portal>:8765/v1` mit einem API-Schlüssel. Das Portal ist der einzige Berührungspunkt. |
| **Provider** (GPU beisteuern) | ein lokales Inferenz-Backend **und** den Node-Agenten davor. Eines von beiden allein reicht nicht. |
| **Portal** (Betreiber) | Docker Desktop mit WSL2, oder Python nativ. Bleibt üblicherweise auf dem Linux-Host. |

Warum der Agent auch als Provider nötig ist: das Portal adressiert einen Node über
`node_url` — und das zeigt **immer auf den Agenten** (Standardport `11435`), nie direkt auf
Ollama oder LM Studio. Der Agent macht Health-Checks, meldet Modelle und GPUs, nimmt die
Anfragen an und leitet sie an das lokale Backend weiter.

---

## Stand der Dinge (gemessen am 18.10.2026)

Auf einem frischen Windows-Rechner ist typischerweise **nichts** vom benötigten Stack da.
Gemessen auf einem Gaming-PC (RTX 3080 Ti, 12 GB, Treiber 616.56):

| | |
|---|---|
| GPU sichtbar (`nvidia-smi`) | ✓ |
| `python` / `py` | ✗ (nur der Microsoft-Store-Platzhalter) |
| Docker | ✗ |
| WSL2 | ✗ („nicht installiert") |
| `winget` | ✓ |

Der Code selbst ist portabel — `netinfo.py` ermittelt die Adresse über reine Sockets (kein
`ip addr`, kein `ifconfig`), der Agent enthält keine POSIX-Aufrufe (`fork`, `fcntl`,
`/proc`, `signal.SIGTERM`), und die GPU-Erkennung läuft über `pynvml`, das unter Windows
funktioniert und bei fehlender NVML sauber auf Stub-Werte zurückfällt. Der Installationsweg steht seit
`install.ps1` bereit: ein Befehl in einer normalen PowerShell, ohne Python und ohne
Administratorrechte (Weg A). `node-agent/setup.py` bleibt der Assistent für den
Container-Betrieb.

Zwei Stolpersteine im Code, die Windows betreffen:

1. **`NODE_STATE_FILE`** hatte als Vorgabe den Linux-Pfad `/data/node-state.json`. Seit dem
   Einzelbinary liegt der Standard im Benutzerverzeichnis
   (`%LOCALAPPDATA%\CoMesh\node-state.json`); der Container setzt den Pfad ausdrücklich
   in seinem Dockerfile. Wer von Hand konfiguriert, kann ihn weiterhin überschreiben.
2. **`host.docker.internal`** in den Vorgaben des Assistenten gilt **nur für Docker**. Läuft
   der Agent nativ neben dem Backend, gehört `127.0.0.1` in die `.env`.

`os.chmod(tmp, 0o600)` im Agenten ist unter Windows wirkungslos, schlägt aber nicht fehl —
die Datei ist dann eben nicht auf den Besitzer beschränkt. Bewusst so gelassen, kein Fehler.

---

## Weg A — ein Befehl (`comesh-agent.exe`)

Der Agent liegt als fertiges Einzelbinary vor; der Rechner braucht **kein Python**,
kein Docker, kein Repo und **keinen offenen Port**:

```powershell
irm https://<portal>/downloads/install.ps1 | iex
```

Das Skript erkennt die Architektur (nur `x86_64` wird ausgeliefert), lädt
`comesh-agent-windows-x86_64.exe` samt `.sha256`, prüft die Summe und bricht ohne
Prüfsumme ab. Danach fragt es den Account-Schlüssel verdeckt (`Read-Host
-AsSecureString` — nicht in der History, nicht in der Prozessliste) und, wenn keine
NVIDIA-GPU erkannt wird, den VRAM.

```
%LOCALAPPDATA%\CoMesh\
├─ comesh-agent.exe        ~15 MB, keine Python-Installation nötig
├─ agent.env               Konfiguration (Rechte: nur das eigene Konto)
├─ node-state.json         selbst erzeugt (NODE_ID / NODE_API_KEY)
└─ agent.log               Protokoll (rotiert)
```

Autostart über die **Aufgabenplanung** — Aufgabe „CoMesh Agent", Auslöser „Bei
Anmeldung", eingerichtet mit `schtasks /Create /SC ONLOGON`. Das geht **ohne
Administratorrechte**; ein Dienst (`/SC ONSTART`, `SYSTEM`) bräuchte sie und ist für
einen Agenten, der im Benutzerkonto läuft, auch nicht nötig.

```powershell
schtasks /Query /TN "CoMesh Agent" /V /FO LIST
Get-Content "$env:LOCALAPPDATA\CoMesh\agent.log" -Tail 30 -Wait
```

Deinstallieren: `irm https://<portal>/downloads/install.ps1 | iex` mit
`$env:COMESH_UNINSTALL = "1"` (oder `\install.ps1 -Uninstall`). Einzelheiten:
[install.md](install.md).

Parameter für Automatisierung (`$env:…`, weil `iex` keine Argumente durchreicht):

| Variable | Bedeutung |
|---|---|
| `COMESH_USER_KEY` | Account-Schlüssel (sonst verdeckte Abfrage) |
| `COMESH_VRAM_GB` | VRAM übersteuern |
| `COMESH_BASE_URL` | anderer Ort für die Binaries |
| `COMESH_PORTAL_URL` | API-Basis, Vorgabe `https://<portal>/api` |
| `COMESH_AGENT_NAME` | Anzeigename der Node |

Der Agent ist ein FastAPI-Dienst; die Hidden-Imports für uvicorn stecken in
`comesh-agent.spec`, gebaut wird mit `build.ps1`.

---

## Weg B — Python nativ (ohne Binary)

```powershell
# 1. Python installieren (ohne Store-Platzhalter, mit PATH)
winget install --id Python.Python.3.12 -e

# 2. Arbeitsverzeichnis und venv
mkdir "$env:LOCALAPPDATA\CoMesh"; cd "$env:LOCALAPPDATA\CoMesh"
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install fastapi==0.115.0 "uvicorn[standard]==0.30.6" httpx==0.27.2 psutil==5.9.8 websockets==13.1 pynvml==11.5.0

# 3. Agentencode holen (aus dem Repo)
#    agent.py und netinfo.py in dieses Verzeichnis kopieren
#    oder: git clone https://github.com/lanlibbi/CoMesh und nach node-agent/ wechseln

# 4. Konfiguration
notepad agent.env       # Inhalt siehe unten

# 5. Selbsttest — startet nichts, prüft nur
python agent.py --check
```

`agent.env` für einen Windows-Provider mit **LM Studio**:

```ini
# Portal, wie es vom Windows-Rechner aus erreichbar ist (Name überlebt DHCP-Wechsel)
PORTAL_URL=http://ai-lanlibbi:8765

# Selbst-Registrierung: API-Key eines Kontos mit Rolle provider oder both
REGISTER_API_KEY=<key-eines-provider-kontos>

# Adresse, unter der das Portal DIESEN Rechner erreicht.
# Leer = automatische Erkennung der Outbound-Adresse.
ADVERTISE_HOST=

# Backend: LM Studio spricht OpenAI-kompatibel
BACKEND=openai
INFERENCE_URL=http://127.0.0.1:1234

# Windows braucht einen eigenen Pfad für den Zustand
NODE_STATE_FILE=C:\Users\<du>\AppData\Local\CoMesh\node-state.json
```

Mit **Ollama** statt LM Studio: `BACKEND=ollama` und `INFERENCE_URL=http://127.0.0.1:11434`.

Der Agent liest seine Konfiguration aus der `.env` im **aktuellen Arbeitsverzeichnis** —
also im CoMesh-Ordner starten, nicht aus `C:\Windows\System32`.

### VRAM: was der Agent meldet, und was daraus wird

Der Agent liest den Speicher über NVML (die `nvidia-smi`-Bibliothek). Klappt das nicht,
meldet er `unknown` / `0 GB`, das Portal macht daraus **1 GB** — und der Router weist
danach jeden Auftrag ab, weil das VRAM-Gate nicht durchgeht. Die Node ist dann online
und bekommt trotzdem nichts; es gibt keine Fehlermeldung, nur Stille.

Dagegen hilft ein ausdrücklicher Wert:

```bash
NODE_VRAM_GB=10        # was diese Maschine dem Pool anbieten soll (GB)
```

`NODE_VRAM_GB` gewinnt immer gegen die Messung und wird beim nächsten Heartbeat auch
im Portal nachgezogen — auch nachträglich, ein Bearbeiten der Geräteseite ist nicht
nötig. Die Herkunft steht als `vram_source` an der Node:

| `vram_source` | Bedeutung |
|---|---|
| `detected` | über NVML gelesen |
| `override` | `NODE_VRAM_GB` gesetzt — dieser Wert gilt |
| `assumed` | nichts erkannt, nichts gesetzt: 1 GB. **Die Node bekommt keine Aufträge.** In der Adminliste steht „VRAM angenommen — keine GPU erkannt“. |

Auf einer Maschine ohne NVIDIA-Treiber (macOS/Apple Silicon, reine CPU-Nodes) ist
`NODE_VRAM_GB` deshalb Pflicht — siehe [macos.md](macos.md).

---

## Weg C — Docker Desktop

Möglich, aber unverhältnismäßig: WSL2 plus Docker Desktop sind 2–3 GB, und GPU-Passthrough
im Container braucht zusätzlich das NVIDIA Container Toolkit. Wenn der Agent im Container
läuft, ist `host.docker.internal` für das Backend richtig — das ist genau der Fall, für den
die Vorgaben im Assistenten gemacht sind.

---

## Backends im Vergleich

| Backend | `BACKEND` | `INFERENCE_URL` | Modelle | Streaming |
|---|---|---|---|---|
| Ollama | `ollama` | `http://127.0.0.1:11434` | `/api/tags` | **ja** |
| LM Studio | `openai` | `http://127.0.0.1:1234` | `/v1/models` | **ja** (ab 0.5.0) |
| LiteLLM-Proxy | `openai` | `http://127.0.0.1:4000` | `/v1/models` | ja (ab 0.5.0) |
| vLLM, llama.cpp u. a. | `openai` | `http://127.0.0.1:8000` | `/v1/models` | ja (ab 0.5.0) |

Mit `BACKEND=openai` schickt der Agent den OpenAI-Body unverändert an
`/v1/chat/completions` und reicht die SSE-Zeilen des Backends durch; mit `BACKEND=ollama`
übersetzt er auf Ollamas `/api/chat` und baut daraus OpenAI-Rahmen. Beide Wege streamen seit
0.5.0 — `stream: true` vom Client genügt.

In LM Studio muss der Server eingeschaltet sein („Start Server", Port 1234). Die Option
„Serve on Local Network" braucht es **nicht**: der Agent läuft auf demselben Rechner und
greift über `127.0.0.1` zu.

---

## Netz und Firewall

Das Portal ruft **nur den Agenten** an. Also muss genau ein Port erreichbar sein:

```powershell
# Agent-Port für das lokale Netz öffnen (Tailnet/LAN je nach Umgebung)
New-NetFirewallRule -DisplayName "CoMesh Agent" -Direction Inbound -Protocol TCP `
  -LocalPort 11435 -Action Allow -Profile Private
```

LM Studio (1234) und Ollama (11434) bleiben lokal — kein Port nach außen, keine
Notwendigkeit, sie ins Netz zu stellen.

Damit das Portal den Rechner findet, muss `ADVERTISE_HOST` stimmen oder die automatische
Erkennung passen: das Portal leitet die Adresse aus der Quell-IP des Heartbeats ab, wenn
`node_url` leer ist. Sitzt der Rechner hinter NAT oder in einem anderen Subnetz, ist eine
feste Angabe besser (Name im Tailnet, LAN-IP, mDNS-Name).

---

## Autostart über die Aufgabenplanung

```powershell
$exe = "$env:LOCALAPPDATA\CoMesh\.venv\Scripts\python.exe"
$arg = "`"$env:LOCALAPPDATA\CoMesh\agent.py`""
schtasks /Create /TN "CoMesh Agent" /SC ONSTART /RU "$env:USERNAME" /RL HIGHEST ^
  /TR "`"$cmd /c cd /d $env:LOCALAPPDATA\CoMesh && $exe $arg`""
```

Für die geplante `.exe` entfällt der Python-Pfad; dann steht dort direkt
`comesh-agent.exe`. In beiden Fällen: „Aufgabe ausführen, wenn Benutzer angemeldet ist" ist
bequemer als „bei Systemstart", weil die GPU-Treiberkontexte dann bereits stehen.

---

## Windows-Troubleshooting

| Symptom | Ursache und Lösung |
|---|---|
| `python` startet den Microsoft Store | Der Store-Platzhalter liegt im PATH. Python per `winget` installieren und ein **neues** Terminal öffnen; `where python` muss auf `...\Python312\python.exe` zeigen. |
| `[Errno 2] No such file or directory: '/data/node-state.json'` | `NODE_STATE_FILE` nicht gesetzt — Windows-Pfad in die `.env`. |
| `--check` meldet Backend nicht erreichbar | LM Studio/Server läuft nicht, oder `INFERENCE_URL` zeigt auf `host.docker.internal` statt `127.0.0.1`. |
| Agent läuft, Portal sieht ihn nicht | Firewall (Port 11435), falsche `ADVERTISE_HOST`, oder der Key hat nicht die Rolle `provider`/`both`. |
| Antworten kommen ohne Streaming | Seit 0.5.0 nicht mehr nötig: beide Backends streamen. Kommt trotzdem alles auf einmal, fordert der Client kein `stream: true` an oder ein Proxy puffert — `X-Accel-Buffering: no` prüfen. |
| GPU wird nicht erkannt | `nvidia-smi` in derselben Konsole prüfen. Der Agent fällt sonst auf Stub-Werte zurück und meldet 1 GB — dann mit `NODE_VRAM_GB` den Speicher ausdrücklich setzen, sonst bekommt die Node keine Aufträge (siehe „VRAM“). |

Nach dem Start: `curl -H "X-Node-Secret: <wert>" http://127.0.0.1:11435/health` liefert
`{"ok":true,"backend":"ollama",…,"node_id":"1","gpu":{…}}` (`backend`/`ollama_reachable`
stehen auch bei `BACKEND=openai` für „Backend erreichbar“). **Ohne** den Kopf antwortet
der Agent nur mit `{"ok":true}` — Details gibt es seit dem Sicherheitsfix vom 03.11.2026
nur noch mit dem gemeinsamen Geheimnis `NODE_SHARED_SECRET`.
