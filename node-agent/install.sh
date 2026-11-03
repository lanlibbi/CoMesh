#!/bin/sh
# CoMesh Node-Agent — Installation mit einem Befehl (macOS und Linux).
#
#   curl -fsSL https://<portal>/downloads/install.sh | sh
#
# Das Skript ist POSIX-sh (läuft unter dash, bash und der sh von macOS) und
# braucht nichts außer curl und einem SHA-256-Werkzeug. Es installiert ein
# fertiges Einzelbinary — kein Python, kein Repo, kein Compiler.
#
# Was es tut:
#   1. Betriebssystem und Architektur erkennen
#   2. Binary + Prüfsumme laden, SHA-256 prüfen (ohne Prüfsumme: Abbruch)
#   3. nach ~/.local/bin/comesh-agent legen
#   4. Account-Schlüssel abfragen (verdeckt, nicht im Verlauf, nicht in argv)
#   5. VRAM abfragen, wenn keine NVIDIA-GPU erkannt wird
#   6. Konfiguration nach ~/.config/comesh/agent.env schreiben (Rechte 600)
#   7. Dienst einrichten: launchd (macOS) / systemd --user (Linux) — ohne sudo
#   8. Status zeigen: Dienst, Portal, Node
#
# Transport ist WebSocket: der Agent wählt sich ausgehend ein, es braucht keinen
# offenen Port und keine vom Portal erreichbare Adresse. HTTP nur mit
# --transport http.
#
# Beenden/entfernen:  install.sh --uninstall
#
# Parameter (alle auch als Umgebungsvariable, siehe --help):
#   --base-url URL      wo die Binaries liegen (Vorgabe: <portal>/downloads)
#   --portal-url URL    API-Basis des Portals (Vorgabe: https://<portal>/api)
#   --transport ws|http Vorgabe ws
#   --key-file PATH     Account-Schlüssel aus Datei (für Automatisierung)
#   --vram GB           VRAM übersteuern (ohne NVIDIA-GPU Pflicht)
#   --name NAME         Anzeigename der Node im Portal
#   --backend X         ollama (Vorgabe) oder openai
#   --inference-url URL Backend-Adresse
#   --uninstall         Dienst und Dateien entfernen
set -eu

# ---------------------------------------------------------------------------
# Vorgaben
# ---------------------------------------------------------------------------
# Dieselbe Adresse, unter der auch die Oberfläche liegt. Die Binaries werden
# vom Portal ausgeliefert (frontend-alpine/downloads/), damit ein Provider nur
# EINEN Namen braucht. `--base-url` überschreibt das z. B. für GitHub Releases.
DEFAULT_ORIGIN="${COMESH_ORIGIN:-https://comesh.lanlibbilab.me}"
BASE_URL="${COMESH_BASE_URL:-$DEFAULT_ORIGIN/downloads}"
PORTAL_URL="${COMESH_PORTAL_URL:-$DEFAULT_ORIGIN/api}"
TRANSPORT="${COMESH_TRANSPORT:-ws}"
ACCOUNT_KEY="${COMESH_USER_KEY:-}"
KEY_FILE=""
VRAM_GB="${COMESH_VRAM_GB:-}"
NODE_NAME="${COMESH_AGENT_NAME:-}"
BACKEND="${COMESH_BACKEND:-ollama}"
INFERENCE_URL="${COMESH_INFERENCE_URL:-}"
DO_UNINSTALL=0

LABEL="de.comesh.agent"
UNIT_NAME="comesh-agent.service"

say()   { printf '%s\n' "$*"; }
step()  { printf '\n==> %s\n' "$*"; }
warn()  { printf 'WARNUNG: %s\n' "$*" >&2; }
die()   { printf '\nFEHLER: %s\n' "$*" >&2; exit 1; }

