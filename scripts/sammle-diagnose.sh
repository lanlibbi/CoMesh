#!/usr/bin/env bash
# Fassung: 2026-11-18a -- reines ASCII
#
# sammle-diagnose.sh -- Bericht ueber eine laufende CoMesh-Instanz, ohne Geheimnisse.
#
# Warum: Wenn ein Betreiber nicht selbst am Server sitzt, ist der schnellste Weg zur Fehlersuche
# ein Bericht von dort. Ein Bericht mit echten Schluesseln ist aber ein Datenleck - er landet in
# Chats, Tickets und Repositories. Dieses Skript sammelt deshalb nur, was zur Diagnose taugt:
# Versionen, Zustand, Struktur, Logzeilen - und maskiert alle Werte, die nach Geheimnis aussehen.
#
# Aufruf:
#   bash sammle-diagnose.sh                 # Bericht nach stdout
#   bash sammle-diagnose.sh > bericht.md    # in eine Datei
#   bash sammle-diagnose.sh --projekt ~/pfad
#   bash sammle-diagnose.sh --mit-adressen   # IP-Adressen behalten (Vorgabe: maskiert)
#
# Das Skript aendert nichts. Es liest, fragt Docker und die Datenbank ab und schreibt Text.

set -u

PROJEKT="${PWD}"
MIT_ADRESSEN=0   # Vorgabe: IP-Adressen werden maskiert, Topologie ist auch ein Geheimnis
while [ $# -gt 0 ]; do
  case "$1" in
    --projekt) PROJEKT="$2"; shift 2 ;;
    --mit-adressen) MIT_ADRESSEN=1; shift ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "Unbekannte Option: $1" >&2; exit 2 ;;
  esac
done

cd "$PROJEKT" 2>/dev/null || { echo "Projektordner nicht gefunden: $PROJEKT" >&2; exit 1; }

# --- Schwaerzung ------------------------------------------------------------------------------
# Alles, was wie ein Geheimnis aussieht, wird ersetzt. Lieber zu viel maskieren als zu wenig:
# ein maskierter Wert kostet eine Rueckfrage, ein durchgesickerter Schluessel kostet die Instanz.
maskiere() {
  sed -E \
    -e 's/(gpu_|node_|sess_|sk-|pk_|ghp_|xoxb-)[A-Za-z0-9._-]{8,}/[REDACTED]/g' \
    -e 's/([A-Za-z0-9_-]*(KEY|TOKEN|SECRET|PASSWORD|PASSWORT|PASSWD|PWD|CREDENTIAL)[A-Za-z0-9_-]*)([[:space:]]*[=:][[:space:]]*).*/\1\3[REDACTED]/I' \
    -e 's/(Bearer[[:space:]]+)[A-Za-z0-9._-]+/\1[REDACTED]/g' \
    -e 's#(://[^:/@[:space:]]+:)[^@[:space:]]+@#\1[REDACTED]@#g' \
    -e 's/([0-9a-f]{32,})/[REDACTED]/g' \
    -e 's/("?password"?[[:space:]]*[:=][[:space:]]*")[^"]*"/\1[REDACTED]"/I' \
    | { if [ "${MIT_ADRESSEN:-0}" -eq 1 ]; then cat; else
          sed -E 's/\b([0-9]{1,3}\.){3}[0-9]{1,3}\b/[IP]/g';
        fi; }
}

abschnitt() { printf '\n## %s\n\n' "$1"; }
unterabschnitt() { printf '\n### %s\n\n' "$1"; }

