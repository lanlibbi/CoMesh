#!/usr/bin/env bash
# Agent-Binaries in eine frische Instanz holen.
#
# Warum es das gibt: die Binaries stehen bewusst NICHT im Repo
# (`frontend-alpine/downloads/.gitignore` schliesst `comesh-agent-*` aus, 15–25 MB je Datei).
# Nach einem frischen Klon oder `git pull` ist der Download-Ordner darum leer, und die
# Beitragen-Ansicht im Portal meldet für jede Datei „nicht ermittelbar / keine Prüfsummendatei“.
# Das ist kein Defekt der Oberfläche, sondern der Normalzustand einer Instanz, die noch keine
# Agent-Binaries gebaut oder übernommen hat.
#
# Das Skript holt die Dateien von einer Quelle, die sie hat (eine andere Instanz oder ein
# Release), prüft jede SHA-256 gegen die mitgelieferte `.sha256` und legt sie dort ab, wo das
# Dockerfile sie erwartet. Es gibt bewusst KEINE fest eingebaute Standardadresse: eine Instanz
# soll nicht stillschweigend bei einer fremden mitlesen (gleiche Regel wie in 0.6.22 für die
# Installer).
#
# Aufruf:
#   scripts/hole-agent-binaries.sh https://<quelle>          # z. B. eine bestehende Instanz
#   scripts/hole-agent-binaries.sh --nur-linux https://<quelle>
#   scripts/hole-agent-binaries.sh --pruefen                 # nur sagen, was fehlt
#
# Danach neu bauen, sonst bleibt das Image ohne die Dateien:
#   docker compose build frontend && docker compose up -d --no-deps --force-recreate frontend

set -euo pipefail

HIER="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ZIEL="$HIER/frontend-alpine/downloads"
NUR_LINUX=0
PRUEFEN=0
QUELLE=""

while [ $# -gt 0 ]; do
  case "$1" in
    --nur-linux) NUR_LINUX=1; shift ;;
    --pruefen)   PRUEFEN=1; shift ;;
    -h|--help)   sed -n '2,28p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*)          echo "Unbekannte Option: $1" >&2; exit 2 ;;
    *)           QUELLE="${1%/}"; shift ;;
  esac
done

DATEIEN=(
  comesh-agent-linux-x86_64        comesh-agent-linux-x86_64.sha256
)
if [ "$NUR_LINUX" -eq 0 ]; then
  DATEIEN+=(
    comesh-agent-windows-x86_64.exe comesh-agent-windows-x86_64.exe.sha256
    comesh-agent-darwin-arm64       comesh-agent-darwin-arm64.sha256
  )
fi

echo "Ziel: $ZIEL"
echo

if [ "$PRUEFEN" -eq 1 ]; then
  fehlt=0
  for f in "${DATEIEN[@]}"; do
    if [ -f "$ZIEL/$f" ]; then
      printf '  vorhanden   %-38s %10s B\n' "$f" "$(stat -c %s "$ZIEL/$f")"
    else
      printf '  FEHLT       %s\n' "$f"; fehlt=$((fehlt+1))
    fi
  done
  echo
  if [ "$fehlt" -gt 0 ]; then
    echo "$fehlt Datei(en) fehlen. Holen mit:"
    echo "  scripts/hole-agent-binaries.sh https://<quelle>"
    exit 1
  fi
  echo "Alle Dateien vorhanden. Prüfsummen:"
  ( cd "$ZIEL" && for f in "${DATEIEN[@]}"; do
      case "$f" in *.sha256) sha256sum -c "$f" ;; esac
    done )
  exit 0
fi

if [ -z "$QUELLE" ]; then
  echo "Fehler: Quelladresse fehlt." >&2
  echo "  scripts/hole-agent-binaries.sh https://<quelle>" >&2
  exit 2
fi

mkdir -p "$ZIEL"
for f in "${DATEIEN[@]}"; do
  if [ -f "$ZIEL/$f" ] && [ "${f##*.}" != "sha256" ]; then
    echo "  übersprungen (liegt schon)  $f"
    continue
  fi
  printf '  lade %-38s ' "$f"
  if curl -fsSL --max-time 600 "$QUELLE/downloads/$f" -o "$ZIEL/$f.tmp"; then
    mv "$ZIEL/$f.tmp" "$ZIEL/$f"
    printf '%10s B\n' "$(stat -c %s "$ZIEL/$f")"
  else
    rm -f "$ZIEL/$f.tmp"
    echo "FEHLGESCHLAGEN"
    echo "  Abruf fehlgeschlagen: Datei nicht vorhanden oder Quelle nicht erreichbar" >&2
    echo "  ($QUELLE/downloads/$f). Ohne passende .sha256 nimmt der Installer die Datei nicht an." >&2
    exit 1
  fi
done

echo
echo "Prüfsummen gegen die gelieferten .sha256:"
( cd "$ZIEL" && for f in "${DATEIEN[@]}"; do
    case "$f" in *.sha256) sha256sum -c "$f" ;; esac
  done )

echo
if [ -x "$ZIEL/comesh-agent-linux-x86_64" ]; then
  echo "Selbstauskunft des Linux-Binaries: $("$ZIEL/comesh-agent-linux-x86_64" --version 2>&1 | head -1)"
  echo "AGENT_VERSION im Repo:            $(cat "$HIER/AGENT_VERSION" 2>/dev/null || echo unbekannt)"
fi

echo
echo "Jetzt neu bauen, sonst fehlen die Dateien im Image:"
echo "  docker compose build frontend && docker compose up -d --no-deps --force-recreate frontend"
echo "Danach prüfen:"
echo "  curl -s -o /dev/null -w '%{http_code} %{size_download}\\n' http://127.0.0.1:8767/downloads/comesh-agent-linux-x86_64"