usage() {
  if [ -n "${0:-}" ] && [ -f "${0:-}" ] && [ -r "${0:-}" ]; then
    sed -n '3,40p' "$0"
  else
    cat <<'EOF'
CoMesh Node-Agent — Installation (macOS/Linux)
  curl -fsSL <base>/install.sh | sh

  --base-url URL      wo die Binaries liegen (Vorgabe: <portal>/downloads)
  --portal-url URL    API-Basis des Portals (Vorgabe: https://<portal>/api)
  --transport ws|http Vorgabe ws (ausgehend, kein offener Port)
  --key-file PATH     Account-Schlüssel aus Datei
  --vram GB           VRAM übersteuern (ohne NVIDIA-GPU nötig)
  --name NAME         Anzeigename der Node
  --backend ollama|openai, --inference-url URL
  --uninstall         Dienst und Dateien entfernen
EOF
  fi
}

# ---------------------------------------------------------------------------
# Argumente
# ---------------------------------------------------------------------------
while [ $# -gt 0 ]; do
  case "$1" in
    --base-url)     [ $# -ge 2 ] || die "--base-url braucht einen Wert"; BASE_URL="$2"; shift 2 ;;
    --base-url=*)   BASE_URL="${1#*=}"; shift ;;
    --portal-url)   [ $# -ge 2 ] || die "--portal-url braucht einen Wert"; PORTAL_URL="$2"; shift 2 ;;
    --portal-url=*) PORTAL_URL="${1#*=}"; shift ;;
    --transport)    [ $# -ge 2 ] || die "--transport braucht ws|http"; TRANSPORT="$2"; shift 2 ;;
    --transport=*)  TRANSPORT="${1#*=}"; shift ;;
    --key-file)     [ $# -ge 2 ] || die "--key-file braucht einen Pfad"; KEY_FILE="$2"; shift 2 ;;
    --key-file=*)   KEY_FILE="${1#*=}"; shift ;;
    --vram)         [ $# -ge 2 ] || die "--vram braucht eine Zahl"; VRAM_GB="$2"; shift 2 ;;
    --vram=*)       VRAM_GB="${1#*=}"; shift ;;
    --name)         [ $# -ge 2 ] || die "--name braucht einen Wert"; NODE_NAME="$2"; shift 2 ;;
    --name=*)       NODE_NAME="${1#*=}"; shift ;;
    --backend)      [ $# -ge 2 ] || die "--backend braucht ollama|openai"; BACKEND="$2"; shift 2 ;;
    --backend=*)    BACKEND="${1#*=}"; shift ;;
    --inference-url) [ $# -ge 2 ] || die "--inference-url braucht einen Wert"; INFERENCE_URL="$2"; shift 2 ;;
    --inference-url=*) INFERENCE_URL="${1#*=}"; shift ;;
    --uninstall)    DO_UNINSTALL=1; shift ;;
    -h|--help)      usage; exit 0 ;;
    *) die "Unbekannter Parameter: $1 (--help zeigt die Liste)" ;;
  esac
done

BASE_URL="${BASE_URL%/}"
PORTAL_URL="${PORTAL_URL%/}"
case "$TRANSPORT" in ws|http) ;; *) die "--transport muss ws oder http sein, nicht '$TRANSPORT'" ;; esac
case "$BACKEND" in ollama|openai) ;; *) die "--backend muss ollama oder openai sein" ;; esac
case "$PORTAL_URL" in http://*|https://*) ;; *) die "PORTAL_URL muss mit http:// oder https:// beginnen: $PORTAL_URL" ;; esac
case "$BASE_URL" in http://*|https://*) ;; *) die "BASE_URL muss mit http:// oder https:// beginnen: $BASE_URL" ;; esac

# ---------------------------------------------------------------------------
# System erkennen
# ---------------------------------------------------------------------------
case "$(uname -s)" in
  Darwin) OS=darwin ;;
  Linux)  OS=linux ;;
  *) die "Unterstützt werden macOS und Linux. Windows: install.ps1 in einer PowerShell." ;;
esac
case "$(uname -m)" in
  arm64|aarch64) ARCH=arm64 ;;
  x86_64|amd64)  ARCH=x86_64 ;;
  *) die "Nicht unterstützte Architektur: $(uname -m) (erwartet arm64 oder x86_64)" ;;
esac

command -v curl >/dev/null 2>&1 || die "curl fehlt — ohne curl kann nichts geladen werden."

