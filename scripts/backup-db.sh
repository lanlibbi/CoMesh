#!/bin/sh
# Sichert die CoMesh-Datenbank aus dem laufenden Container — geprüft, nicht nur kopiert.
#
# Warum nicht einfach die Datei kopieren: SQLite schreibt im WAL-Modus und kann mitten
# in einer Transaktion kopiert werden. `sqlite3.Connection.backup()` erzeugt dagegen
# eine konsistente Momentaufnahme, auch während geschrieben wird.
#
# Aufruf:   ./scripts/backup-db.sh
# Umgebung: COMESH_BACKUP_DIR   (Default ~/backups/comesh)
#           COMESH_BACKUP_KEEP_DAYS (Default 14)
#           COMESH_API_CONTAINER    (Default comesh-api)
set -eu

BACKUP_DIR="${COMESH_BACKUP_DIR:-$HOME/backups/comesh}"
KEEP_DAYS="${COMESH_BACKUP_KEEP_DAYS:-14}"
CONTAINER="${COMESH_API_CONTAINER:-comesh-api}"
STAMP=$(date +%Y%m%d-%H%M%S)
ZIEL="$BACKUP_DIR/gpu_pool-$STAMP.db"

mkdir -p "$BACKUP_DIR"

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
    echo "FEHLER: Container $CONTAINER läuft nicht — keine Sicherung möglich." >&2
    exit 1
fi

# 1. Konsistente Kopie innerhalb des Containers
docker exec "$CONTAINER" python3 -c "
import sqlite3
quelle = sqlite3.connect('/data/gpu_pool.db')
ziel = sqlite3.connect('/tmp/backup.db')
quelle.backup(ziel)
ziel.close()
quelle.close()
"

# 2. Herauskopieren
docker cp "$CONTAINER:/tmp/backup.db" "$ZIEL" >/dev/null
docker exec "$CONTAINER" rm -f /tmp/backup.db

# 3. Prüfen: Integrität und Inhalt. Eine Sicherung ohne Prüfung ist eine Behauptung.
python3 - "$ZIEL" <<'PY'
import sqlite3
import sys

pfad = sys.argv[1]
conn = sqlite3.connect(pfad)
integritaet = conn.execute("PRAGMA integrity_check").fetchone()[0]
tabellen = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
konten = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] if "users" in tabellen else -1
nodes = conn.execute("SELECT COUNT(*) FROM gpu_nodes").fetchone()[0] if "gpu_nodes" in tabellen else -1
conn.close()

if integritaet != "ok":
    sys.exit(f"FEHLER: Integritätsprüfung: {integritaet}")
if "users" not in tabellen:
    sys.exit("FEHLER: Tabelle users fehlt — das ist keine CoMesh-Datenbank")
print(f"  Integrität: ok · {len(tabellen)} Tabellen · {konten} Konten · {nodes} Nodes")
PY

# 4. Komprimieren und aufräumen
gzip -f "$ZIEL"
echo "  gesichert: $ZIEL.gz ($(du -h "$ZIEL.gz" | cut -f1))"

find "$BACKUP_DIR" -name 'gpu_pool-*.db.gz' -type f -mtime "+$KEEP_DAYS" -print -delete \
    | sed 's/^/  verworfen (älter als '"$KEEP_DAYS"' Tage): /'

echo "  Sicherungen insgesamt: $(find "$BACKUP_DIR" -name 'gpu_pool-*.db.gz' | wc -l)"
