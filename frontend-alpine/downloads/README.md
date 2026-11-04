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
| `comesh-agent-darwin-arm64` + `.sha256` | Apple Silicon | **vorhanden** — 0.6.10, 14,0 MB, in GitHub Actions gebaut (04.11.2026), `--version` und Prüfsumme geprüft |
| `comesh-agent-darwin-x86_64` + `.sha256` | Intel-Mac | **fehlt** — `macos-latest` ist arm64; bräuchte einen Lauf auf `macos-13` |
| `comesh-agent-linux-arm64` + `.sha256` | Linux ARM64 | **fehlt** — nur auf einem ARM-Linux zu bauen, PyInstaller baut nicht über Architekturen |
| `comesh-agent-linux-x86_64` + `.sha256` | Linux x86_64 | **vorhanden** — 0.6.10, 14,6 MB |
| `comesh-agent-windows-x86_64.exe` + `.sha256` | Windows x64 | **vorhanden** — 0.6.10, 14,1 MB |

Nur die Zeilen mit **vorhanden** lassen sich installieren. Der Installer bricht
bei einem fehlenden Binary mit klarer Meldung ab, statt etwas Falsches
einzurichten; `docs/install.md` sagt, was dann zu tun ist.

### macOS: gebaut in GitHub Actions, nicht auf einem Mac

Ein Darwin-Binary entsteht seit 04.11.2026 in
`.github/workflows/build-node-agent.yml` auf `macos-latest` (Apple Silicon):
Der Workflow misst `uname -m`, prüft `comesh-agent --version` gegen die
`VERSION`-Datei und lädt Binary + `.sha256` als Artefakt hoch. Das Binary wird
von dort geholt und hierher gelegt:

```bash
# Artefakt des letzten grünen Laufs (braucht ein GitHub-Token)
gh run download --repo lanlibbi/CoMesh --name comesh-agent-darwin-arm64 -D /tmp/mac
# oder über die REST-API: /repos/lanlibbi/CoMesh/actions/artifacts/<id>/zip
cp /tmp/mac/comesh-agent-darwin-arm64* frontend-alpine/downloads/
sha256sum -c frontend-alpine/downloads/comesh-agent-darwin-arm64.sha256
```

Wer das Binary lieber lokal baut, kann es weiterhin:
`cd node-agent && ./build.sh` (PyInstaller baut nur für die Architektur des
Rechners, auf dem es läuft).

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