CONF_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/comesh"
ENV_FILE="$CONF_DIR/agent.env"
STATE_FILE="$CONF_DIR/node-state.json"
LOG_FILE="$CONF_DIR/agent.log"
BIN_DIR="$HOME/.local/bin"
BIN="$BIN_DIR/comesh-agent"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT="$UNIT_DIR/$UNIT_NAME"

[ -n "$NODE_NAME" ] || NODE_NAME="$(uname -n 2>/dev/null | cut -d. -f1)"
[ -n "$NODE_NAME" ] || NODE_NAME="comesh-node"
[ -n "$INFERENCE_URL" ] || {
  if [ "$BACKEND" = "openai" ]; then INFERENCE_URL="http://127.0.0.1:1234"; else INFERENCE_URL="http://127.0.0.1:11434"; fi
}

# ---------------------------------------------------------------------------
# Hilfsmittel
# ---------------------------------------------------------------------------
sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | cut -d' ' -f1
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | cut -d' ' -f1
  elif command -v openssl >/dev/null 2>&1; then
    openssl dgst -sha256 "$1" | awk '{print $NF}'
  else
    die "Kein SHA-256-Werkzeug gefunden (sha256sum, shasum oder openssl)."
  fi
}

# fetch <url> <ziel> — bricht bei HTTP-Fehlern ab, ohne halbe Dateien zu lassen.
fetch() {
  case "$1" in
    https://*) curl -fsSL --proto '=https' --tlsv1.2 --retry 2 -o "$2" "$1" ;;
    http://*)  warn "Unverschlüsselte Verbindung: $1"
               curl -fsSL --retry 2 -o "$2" "$1" ;;
  esac
}

# ask <frage> <vorgabe> — liest vom Terminal, nicht von stdin: bei
# `curl … | sh` ist stdin das Skript selbst und nach dem Parsen aufgebraucht.
ask() {
  _q="$1"; _d="${2:-}"
  if [ ! -r /dev/tty ]; then printf '%s' "$_d"; return 0; fi
  printf '%s [%s]: ' "$_q" "$_d" >/dev/tty
  IFS= read -r _a < /dev/tty || _a=""
  [ -n "$_a" ] || _a="$_d"
  printf '%s' "$_a"
}

# ask_secret <frage> — verdeckte Eingabe. Der Wert landet weder in der
# Prozessliste (kein Argument) noch in der Shell-History (keine Kommandozeile)
# noch im Terminalprotokoll (kein Echo).
ask_secret() {
  [ -r /dev/tty ] || return 1
  printf '%s' "$1" >/dev/tty
  _saved=$(stty -g < /dev/tty 2>/dev/null || true)
  stty -echo < /dev/tty 2>/dev/null || true
  trap 'stty echo < /dev/tty 2>/dev/null || true; printf "\n" >/dev/tty; exit 130' INT TERM
  IFS= read -r _v < /dev/tty || _v=""
  trap - INT TERM
  if [ -n "$_saved" ]; then stty "$_saved" < /dev/tty 2>/dev/null || stty echo < /dev/tty 2>/dev/null || true
  else stty echo < /dev/tty 2>/dev/null || true; fi
  printf '\n' >/dev/tty
  printf '%s' "$_v"
}

env_get() {  # env_get SCHLUESSEL — Wert aus einer vorhandenen agent.env
  [ -f "$ENV_FILE" ] || return 0
  sed -n "s/^$1=//p" "$ENV_FILE" | tail -n 1
}

detect_nvidia_vram_gb() {
  command -v nvidia-smi >/dev/null 2>&1 || return 1
  _mb=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null | head -n 1 | tr -dc '0-9')
  [ -n "$_mb" ] || return 1
  [ "$_mb" -gt 0 ] 2>/dev/null || return 1
  echo $(( _mb / 1024 ))
}

total_memory_gb() {
  if [ "$OS" = darwin ]; then
    _b=$(sysctl -n hw.memsize 2>/dev/null || echo 0)
  else
    _kb=$(awk '/^MemTotal:/{print $2}' /proc/meminfo 2>/dev/null || echo 0)
    _b=$(( ${_kb:-0} * 1024 ))
  fi
  [ "${_b:-0}" -gt 0 ] 2>/dev/null || { echo 0; return 0; }
  echo $(( _b / 1024 / 1024 / 1024 ))
}

