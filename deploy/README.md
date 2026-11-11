# Betrieb auf dem Host

## Datensicherung

`scripts/backup-db.sh` sichert die SQLite-Datenbank als konsistente Momentaufnahme
(`sqlite3.Connection.backup`) aus dem laufenden Container, prüft die Integrität und die
Zahl der Konten, komprimiert und verwirft Sicherungen, die älter als 14 Tage sind.

**Als Benutzerdienst (funktioniert ohne root):**

```bash
mkdir -p ~/.config/systemd/user
cp deploy/comesh-backup.service deploy/comesh-backup.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now comesh-backup.timer
systemctl --user list-timers comesh-backup.timer
```

Benutzerdienste laufen nur, solange eine Sitzung offen ist — es sei denn, es ist
`loginctl enable-linger <benutzer>` gesetzt. Für einen Dienst, der auch nach einem
Neustart ohne Anmeldung sichern soll, die beiden Dateien nach `/etc/systemd/system/`
legen (dort `%h` durch den absoluten Pfad ersetzen) und `systemctl enable --now
comesh-backup.timer` ausführen — das braucht root.

**Wiederherstellen (einmal geübt, nicht nur geplant):**

```bash
gunzip -c ~/backups/comesh/gpu_pool-<stempel>.db.gz > /tmp/restore.db
docker run --rm -v /tmp:/in -e DATA_DIR=/data comesh-api:<version> \
  sh -c 'cp /in/restore.db /data/gpu_pool.db && python3 -c "import sqlite3;print(sqlite3.connect(\"/data/gpu_pool.db\").execute(\"select count(*) from users\").fetchone())"'
```

Im Ernstfall: Container stoppen, Volume-Datei ersetzen (`docker cp` in einen
Hilfscontainer mit demselben Volume), Container starten, `/health` prüfen.
