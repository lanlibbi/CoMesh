# Changelog

## 0.6.11 — 2026-11-04

**Konten löschen, Sprachauswahl reparieren, Modellfreigabe zum Provider, echte
Lastverteilung**

1. **`DELETE /admin/users/{id}`** — bisher mussten Testkonten direkt in der DB
   entfernt werden. Der Endpunkt entscheidet **je Tabelle**, statt eine Kaskade
   laufen zu lassen: `api_keys` (auch `sess_…`) werden gelöscht, `node_earnings`,
   `pool_jobs`, `usages`, `credit_transactions` und `payments` auf ein
   Platzhalterkonto umgehängt (die **Einnahmen der Node bleiben**), eine Node
   **mit** Umsatz wird stillgelegt (`is_enabled=false`, Agent-Schlüssel weg) und
   behalten, eine Node **ohne** Umsatz verschwindet mit. `db.delete(user)` wäre
   hier falsch: `User.nodes` hat `cascade="all, delete-orphan"` und nähme die
   Einnahmen mit — und die Datenbank erzwingt keine Fremdschlüssel, verwaiste
   Zeilen fielen also still auf. Sperren: eigenes Konto und letzter Admin (409).
   In der Kontenliste ein Knopf mit zwei Rückfragen, die den Bestand nennen
   („1 Schlüssel entfernt", „Nodes mit Einnahmen behalten: 7").

2. **Sprachauswahl war unlesbar.** Das Menü öffnet nach unten in die
   Navigationszeile; beide Kopfzeilen sind `.shell` mit `z-index: 1`, also
   gewann die **spätere** Zeile — die ersten beiden Einträge (EN, **DE**) lagen
   unter den Navigationslinks, waren nicht anklickbar und sahen „transparent"
   aus. `elementFromPoint` traf dort `NAV.nav` statt des Menüpunkts. Die obere
   Zeile liegt jetzt davor (`z-index: 3`). Dazu `option`-Farben explizit in
   beiden Designs (`color-scheme` je Theme, `background-color: var(--bg-deep)`,
   `color: var(--text)`; 16,4:1 dunkel, 15,5:1 hell) — die ausgeklappte Liste
   eines `<select>` ist ein Fenster des Betriebssystems und erbt nicht
   zuverlässig. Gilt für alle sechs `<select>` im Projekt.

   **Zweiter Fehler im selben Bild:** die Navigation trug ihren Text als
   Literal (`label: "Mein Verbrauch"`) und überschrieb damit `I18n.t(labelKey)`
   — sie blieb in jeder Sprache deutsch, der Gruß im Dashboard ebenfalls. Jetzt
   eigene Schlüssel je Eintrag, und `I18n.set()` baut die Seite neu auf, weil
   JS-gebaute Texte von `data-i18n` nicht erfasst werden.

3. **Modellfreigabe gehört dem Provider.** `PUT /nodes/{id}` ist für den
   Eigentümer **und** die Administration offen (vorher kam der Admin mit 404
   nicht durch, der Besitzer schon). Neu an der Geräteseite: ein Freitextfeld
   für die Modelle der eigenen Maschine (Komma oder Zeile), `clear_allowed_models`
   für „alle lokalen" (`NULL`), und der Hinweis, dass die Kästchenliste darunter
   der Katalog des **Portal-Hosts** ist. `[]` = nichts, `NULL` = alle lokalen.
   Rechte bleiben auf die eine Node beschränkt: `owner_id` ist kein Feld der
   Anfrage, Freischalten/Löschen/Schlüssel haben eigene Endpunkte.