# ---------------------------------------------------------------------------
# Deinstallation
# ---------------------------------------------------------------------------
uninstall() {
  step "CoMesh-Agent entfernen"
  if [ "$OS" = darwin ]; then
    launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || launchctl unload "$PLIST" 2>/dev/null || true
    rm -f "$PLIST"
    say "launchd-Dienst entfernt: $PLIST"
  else
    systemctl --user disable --now "$UNIT_NAME" 2>/dev/null || true
    rm -f "$UNIT"
    systemctl --user daemon-reload 2>/dev/null || true
    say "systemd-Dienst entfernt: $UNIT"
  fi
  rm -f "$BIN"
  rm -f "$ENV_FILE" "$LOG_FILE" "$LOG_FILE.1" "$LOG_FILE.2" "$STATE_FILE"
  # Leeren Konfigurationsordner mitnehmen; bleibt er stehen, sieht er wie eine
  # halbe Installation aus.
  rmdir "$CONF_DIR" 2>/dev/null || true
  say "Binary und Konfiguration entfernt."
  say ""
  say "Im Portal steht die Node weiterhin in der Geräteliste — dort löschen,"
  say "sonst bleibt sie als offline sichtbar."
  exit 0
}

[ "$DO_UNINSTALL" = "1" ] && uninstall

# ---------------------------------------------------------------------------
# 1. Binary laden und prüfen
# ---------------------------------------------------------------------------
step "Binary laden ($OS/$ARCH)"
ASSET="comesh-agent-$OS-$ARCH"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/comesh-install.XXXXXX")" || die "Kein Temporärverzeichnis verfügbar."
trap 'rm -rf "$WORK"' EXIT

if ! fetch "$BASE_URL/$ASSET" "$WORK/$ASSET"; then
  die "Download fehlgeschlagen: $BASE_URL/$ASSET
Prüfe die Basis-URL (--base-url) und ob die Datei dort liegt."
fi
if ! fetch "$BASE_URL/$ASSET.sha256" "$WORK/$ASSET.sha256"; then
  die "Prüfsumme nicht ladbar: $BASE_URL/$ASSET.sha256
Ohne Prüfsumme wird nichts installiert. Das ist Absicht: ein Binary aus dem
Netz ohne Kontrolle der Bytes ist ein offenes Tor."
fi

EXPECTED=$(cut -d' ' -f1 "$WORK/$ASSET.sha256" | head -n 1 | tr -d '\r' | tr 'A-F' 'a-f')
printf '%s' "$EXPECTED" | grep -Eq '^[0-9a-f]{64}$' \
  || die "Die Datei $ASSET.sha256 enthält keine gültige SHA-256-Summe (gelesen: '$EXPECTED')."
ACTUAL=$(sha256_of "$WORK/$ASSET" | tr 'A-F' 'a-f')
[ "$EXPECTED" = "$ACTUAL" ] || die "Prüfsumme stimmt nicht.
  erwartet: $EXPECTED
  erhalten: $ACTUAL
Die Datei wurde unterwegs verändert oder ist unvollständig. Nicht installiert."

say "SHA-256 geprüft: $ACTUAL"

mkdir -p "$BIN_DIR"
chmod 755 "$WORK/$ASSET"
cp -f "$WORK/$ASSET" "$BIN.tmp"
chmod 755 "$BIN.tmp"
mv -f "$BIN.tmp" "$BIN"
if ! VERSION_LINE=$("$BIN" --version 2>&1); then
  die "Das Binary startet nicht: $VERSION_LINE
Häufigste Ursache: falsche Architektur (z. B. x86_64-Binary auf Apple Silicon
ohne Rosetta). Nichts wurde eingerichtet."
fi
say "installiert: $BIN — $VERSION_LINE"

# Der Agent liest seine Konfiguration aus COMESH_AGENT_ENV (siehe Dienst unten)
# und schreibt Zustand und Protokoll dorthin. Nichts davon liegt in /data.
mkdir -p "$CONF_DIR"
chmod 700 "$CONF_DIR"

