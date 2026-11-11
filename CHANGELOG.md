# Changelog

## 0.6.20 — 2026-11-11

**Rechtstexte trägt der Betreiber in der Konsole ein**

Die Texte sind Betreibersache, nicht Projektsache: wer eine Instanz öffentlich stellt, ist
Impressums- und Datenschutz-Ansprechpartner. Bisher ging das nur über `.env`-Variablen — jetzt
über ein Formular.

1. **Verwaltung → Rechtstexte** (`/admin/legal`): elf Felder, Pflichtangaben markiert, Speichern
   ohne Neustart. Die Werte liegen in `system_settings` (`legal.*`) und haben Vorrang vor der
   Umgebung; ein geleertes Feld löscht den Eintrag, dann gilt wieder `.env`.
2. **Die Seiten lesen beides** — Datenbank zuerst, dann Umgebung. `/impressum`, `/datenschutz`
   und `/agb` aktualisieren sich sofort nach dem Speichern.
3. **Ehrlicher Fallback bleibt:** fehlt eine Pflichtangabe, zeigt die Seite einen roten Hinweis
   mit der Liste der fehlenden Felder, nennt das Upstream-Projekt als Software-Quelle und geht
   auf `noindex`.
4. **README-Abschnitt „Öffentlich betreiben: deine Pflichten"** in Englisch und Deutsch, damit
   beim Klonen klar ist, wer die Texte füllen muss.

**Nebenfund, gleich mitbehoben:** `seed_test_user_if_empty()` legte auf einer leeren Datenbank
ein Konto `test@example.com` mit dem Passwort `password123` an — auf einer frischen, öffentlich
erreichbaren Instanz eine offene Tür. Der Seed läuft jetzt nur noch mit `SEED_TEST_USER=1`
(Tests, lokale Entwicklung).

## 0.6.19 — 2026-11-11

**Produktionsliste P0 abgearbeitet: Sicherung, Rechtstexte, Köpfe, Healthchecks, Logs**

1. **Datensicherung.** `scripts/backup-db.sh` zieht eine konsistente Momentaufnahme
   (`sqlite3.Connection.backup`, nicht `cp` mitten in einer Transaktion), prüft Integrität und
   Kontozahl, komprimiert und verwirft Sicherungen älter als 14 Tage. Dazu
   `deploy/comesh-backup.{service,timer}` (täglich 03:20, `Persistent=true`) und eine geübte
   Wiederherstellung in `deploy/README.md`.
2. **Rechtstexte aus der Umgebung.** `/impressum`, `/datenschutz`, `/agb` werden vom Backend
   gerendert (`legal.py`) und aus `IMPRESSUM_*`/`DATENSCHUTZ_EMAIL`/`HOSTING_ANBIETER` gefüllt.
   Fehlt eine Pflichtangabe, steht ein roter Hinweis mit der Liste der fehlenden Variablen auf
   der Seite und sie geht auf `noindex` — statt still ein unvollständiges Impressum
   auszuliefern. In allen Fußzeilen verlinkt, viersprachig beschriftet.
3. **Sicherheitsköpfe** (`frontend-alpine/security-headers.conf`): HSTS,
   `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy` und CSP.
   Die CSP erlaubt `unpkg.com` (Alpine) und Google Fonts, weil die Seiten beides laden.
   In jedem `location`-Block erneut eingebunden, der eigenes `add_header` setzt — sonst erbt er
   die Server-Köpfe nicht.
4. **CORS standardmäßig aus.** Nötig wird es nur, wenn eine fremde Web-Anwendung die API
   aufruft: dann `CORS_ORIGINS` setzen.
5. **Healthchecks und Logrotation.** Alle drei Dienste melden ihren Zustand (API `/health`,
   nginx `index.html`, Agent `/health`); Docker schreibt `json-file` mit 50 MB × 5 statt
   unbegrenzt.
6. **Selbstregistrierung abschaltbar** (`REGISTRATION_OPEN=0`).
7. **Agent-Version von der Portal-Version gelöst.** Neue Datei `AGENT_VERSION`: ein reines
   Server-Release markiert die ausgelieferten Agenten nicht mehr fälschlich als „veraltet".
8. **CI prüft Abhängigkeiten** (`pip-audit`, Bericht ohne Blocker) und Dependabot schlägt
   wöchentlich Aktualisierungen vor.