4. **Lastverteilung — vorher gab es keine.** `find_best_node` sortierte nur nach
   Score (`hourly_rate + 0,5·utilization`); bei zwei gleichwertigen Nodes mit
   demselben Modell gewann immer dieselbe. Gemessen an zwei Wegwerf-Agenten:
   alt 6/6 Anfragen auf Node 1, zwei gleichzeitige ebenfalls beide auf Node 1.
   Jetzt zählt `pool.node_inflight` die laufenden Anfragen je Node (Erhöhen vor
   der Weiterleitung, `finally` verringert — Erfolg, Fehler, Timeout, Abbruch),
   die Auswahl nimmt **wenigste laufende Anfragen → Score → reihum**. Neu
   gemessen: 3/3 abwechselnd, zwei gleichzeitige je eine Node. Der Zähler lebt
   im Prozess (passend zu `--workers 1`) und hinterlässt bei Fehlern nichts.

5. **`HEARTBEAT_INTERVAL_SECONDS` entfernt.** Die Variable stand nur in
   `docs/portal.md` und in einem Beispiel-Compose; kein Code liest sie. Das
   Intervall setzt der Agent (`HEARTBEAT_SEC` 30 s, `WS_HEARTBEAT_SEC` 15 s),
   das Portal zählt nur die Gegenrichtung (90 s ohne Lebenszeichen → offline).

## 0.6.10 — 2026-11-04

**Node-Agent: Zugangssperre, WebSocket-Betrieb, ein Befehl zur Installation**

Diese Fassung schließt die Lücke, die eine Node bisher zu einem offenen Modell-Proxy
machte, und bringt den Agenten überallhin, wo ein Rechner steht — ohne Docker, ohne
Python, ohne offenen Port.

1. **Zugangssperre am Agenten (`NODE_SHARED_SECRET`).** Der Agent nahm jeden
   Chat-Aufruf ohne Schlüssel an und reichte ihn an das lokale Backend weiter;
   `/health` verriet unangemeldet Node-Id, GPU und Speicher. Ohne NVML-Absicherung war
   nur die Bindung an die Tailscale-Adresse der Schutz. Jetzt verlangt **jeder**
   Endpunkt außer `/health` den Kopf `X-Node-Secret`; das Portal schickt ihn aus
   `pool.node_request_headers()`. Fehlt die Variable, bleibt der Agent offen und warnt
   beim Start — das ist der Rückweg, nicht der Normalzustand.

2. **WebSocket-Betrieb repariert.** Im WS-Modus fiel eine verbundene Node nach 90 s aus
   dem Routing, obwohl die Verbindung stand: die Online-Regel las nur `last_seen`, nicht
   `last_ws_seen`. `GpuNode.ws_is_alive()` (offene Verbindung **und** Ping innerhalb von
   90 s) ist jetzt in allen drei `_is_online`-Varianten (pool, nodes, admin) verankert,
   der Ping schreibt zusätzlich `status`/`last_seen`. Damit verbindet eine Node
   **ausgehend** und braucht keinen eingehenden Port mehr. `_authenticate_node` prüft
   dabei `api_key_hash` (SHA-256) statt der Klartextspalte.

3. **macOS/Apple Silicon: VRAM-Übersteuerung (`NODE_VRAM_GB`).** Ohne NVML meldete der
   Agent 0 GB, die Registrierung machte `max(1, …)` daraus, und das VRAM-Gate verwarf
   die Node still (4,0 GB bei `*:8b`): online, aber dauerhaft auftragslos.
   `NODE_VRAM_GB` setzt den Wert von Hand (Unified Memory), `gpu_nodes.vram_source`
   sagt, woher er kommt (`detected` | `override` | `assumed`), und ein Heartbeat mit
   `override` korrigiert den Portalwert selbst.

4. **Ein-Befehl-Installer für Linux, macOS und Windows** (`node-agent/install.sh`,
   `install.ps1`). Holt das Binary von `<portal>/downloads/`, prüft die SHA-256 aus der
   `.sha256` daneben (ohne Prüfsumme kein Install), fragt den Account-Schlüssel verdeckt
   ab, setzt `AGENT_TRANSPORT=ws` als Vorgabe und richtet den Dienst ein — launchd,
   `systemd --user` oder `schtasks /SC ONLOGON`, alles ohne sudo.