# ---------------------------------------------------------------------------
# 2. Account-Schlüssel
# ---------------------------------------------------------------------------
step "Portal-Konto"
if [ -n "$KEY_FILE" ]; then
  [ -r "$KEY_FILE" ] || die "Schlüsseldatei nicht lesbar: $KEY_FILE"
  ACCOUNT_KEY=$(tr -d '\r\n ' < "$KEY_FILE")
elif [ -z "$ACCOUNT_KEY" ]; then
  EXISTING=$(env_get PORTAL_USER_KEY)
  if [ -n "$EXISTING" ]; then
    ACCOUNT_KEY="$EXISTING"
    say "Vorhandener Account-Schlüssel wird beibehalten (neu setzen: COMESH_USER_KEY=… oder --key-file)."
  else
    if ! ACCOUNT_KEY=$(ask_secret "Account-Schlüssel (API-Key deines CoMesh-Kontos, Eingabe bleibt unsichtbar): "); then
      die "Kein Terminal für die Eingabe und COMESH_USER_KEY nicht gesetzt.
Setze den Schlüssel so:  COMESH_USER_KEY=gpu_… sh install.sh"
    fi
  fi
fi

[ -n "$ACCOUNT_KEY" ] || die "Ohne Account-Schlüssel kann sich die Node nicht registrieren."
case "$ACCOUNT_KEY" in
  *[!A-Za-z0-9._:-]*) die "Der Schlüssel enthält unerwartete Zeichen (erwartet: Buchstaben, Ziffern, . _ : -)." ;;
esac

# Vorprüfung: stimmt Schlüssel + Portal-URL? Das ist der häufigste Fehlschlag
# und er zeigt sich hier sofort statt fünf Minuten später im Dienst-Log.
ME=$(curl -sS -m 20 -H "Authorization: Bearer $ACCOUNT_KEY" "$PORTAL_URL/v1/me" 2>/dev/null || true)
ROLE=$(printf '%s' "$ME" | sed -n 's/.*"role"[[:space:]]*:[[:space:]]*"\([a-z]*\)".*/\1/p' | head -n 1)
case "$ME" in
  *'"email"'*) : ;;
  '') warn "Portal nicht erreichbar unter $PORTAL_URL — Installation läuft weiter, der Dienst wird es erneut versuchen." ;;
  *)  warn "Portal antwortete unerwartet auf /v1/me (kein Konto-JSON). Prüfe --portal-url." ;;
esac
case "$ROLE" in
  provider|both|admin) say "Konto erkannt (Rolle: $ROLE)." ;;
  consumer) warn "Das Konto hat die Rolle 'consumer'. Eine Node registriert nur ein Konto mit 'provider' oder 'both' — im Profil umstellen, sonst bleibt die Node unsichtbar." ;;
  '') : ;;
esac

# ---------------------------------------------------------------------------
# 3. VRAM
# ---------------------------------------------------------------------------
step "VRAM"
if [ -z "$VRAM_GB" ]; then
  if DETECTED=$(detect_nvidia_vram_gb); then
    say "NVIDIA-GPU erkannt: ${DETECTED} GB. Der Agent misst selbst — kein Eintrag nötig."
  else
    TOTAL=$(total_memory_gb)
    if [ "$TOTAL" -gt 1 ]; then SUGGEST=$(( TOTAL * 3 / 4 )); else SUGGEST=8; fi
    say "Keine NVIDIA-GPU erkannt (macOS/NVIDIA-Treiber fehlt/CPU-Node)."
    say "Ohne Angabe meldet der Agent 1 GB — das Portal weist dann JEDEN Auftrag ab,"
    say "die Node steht online und bekommt nichts. Deshalb wird der Wert hier gesetzt."
    if [ "$OS" = darwin ]; then
      say "Auf Apple Silicon: Unified Memory eintragen, aber nicht alles — System und"
      say "Backend brauchen selbst Speicher (bei ${TOTAL} GB sind ${SUGGEST} GB realistisch)."
    fi
    VRAM_GB=$(ask "VRAM, den diese Node anbieten darf (GB)" "$SUGGEST")
  fi