Nicht in diesem Schritt: Container als Nicht-root (braucht Entrypoint mit Rechteübergabe am
Volume), externe Verfügbarkeitsüberwachung (eigener Host nötig), die inhaltliche Prüfung der
Rechtstexte (bleibt beim Betreiber).

## 0.6.18 — 2026-11-11

**Erstinstallation im Browser: Administrator anlegen, dann ist die Tür zu**

Bisher entstand der erste Administrator beim Start des Containers — mit einem
Passwort, das in `$DATA_DIR/admin_password.txt` stand. Auf einem frischen Rechner liegt dieses
Verzeichnis in einem Docker-Volume, das man unter Windows nicht sieht; wer es nicht findet, steht
vor einer Anmeldeseite ohne Konto.

1. **`setup.html`** erscheint bei einer frischen Instanz und leitet dorthin um, solange kein
   Konto mit der Rolle `admin` existiert. Anmeldung, Name, E-Mail, Passwort — wie bei WordPress,
   nur mit einer Prüfung davor.
2. **Das Setup-Token steht im Log** (`docker compose logs api`, Datei `$DATA_DIR/setup_token.txt`).
   Ohne Token legt sich niemand Administratorrechte an — eine frische Instanz im Internet ist
   damit nicht für den ersten Fremden übernehmbar. Wer ohne das Web-Formular einrichten will,
   setzt weiterhin `ADMIN_API_KEY`/`ADMIN_EMAIL`; dann meldet `/setup/status` kein offenes Setup.
3. **Nach dem Abschluss ist der Endpunkt dauerhaft zu** (`410 Gone`), Token und die generierten
   Notfall-Dateien sind gelöscht. Der Bootstrap fasst das Konto nicht mehr an — sonst hätte der
   nächste Neustart das eben gewählte Passwort überschrieben.
4. **Die Seite gibt es in vier Sprachen**, Katalog jetzt 795 Schlüssel.

## 0.6.17 — 2026-11-09

**Das Portal zeigt, welcher Agent auf einer Node läuft — und ob er veraltet ist**

Der Anlass war ein Provider, dessen lokale Modelle im Portal nicht erschienen: auf seiner
Maschine lief noch ein Agent vom 04.11. (0.6.10), und nirgends war zu sehen, welche Version dort
tatsächlich arbeitet. `/version` nennt nur die Version, die das Portal *ausliefert*.

1. **Der Agent meldet seine Version.** `send_heartbeat` schickt `agent_version` mit; das Portal
   speichert sie in `gpu_nodes.agent_version` / `agent_version_at` (Migration beim Start,
   idempotent, beide Spalten NULL-fähig).
2. **Die Node-Karte zeigt sie.** Bei jeder eigenen Node steht „Agent-Version:"; weicht sie von der
   Version ab, die dieses Portal ausliefert, erscheint ein „veraltet"-Kennzeichen mit der
   erwarteten Nummer. Die erwartete Nummer kommt als `agent_version_expected` in der
   Node-Antwort — `/version` ist am Frontend-Port nicht erreichbar, ein zweiter Aufruf wäre
   ohnehin unnötig.
3. **Alte Agenten bleiben sichtbar, nicht still.** Meldet eine Node nichts, steht dort „noch
   keine Meldung"; ein zuletzt bekannter Wert wird nicht gelöscht.
4. **Die Anleitung hat einen Abschnitt „Installation verwalten"** (de/en/es/fr): wo die Dateien
   liegen, wie man aktualisiert und wie man den Agenten wieder entfernt — samt dem Hinweis, dass
   die Node im Portal stehen bleibt und dort gelöscht gehört.

## 0.6.16 — 2026-11-06

**Der Abnahmeprüfer findet jetzt die Stellen, die er vorher übersah — und alle
sind behoben**

Das Gate aus 0.6.15 war grün und trotzdem nicht ehrlich: der Prüfer hielt
deutsche Einzelwörter für Bezeichner, sah nur Markup und Katalog an und griff
kein einziges der deutschen Literale in `admin-audit.js`, `admin-registrations.js`,
`admin-nodes.js`, `app.js`, `nodes.js` oder in den inline-`<script>`-Blöcken der
Seiten auf.

