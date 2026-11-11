# Vom POC zur Produktion — offene Punkte

**Stand 11.11.2026, Version 0.6.19.** Was erledigt ist, steht mit ✔ und dem Weg dorthin; was
offen bleibt, mit dem, was konkret fehlt. Reihenfolge nach Risiko, nicht nach Aufwand.

## Erledigt in 0.6.19

| Punkt | Wie |
|---|---|
| Datensicherung | `scripts/backup-db.sh` + `deploy/comesh-backup.{service,timer}`, täglich 03:20, 14 Tage Aufbewahrung, Wiederherstellung geübt (11 Konten, 140 Nutzungen, Integrität ok) |
| Rechtstexte | `/impressum`, `/datenschutz`, `/agb` aus der Umgebung (`legal.py`), fehlende Pflichtangaben werden auf der Seite angezeigt; in allen Fußzeilen verlinkt, viersprachig |
| Sicherheitsköpfe | HSTS, CSP, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy` in `frontend-alpine/security-headers.conf`, in **jedem** `location`-Block eingebunden |
| Healthchecks | API, nginx und Agent melden ihren Zustand (`healthy` gemessen) |
| Logrotation | `json-file`, 50 MB × 5 je Dienst |
| CORS | standardmäßig aus; `CORS_ORIGINS` nur bei fremder Web-Anwendung |
| Selbstregistrierung | `REGISTRATION_OPEN=0` schaltet sie ab |
| Agent-Version | eigene `AGENT_VERSION`, unabhängig von der Portal-Version; Vergleich „älter als", nicht „ungleich" |
| Abhängigkeiten | `pip-audit` in der CI (Bericht), Dependabot wöchentlich |

---

## P0 — vor dem ersten fremden Nutzer zu erledigen

### 1. Sicherung der Datenbank fehlt vollständig

`gpu_pool.db` liegt im Volume `comesh_sqlite_data` und enthält Konten, Schlüssel, Guthaben und
Node-Zustand. Auf dem Host gibt es **keinen Timer, keinen Cron, kein Skript** dafür (geprüft:
`systemctl list-timers`, `crontab -l`, kein `scripts/*backup*`).

Nötig: `sqlite3 /data/gpu_pool.db ".backup '/backup/gpu_pool-$(date +%F).db'"` als systemd-Timer,
Aufbewahrung (z. B. 14 Tage), **Restore einmal wirklich durchspielen**, und die Sicherung außer
Haus kopieren (das NAS ist vorhanden). Ohne Restore-Test ist eine Sicherung eine Behauptung.

### 2. Impressum, Datenschutzerklärung, AGB fehlen

Im Frontend existiert **keine** dieser Seiten und **kein Link** darauf (geprüft: `frontend-alpine/`
enthält weder `impressum*` noch `datenschutz*`; in `login.html`, `index.html`, `guide.html` kommt
das Wort nicht vor). Das Portal ist öffentlich erreichbar, verarbeitet personenbezogene Daten
(Mail, Guthaben, IP) und hat einen Zahlungsweg.

Nötig: Impressum (§ 5 DDG), Datenschutzerklärung (Art. 13 DSGVO, inklusive Auftragsverarbeitung
für Cloudflare und die eingesetzten Modellanbieter), Nutzungsbedingungen bei Credits, und die
Löschung/den Export von Kontodaten als Funktion — nicht nur als Zusage.

### 3. Keine Sicherheitsköpfe in nginx

`frontend-alpine/nginx.conf` setzt nur `Cache-Control`. Es fehlen `Strict-Transport-Security`,
`Content-Security-Policy`, `X-Content-Type-Options`, `Referrer-Policy` und
`Permissions-Policy`.

Die CSP ist der unangenehme Teil, weil die Seiten Alpine.js von `unpkg.com` laden und Google
Fonts einbinden — das gehört mit auf die Liste „externe Abhängigkeiten im Browser", sonst ist
jede CSP entweder wirkungslos oder kaputt.

### 4. Container laufen als root, ohne Healthcheck

Alle drei Images haben **kein `USER`** (geprüft in `Dockerfile`, `frontend-alpine/Dockerfile`,
`node-agent/Dockerfile`) und in `docker-compose.yml` steht **kein `healthcheck:`**. `restart:
unless-stopped` startet einen Container, der läuft aber nicht arbeitet, endlos neu.

Nötig: `USER` in allen drei Images, `healthcheck` gegen `/health` (API) bzw. `wget -q --spider`
(nginx), `depends_on: condition: service_healthy`.

### 5. Logs ohne Rotation

In `docker-compose.yml` ist **kein `logging:`** gesetzt. Damit schreibt Docker in `json-file` ohne
Begrenzung — bei einem 24/7-Dienst mit Zugriffsprotokoll füllt das irgendwann die Platte, und
zwar nachts.

Nötig: `logging: {driver: json-file, options: {max-size: "50m", max-file: "5"}}` je Dienst oder
ein zentraler Log-Treiber.

### 6. CORS steht offen

`main.py:146` — `allow_origins=["*"]`, im Kommentar selbst als „open for the POC" markiert.
Für eine öffentliche API mit Konten und Guthaben ist das zu weit.

### 7. Fehler sieht niemand

Es gibt kein Fehlertracking, keinen Uptime-Check von außen und keine Benachrichtigung bei
Ausfällen. Die einzigen „Alarme" (`alerts.py`) betreffen die Nachfrage nach Kapazität im
Marktplatz, nicht den Betrieb. Ein Ausfall wird derzeit gemeldet, indem jemand anruft.

Nötig (kleinster sinnvoller Schritt): ein externer Ping auf `/health` alle paar Minuten mit
Benachrichtigung, plus eine Prüfung „Festplatte > 85 %" und „letzter Node-Heartbeat älter als
5 Minuten".

---

## P1 — vor dem ersten zahlenden Kunden

### 8. Schemaänderungen passieren beim Start, nicht als Migration

15 Funktionen `_ensure_*` in `main.py` legen Spalten per `ALTER TABLE` an. Das funktioniert und
ist rückwärtskompatibel, hat aber keinen Rückweg: eine misslungene Änderung lässt sich nicht
zurückrollen, und es gibt keinen Stand, den man in einer älteren Version wiederherstellen kann.

Empfehlung: Alembic einführen, die bestehenden `_ensure_*` in eine Baseline-Migration überführen,
danach jede Änderung als Revision.

### 8a. Registrierung steht jedem offen

`register.html` ist ohne Einladung erreichbar; jedes neue Konto landet als `pending` in der
Freigabeliste und braucht einen Klick im Adminbereich. Für einen POC richtig, für eine öffentliche
Instanz zu offen: Wer die Adresse kennt, kann die Freigabeliste zumüllen, und jede Registrierung
kostet einen Verwaltungsschritt.

Nötig: eine der drei Varianten — Registrierung ganz abschaltbar (`REGISTRATION_OPEN=0`),
E-Mail-Bestätigung vor der Freigabe, oder Einladungscode. Die Admin-Freigabe bleibt in jedem Fall
bestehen.

### 9. SQLite und ein einzelner Worker sind die Skalierungsgrenze

`database.py` nutzt `sqlite:///…/gpu_pool.db`; `docker-compose.yml` hält ausdrücklich an einem
Uvicorn-Worker fest, weil die WebSocket-Registry und ausstehende Aufträge prozesslokal sind
(Kommentar im Compose-File). Das ist eine bewusste Entscheidung, aber sie ist die Obergrenze:
mehrere Worker brauchen Redis pub/sub, mehr Schreiber brauchen Postgres.

Für Produktion mit mehreren Providern: Postgres, Redis für die Registry, und ein Lasttest, der
belegt, wie viele gleichzeitige Anfragen bei welcher VRAM-Größe durchgehen. Diese Zahl gehört in
die README — „skaliert" ohne Messung ist eine Meinung.

### 10. Auslieferung ist Handarbeit

Es gibt kein `deploy/`-Verzeichnis, kein Release-Skript und keinen dokumentierten Rückweg. Jeder
Deploy läuft heute von Hand: Quelltext kopieren, Image bauen, Container neu erzeugen, `downloads/`
austauschen, Prüfsummen schreiben, Image neu bauen, Release anlegen. Genau deshalb gab es die
beiden Fehler der letzten Tage (`.sha256` mit Rechten 600, Images unter altem Tag gebaut).

Nötig: ein Skript `deploy.sh <version>`, das die Schritte in der richtigen Reihenfolge ausführt und
am Ende `/version`, `/health` und die Prüfsumme der Downloads vergleicht; Rollback = vorheriges
Image-Tag starten.

### 11. Geheimnisse haben kein Rotationsverfahren

`ADMIN_API_KEY`, `NODE_SHARED_SECRET`, `PAYPAL_*`, `STRIPE_*` liegen in `.env` (nicht versioniert,
gut). Es gibt aber kein Verfahren für den Fall, dass einer davon abfließt — der Fall ist am
02.11. schon einmal eingetreten (`NODE_API_KEY` stand in einer Sitzungsausgabe).

Nötig: dokumentierte Rotation je Schlüssel (Reihenfolge, was bricht, wie man prüft), und für
Node-Schlüssel das vorhandene `POST /nodes/{id}/rotate-key` als Standardweg.

### 12. Zahlungen sind implementiert, aber nicht abgesichert betrieben

PayPal und Stripe sind angebunden, `PAYMENTS_ALLOW_MOCK` ist im Compose-File auf `0` verdrahtet,
die IPN-Prüfung lehnt ohne Empfängeradresse ab (fail closed) — das ist solide. Offen sind:
Abgleich Laufzeit ↔ Abrechnung (Reconciliation), Umgang mit Rückbuchungen, und die Frage, wer
Rechnungen mit ausgewiesener Umsatzsteuer erzeugt.

### 13. Keine Prüfung der Abhängigkeiten auf bekannte Lücken

Pakete sind gepinnt, aber es läuft kein `pip-audit`, kein Dependabot/Renovate und kein
Image-Scan. Ein gepinntes Paket ist nicht automatisch ein sicheres Paket.

---

## P2 — danach, in beliebiger Reihenfolge

14. **Browser-Abhängigkeiten lokal ausliefern.** Alpine.js kommt von `unpkg.com`, Schriften von
    `fonts.googleapis.com`. Beides ist ein Datenschutzthema (IP an Dritte) und ein
    Verfügbarkeitsrisiko — und blockiert eine saubere CSP.
15. **Metriken.** Bisher gibt es `/health` und Logzeilen; Zahlen zu Latenz, Token-Durchsatz und
    Fehlerquote je Modell fehlen.
16. **Repo-Hygiene.** 29 `*.bak-*`-Dateien sind versioniert. Weg damit, die Historie hat sie
    ohnehin.
17. **Auffindbarkeit.** Startseite hat keine `meta description`, keine Open-Graph-Tags, keine
    echte `sitemap.xml` (die ausgelieferte ist der SPA-Fallback).
18. **Statusseite und Wartungsfenster.** Wer Credits verkauft, sollte Ausfälle kommunizieren
    können, ohne eine Mail zu schreiben.
19. **Barrierefreiheit.** Kontrast ist geprüft (die Prüfer melden WCAG AA), Tastaturbedienung und
    Fokusführung der Ausklappbereiche sind es nicht.

---

## Was diese Liste nicht ist

Sie ersetzt keine Rechtsberatung und keinen Pentest. Punkt 2 und 12 gehören zu jemandem, der
dafür haftet; Punkt 1, 3, 4, 5, 6 und 7 sind Handwerk und in wenigen Stunden erledigt.