fi
if [ -n "$VRAM_GB" ]; then
  case "$VRAM_GB" in ''|*[!0-9]*) die "VRAM muss eine ganze Zahl in GB sein, nicht '$VRAM_GB'" ;; esac
  [ "$VRAM_GB" -ge 1 ] || die "VRAM muss mindestens 1 GB sein."
  say "gemeldeter VRAM: ${VRAM_GB} GB (Übersteuerung)"
fi

# ---------------------------------------------------------------------------
# 4. Konfiguration schreiben
# ---------------------------------------------------------------------------
step "Konfiguration"
umask 077
{
  printf '# CoMesh Node-Agent — erzeugt von install.sh (Rechte 600, enthält den Account-Schlüssel)\n'
  printf '# Ein erneuter Lauf von install.sh überschreibt diese Datei.\n'
  printf 'PORTAL_URL=%s\n' "$PORTAL_URL"
  printf 'PORTAL_USER_KEY=%s\n' "$ACCOUNT_KEY"
  printf 'AGENT_TRANSPORT=%s\n' "$TRANSPORT"
  printf 'NODE_NAME=%s\n' "$NODE_NAME"
  printf 'BACKEND=%s\n' "$BACKEND"
  if [ "$BACKEND" = openai ]; then
    printf 'INFERENCE_URL=%s\n' "$INFERENCE_URL"
  else
    printf 'OLLAMA_URL=%s\n' "$INFERENCE_URL"
  fi
  [ -n "$VRAM_GB" ] && printf 'NODE_VRAM_GB=%s\n' "$VRAM_GB"
  printf 'NODE_STATE_FILE=%s\n' "$STATE_FILE"
  printf 'AGENT_LOG_FILE=%s\n' "$LOG_FILE"
} > "$ENV_FILE.tmp"
chmod 600 "$ENV_FILE.tmp"
mv -f "$ENV_FILE.tmp" "$ENV_FILE"
say "geschrieben: $ENV_FILE (600)"

# Selbsttest mit genau dieser Konfiguration — vor dem Dienst, damit ein Fehler
# hier sichtbar wird und nicht erst im Hintergrund.
if COMESH_AGENT_ENV="$ENV_FILE" "$BIN" --check >"$WORK/check.txt" 2>&1; then
  sed 's/^/  /' "$WORK/check.txt"
else
  sed 's/^/  /' "$WORK/check.txt"
  warn "Selbsttest meldet eine unvollständige Konfiguration (siehe oben). Der Dienst wird trotzdem eingerichtet."
fi

# ---------------------------------------------------------------------------
# 5. Dienst einrichten (ohne sudo)
# ---------------------------------------------------------------------------
step "Dienst"
# Protokoll weiterdrehen, BEVOR der Dienst neu startet: sonst enthält die Datei
# noch die Zeilen des vorigen Laufs, und die Statusprüfung unten hält eine alte
# "WS welcome received"-Zeile für ein Lebenszeichen — ein Erfolg, der keiner ist.
if [ -f "$LOG_FILE" ]; then
  mv -f "$LOG_FILE" "$LOG_FILE.1" 2>/dev/null || true
fi