echo "# CoMesh-Instanz: Diagnosebericht"
echo
echo "Erzeugt: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "Projektordner: \`$PROJEKT\`"
echo "Werte sind maskiert (Schluessel, Kennwoerter, Verbindungszeichenfolgen)."

# --- 1. Version und Stand ---------------------------------------------------------------------
abschnitt "1. Version und Stand"
[ -f VERSION ] && echo "- Portal: \`$(head -1 VERSION)\`"
[ -f AGENT_VERSION ] && echo "- Agent (Quelle): \`$(head -1 AGENT_VERSION)\`"
if [ -d .git ]; then
  echo "- Commit: \`$(git rev-parse --short HEAD 2>/dev/null)\` ($(git rev-parse --abbrev-ref HEAD 2>/dev/null))"
  echo "- Aenderungen im Arbeitsbaum: $(git status --porcelain 2>/dev/null | wc -l) Datei(en)"
  echo "- Letzte Commits:"
  git log --oneline -5 2>/dev/null | sed 's/^/    /'
fi

# --- 2. Container -----------------------------------------------------------------------------
abschnitt "2. Container"
if command -v docker >/dev/null 2>&1; then
  docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}' 2>&1 | maskiere
  unterabschnitt "Abbilder (lokal)"
  docker images --format '{{.Repository}}:{{.Tag}} {{.Size}} seit {{.CreatedSince}}' 2>&1 \
    | grep -i comesh | maskiere
else
  echo "docker nicht im PATH."
fi

# --- 3. Konfiguration: Struktur statt Werte ---------------------------------------------------
abschnitt "3. Konfiguration (nur Schluesselnamen)"
if [ -f .env ]; then
  echo "Variablen in \`.env\`:"
  grep -E '^[A-Za-z_][A-Za-z0-9_]*=' .env 2>/dev/null \
    | cut -d= -f1 | sort | sed 's/^/    /'
else
  echo "Keine \`.env\` im Projektordner."
fi
unterabschnitt "docker-compose: Dienste und Ports"
if command -v docker >/dev/null 2>&1; then
  docker compose config 2>/dev/null | grep -E '^  [a-z].*:|container_name:|image:|  ports:|    - "?[0-9]' \
    | head -60 | maskiere
fi

# --- 4. Zustand der API -----------------------------------------------------------------------
abschnitt "4. Zustand der API"
PORT="$(grep -E '^[A-Z_]*PORT=' .env 2>/dev/null | head -1 | cut -d= -f2 | tr -d '"'"'"' ')"
PORT="${PORT:-8767}"
if command -v curl >/dev/null 2>&1; then
  echo "\`GET /api/health\` auf Port $PORT:"
  echo '```'
  curl -sS --max-time 8 "http://127.0.0.1:$PORT/api/health" 2>&1 | head -c 600 | maskiere
  echo
  echo '```'
fi

# --- 5. Nodes (ohne Schluessel) ---------------------------------------------------------------
abschnitt "5. Registrierte Nodes"
if command -v docker >/dev/null 2>&1; then
  CONTAINER="$(docker ps --format '{{.Names}}' | grep -iE 'api|backend' | head -1)"
  if [ -n "$CONTAINER" ]; then
    docker exec -i "$CONTAINER" python3 - <<'PY' 2>&1 | maskiere
import os, sqlite3, glob
kandidaten = glob.glob("/data/*.db") + glob.glob("/data/*.sqlite3")
for pfad in kandidaten:
    try:
        c = sqlite3.connect(f"file:{pfad}?mode=ro", uri=True)
        c.row_factory = sqlite3.Row
        zeilen = c.execute(
            "select id, name, gpu_type, vram_gb, vram_source, status, is_enabled, "
            "last_seen, last_ws_seen, agent_version, connection_state from gpu_nodes"
        ).fetchall()
    except Exception as e:
        print(f"{os.path.basename(pfad)}: nicht lesbar ({e})")
        continue
    print(f"{os.path.basename(pfad)}: {len(zeilen)} Node(s)")
    for z in zeilen:
        d = dict(z)
        print(f"  id={d['id']} name={d['name']!r} gpu={d['gpu_type']!r} "
              f"vram={d['vram_gb']} ({d['vram_source']}) status={d['status']} "
              f"enabled={d['is_enabled']} agent={d['agent_version']} "
              f"verbindung={d['connection_state']} letzter_ping={d['last_ws_seen']}")
PY
  else
    echo "Kein API-Container gefunden."
  fi
fi

# --- 6. Protokoll -----------------------------------------------------------------------------
abschnitt "6. Protokoll (letzte Zeilen)"
if command -v docker >/dev/null 2>&1; then
  for name in $(docker ps --format '{{.Names}}' | grep -i comesh | head -3); do
    unterabschnitt "$name"
    echo '```'
    docker logs --tail 40 "$name" 2>&1 | maskiere
    echo '```'
  done
fi

# --- 7. Rechner -------------------------------------------------------------------------------
abschnitt "7. Rechner"
echo "- Kernel: $(uname -sr)"
echo "- Speicher:"
free -h 2>/dev/null | sed 's/^/    /'
echo "- Belegung des Projektordners:"
df -h "$PROJEKT" 2>/dev/null | tail -1 | sed 's/^/    /'
echo "- Lauschende Ports (Auszug):"
(ss -ltnp 2>/dev/null || netstat -ltnp 2>/dev/null) | grep -E ':(8[0-9]{3}|11434|5432|6379)\b' \
  | head -12 | sed 's/^/    /'

# --- 8. Dateien -------------------------------------------------------------------------------
abschnitt "8. Dateien im Projekt"
find . -maxdepth 2 -type f \( -name '*.py' -o -name '*.yml' -o -name '*.yaml' -o -name '*.conf' \
  -o -name 'Dockerfile*' -o -name '*.md' -o -name 'VERSION' -o -name 'AGENT_VERSION' \) \
  -not -path './.git/*' 2>/dev/null | sort | head -60 | sed 's/^/    /'

echo
echo "---"
echo
echo "Hinweis: Dieser Bericht enthaelt keine Schluesselwerte. Wenn zur Fehlersuche ein bestimmter"
echo "Wert gebraucht wird, bitte gezielt danach fragen - nicht die ganze Datei schicken."
