# Auslieferung der Node-Agent-Binaries

Dieser Ordner wird vom Frontend-Container mit ausgeliefert
(`COPY downloads/ /usr/share/nginx/html/downloads/`), damit ein Provider nur
**einen** Namen braucht:

```bash
curl -fsSL https://<portal>/downloads/install.sh | sh
irm https://<portal>/downloads/install.ps1 | iex
```

Der Installer lädt von hier:

| Datei | Ziel | Stand (04.11.2026) |
|---|---|---|
| `install.sh` | macOS/Linux-Installer (aus `node-agent/install.sh`) | **vorhanden** |
| `install.ps1` | Windows-Installer (aus `node-agent/install.ps1`) | **vorhanden** |
| `comesh-agent-darwin-arm64` + `.sha256` | Apple Silicon | **fehlt** |
| `comesh-agent-darwin-x86_64` + `.sha256` | Intel-Mac | **fehlt** |
| `comesh-agent-linux-arm64` + `.sha256` | Linux ARM64 | **fehlt** |
| `comesh-agent-linux-x86_64` + `.sha256` | Linux x86_64 | **vorhanden** — 0.6.9, 14 MB |
| `comesh-agent-windows-x86_64.exe` + `.sha256` | Windows x64 | **vorhanden** — 0.6.9, 13,4 MB |

Nur die Zeilen mit **vorhanden** lassen sich installieren. Der Installer bricht
bei einem fehlenden Binary mit klarer Meldung ab, statt etwas Falsches
einzurichten; `docs/install.md` sagt, was dann zu tun ist. Ein fehlendes
Darwin-Binary heißt: auf dem Mac selbst bauen (`cd node-agent && ./build.sh`) —
PyInstaller kann nicht architekturübergreifend bauen.

**Die Binaries liegen nicht im Repo** (15–25 MB je Datei, und sie gehören zu
einem Release, nicht zu einem Quellstand); die beiden Installer schon. Erzeugt
werden die Binaries mit `node-agent/build.sh` bzw. `node-agent/build.ps1`; die
Dateien werden hier abgelegt und **immer zusammen mit ihrer `.sha256`**
veröffentlicht — ohne Prüfsumme verweigert der Installer die Installation.

```bash
# Beispiel: auf dem Zielsystem bauen und hierher kopieren
cd node-agent && ./build.sh
cp dist/comesh-agent-* ../frontend-alpine/downloads/
cp install.sh install.ps1 ../frontend-alpine/downloads/
cmp install.sh ../frontend-alpine/downloads/install.sh   # Kopien nicht auseinanderlaufen lassen
```

Danach den Frontend-Container neu bauen und **prüfen, was ausgeliefert wird**
(der Container-Status ist kein Beleg):

```bash
docker compose build frontend && docker compose up -d --no-deps --force-recreate frontend
curl -sI https://<portal>/downloads/install.sh | head -3
curl -s https://<portal>/downloads/comesh-agent-linux-x86_64.sha256
```