1. **Der Prüfer prüft drei Klassen mehr.** `audit_coverage.py` arbeitet im
   Markup jetzt mit einer geschlossenen Welt: ungedeckter sichtbarer Text darf
   nur aus freigegebenen Wörtern bestehen (Fachbegriffe der Produktregel,
   Marke, Zahlen, Symbole) — damit fallen auch Einzelwörter wie
   `Aktualisieren`, `Registrieren`, `Anmelden`, `Protokoll` und `Wann` auf, die
   ein Umlaut- oder Funktionswort-Filter nicht sieht. Dazu: sichtbare Attribute
   (`placeholder`, `title`, `aria-label`, `alt`) auf **jedem** Element statt nur
   auf fünf Tag-Typen, und deutsche String-Literale in Anwendungs-JS — Dateien
   *und* inline-`<script>`, einschließlich der Alpine-Ausdrücke in Attributen.
   Kommentare, Schlüsselnamen in `I18n.t(...)` und Code-Literale (URLs, Pfade,
   Dateinamen, Selektoren) sind ausgenommen, Fachbegriffe stehen als
   ausdrückliche Ausnahmeliste im Prüfer.
2. **Mit der erweiterten Prüfung: 271 Fundstellen vorher, 0 nachher**
   (96 Markuptext, 15 Attribute, 160 JS-Literale im Stand 0.6.15).
3. **Rund 150 neue Schlüssel** in `scripts/i18n/i18n_parts/part12_js_and_words.py`
   (Katalog 557 → 767), vollständig in EN/DE/ES/FR: Tabellenköpfe und
   Chip-Beschriftungen der Admin-Seiten, die ganze Einrichtungs- und
   Freigabemaske, Sortier-Titel, Dialoge und Toasts (Bestätigungen, Fehler,
   Prompts), Chatformulierungen samt Startvorschlägen, Preisstaffel und
   Kauf-Dialog der Credits-Seite. Wo eine ganze Zeile mit `<code>`-Elementen
   steht, trägt sie `data-i18n-html`; wo der Text zwischen Kindelementen stand,
   sitzt er in einem eigenen `<span>` mit Schlüssel.
4. **Schlüssel werden nicht mehr weggespart.** `build_catalog.py` verwirft
   unbenutzte Einträge; ein Schlüssel in `I18n.t(cond ? "a" : "b")` galt dabei
   als unbenutzt und verschwand. Die betroffenen Stellen rufen `I18n.t(...)`
   jetzt je Zweig auf.
5. **Datum und relative Zeit folgen der Sprache.** `app.js` formatierte fest
   mit `de-DE` und zeigte „vor 5 min" in jeder Sprache; beides läuft über
   `LOCALE_TAG` bzw. `I18n.t(...)`.
6. Nebenbei: ein kaputter `title` (fehlendes schließendes Anführungszeichen im
   deutschen Text) und ein versehentlich zerstörter `I18n.t`-Aufruf in
   `nodes.js` sind repariert.

Nicht übersetzt bleiben bewusst: `guide.html` (eigener `<div lang>`-Mechanismus,
muss ohne JS lesbar sein — dort bleibt auch der `<title>` in der
Ausgangssprache), die Downloads, die Installer-Skripte, das als Nutzlast an die
API gehende `reason: "manuell (admin)"` und die CSS-Klasse `is-online`.

## 0.6.15 — 2026-11-06

**Alle Oberflächentexte sind übersetzt — der Abnahmeprüfer steht auf PASS**

1. **75 deutsche Textstellen im Markup hatten keinen Übersetzungsschlüssel** und
   blieben bei jedem Sprachwechsel deutsch: Überschriften und Hinweise auf den
   Admin-Seiten (Protokoll, Geräte, Konten und Freigaben), die
   Konto-von-Hand-Maske, der E-Mail-Abschnitt samt Testmail-Hinweis, die
   Node-Formulare (Adresse/Port, gemeldete Modelle), Anmeldung, Chat-Hinweiszeile,
   Pool-Leerzustand und die Rück-Links. Sie tragen jetzt Schlüssel aus
   `scripts/i18n/i18n_parts/part11_rest.py` (63 neue Schlüssel, Katalog 494 → 557).
2. **Neun Attribute waren unübersetzt** — `placeholder`, `title` und
   `aria-label` in Suche, VRAM-Spalte, Modellfreigabe, Beschreibungsfeld und
   Betriebsauswahl. Sie haben `data-i18n-placeholder` / `-title` / `-aria-label`;
   drei Alpine-Bindungen (`:placeholder`, zweimal `:aria-label`) lösen ihre Texte
   jetzt über `I18n.t(...)` auf, weil ein statisches Attribut die Bindung sofort
   wieder überschreiben würde.