5. **Binaries für Linux x86_64, Windows x86_64 und macOS arm64.** PyInstaller-Builds
   mit der `VERSION`-Datei im Bundle, `--version` geprüft, `.sha256` daneben. Das
   Darwin-Binary entsteht in GitHub Actions auf `macos-latest`, nicht auf einem Mac.

6. **`/downloads` ohne SPA-Fallback.** `try_files $uri $uri/ /index.html` antwortete für
   eine fehlende Datei mit **200 und HTML**; `install.sh` holt mit `curl -fsSL`, sah 200
   und meldete dann „die Datei …sha256 enthält keine gültige SHA-256-Summe (gelesen:
   `<!doctype html>`)" — der Fehler sah nach einem Installer-Problem aus. Jetzt gibt es
   einen eigenen Block `location /downloads/ { try_files $uri =404; }` **vor**
   `location /`: eine fehlende Datei antwortet 404, der Installer sagt
   „Download fehlgeschlagen".

**Nebenbefund behoben:** Der Agent meldete im FastAPI-Titel hart `0.6.0`, während
`/version` längst 0.6.9 sagte — das Image kopierte die `VERSION`-Datei nicht mit. Der
Agent liest sie jetzt aus dem Image (`COPY VERSION`), der Build-Kontext ist die
Repo-Wurzel, und auch die FastAPI-Kennung des Portals kommt aus `VERSION` statt aus
einer zweiten Konstante. Der Ersatzwert ist `0.0.0`: fehlt die Datei, sieht man das,
statt eine alte Nummer zu lesen.

## Sicherheitsfix — 2026-11-03

**Veröffentlichte Ports liegen per Default nur noch auf 127.0.0.1**

`docker-compose.yml` veröffentlichte 8767 (Oberfläche) und 8765 (API) auf allen
Schnittstellen. Wer den Port direkt erreichte, sprach mit dem Portal an Cloudflare
vorbei — an TLS, Ratenlimit und Zugriffsregeln des Tunnels vorbei. Für eine frische
Installation ohne Tunnel war das nur eine offene Tür ohne Nutzen.

Beide Bindungen stehen jetzt hinter einer Variablen, Vorgabe `127.0.0.1`:

| Variable | Port | Vorgabe |
|---|---|---|
| `COMESH_BIND_ADDRESS` | 8767 → 80 (Oberfläche) | `127.0.0.1` |
| `COMESH_API_BIND_ADDRESS` | 8765 → 8000 (API) | `127.0.0.1` |

Wer von außen zugreifen will (Cloudflare-Tunnel, Reverse Proxy auf demselben Host),
setzt `COMESH_BIND_ADDRESS=0.0.0.0` **vor** dem Neuerzeugen der Container. Die API
braucht das nur, wenn Clients oder ein Node-Agent auf anderen Rechnern sie direkt
ansprechen; nginx und der Agent auf dem Portal-Host gehen über das Compose-Netz
(`http://api:8000`).

**Gemessen auf der laufenden Instanz:** mit `COMESH_BIND_ADDRESS=0.0.0.0` und
`COMESH_API_BIND_ADDRESS=127.0.0.1` in der `.env` zeigt `docker ps`
`0.0.0.0:8767->80/tcp` und `127.0.0.1:8765->8000/tcp`; Oberfläche und API antworten
über den Tunnel (HTTP 200), `192.168.2.187:8765` ist von außen nicht mehr
erreichbar. Ein `docker compose config` ohne `.env` in einem leeren Verzeichnis
zeigt für beide Ports `host_ip: 127.0.0.1`.

## Sicherheitsfix — 2026-11-02

**Zwei offene Türen: globale Login-Sperre und ungeprüfte PayPal-IPN**

