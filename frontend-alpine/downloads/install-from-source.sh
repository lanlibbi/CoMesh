#!/usr/bin/env bash
# CoMesh Node-Agent aus dem Quelltext installieren — für Rechner, für die es kein passendes
# Binary gibt (z. B. linux-arm64) oder auf denen eine Richtlinie das Binary blockiert.
#
# Warum es das gibt: die Binaries werden für linux-x86_64, windows-x86_64 und darwin-arm64
# ausgeliefert. Wer eine andere Architektur hat oder kein Recht hat, ein fremdes Binary
# auszuführen, startet den Agenten direkt als Python-Programm. Der Agent ist ein normales
# Python-Programm; das Binary ist nur eine Verpackung (PyInstaller).
#
# Aufruf:
#   curl -fsSL https://<portal>/downloads/install-from-source.sh | sh
#   ./-install-from-source.sh --portal-url https://<portal>/api --uninstall
#
# Voraussetzung: Python 3.10 oder neuer. Das Skript sagt es und nennt den Befehl für die
# Distribution, wenn es fehlt — es installiert selbst nichts systemweit.

set -eu

PORTAL_URL="${COMESH_PORTAL_URL:-}"
ACCOUNT_KEY="${COMESH_USER_KEY:-}"
KEY_FILE="${COMESH_KEY_FILE:-}"
TRANSPORT="${COMESH_TRANSPORT:-ws}"
BACKEND="${COMESH_BACKEND:-ollama}"
INFERENCE_URL="${COMESH_INFERENCE_URL:-}"
VRAM_GB="${COMESH_VRAM_GB:-}"
NODE_NAME="${COMESH_AGENT_NAME:-$(hostname 2>/dev/null || echo node)}"
SOURCE_TARBALL="${COMESH_SOURCE_TARBALL:-https://github.com/lanlibbi/CoMesh/archive/refs/heads/main.tar.gz}"
DO_UNINSTALL=0

say()  { printf '  %s\n' "$*"; }
step() { printf '\n==> %s\n' "$*"; }
warn() { printf 'WARNUNG: %s\n' "$*" >&2; }
die()  { printf '\nFEHLER: %s\n' "$*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --portal-url) PORTAL_URL="${2:-}"; shift 2 ;;
    --name)       NODE_NAME="${2:-}"; shift 2 ;;
    --backend)    BACKEND="${2:-}"; shift 2 ;;
    --inference-url) INFERENCE_URL="${2:-}"; shift 2 ;;
    --vram-gb)    VRAM_GB="${2:-}"; shift 2 ;;
    --key-file)   KEY_FILE="${2:-}"; shift 2 ;;
    --source-tarball) SOURCE_TARBALL="${2:-}"; shift 2 ;;
    --uninstall)  DO_UNINSTALL=1; shift ;;
    -h|--help)    sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)            die "Unbekannte Option: $1" ;;
  esac
done

CONF_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/comesh"
ENV_FILE="$CONF_DIR/agent.env"
STATE_FILE="$CONF_DIR/node-state.json"
LOG_FILE="$CONF_DIR/agent.log"
SRC_DIR="$HOME/.local/share/comesh/src"
VENV_DIR="$HOME/.local/share/comesh/venv"
PY="$VENV_DIR/bin/python"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT_NAME="comesh-agent.service"
UNIT="$UNIT_DIR/$UNIT_NAME"
LABEL="me.lanlibbi.comesh.agent"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

# ---------------------------------------------------------------------------
# Entfernen
# ---------------------------------------------------------------------------
if [ "$DO_UNINSTALL" -eq 1 ]; then
  step "Entfernen"
  if [ "$(uname -s)" = "Darwin" ]; then
    launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || launchctl unload "$PLIST" 2>/dev/null || true
    rm -f "$PLIST"
    say "launchd-Dienst entfernt"
  else
    systemctl --user disable --now "$UNIT_NAME" 2>/dev/null || true
    rm -f "$UNIT"
    systemctl --user daemon-reload 2>/dev/null || true
    say "systemd-Dienst entfernt"
  fi
  rm -rf "$SRC_DIR" "$VENV_DIR"
  say "Quelltext und Umgebung unter ~/.local/share/comesh entfernt."
  say "Die Konfiguration liegt weiter in $ENV_FILE — löschen: rm -rf \"$CONF_DIR\""
  exit 0
fi

printf 'CoMesh Node-Agent — Installation aus dem Quelltext\n'

# ---------------------------------------------------------------------------
# 1. Python prüfen
# ---------------------------------------------------------------------------
step "Python"
PYTHON=""
for kandidat in python3.13 python3.12 python3.11 python3.10 python3 python; do
  if command -v "$kandidat" >/dev/null 2>&1; then
    if "$kandidat" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
      PYTHON="$kandidat"; break
    fi
  fi
