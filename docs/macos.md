# CoMesh auf macOS (Apple Silicon)

**Schnellweg:** `curl -fsSL https://<portal>/downloads/install.sh | sh` — Binary,
Prüfsumme, launchd-Dienst und VRAM-Abfrage in einem Schritt, ohne Python und ohne
offenen Port ([install.md](install.md)). Der Rest dieser Seite erklärt, was dabei
passiert und wie man es von Hand macht.

Ein Mac als Provider-Node ist möglich, hat aber **eine** Falle, die still bleibt:
Ohne NVIDIA-Treiber gibt es kein NVML, also meldet der Agent `unknown` und
`0 GB` — und das Portal macht daraus 1 GB. Der Router prüft vor jedem Auftrag,
ob der freie VRAM für das Modell reicht (`pool.find_best_node`), und schickt der
Node deshalb **nie** etwas. Die Node steht auf „online", der Betreiber sieht
keinen Fehler und keinen Auftrag.

Die Lösung ist eine Zeile in der `.env`:

```bash
# Unified Memory, den dieser Mac dem Pool anbieten darf (GB).
# Bei einem 16-GB-Mac mini/MacBook sind 8–12 realistisch, nicht 16:
# das System und das Backend brauchen selbst Speicher.
NODE_VRAM_GB=12
```

**Ohne `NODE_VRAM_GB` bekommt ein Mac keine Aufträge.** Der Agent warnt beim
Start (`No GPU detected via NVML and NODE_VRAM_GB is unset`), und die
Portal-Liste zeigt an der Node „VRAM angenommen — keine GPU erkannt" (Feld
`vram_source: "assumed"`). Mit gesetztem Wert steht dort „aus NODE_VRAM_GB",
und der Wert wird beim nächsten Heartbeat auch im Portal nachgezogen.

---

## Weg 0 — ein Befehl (empfohlen für Provider)

Der Agent liegt als fertiges Binary vor; kein Python, kein Repo, kein Docker:

```bash
curl -fsSL https://<portal>/downloads/install.sh | sh
```

Das Skript fragt den Account-Schlüssel verdeckt ab, **fragt nach `NODE_VRAM_GB`**
(ohne NVIDIA-GPU ist das Pflicht — genau dieser Mac-Fall, Vorgabe: 75 % des
Speichers), prüft die Prüfsumme und legt einen launchd-Dienst in
`~/Library/LaunchAgents/de.comesh.agent.plist` an, ohne `sudo`.
Transport ist WebSocket: der Mac wählt sich ausgehend ein, es muss **kein Port**
offen sein. Einzelheiten: [install.md](install.md).

Vorher nur Ollama starten und ein Modell ziehen:

```bash
brew install ollama
brew services start ollama            # oder: ollama serve
ollama pull llama3.1:8b               # ein Modell, das in den Speicher passt
```

---

## Weg A — nativ aus dem Quellbaum (Entwicklung)

Ollama nutzt auf Apple Silicon Metal und damit die GPU; das ist der einfachste
Weg und braucht kein Docker.

```bash
# 1. Ollama
brew install ollama
brew services start ollama            # oder: ollama serve
ollama pull llama3.1:8b               # ein Modell, das in den Speicher passt

# 2. Agent
cd ~/CoMesh/node-agent                # agent.py + netinfo.py aus dem Repo
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

# 3. Konfiguration
cat > .env <<'EOF'
PORTAL_URL=http://<portal-host>:8765
# Selbst-Registrierung: API-Key eines Kontos mit Rolle provider oder both
PORTAL_USER_KEY=gpu_xxxxxxxx
# Name, unter dem das Portal diesen Mac erreicht (mDNS: <name>.local)
ADVERTISE_HOST=mein-mac.local
AGENT_PORT=11435
OLLAMA_URL=http://127.0.0.1:11434
BACKEND=ollama
# Der Punkt, an dem es sonst still scheitert:
NODE_VRAM_GB=12
# Zustandsdatei: /data gibt es auf dem Mac nicht
NODE_STATE_FILE=~/.comesh/node-state.json
NODE_SHARED_SECRET=<derselbe Wert wie im Portal>
EOF

# 4. Selbsttest (startet nichts)
python agent.py --check

# 5. Start
python agent.py
```

Das Backend bleibt lokal: nach außen muss nur `11435` erreichbar sein, und auch
das nur aus dem Netz, in dem das Portal steht (LAN/Tailnet). Der Agent selbst
prüft bei jeder Anfrage den Kopf `X-Node-Secret`; ohne den richtigen Wert
antwortet er `401`.

## Weg B — Docker auf dem Mac

Geht, ist aber langsamer als nativ: Docker Desktop auf macOS reicht Metal nicht
an Container durch, das Backend rechnet dann auf der CPU. Wenn es trotzdem ein
Container sein soll:

```yaml
services:
  node-agent:
    build: ./node-agent
    environment:
      - PORTAL_URL=http://<portal-host>:8765
      - PORTAL_USER_KEY=gpu_xxxxxxxx
      - ADVERTISE_HOST=mein-mac.local
      - OLLAMA_URL=http://host.docker.internal:11434
      - NODE_VRAM_GB=12
      - NODE_SHARED_SECRET=${NODE_SHARED_SECRET}
    ports:
      - "11435:11435"
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

## Backends auf macOS

| Backend | `BACKEND` | `INFERENCE_URL` | Anmerkung |
|---|---|---|---|
| Ollama | `ollama` | `http://127.0.0.1:11434` | Metal, Streaming ja — der übliche Weg |
| LM Studio | `openai` | `http://127.0.0.1:1234` | Metal, Streaming ja (ab 0.5.0) |
| llama.cpp-Server | `openai` | `http://127.0.0.1:8080` | `-ngl` hochsetzen, sonst CPU |

## Was der Mac nicht kann

- **Kein NVML.** `nvidia-smi` gibt es nicht; GPU-Name und Speicher kommen nicht
  aus dem Agenten. Deshalb ist `NODE_VRAM_GB` Pflicht.
- **Kein VRAM im NVIDIA-Sinn.** Unified Memory wird von System, Backend und
  Modell geteilt. Wer 16 GB einträgt, verspricht mehr, als das Modell zusammen
  mit macOS tatsächlich belegen kann; das Backend bricht dann bei großen
  Modellen ab (oder lagert aus und wird sehr langsam). Lieber konservativ.
- **`VRAM_GB` ist nicht dasselbe.** `gpu_summary()` liest als Rückfall
  `VRAM_GB`/`GPU_TYPE`; für die Anzeige im Portal ist `NODE_VRAM_GB`
  maßgeblich, weil nur dieser Wert das Routing-Gate öffnet.

## Prüfen, dass es angekommen ist

```bash
# Am Mac: Agent meldet sich
curl -s http://127.0.0.1:11435/health -H "X-Node-Secret: <wert>"

# Im Portal: steht der Wert und die Herkunft?
#   GET /api/admin/nodes  -> vram_gb, vram_source ("override")
```

Steht in der Adminliste weiter „VRAM angenommen", kam der Heartbeat nicht an
(Portal-URL, Firewall, Key) — nicht der VRAM-Wert ist dann das Problem.
