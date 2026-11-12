# Auslieferung der Node-Agent-Binaries

Dieser Ordner wird vom Frontend-Container mit ausgeliefert
(`COPY downloads/ /usr/share/nginx/html/downloads/`), damit ein Provider nur
**einen** Namen braucht:

```bash
curl -fsSL https://<portal>/downloads/install.sh | sh
powershell -ExecutionPolicy Bypass -Command "irm https://<portal>/downloads/install.ps1 | iex"
```

Der Installer lädt von hier:

| Datei | Ziel | Stand (09.11.2026) |
|---|---|---|
| `install.sh` | macOS/Linux-Installer (aus `node-agent/install.sh`) | **vorhanden** |
| `install.ps1` | Windows-Installer (aus `node-agent/install.ps1`) | **vorhanden** |
| `comesh-agent-darwin-arm64` + `.sha256` | Apple Silicon | **vorhanden** — 0.6.10, 14.044.992 B, in GitHub Actions gebaut (04.11.2026), `--version` und Prüfsumme geprüft, `3881a74dece1…` |
| `comesh-agent-darwin-x86_64` + `.sha256` | Intel-Mac | **fehlt** — `macos-latest` ist arm64; bräuchte einen Lauf auf `macos-13` |
| `comesh-agent-linux-arm64` + `.sha256` | Linux ARM64 | **fehlt** — nur auf einem ARM-Linux zu bauen, PyInstaller baut nicht über Architekturen |
| `comesh-agent-linux-x86_64` + `.sha256` | Linux x86_64 | **vorhanden** — 0.6.18, 14610072 B, am 12.11.2026 auf ai-lanlibbi gebaut (liest `AGENT_VERSION`), `--version` geprüft (`comesh-agent 0.6.18`), `8cfc5e866e23…` |
| `comesh-agent-windows-x86_64.exe` + `.sha256` | Windows x64 | **0.6.17 — Neubau für 0.6.18 offen**) (Bauhost war am 11.11. offline), 14.059.703 B, `02fa4ad075fe…`; das Portal zeigt an dieser Node „veraltet“ bis der Bau nachgezogen ist |

Die Größen sind am 09.11.2026 gegen die Dateien hier nachgemessen
(SHA-256 der geladenen Datei == `.sha256` daneben == Datei in diesem Ordner).

### Cloudflare liefert `.exe` aus dem Edge-Cache

Dateien mit der Endung `.exe` cached Cloudflare von sich aus am Rand
(`cache-control: max-age=14400`, also 4 h) — `.sh`, `.ps1` und `.sha256` nicht
(`cf-cache-status: DYNAMIC`). Am 04.11.2026 stand deshalb nach dem Austausch des
Windows-Binaries über HTTPS weiter die alte 0.6.9er Datei (`cf-cache-status:
HIT`, `age: 6508`), während die `.sha256` schon die neue Summe trug: der
Windows-Installer brach an der Prüfsumme ab, obwohl am Ursprung alles stimmte.
Zwei Gegenmaßnahmen, beide im Repo:

* `install.sh`/`install.ps1` hängen die Prüfsumme als Query an die
  Binary-Adresse (`…exe?sha=<erste 12 Zeichen>`). Der Query ändert sich mit dem
  Inhalt, eine alte Cache-Kopie kann nicht mehr greifen — das wirkt auch auf
  einen Edge, der die Datei schon hält. **Das ist der belastbare Teil.**
* `frontend-alpine/nginx.conf` schickt für `/downloads/`
  `Cache-Control: no-cache`. Gemessen: solange die gespeicherte Kopie frisch
  war, hat der Edge den Header ignoriert (`max-age=14400`, HIT); nach Ablauf
  der TTL fragt er den Ursprung und antwortet danach
  `cf-cache-status: REVALIDATED` — mit dem Header bleibt es beim Rückfragen,
  statt wieder vier Stunden eine Kopie zu halten. Er verkürzt also die
  Frischezeit einer **schon** gespeicherten Datei nicht; dafür ist der Query
  da. `.sh`, `.ps1` und `.sha256` sind ohnehin nicht betroffen (`DYNAMIC`).

Nach einem Release deshalb **über den öffentlichen Namen** prüfen, nicht nur am
Container:

```bash
SHA=$(curl -fsS https://<portal>/downloads/comesh-agent-windows-x86_64.exe.sha256 | cut -d' ' -f1)
curl -fsS -o /tmp/a.exe -w '%{http_code} %{size_download}\n' \
  "https://<portal>/downloads/comesh-agent-windows-x86_64.exe?sha=${SHA:0:12}"
sha256sum /tmp/a.exe    # muss $SHA sein
```

(Die letzte Prüfung gehört auf den Zielrechner: `& $env:TEMP\a.exe --version`
muss die neue Version melden — die Größe allein beweist keine Version.)

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