1. **Die Sperre sperrte alle aus.** Hinter Cloudflare ist `$remote_addr` in nginx die Adresse des
   Docker-Gateways (gemessen: 172.31.0.1), die Anwendung sah zusätzlich nur den nginx-Container
   (172.31.0.3). Alle Benutzer teilten damit einen Zähler — fünf Fehlversuche sperrten die ganze
   Installation. nginx wertet jetzt `CF-Connecting-IP` über das `real_ip`-Modul aus, aber nur von
   `172.31.0.0/16` und `127.0.0.1`; aus LAN oder Tailnet bleibt die Verbindungsadresse maßgeblich,
   ein gefälschter Header wird ignoriert. `X-Forwarded-For` wird überschrieben statt fortgeschrieben.
   Die Anwendung nimmt `X-Real-IP` (das nginx immer selbst setzt) nur, wenn der TCP-Peer ein
   vertrauenswürdiger Proxy ist (`TRUST_PROXY_HEADERS=1`, `TRUSTED_PROXY_NETS`).

2. **Kostenloses Guthaben über die PayPal-IPN.** `/payments/paypal/ipn` schrieb bei
   `payment_status=Completed` Guthaben gut, ohne PayPal zu fragen. Jetzt geht der **Rohtext** der
   Meldung unverändert mit `cmd=_notify-validate` an PayPal; nur `VERIFIED` wird akzeptiert.
   Zusätzlich müssen `payment_status`, Empfänger (`PAYPAL_RECEIVER_EMAIL`), Betrag und Währung
   passen, und `txn_id` schreibt über `payments.provider_event_id` (Unique-Index) nur einmal gut.
   Die vier weiteren Gutschrift-Pfade (`stripe/success`, `alipay/success`, `applepay/success`,
   `stripe/simulate-success`) fragen jetzt bei Stripe nach bzw. sind nur mit
   `PAYMENTS_ALLOW_MOCK=1` erreichbar; der Mock-Webhook ebenso. `_fulfill_payment` lehnt
   abgebrochene und fehlgeschlagene Aufträge ab.

**Gemessen:** Fünf Fehlversuche von 203.0.113.10 sperren nur diese Adresse (429 mit
`Retry-After: 216`), ein Login von 198.51.100.20 geht weiter (401) — Log:
`login blocked by lockout: key=login:ip:203.0.113.10`. Ein gefälschter IPN gegen die laufende
Instanz ergab HTTP 400 (`IPN verification failed`), PayPals Sandbox antwortete `INVALID`,
Guthaben und Zahlungstabelle blieben unverändert.

## 0.6.9 — 2026-10-24

**Werkzeugaufrufe: `tools` rein, `tool_calls` raus**

Ein Agent konnte über CoMesh bisher nicht arbeiten — nicht wegen des Modells, sondern weil
`tools` und `tool_choice` im Code **nirgends** vorkamen. Der Endpunkt nahm sie entgegen, verwarf sie
stillschweigend, und `tool_calls` aus der Antwort ebenso. `qwen3.8:latest` (27,3B) liefert direkt gegen
Ollama saubere Aufrufe; über den Pool antwortete dasselbe Modell „I don't have that tool".

Geändert an vier Stellen, jede mit eigener Verantwortung:

- **`main.py`** — `ChatMessage` trägt `tool_calls`, `tool_call_id` und `name`; `content` darf fehlen
  (eine Assistenten-Nachricht, die nur aufruft, hat keinen Text). `ChatCompletionRequest` nimmt
  `tools` und `tool_choice` an, `_bau_ollama_payload()` gibt beides weiter und lässt `content: null`
  weg. Die Antwort führt `tool_calls` mit.
- **`pool.py`** — `_ollama_to_openai_shape()` reicht `tool_calls` durch, `_forward_to_node()` schickt
  die Werkzeuge an den Node und nimmt die Aufrufe zurück.
- **`node-agent/agent.py`** — beide Backends (`ollama`, `openai`) geben Werkzeuge weiter und
  Werkzeugaufrufe zurück.
- **`finish_reason`**: liegt ein Aufruf vor, meldet die Antwort `tool_calls`, nicht `stop`. Ollama
  sagt `done_reason: "stop"`, weil aus seiner Sicht die Antwort fertig ist — Clients entscheiden aber
  an `finish_reason == "tool_calls"`. Der Test hat genau das aufgedeckt: erst war der Code zu
  nachgiebig, angepasst wurde der Code, nicht der Test.
