# Changelog

## 0.6.3 — 2026-10-22

**Registrierung wartet wieder auf Freigabe**
- Der Register-Endpunkt setzte `registration_status = "approved"` und `is_active = True` fest und
  stellte sofort einen API-Schlüssel aus. Ein neues Konto war damit ohne Zutun eines Administrators
  benutzbar — die Freigabe, die es in der Oberfläche längst gibt, wurde vom Server übersprungen.
- Neue Konten entstehen jetzt als `pending`, inaktiv und **ohne** Schlüssel. Startguthaben bucht der
  Freigabe-Pfad (nicht mehr doppelt: einmal bei der Registrierung, einmal bei der Freigabe).
- `resolve_token` weist nicht freigegebene Konten mit **403** ab. Vorher prüfte nur der Login den
  Status — ein Konto mit ausgestelltem Schlüssel kam über die API weiter durch.
- Der Hinweis „Registrierung eingereicht" ist ein Übersetzungsschlüssel in vier Sprachen.

## 0.6.2 — 2026-10-21

**Cloud-Modelle nur mit Provider-Freigabe**
- `allow_cloud` am Konto schaltete bisher **alle** Cloud-Modelle des Katalogs frei — auch solche, die
  kein Provider angeboten hatte. Jetzt gilt: nutzbar ist ein Cloud-Modell nur, wenn das Konto es
  erlaubt **und** ein aktiver Node es in `gpu_nodes.allowed_models` führt. `None` beim Node bedeutet
  weiterhin „alle lokalen, keine Cloud".
- `GET /v1/models` filtert entsprechend; was niemand anbietet, taucht auch bei gesetztem Cloud-Häkchen
  nicht auf.
- `docs/api.md` beschreibt die doppelte Freigabe.

## 0.6.1 — 2026-10-21

**Consumer sehen nur noch ausdrücklich freigegebene Modelle**
- `allowed_models = NULL` heißt für ein **Consumer**-Konto jetzt „nichts freigegeben" statt „alle
  lokalen Modelle". Ein Consumer sah bisher acht lokale Modelle, ohne dass jemand sie freigegeben
  hätte — im Chat und in jedem Client. Für **provider/both/admin** bleibt `NULL` = „alle lokalen".
- Der Administrator gibt einem Consumer die lokalen Modelle mit einem Klick frei: Admin-Oberfläche →
  Freigaben → **Modelle** → „Alle lokalen freigeben" (schreibt die Liste ausdrücklich ins Konto).
- Das Profil zeigt Consumer-Konten den Hinweis „Dir sind derzeit keine Modelle freigegeben" auch
  dann, wenn gar keine Liste hinterlegt ist.
- `docs/api.md` beschreibt die Regel jetzt als Tabelle nach Rolle.

## 0.6.0 — 2026-10-21

**Modelle, Freigaben und Schlüssel**
- `GET /v1/models` liefert das **OpenAI-Format** (`object`/`data`/`created`/`owned_by`) und
  filtert nach der Freigabe des Kontos. Vorher kam Ollamas Rohformat zurück — externe Clients
  sahen null Modelle —, und die Auswahl enthielt Modelle, die beim Aufruf mit 403 scheiterten.
  Die rohe Liste bleibt zusätzlich als `models[]` erhalten, weil die Chat-Seite sie liest.
- **Neue Spalte `users.allow_cloud`**: Cloud-Modelle werden getrennt von der Freigabeliste
  zugeschaltet. Damit überschreibt ein „Cloud erlauben" des Kontos keine gezielte Freigabe mehr.
  Migration läuft idempotent beim Start.
- `POST /v1/me/keys` stellt einen eigenen API-Schlüssel aus (Passwort bestätigt, einmal
  sichtbar); frühere `gpu_`-Schlüssel des Kontos werden ungültig, Sitzungsmarken bleiben gültig.
  `GET /v1/me/keys` listet Präfixe und Datum.
- `PUT /v1/me/allowed-models` nimmt von einem **Consumer** nur noch das Cloud-Kennzeichen an;
  Modelle auswählen bleibt Provider und „beides" vorbehalten.

**Öffentlicher Zugang**
- Die Oberfläche reicht `/v1/` an die API durch (`proxy_buffering off` für Streaming). Damit
  funktioniert ein OpenAI-kompatibler Client unter derselben Adresse wie das Portal, ohne Port.

**Oberfläche**
- Einsteiger-Anleitung `/hilfe.html` in allen vier Sprachen, Knopf im Kopf statt im Menü.
- Anmeldeseite: Mesh-Szene als Hintergrund, Glaskarte, Fußzeile mit Zustandsanzeige der API.
- Profil: Consumer sehen die Liste der verfügbaren Modelle und dürfen Cloud-Modelle selbst
  erlauben (mit Bestätigung); die Modellauswahl bleibt bei Provider/both.
- Dashboard zeigt einen API-Schlüssel nur noch, wenn es wirklich einer ist (`gpu_…`), und nennt
  das Konto, zu dem er gehört.