xml_escape() { printf '%s' "$1" | sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g'; }

if [ "$OS" = darwin ]; then
  mkdir -p "$HOME/Library/LaunchAgents"
  {
    printf '<?xml version="1.0" encoding="UTF-8"?>\n'
    printf '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
    printf '<plist version="1.0">\n<dict>\n'
    printf '  <key>Label</key><string>%s</string>\n' "$LABEL"
    printf '  <key>ProgramArguments</key><array><string>%s</string></array>\n' "$(xml_escape "$BIN")"
    printf '  <key>EnvironmentVariables</key><dict><key>COMESH_AGENT_ENV</key><string>%s</string></dict>\n' "$(xml_escape "$ENV_FILE")"
    printf '  <key>RunAtLoad</key><true/>\n'
    printf '  <key>KeepAlive</key><true/>\n'
    printf '  <key>ThrottleInterval</key><integer>10</integer>\n'
    printf '  <key>WorkingDirectory</key><string>%s</string>\n' "$(xml_escape "$CONF_DIR")"
    printf '  <key>StandardOutPath</key><string>%s</string>\n' "$(xml_escape "$LOG_FILE")"
    printf '  <key>StandardErrorPath</key><string>%s</string>\n' "$(xml_escape "$LOG_FILE")"
    printf '</dict>\n</plist>\n'
  } > "$PLIST"
  chmod 644 "$PLIST"
  # Idempotent: erst abmelden, dann neu laden. `launchctl load -w` bleibt als
  # Rückfall für macOS-Fassungen ohne `bootstrap`.
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || launchctl unload "$PLIST" 2>/dev/null || true
  sleep 1
  launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null || launchctl load -w "$PLIST" \
    || die "launchd konnte $PLIST nicht laden. Von Hand: launchctl bootstrap gui/$(id -u) $PLIST"
  say "launchd: $PLIST (Label $LABEL, Start bei Anmeldung, Neustart bei Abbruch)"
else
  mkdir -p "$UNIT_DIR"
  {
    printf '[Unit]\n'
    printf 'Description=CoMesh Node-Agent\n'
    printf 'Documentation=https://github.com/lanlibbi/CoMesh/blob/main/docs/install.md\n'
    printf 'After=network-online.target\n'
    printf 'Wants=network-online.target\n\n'
    printf '[Service]\n'
    printf 'Type=simple\n'
    printf 'ExecStart=%s\n' "$BIN"
    printf 'Environment=COMESH_AGENT_ENV=%s\n' "$ENV_FILE"
    printf 'Restart=always\n'
    printf 'RestartSec=10\n'
    printf '# Kein Port, keine Root-Rechte: der Agent wählt sich ausgehend ein.\n'
    printf 'NoNewPrivileges=true\n'
    printf 'PrivateTmp=true\n\n'
    printf '[Install]\n'
    printf 'WantedBy=default.target\n'
  } > "$UNIT"
  chmod 644 "$UNIT"
  systemctl --user daemon-reload || die "systemctl --user antwortet nicht — läuft eine Benutzersitzung?"
  systemctl --user enable "$UNIT_NAME" >/dev/null 2>&1 || warn "enable fehlgeschlagen (Dienst startet trotzdem jetzt)."
  systemctl --user restart "$UNIT_NAME" || die "Der Dienst startet nicht. Protokoll: journalctl --user -u $UNIT_NAME -n 50"
  say "systemd --user: $UNIT"
  # Ohne linger endet der Dienst mit der Sitzung (Logout/SSH-Ende). Das ist
  # ohne Benutzerpasswort nicht immer erlaubt — deshalb nur der Versuch.
  if ! loginctl enable-linger "$(id -un)" >/dev/null 2>&1; then
    say "Hinweis: 'loginctl enable-linger $(id -un)' nicht erlaubt — der Dienst läuft,"
    say "         solange eine Sitzung dieses Benutzers offen ist (Autostart bei Anmeldung)."
  fi
fi

# ---------------------------------------------------------------------------
# 6. Status
# ---------------------------------------------------------------------------
step "Status"
# Bis zu ~45 s auf das erste Lebenszeichen warten (Registrierung + WS-Handshake).
i=0
while [ "$i" -lt 15 ]; do
  if grep -q "WS welcome received" "$LOG_FILE" 2>/dev/null; then break; fi
  if [ "$TRANSPORT" = "http" ] && grep -q "Node-agent started" "$LOG_FILE" 2>/dev/null; then break; fi
  sleep 3
  i=$((i + 1))
done

case "$OS" in
  darwin)
    if launchctl print "gui/$(id -u)/$LABEL" >/dev/null 2>&1; then SVC="läuft"; else SVC="läuft NICHT"; fi ;;
  linux)
    if systemctl --user is-active --quiet "$UNIT_NAME"; then SVC="läuft"; else SVC="läuft NICHT"; fi ;;
esac