3. **Der Prüfer selbst war die halbe Ursache.** `audit_coverage.py` suchte nach
   `placeholder-i18n` — eine Schreibweise, die im Frontend nirgends vorkommt und
   die `i18n.js` nicht auswertet. Bereits übersetzte Attribute galten damit als
   offen. Er prüft jetzt `data-i18n-<attr>` und führt die statische Anleitung
   (`guide.html`) in einem eigenen Abschnitt: dort zählt nicht ein Schlüssel,
   sondern dass **jeder** Text in einem `<div lang="…">`-Block steht.
4. **Inhalte aus `<template>` wurden nie übersetzt.** `x-if`/`x-for` halten ihren
   Inhalt in einem eigenen DocumentFragment; ein Selektor auf dem Dokument
   erreicht ihn nicht, Alpine klont ihn erst beim Rendern. Die Tabellenzeilen der
   Admin-Seiten und das Whitelist-Fenster blieben deshalb in jeder Sprache
   deutsch. `I18n.apply()` läuft jetzt auch durch die Vorlagen.
5. **Zwei alte Katalogeinträge passten nicht mehr zum Markup:** die Admin-Usage-
   Einleitung war nach „die Admin-Sicht auf“ abgeschnitten (der Code-Teil fehlte
   in allen vier Sprachen), und der Agent-Hinweis trug noch einen Satz über die
   70-%-Gutschrift, den das Markup nicht mehr hat. Beide sind auf den
   Markup-Text gebracht — Prüfung 4 des Katalogs vergleicht zeichengleich.
6. **Abnahme:** `audit_coverage.py` meldet `GATE: PASS` (0 Fundstellen in allen
   Abschnitten), `build_catalog.py` läuft ohne Beanstandung durch, die
   Testsuite bleibt grün.

## 0.6.14 — 2026-11-06

**Modelle, die nur auf einer Node liegen, sind im Portal sichtbar und nutzbar**

1. **Der Agent meldet seine eigenen Modelle.** Bisher fragte nur das Portal sein
   zentrales Ollama und bot genau diesen Katalog an. Ein Provider, der auf seiner
   Maschine etwas anderes laufen hat — qwen3:4b/8b/14b auf einem Windows-Rechner, ein
   Llama-Server hinter `BACKEND=openai` —, konnte es deshalb niemandem anbieten: das
   Modell fehlte in der Auswahl, obwohl die Node es bedient. Der Agent liest jetzt bei
   jedem Heartbeat sein eigenes Backend (`/api/tags` bzw. `/v1/models`) und schickt die
   Namen mit. Schlägt die Abfrage fehl, bleibt die zuletzt gemeldete Liste stehen —
   ein stummgeschaltetes Backend löscht also nichts.
2. **Das Portal speichert die Meldung je Node** (`gpu_nodes.reported_models`,
   `reported_models_at`) und zeigt sie auf der Node-Seite unter „Auf dieser Maschine
   gemeldet“. Die Freigabe-Liste bleibt davon getrennt und wird unverändert im
   Bearbeiten-Fenster gepflegt; ein Knopf trägt die gemeldeten Namen nur ins Feld ein —
   gespeichert wird weiterhin bewusst mit „Speichern“.
3. **`GET /v1/models` bietet sie an, auch ohne Eintrag im zentralen Katalog.** Gefiltert
   wird weiterhin mit `can_use_model`, also nach der Freigabe des Kontos, und nur
   Modelle aktiver (nicht pausierter) Nodes. Solche Einträge tragen `source: "node"`.
   Cloud-Modelle bleiben wie bisher: sie müssen zusätzlich von einem Provider
   freigegeben sein.
4. **Das Routing nimmt nur noch Nodes, die das Modell wirklich haben.** Eine Node, die
   ihre Modelle meldet, bedient ausschließlich diese; eine Node ohne Meldung (alter
   Agent) verhält sich wie bisher. Bei der Auswahl gewinnt die Node, die das Modell
   bestätigt hat, vor einer mit unbekannter Liste — vorher konnte ein Auftrag an eine
   Maschine gehen, die das Modell gar nicht geladen hatte.
5. **Bestehende Datenbanken laufen ohne Eingriff weiter.** Die Migration ergänzt beide
   Spalten idempotent beim Start (Muster wie bei `vram_source`); alte Nodes gelten als
   „Modelle unbekannt“ und werden weiter wie bisher behandelt.

