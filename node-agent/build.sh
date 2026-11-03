#!/usr/bin/env bash
# Baut das CoMesh-Agent-Einzelbinary für macOS oder Linux.
#
#   ./build.sh              # Binary + Prüfsumme nach dist/
#   ./build.sh --no-venv    # vorhandenes PyInstaller im aktuellen Python nutzen
#
# Ergebnis (Name = was install.sh erwartet):
#   dist/comesh-agent-darwin-arm64      + .sha256
#   dist/comesh-agent-darwin-x86_64     + .sha256
#   dist/comesh-agent-linux-arm64       + .sha256
#   dist/comesh-agent-linux-x86_64      + .sha256
#
# Das Skript baut NUR für die Architektur des Rechners, auf dem es läuft: ein
# PyInstaller-Binary ist nicht architekturübergreifend. Für macOS arm64 **und**
# x86_64 braucht es zwei Rechner (oder einen x86_64-Mac mit Rosetta-fähigem
# Python; ein arm64-Mac kann kein x86_64-Binary einfrieren).
#
# Speicher: PyInstaller braucht beim Einfrieren rund 400–800 MB. Auf einem
# 4-GB-Raspberry lief der Build durch; unter 1,5 GB frei wird es eng.
set -euo pipefail
cd "$(dirname "$0")"

VERSION="$(cat ../VERSION 2>/dev/null || echo "")"
if [ -z "$VERSION" ]; then
  VERSION="0.0.0"
  echo "WARNUNG: ../VERSION nicht gefunden — das Binary meldet $VERSION statt der Repo-Version." >&2
  echo "         Das ist nur bei einem losgeloesten node-agent/-Verzeichnis normal." >&2
fi
PYTHON="${PYTHON:-python3}"
USE_VENV=1
for arg in "$@"; do
  case "$arg" in
    --no-venv) USE_VENV=0 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "Unbekannter Parameter: $arg" >&2; exit 2 ;;
  esac
done

case "$(uname -s)" in
  Darwin) OS_NAME=darwin ;;
  Linux)  OS_NAME=linux ;;
  *) echo "Nicht unterstütztes Betriebssystem: $(uname -s). Windows: build.ps1." >&2; exit 1 ;;
esac

case "$(uname -m)" in
  arm64|aarch64) ARCH=arm64 ;;
  x86_64|amd64)  ARCH=x86_64 ;;
  *) echo "Nicht unterstützte Architektur: $(uname -m)" >&2; exit 1 ;;
esac

ARTIFACT="dist/comesh-agent-${OS_NAME}-${ARCH}"

if [ "$USE_VENV" = "1" ]; then
  if [ ! -x .venv-build/bin/python ]; then
    echo "==> Baust-venv anlegen (.venv-build, nicht systemweit)"
    "$PYTHON" -m venv .venv-build
  fi
  # shellcheck disable=SC1091
  . .venv-build/bin/activate
  echo "==> Abhängigkeiten installieren (requirements-build.txt)"
  python -m pip install --quiet --upgrade pip
  python -m pip install --quiet -r requirements-build.txt
else
  command -v pyinstaller >/dev/null 2>&1 || {
    echo "pyinstaller fehlt — ohne --no-venv installiert das Skript es selbst." >&2; exit 1; }
fi

echo "==> Einfrieren (PyInstaller, onefile)"
pyinstaller --clean --noconfirm --distpath dist --workpath build comesh-agent.spec

[ -f dist/comesh-agent ] || { echo "Build hat kein dist/comesh-agent erzeugt." >&2; exit 1; }
mv -f dist/comesh-agent "$ARTIFACT"
chmod 755 "$ARTIFACT"

# Prüfsumme im Format "<hex>  <dateiname>" (zwei Leerzeichen, wie sha256sum).
# install.sh liest das erste Feld; install.ps1 vergleicht die ganze Zeile.
if command -v sha256sum >/dev/null 2>&1; then
  ( cd dist && sha256sum "$(basename "$ARTIFACT")" > "$(basename "$ARTIFACT").sha256" )
else
  ( cd dist && shasum -a 256 "$(basename "$ARTIFACT")" > "$(basename "$ARTIFACT").sha256" )
fi

echo
echo "Fertig: $ARTIFACT (Version $VERSION, $(du -h "$ARTIFACT" | cut -f1))"
echo "Prüfsumme: $(cut -d' ' -f1 "dist/$(basename "$ARTIFACT").sha256")"
echo
echo "Ausliefern (beide Dateien zusammen, sonst verweigert der Installer):"
echo "  $(basename "$ARTIFACT")"
echo "  $(basename "$ARTIFACT").sha256"
echo "Zum Beispiel nach frontend-alpine/downloads/ im Portal — erreichbar unter"
echo "  https://<portal>/downloads/$(basename "$ARTIFACT")"
