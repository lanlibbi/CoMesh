#!/usr/bin/env bash
# Fassung: 2026-11-18a -- reines ASCII
#
# deploy.sh -- Api, Oberflaeche und Agent aus dem Arbeitsbaum bauen und neu starten.
#
# Warum ein Skript: `docker compose build` allein laesst laufende Container unberuehrt, und ein
# festes Image-Tag im Compose verschleiert, welcher Code laeuft. Hier kommt der Tag aus der
# VERSION-Datei, und `--force-recreate` sorgt dafuer, dass auch Dienste mit unveraendertem Tag
# wirklich mit dem neuen Abbild starten.
#
# Aufruf:
#   bash scripts/deploy.sh              # alles bauen und starten
#   bash scripts/deploy.sh --nur-api    # nur die API
#   bash scripts/deploy.sh --pruefen    # nichts bauen, nur den laufenden Stand anzeigen

set -u
cd "$(dirname "$0")/.." || exit 1

NUR_API=0
NUR_PRUEFEN=0
for arg in "${@:-}"; do
  case "$arg" in
    --nur-api) NUR_API=1 ;;
    --pruefen) NUR_PRUEFEN=1 ;;
    "") ;;
    *) echo "Unbekannte Option: $arg" >&2; exit 2 ;;
  esac
done

VERSION="$(head -1 VERSION | tr -d ' \r\n')"
[ -n "$VERSION" ] || { echo "VERSION ist leer" >&2; exit 1; }
export COMESH_VERSION="$VERSION"

pruefen() {
  echo
  echo "==> Was laeuft"
  docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}' | grep -E 'NAMES|comesh' || true

  PORT="$(grep -E '^COMESH_BIND_ADDRESS' .env 2>/dev/null | head -1 | cut -d= -f2)"
  LOKAL="http://127.0.0.1:8767"
  echo
  echo "==> API"
  echo -n "  /api/health          : "
  curl -s --max-time 8 "$LOKAL/api/health" | head -c 200 || echo "keine Antwort"
  echo
  echo -n "  POST /api/v1/messages: "
  curl -s -o /dev/null -w '%{http_code}' --max-time 8 -X POST \
    -H 'Content-Type: application/json' -d '{"model":"x","max_tokens":5,"messages":[]}' \
    "$LOKAL/api/v1/messages"
  echo "  (401 = Route vorhanden und verlangt Zugangsdaten)"
  echo -n "  GET  /api/v1/models  : "
  curl -s -o /dev/null -w '%{http_code}' --max-time 8 "$LOKAL/api/v1/models"
  echo

  echo
  echo "==> Nodes"
  docker exec -w /app -e PYTHONPATH=/app comesh-api python3 -c "
import sqlite3
c = sqlite3.connect('/data/gpu_pool.db'); c.row_factory = sqlite3.Row
for r in c.execute('select id,name,gpu_type,vram_gb,status,agent_version,connection_state from gpu_nodes'):
    d = dict(r)
    print('  id=%s %s | %s | %s GB | %s | Agent %s | %s' % (
        d['id'], d['name'], d['gpu_type'], d['vram_gb'], d['status'], d['agent_version'], d['connection_state']))
" 2>/dev/null || echo "  (Node-Tabelle nicht lesbar)"
}

if [ "$NUR_PRUEFEN" -eq 1 ]; then
  pruefen
  exit 0
fi

echo "==> Bauen (Tag $VERSION)"
if [ "$NUR_API" -eq 1 ]; then
  DIENSTE="api"
else
  DIENSTE="api frontend node-agent"
fi
docker compose build $DIENSTE || { echo "Build fehlgeschlagen" >&2; exit 1; }

echo
echo "==> Starten (--force-recreate)"
# Ohne --force-recreate bleibt ein Dienst stehen, dessen Image-Tag sich nicht geaendert hat -
# genau so lief der Agent sechs Tage mit einer Konfiguration ohne GPU-Zugriff weiter.
if [ "$NUR_API" -eq 1 ]; then
  docker compose up -d --no-deps --force-recreate api
else
  # Der Agent laeuft im Profil "node"; auf anderen Hosts bewusst nicht.
  # `ps -a`: ein Dienst in einer Neustart-Schleife gilt nicht als "running" und wurde so
  # uebersprungen - genau deshalb lief der Agent mit einem alten Abbild weiter.
  if docker compose ps -a --services 2>/dev/null | grep -qx node-agent; then
    docker compose up -d --no-deps --force-recreate api frontend node-agent
  else
    docker compose up -d --no-deps --force-recreate api frontend
  fi
fi

sleep 8
pruefen
