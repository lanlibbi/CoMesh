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
funktioniert und bei fehlender NVML sauber auf Stub-Werte zurückfällt. **Was fehlt, ist der
Installationsweg** — `node-agent/setup.py` ist ein Assistent, der am Ende eine
`docker-compose.yml` erzeugt.

Zwei Stolpersteine im Code, die Windows betreffen:

1. **`NODE_STATE_FILE`** steht standardmäßig auf `/data/node-state.json` — ein Linux-Pfad.
   Unter Windows überschreiben, z. B. `%LOCALAPPDATA%\CoMesh\node-state.json`.
2. **`host.docker.internal`** in den Vorgaben des Assistenten gilt **nur für Docker**. Läuft
   der Agent nativ neben dem Backend, gehört `127.0.0.1` in die `.env`.

`os.chmod(tmp, 0o600)` im Agenten ist unter Windows wirkungslos, schlägt aber nicht fehl —
die Datei ist dann eben nicht auf den Besitzer beschränkt. Bewusst so gelassen, kein Fehler.

---

## Weg A — `comesh-agent.exe` (geplant, noch nicht gebaut)

Der Agent lässt sich mit PyInstaller einfrieren. Dann braucht der Rechner **kein Python**:

```
%LOCALAPPDATA%\CoMesh\
├─ comesh-agent.exe        ~20–30 MB, keine Python-Installation nötig
├─ agent.env               Konfiguration (siehe unten)
└─ node-state.json         selbst erzeugt (NODE_ID / NODE_API_KEY)
```

Start per Doppelklick oder als Aufgabe in der Aufgabenplanung. Der Agent ist ein
FastAPI-Dienst; PyInstaller braucht für uvicorn ein paar Hidden-Imports, das ist einmalig
im Build-Skript erledigt.

**Status:** vorgeschlagen, nicht umgesetzt. Wer es vorher braucht, nimmt Weg B.

---

## Weg B — Python nativ (heute der einzige Weg)

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
| GPU wird nicht erkannt | `nvidia-smi` in derselben Konsole prüfen. Der Agent fällt sonst auf Stub-Werte zurück und meldet keine GPU. |

Nach dem Start: `curl http://127.0.0.1:11435/health` liefert `{"status":"ok","agent":"running",
"ollama":"ok","gpu":"RTX …"}` (der Schlüssel `ollama` steht auch bei `BACKEND=openai` für
„Backend erreichbar").