done
if [ -z "$PYTHON" ]; then
  warn "Kein Python 3.10 oder neuer gefunden. Installieren (ohne root, wenn möglich):"
  cat >&2 <<'HINWEIS'
    Debian/Ubuntu:  sudo apt update && sudo apt install -y python3 python3-venv python3-pip
    Fedora/RHEL:    sudo dnf install -y python3 python3-pip
    Arch:           sudo pacman -S --needed python python-pip
    Alpine:         sudo apk add python3 py3-pip
    macOS:          brew install python@3.12     (oder: xcode-select --install)
HINWEIS
  die "Bitte Python installieren und dieses Skript erneut starten."
fi
say "gefunden: $("$PYTHON" --version 2>&1) ($PYTHON)"

# ---------------------------------------------------------------------------
# 2. Portal und Schlüssel
# ---------------------------------------------------------------------------
step "Portal"
if [ -z "$PORTAL_URL" ] && [ -r "$ENV_FILE" ]; then
  PORTAL_URL=$(sed -n 's/^PORTAL_URL=//p' "$ENV_FILE" | head -1)
  [ -n "$PORTAL_URL" ] && say "Adresse aus der vorhandenen Konfiguration übernommen."
fi
if [ -z "$PORTAL_URL" ]; then
  printf '  Adresse der API (z. B. http://192.168.2.187:8765): '
  read -r PORTAL_URL || die "Keine Eingabe möglich — setze COMESH_PORTAL_URL."
fi
PORTAL_URL="${PORTAL_URL%/}"
case "$PORTAL_URL" in http://*|https://*) ;; *) die "Portal-Adresse muss mit http:// oder https:// beginnen." ;; esac
if command -v curl >/dev/null 2>&1 && curl -fsS --max-time 10 "$PORTAL_URL/version" >/dev/null 2>&1; then
  say "Portal erreichbar: $(curl -fsS --max-time 10 "$PORTAL_URL/version" | head -c 120)"
else
  warn "Portal antwortet nicht auf $PORTAL_URL/version — Installation läuft weiter."
fi

case "$BACKEND" in ollama|openai) ;; *) die "Backend muss 'ollama' oder 'openai' sein." ;; esac
[ -n "$INFERENCE_URL" ] || { [ "$BACKEND" = "openai" ] && INFERENCE_URL="http://127.0.0.1:1234" || INFERENCE_URL="http://127.0.0.1:11434"; }

step "Konto-Schlüssel"
if [ -n "$KEY_FILE" ]; then
  [ -r "$KEY_FILE" ] || die "Schlüsseldatei nicht lesbar: $KEY_FILE"
  ACCOUNT_KEY=$(tr -d '\r\n ' < "$KEY_FILE")
elif [ -z "$ACCOUNT_KEY" ] && [ -r "$ENV_FILE" ]; then
  ACCOUNT_KEY=$(sed -n 's/^PORTAL_USER_KEY=//p' "$ENV_FILE" | head -1)
  [ -n "$ACCOUNT_KEY" ] && say "Vorhandener Account-Schlüssel wird beibehalten."
fi
if [ -z "$ACCOUNT_KEY" ]; then
  if [ -t 0 ]; then
    printf '  Account-Schlüssel (API-Key deines CoMesh-Kontos, Eingabe bleibt unsichtbar): '
    stty -echo 2>/dev/null || true
    read -r ACCOUNT_KEY || true
    stty echo 2>/dev/null || true
    printf '\n'
  else
    die "Kein Terminal für die Eingabe — setze COMESH_USER_KEY=gpu_… oder nutze --key-file."
  fi
fi
[ -n "$ACCOUNT_KEY" ] || die "Ohne Account-Schlüssel kann sich die Node nicht registrieren."

# ---------------------------------------------------------------------------
# 3. Quelltext holen
# ---------------------------------------------------------------------------
step "Quelltext"
mkdir -p "$HOME/.local/share/comesh"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT INT TERM
if ! curl -fsSL --max-time 300 "$SOURCE_TARBALL" -o "$WORK/src.tar.gz"; then
  die "Quelltext nicht ladbar von $SOURCE_TARBALL (Netzzugang zu GitHub?)."
fi
tar -xzf "$WORK/src.tar.gz" -C "$WORK" || die "Archiv nicht entpackbar."
QUELLE=$(find "$WORK" -maxdepth 2 -name agent.py -path '*/node-agent/*' -printf '%h\n' 2>/dev/null | head -1)
[ -n "$QUELLE" ] || QUELLE=$(find "$WORK" -maxdepth 3 -type d -name node-agent | head -1)
[ -n "$QUELLE" ] || die "Im Archiv fehlt node-agent/agent.py — ist das wirklich das CoMesh-Repo?"
rm -rf "$SRC_DIR"
mkdir -p "$(dirname "$SRC_DIR")"
cp -a "$(dirname "$QUELLE")/." "$SRC_DIR/" 2>/dev/null || cp -a "$QUELLE/." "$SRC_DIR/"
AGENT_DIR="$SRC_DIR/node-agent"
[ -f "$AGENT_DIR/agent.py" ] || AGENT_DIR="$SRC_DIR"
[ -f "$AGENT_DIR/agent.py" ] || die "agent.py nach dem Kopieren nicht gefunden."
say "liegt in $SRC_DIR (Agent-Version $(cat "$SRC_DIR/AGENT_VERSION" 2>/dev/null || echo unbekannt))"