## 0.6.13 — 2026-11-06

**Windows-Installation ohne Adminrechte, stabile Streams, Node-Adresse korrigierbar**

1. **Der Windows-Installer bricht nicht mehr ab, wenn die Aufgabenplanung sperrt.** Auf
   unternehmensverwalteten Rechnern antwortet `schtasks /Create` mit *Zugriff verweigert*;
   die Installation endete dort, obwohl der Agent einwandfrei lief. Der Autostart läuft
   jetzt als Kette ohne Adminrechte: Aufgabenplanung, sonst der `Run`-Schlüssel des
   Benutzers (`HKCU`), sonst eine Verknüpfung im Autostart-Ordner. Der gewählte Weg steht
   im Abschlussbericht, die Deinstallation räumt alle drei ab.
2. **Der Ein-Zeilen-Befehl umgeht die Skriptrichtlinie.** `powershell -ExecutionPolicy
   Bypass -Command "irm … | iex"` statt `irm … | iex` — der Bypass gilt nur für diesen
   Aufruf, die Rechnerrichtlinie bleibt unangetastet. Vorher scheiterte die Installation
   mit `PSSecurityException`.
3. **Streaming hält die Verbindung, auch wenn das Modell rechnet.** Im streamenden Weg
   wurde zwischen den Teilstücken nichts gesendet; hinter Cloudflare gilt das als tote
   Verbindung und wird gekappt („Streaming-Verbindung wurde vor einer vollständigen Antwort
   beendet"). Jetzt geht alle 15 s eine SSE-Kommentarzeile (`: keepalive`) — gültig,
   für Clients unsichtbar und abschaltbar über `COMESH_SSE_KEEPALIVE_S=0`.
   **Der nicht-streamende Weg bleibt davon unberührt:** er wartet auf die ganze Antwort und
   läuft hinter Cloudflare nach rund 100 s in einen `524`. Lange Läufe gehören auf Streaming.
4. **Adresse und Port einer Node lassen sich bearbeiten, ohne den Konto-Schlüssel neu
   einzutragen.** Ein falsch eingetragener Port war im Portal nicht korrigierbar; der
   Server konnte es längst (`PUT /nodes/{id}`). Das Bearbeiten-Fenster hat jetzt Felder für
   Adresse und Port. Der Agent kennt seinen Schlüssel selbst — das Portal speichert nur
   dessen Hash —, deshalb ist die Korrektur gefahrlos. Leer lassen heißt weiterhin: der
   Agent meldet seine Adresse beim Heartbeat selbst.

## 0.6.12 — 2026-11-04

**Der Provider-Weg steht im Portal, und er ist benannt wie eine Einladung**

1. **`nodes.html` hängt an keiner Rolle mehr.** Der Menüpunkt **Nodes** (seit dieser Fassung
   **Deine Node**) stand nur für `provider` in der Navigation (`NAV_ITEMS`, `providerOnly: true`) — ein Consumer fand den
   Abschnitt „Eigene Node beitragen" deshalb gar nicht, obwohl genau das der Weg ist, über den
   ein Konto Provider wird. Die Seite ist jetzt für jedes Konto offen; ausgeblendet werden nur
   die Provider-Funktionen (Registrierungsformular, Massenaktionen), und das Server-Gate in
   `POST /nodes/register` bleibt unverändert.
2. **Rollen-Hinweis mit Weg statt Sackgasse.** Ein Konto ohne Provider-Rolle sieht auf der
   Node-Seite, dass die Befehle gelten, der Agent die Node aber mit dem Account-Schlüssel
   anmeldet — und dass die Rolle im Profil selbst umgestellt wird
   (`PUT /v1/me/role`, `profile.html#rolle`). Kein Administrator nötig.
3. **Karte auf dem Dashboard.** Ein Konto ohne Node sieht „Teile deine GPU" mit dem fertigen
   Ein-Zeilen-Befehl, Kopierknopf und Link auf `nodes.html#beitragen`; ein Konto mit Node sieht
   stattdessen Name, Status (online/offline, pausiert) und den Weg zur Node-Seite.
4. **Anleitung verlinkt.** `guide.html` (vier Sprachen) verweist vom Abschnitt „Teile deine
   GPU" auf `nodes.html#beitragen` und auf die Rollenwahl im Profil.
5. **Die Node-Seite lädt ein, statt eine Rolle zu verlangen.** Sie hieß „PROVIDER / GPU
   bereitstellen" — ein Rollenetikett als Überschrift, genau an der Stelle, an der ein
   normales Konto erst erfahren soll, dass es eine Node beitragen kann. Jetzt: **Teile deine
   GPU** (EN „Share your GPU", ES „Comparte tu GPU", FR „Partagez votre GPU"), darüber die
   kleine Zeile **Deine Node**. Durchgezogen bis in Seitentitel, Navigation, Dashboard-Karte
   (die schon so hieß) und Anleitung; der Rollen-Hinweis heißt „Rolle noch nicht gesetzt"
   statt „Noch kein Provider-Konto" und sagt weiter, dass die Befehle für jedes Konto gelten.
6. **Anleitung beschreibt den Weg vollständig.** Der Abschnitt „Teile deine GPU" führt jetzt
   fünf Schritte in allen vier Sprachen: Konto, Rolle im Profil (`profile.html#rolle`),
   Account-Schlüssel (`profile.html#schluessel`), Installation per Ein-Zeilen-Befehl für
   Linux/macOS und Windows, und dass die Node danach in der Liste steht und **ausgehend**
   verbindet (kein offener Port). `docs/guide.md` ist angeglichen, die Fußnote nennt Stand
   und Version, und der Guide sagt nicht mehr „Deutsch und Englisch", wo vier Sprachen
   umschaltbar sind.

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

6. **Konto-Seite: eigene API-Schlüssel einsehen und erzeugen.** Der Abschnitt
   „Eigene Node beitragen" verlangt den Account-Schlüssel als
   `PORTAL_USER_KEY` — in der Oberfläche war er nirgends zu sehen. Das Profil hat
   jetzt einen Abschnitt „API-Schlüssel": Liste der ausgestellten Schlüssel mit
   Präfix, Erstellungsdatum und Zustand (aktiv/ersetzt), nie der volle Wert
   (gespeichert ist nur ein SHA-256-Hash), dazu „Neuen Schlüssel erzeugen" mit
   Passwortfeld — der Wert erscheint **genau einmal**, mit Warnung und
   Kopierknopf. `GET /v1/me/keys` liefert zusätzlich `count`, `active` und
   `last_used_at`; die neuen Felder sind reine Anzeige, der Schlüssel selbst
   bleibt nicht rekonstruierbar. `nodes.html` verweist jetzt auf
   `profile.html#schluessel` statt auf „derzeit nicht erneut anzeigen".

7. **Doku auf den Code-Stand.** `README.md` neu als Produkttext, Englisch zuerst
   und Deutsch darunter, mit Abschnitt „Eigene Node beitragen" (Befehle,
   Downloads, Prüfsummen, Größen). `ARCHITECTURE.md` beschrieb noch einen POC
   ohne Auth und Streaming mit Agent auf 8080; jetzt Rollen, beide
   Transportwege samt Begründung, Anfrageweg mit Node-Auswahl und VRAM-Gate, die
   drei Zugangssperren, Tabellen und die bewussten Lücken — jede Aussage mit der
   Datei, aus der sie stammt. Der eine 8080-Treffer ist Open WebUI auf demselben
   Host und als Historie gekennzeichnet, `gpu_nodes.port` hat jetzt die
   Vorgabe 11435 (`DEFAULT_AGENT_PORT`) statt 11434 (Ollama selbst; gilt nur für
   neue Zeilen, keine Migration).

   **Downloads am Cloudflare-Edge:** nach dem Austausch des Windows-Binaries
   lieferte der Edge weiter die 0.6.9er Datei (`cf-cache-status: HIT`, age 6508),
   während die `.sha256` daneben schon die neue Summe trug — Installationen
   brachen an der Prüfsumme ab. `install.sh`/`install.ps1` holen jetzt zuerst die
   `.sha256` und laden das Binary unter `<base>/<asset>?sha=<erste 12 Zeichen>`;
   der Query ändert sich mit dem Inhalt, eine alte Cache-Kopie greift nicht mehr.
   nginx `/downloads/` setzt zusätzlich `Cache-Control: no-cache` (am Edge
   wirkungslos, deshalb der Query als tragender Teil).

   **Nebenbefund:** `nodes.html` brach den Aufbau ab, weil ein Credits-Flag nicht
   definiert war — jetzt definiert.

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
