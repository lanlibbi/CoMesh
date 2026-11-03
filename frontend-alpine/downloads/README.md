# Auslieferung der Node-Agent-Binaries

Dieser Ordner wird vom Frontend-Container mit ausgeliefert
(`COPY downloads/ /usr/share/nginx/html/downloads/`), damit ein Provider nur
**einen** Namen braucht:

```bash
curl -fsSL https://<portal>/downloads/install.sh | sh
irm https://<portal>/downloads/install.ps1 | iex
```

Der Installer lädt von hier:

| Datei | Ziel |
|---|---|
| `install.sh` | macOS/Linux-Installer (aus `node-agent/install.sh`) |
| `install.ps1` | Windows-Installer (aus `node-agent/install.ps1`) |
| `comesh-agent-darwin-arm64` + `.sha256` | Apple Silicon |
| `comesh-agent-darwin-x86_64` + `.sha256` | Intel-Mac |
| `comesh-agent-linux-arm64` + `.sha256` | Linux ARM64 |
| `comesh-agent-linux-x86_64` + `.sha256` | Linux x86_64 |
| `comesh-agent-windows-x86_64.exe` + `.sha256` | Windows x64 |

**Die Binaries liegen nicht im Repo** (15–25 MB je Datei, und sie gehören zu
einem Release, nicht zu einem Quellstand). Erzeugt werden sie mit
`node-agent/build.sh` bzw. `node-agent/build.ps1`; die Dateien werden hier
abgelegt und **immer zusammen mit ihrer `.sha256`** veröffentlicht — ohne
Prüfsumme verweigert der Installer die Installation.

```bash
# Beispiel: auf dem Zielsystem bauen und hierher kopieren
cd node-agent && ./build.sh
cp dist/comesh-agent-* ../frontend-alpine/downloads/
cp install.sh install.ps1 ../frontend-alpine/downloads/
```

Danach den Frontend-Container neu bauen und **prüfen, was ausgeliefert wird**
(der Container-Status ist kein Beleg):

```bash
docker compose build frontend && docker compose up -d --no-deps --force-recreate frontend
curl -sI https://<portal>/downloads/install.sh | head -3
curl -s https://<portal>/downloads/comesh-agent-linux-x86_64.sha256
```