- **Zeitlimits** gegen den 502 beim Kaltstart: Pool 120 → 300 s, Agent 180 → 300 s, nginx 180 → 600 s.
  Ein 27B-Modell braucht beim ersten Aufruf Minuten, bis es geladen ist.

**Gemessen über den öffentlichen Weg** (`/api/v1/chat/completions`):

| Fall | Ergebnis |
| --- | --- |
| `llama3.1:8b`, ohne Werkzeuge | `finish_reason: stop`, Text „Ok." — keine Regression |
| `qwen3.8:latest`, mit `tools` | **`finish_reason: tool_calls`**, ein Aufruf `write_file`, Argumente `{"path":"hello.py","content":"def add(a, b):…"}`, 375 Token in 28 s |

Tests: 72 grün (6 neue in `tests/test_tool_calls.py`).

## 0.6.8 — 2026-10-23

**Richtige Pfade für Agenten — und die Falle dabei**

- Die Dokumentation und `scripts/agent-report.sh` sprachen von `/v1/admin/…`. Das ist falsch: die
  Administration liegt unter **`/api/admin/…`**, die Mandanten-API unter **`/api/v1/…`**.
- **`/admin/…` ohne `/api`** liefert die HTML-Oberfläche mit **Status 200** — kein Fehler, kein JSON.
  Ein Agent, der nur den Statuscode prüft, hält das für Erfolg und bekommt still keine Daten. Beide
  Stellen warnen jetzt davor; das Skript bricht bei `--fail-with-body` laut ab, statt leere Dateien
  zu erzeugen.
- Nachgewiesen über den öffentlichen Namen: `/admin/whoami` → HTML, `/api/admin/whoami` → JSON,
  `/v1/admin/whoami` → 404. `usage/export.csv` über `/api/admin/` liefert 412 Bytes, das Protokoll
  4249 Bytes.

## 0.6.7 — 2026-10-23

**Agenten-Konto und Berichte**

- **`docs/agent-api.md`**: wie ein Agent Zugang bekommt (eigenes Konto mit Rolle `admin`, Schlüssel im
  Profil), was es tun kann — Freigaben, Konten, Modelle, Guthaben, Geräte, Berichte, Protokoll — und
  was ausdrücklich **nicht** (kein Zugriff auf den Quellbaum, keine Schema-Änderung, Protokoll nur
  lesbar, ein Administrator kann sich nicht selbst aussperren). Dazu die Fehlerbilder 401/403/409/422.
- **`GET /admin/usage/export.csv?window=…`** — Verbrauch aller Konten als CSV, Semikolon als Trenner
  und Komma als Dezimalzeichen, mit BOM damit Excel Umlaute richtig liest.
- **`GET /admin/audit/export.csv?limit=…`** — Protokoll als CSV, für Berichte „wer hat was freigegeben".
- **`scripts/agent-report.sh <portal> <schlüsseldatei> [fenster]`** — holt beide CSVs und zeigt vorher
  das angemeldete Konto und die ausstehenden Freigaben. Der Schlüssel wird nur aus einer Datei
  gelesen, nie als Argument.
- **Chat: mehrere Unterhaltungen parallel** (aus 0.6.6 nachgezogen, siehe Commit `ed6093e`).

**Gemessen:** `usage/export.csv?window=7d` liefert 3 Datenzeilen mit den Spalten
Konto;Name;Rolle;Status;Token;Anfragen;Modelle;Credits;Quota;Zuletzt, `audit/export.csv?limit=200`
27 Zeilen; beide antworten ohne Schlüssel mit 401.

**Fehler beim Bauen gefunden:** der erste Anlauf des Verbrauch-Exports endete in einem 500er —
`build_admin_usage` gibt ein pydantic-Objekt zurück, kein `dict`, `.get("users")` scheiterte an
`AttributeError`. Behoben, bevor jemand den Endpunkt benutzt hat.