**Behoben**
- Die Modellliste zeigte die Browser-Sitzung (`sess_…`) als API-Schlüssel an, „Neu ausstellen"
  machte in Wahrheit einen neuen Login.
- Ein Konto mit leerer Freigabeliste (`[]` = nichts erlaubt) blieb stumm ohne Hinweis; die
  Oberfläche sagt es jetzt.
- `brand-mesh` ließ den Zeichenpuffer auf 300×150 stehen, wenn die Fläche längst größer war.

Alle nennenswerten Änderungen. Versionierung ab 18.10.2026 einheitlich für Portal
und Node-Agent; vorher liefen die Komponenten auseinander (Portal 0.3.0, Agent 0.1.0,
einziger Git-Tag `v0.1.0`).

## 0.5.0 — 2026-10-18

**Streaming (SSE)**
- `POST /v1/chat/completions` mit `stream: true` liefert jetzt echtes
  `text/event-stream` statt einer kompletten JSON-Antwort. Damit überlebt eine lange
  Antwort einen Cloudflare-Tunnel (der kappt sonst bei rund 100 s mit 524).
- Der Node-Agent streamt auf seinem HTTP-Endpunkt für beide Backends: `BACKEND=ollama`
  übersetzt Ollamas NDJSON in OpenAI-Rahmen, `BACKEND=openai` reicht die SSE-Zeilen des
  Backends unverändert weiter. LM-Studio-Provider streamen damit ebenfalls.
- Der Portal-Weg zum Agenten streamt mit (`_forward_to_node_stream`), Nutzung und
  Buchhaltung werden aus dem Schluss-Rahmen übernommen.
- Nicht-streamende Anfragen bleiben unverändert.

**Nebenbei repariert**
- `admin.py`: neun Log-Zeilen nutzten verschachtelte Anführungszeichen in f-Strings —
  das ist erst ab Python 3.12 gültig, das Image läuft mit 3.11. Beim ersten Neubau
  brach der Start mit `SyntaxError`.
- Migration ergänzt: `api_keys.token_type`, `api_keys.expires_at` und
  `gpu_nodes.api_key_hash` fehlten in der laufenden Datenbank (die Auth-Härtung war
  nie migriert worden). Jede Abfrage auf `ApiKey` scheiterte mit „no such column".
  `_ensure_api_key_and_node_columns()` rüstet das beim Start idempotent nach.

## 0.4.0 — 2026-10-18

**Adminbereich**
- Freigabe-Oberfläche (`admin-registrations.html`): Registrierungen freigeben und
  ablehnen, Statusfilter, Suche, Blättern, Konto anlegen, Rolle vergeben,
  Passwort setzen, Credits buchen, Schlüssel ausstellen, Konto deaktivieren.
- Protokoll (`admin-audit.html`) und neuer Endpunkt `GET /admin/audit` — die Tabelle
  `admin_audit_log` war bisher nur schreibend genutzt.
- `PATCH /admin/users/{id}` kann jetzt ein Passwort setzen; Passwortwerte werden im
  Protokoll redigiert.
- Schutz vor Aussperrung in der API: ein Admin kann sich weder degradieren noch
  deaktivieren (409). `PUT /v1/me/role` lehnt Admins ebenfalls ab, damit ein
  Profil-Speichern die Rechte nicht löscht.

**Oberfläche**
- Neue Marke (Mesh-Zelle), größere Kopfzeile, Theme-Knopf und Sprachschalter in einer
  ruhigen Form, kleine Canvas-Animation im Kopf (`brand-mesh.js`).
- Fehler behoben: Filter „Alle" schickte `status=Alle` (422), `--brass-grad-2` fehlte
  (Messing-Zahlen unsichtbar), drei Aufrufe in `admin-usage.js` liefen ohne `auth`.

**Betrieb**
- `ADMIN_API_KEY` nicht mehr im Klartext in `docker-compose.yml`, sondern in `.env`
  (600, ignoriert). Schlüssel rotiert.
- Datenbank aufgeräumt: 38 Testkonten mit 44 Schlüsseln, 51 Buchungen und 16 Geräten
  entfernt (Sicherung und JSON-Export in `/data/aufraeumen/`).

## 0.3.0 — 2026-10-11

- Rolle `admin` und rollen-geprüfte `/admin`-Endpunkte (Nutzer, Geräte, Verbrauch).
- Admin-Bootstrap über `ADMIN_API_KEY` / `ADMIN_EMAIL`.
- Verbrauchs-Dashboard (`usage_stats.py`), Admin-Sicht über alle Konten.
- Rebrand GPU-Pool → CoMesh in der ausgelieferten Oberfläche.

## 0.2.0

- Chat über WebSocket (`/ws/chat`) als tunnel-fester Weg neben HTTP.
- Node-Agent: Reconnect abgesichert, Bulk-Bearbeitung im Gerätebestand.
- Auth-Hardening: opake Token statt JWT, Rollen statt Freitext.

## 0.1.0

- Erste lauffähige POC: Portal, Node-Agents, Lastverteilung, Credits.