# curl schreibt bei einem Verbindungsfehler selbst "000" und endet ungleich 0 —
# ein zusätzliches `|| echo 000` ergäbe "000000".
HEALTH=$(curl -s -o /dev/null -w '%{http_code}' -m 10 "$PORTAL_URL/health" 2>/dev/null || true)
[ -n "$HEALTH" ] || HEALTH="000"
NODES=$(curl -s -m 15 -H "Authorization: Bearer $ACCOUNT_KEY" "$PORTAL_URL/nodes/my" 2>/dev/null || true)
# Zuerst über die node_id aus der Zustandsdatei: der Name im Portal ist der vom
# Zeitpunkt der Registrierung und kann von der Konfiguration abweichen. Eine
# Suche nach dem Namen allein trifft auch Teilstrings ("hermes" in
# "node-a-2") und meldet dann fälschlich Erfolg.
STATE_ID=$(sed -n 's/.*"node_id"[[:space:]]*:[[:space:]]*"\([0-9][0-9]*\)".*/\1/p' "$STATE_FILE" 2>/dev/null | head -n 1)
APPEARS="noch nicht"
if [ -n "$STATE_ID" ] && printf '%s' "$NODES" | grep -qE "\"id\"[[:space:]]*:[[:space:]]*${STATE_ID}([,}])"; then
  APPEARS="ja (node_id $STATE_ID)"
elif printf '%s' "$NODES" | grep -qF "\"name\":\"$NODE_NAME\""; then
  APPEARS="ja (Name: $NODE_NAME)"
fi
if grep -q "WS welcome received" "$LOG_FILE" 2>/dev/null; then WS="verbunden"; else WS="nicht verbunden"; fi

say "  Dienst        : $SVC"
if [ "$TRANSPORT" = "ws" ]; then
  say "  Transport     : ws (WebSocket $WS)"
else
  say "  Transport     : http"
fi
say "  Portal        : $PORTAL_URL/health -> HTTP $HEALTH"
# Das Backend ist die zweithäufigste Ursache für "Node online, aber nie ein
# Auftrag": der Agent steht, nur rechnen kann er nichts.
if [ "$BACKEND" = "openai" ]; then BACKEND_PROBE="$INFERENCE_URL/v1/models"; else BACKEND_PROBE="$INFERENCE_URL/api/tags"; fi
BACKEND_CODE=$(curl -s -o /dev/null -w '%{http_code}' -m 5 "$BACKEND_PROBE" 2>/dev/null || true)
[ -n "$BACKEND_CODE" ] || BACKEND_CODE="000"
say "  Backend       : $INFERENCE_URL -> HTTP $BACKEND_CODE"
if [ "$BACKEND_CODE" != "200" ]; then
  warn "Das Backend antwortet nicht ($INFERENCE_URL). Die Node ist dann online, bekommt"
  warn "aber keinen Auftrag — erst Ollama/LM Studio starten, dann den Dienst neu starten."
fi
say "  Node im Portal: $APPEARS"

say ""
say "  Protokoll     : $LOG_FILE"
case "$OS" in
  darwin) say "  Dienststatus  : launchctl print gui/$(id -u)/$LABEL" ;;
  linux)  say "  Dienststatus  : systemctl --user status $UNIT_NAME" ;;
esac

if [ "$SVC" != "läuft" ] || [ "$APPEARS" = "noch nicht" ]; then
  say ""
  warn "Noch nicht vollständig. Die letzten Protokollzeilen:"
  [ -f "$LOG_FILE" ] && tail -n 15 "$LOG_FILE" | sed 's/^/    /'
  say ""
  say "Häufige Ursachen (ausführlich: docs/install.md):"
  say "  - Konto nicht für Provider freigegeben (Rolle 'provider' oder 'both')"
  say "  - Schlüssel falsch oder widerrufen -> neu ausstellen, COMESH_USER_KEY=… erneut laufen lassen"
  say "  - Backend läuft nicht ($INFERENCE_URL) — der Agent ist dann online, aber ohne Modell"
  exit 1
fi

say ""
say "Fertig. Die Node ist im Portal unter 'Geräte' sichtbar, sobald das Backend"
say "antwortet. Neu starten: Dienst neu starten oder install.sh erneut ausführen."