## 0.6.6 — 2026-10-23

**E-Mail-Benachrichtigung bei ausstehender Freigabe, SMTP in der Datenbank**

- Neue Seite auf **Konten**: SMTP-Server, Port, Sicherheitsstufe (STARTTLS/SSL/ohne), Benutzer,
  Kennwort, Absender und Empfänger — aufklappbar, damit die Freigabeliste nicht darunter leidet.
  Dazu **Testmail senden** mit Klartext-Fehler, wenn der Server nicht antwortet.
- Die Einstellungen liegen als Schlüssel/Werte in `system_settings` (dieselbe Tabelle wie
  `credits_enabled`), nicht in der `.env` — pflegbar ohne Serverzugriff. Das Kennwort wird
  gespeichert, aber **nie** über die API zurückgegeben; gelesen wird nur `password_set`. Ein leeres
  Feld beim Speichern lässt das hinterlegte Kennwort stehen.
- Meldet sich jemand an, geht eine Nachricht an die eingetragene Adresse — in einem eigenen Thread.
  Eine Anmeldung wartet nie auf einen fremden Mailserver und scheitert nie an ihm.
- `mailer.py` nutzt `smtplib` aus der Standardbibliothek; keine neue Abhängigkeit, kein extra Container.

**Gemessen:** Lesen liefert Vorgaben ohne Kennwort; Schreiben setzt Server und Empfänger, `password_set`
wird `true`, das Kennwort kommt nicht zurück; die Testmail gegen einen unerreichbaren Server antwortet
HTTP 200 mit `ok: false` und `gaierror: Name or service not known`; eine Registrierung bei aktiver
Benachrichtigung landet weiter als `pending` und scheitert nicht.

## 0.6.5 — 2026-10-23

**Anpassungsliste aus dem Betrieb, Teil eins**

- **Profil: der Haken „Cloud-Modelle erlauben" blieb nicht gesetzt.** `loadMe()` leitete ihn aus der
  Modellliste ab — und zwar bevor `availableModels` geladen war. `isCloud()` fand deshalb nie etwas,
  der Haken sprang immer auf false. Jetzt zählt `allow_cloud` aus der Antwort des Servers.
- **Menüpunkt „Freigaben" heißt „Konten"** (die Seite selbst hieß schon „Konten und Freigaben").
- **Chat: Enter senden ist wählbar.** Ein Kästchen unter dem Eingabefeld schaltet zwischen „Enter
  sendet" und „Strg+Enter sendet, Enter bricht um"; die Wahl bleibt in `localStorage`.
- **Verbrauch (alle): die Kontenliste ist sortierbar** — Klick auf die Spaltenüberschrift, zweiter
  Klick dreht die Richtung. Sortiert wird im Browser, die API bleibt unverändert.
- **Geräte: Agentenadressen sind maskiert** (`http://••••••••:11435`), ein Knopf im Kopf blendet sie ein.
- **Geräte: Besitzer anonymisierbar, Betriebsart wählbar.** Zwei neue Spalten an `gpu_nodes`
  (Migration `_ensure_node_privacy_columns`): `hide_owner` blendet den Besitzer im Adminbereich aus
  (serverseitig, `owner_email` kommt dann gar nicht erst mit), `availability` unterscheidet
  `always` (Dauerbetrieb) und `partial` (nur zeitweise). Der Provider setzt beides direkt an seinem
  Gerät; die Betriebsart steht zusätzlich im öffentlichen Knotenkatalog.
- **Hover-Rückmeldung** in Karten, Tabellenzeilen und im Mesh — dezent: feine Kante statt greller
  Fläche, und im Canvas wachsen Knoten in Zeigernähe mit Ring und Schein.
- **Bildnamen auf `comesh-*`** umgestellt (`comesh-api`, `comesh-frontend`, `comesh-agent`); im Agenten
  standen die Container noch als „gpu pool".

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