# ---------------------------------------------------------------------------
# 4. Umgebung
# ---------------------------------------------------------------------------
step "Abhängigkeiten"
[ -x "$PY" ] || "$PYTHON" -m venv "$VENV_DIR" || die "Python-Umgebung liess sich nicht anlegen (python3-venv installiert?)."
"$PY" -m pip install --quiet --upgrade pip >/dev/null 2>&1 || true
"$PY" -m pip install --quiet -r "$AGENT_DIR/requirements.txt" || die "pip install fehlgeschlagen (PyPI erreichbar?)."
say "Pakete installiert in $VENV_DIR"

# ---------------------------------------------------------------------------
# 5. Konfiguration
# ---------------------------------------------------------------------------
step "Konfiguration"
mkdir -p "$CONF_DIR"
chmod 700 "$CONF_DIR"
umask 077
{
  echo "# CoMesh Node-Agent — erzeugt von install-from-source.sh (enthält den Account-Schlüssel)"
  echo "PORTAL_URL=$PORTAL_URL"
  echo "PORTAL_USER_KEY=$ACCOUNT_KEY"
  echo "AGENT_TRANSPORT=$TRANSPORT"
  echo "NODE_NAME=$NODE_NAME"
  echo "BACKEND=$BACKEND"
  if [ "$BACKEND" = "openai" ]; then echo "INFERENCE_URL=$INFERENCE_URL"; else echo "OLLAMA_URL=$INFERENCE_URL"; fi
  echo "NODE_STATE_FILE=$STATE_FILE"
  echo "AGENT_LOG_FILE=$LOG_FILE"
  [ -n "$VRAM_GB" ] && echo "NODE_VRAM_GB=$VRAM_GB"
} > "$ENV_FILE"
chmod 600 "$ENV_FILE"
say "geschrieben: $ENV_FILE (600)"

# ---------------------------------------------------------------------------
# 6. Selbsttest
# ---------------------------------------------------------------------------
step "Selbsttest"
CHECK_OK=0
if ( cd "$AGENT_DIR" && COMESH_AGENT_ENV="$ENV_FILE" "$PY" agent.py --check 2>&1 ); then
  CHECK_OK=1
else
  warn "Selbsttest meldet eine unvollständige Konfiguration."
fi

# ---------------------------------------------------------------------------
# 7. Dienst
# ---------------------------------------------------------------------------
step "Dienst"
if [ "$(uname -s)" = "Darwin" ]; then
  mkdir -p "$HOME/Library/LaunchAgents"
  cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>$PY</string><string>$AGENT_DIR/agent.py</string></array>
  <key>WorkingDirectory</key><string>$AGENT_DIR</string>
  <key>EnvironmentVariables</key><dict><key>COMESH_AGENT_ENV</key><string>$ENV_FILE</string></dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$LOG_FILE</string>
  <key>StandardErrorPath</key><string>$LOG_FILE</string>
</dict>
</plist>
PLISTEOF
  chmod 644 "$PLIST"
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null || launchctl load -w "$PLIST" \
    || warn "launchd-Dienst konnte nicht geladen werden. Von Hand: $PY $AGENT_DIR/agent.py"
  say "launchd-Dienst eingerichtet: $PLIST"
else
  mkdir -p "$UNIT_DIR"
  cat > "$UNIT" <<UNITEOF
[Unit]
Description=CoMesh Node-Agent (Quelltext)
Documentation=https://github.com/lanlibbi/CoMesh/blob/main/docs/install.md
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$AGENT_DIR
ExecStart=$PY $AGENT_DIR/agent.py
Environment=COMESH_AGENT_ENV=$ENV_FILE
Restart=always
RestartSec=10
# Kein Port, keine Root-Rechte: der Agent wählt sich ausgehend ein.
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=default.target
UNITEOF
  chmod 644 "$UNIT"
  systemctl --user daemon-reload 2>/dev/null || warn "systemctl --user antwortet nicht (keine Benutzersitzung?)."
  systemctl --user enable --now "$UNIT_NAME" 2>/dev/null \
    || warn "Dienst konnte nicht gestartet werden. Von Hand: $PY $AGENT_DIR/agent.py"
  say "systemd-Dienst eingerichtet: $UNIT"
fi

step "Status"
if [ -f "$LOG_FILE" ]; then
  tail -n 6 "$LOG_FILE" | sed 's/^/    /'
else
  say "Noch kein Protokoll — der Dienst schreibt nach $LOG_FILE"
fi
printf '\nFertig. Im Portal unter „Node beitragen" muss die Node als verbunden erscheinen.\n'
