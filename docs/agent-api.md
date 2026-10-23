# Agenten-Konto: Vollzugriff für Automatisierung

Diese Seite beschreibt, wie ein Agent — ein Programm, das regelmäßig Aufgaben im Portal
erledigt — Zugang bekommt und was es damit tun kann. Gedacht ist das für **Routinearbeit**:
Konten freigeben, Modelle zuweisen, Berichte ziehen, Verbrauch prüfen. Nicht dafür, Aufbau
oder Verhalten der Software zu ändern — dafür gibt es dieses Konto nicht und braucht es
auch nicht.

## Konto anlegen

1. Als Administrator anmelden, **Konten** öffnen, **Konto anlegen**.
2. Rolle `admin` wählen — nur damit sind die `/api/admin`-Endpunkte erreichbar.
3. Im Profil des neuen Kontos einen API-Schlüssel ausstellen. Der Wert wird **einmal**
   angezeigt; danach lässt sich nur noch das Präfix abfragen.
4. Den Schlüssel dort ablegen, wo der Agent ihn liest — Datei mit `chmod 600`, nie im
   Klartext in einem Repository oder einer Prozessliste.

Der Schlüssel beginnt mit `gpu_`. Eine Sitzungsmarke (`sess_…`) aus dem Browser ist **kein**
API-Schlüssel und antwortet mit `401 API key is revoked or inactive.`

## Aufrufe

Basis ist `https://<portal>`. Die Mandanten-API liegt unter `/api/v1`, die Administration unter
`/api/admin`:

> **Der häufigste Fehler: `/admin/…` ohne `/api`.** Dieser Pfad liefert die HTML-Oberfläche mit
> Status **200** — kein Fehler, kein JSON, und ein Agent hält es für Erfolg. Immer `/api/admin/…`
> benutzen und beim ersten Aufruf prüfen, dass die Antwort mit `{` beginnt.

```bash
BASE=https://comesh.example.net
KEY=$(cat ~/.config/comesh/agent.key)      # Datei mit chmod 600

# Wer bin ich?
curl -s "$BASE/api/v1/me" -H "Authorization: Bearer $KEY"

# Wartende Anmeldungen ansehen
curl -s "$BASE/api/admin/registrations?status=pending" -H "Authorization: Bearer $KEY"

# Eine Anmeldung freigeben
curl -s -X POST "$BASE/api/admin/registrations/149/approve" \
     -H "Authorization: Bearer $KEY"

# Modelle eines Kontos setzen (Liste = genau diese, null = Standard, [] = nichts)
curl -s -X PATCH "$BASE/api/admin/users/102" -H "Authorization: Bearer $KEY" \
     -H "Content-Type: application/json" \
     -d '{"allowed_models":["llama3.1:8b","qwen3-vl:8b"],"allow_cloud":false}'

# Bericht: Verbrauch aller Konten als CSV
curl -s "$BASE/api/admin/usage/export.csv?window=30d" \
     -H "Authorization: Bearer $KEY" -o verbrauch-30d.csv

# Bericht: Protokoll (wer hat was freigegeben) als CSV
curl -s "$BASE/api/admin/audit/export.csv?limit=2000" \
     -H "Authorization: Bearer $KEY" -o protokoll.csv
```

Die CSVs nutzen Semikolon als Trenner und Komma als Dezimalzeichen, damit sie in deutschen
Tabellenprogrammen direkt aufgehen. Die Datei beginnt mit einem BOM, damit Excel Umlaute
richtig liest.

## Was ein Agent hier tun kann

| Aufgabe | Endpunkt |
| --- | --- |
| Wartende Anmeldungen auflisten | `GET /api/admin/registrations?status=pending` |
| Freigeben / ablehnen | `POST /api/admin/registrations/{id}/approve` · `/reject` |
| Konto anlegen | `POST /api/admin/users` |
| Rolle, Name, Aktiv-Zustand, Modelle, Cloud ändern | `PATCH /api/admin/users/{id}` |
| Guthaben buchen | `POST /api/admin/users/{id}/topup` |
| Schlüssel ausstellen / widerrufen | `POST /api/admin/users/{id}/keys` · `/keys/{kid}/revoke` |
| Geräte ansehen, pausieren | `GET /api/admin/nodes` · `POST /api/admin/users/{uid}/nodes/{nid}/enable` |
| Verbrauch, Berichte | `GET /api/admin/usage` · `GET /api/admin/usage/export.csv` |
| Protokoll | `GET /api/admin/audit` · `GET /api/admin/audit/export.csv` |
| Mail-Einstellungen | `GET/PUT /api/admin/mail` · `POST /api/admin/mail/test` |

Jeder schreibende Aufruf landet im Protokoll (`admin_audit_log`) mit Admin-Kennung,
Aktion, Ziel und Nutzdaten — ohne Geheimnisse.

## Was es bewusst nicht kann

- **Kein Zugriff auf den Quellbaum.** Über die API lässt sich keine Datei ändern, kein Container
  neu bauen, keine Abhängigkeit installieren. Wer die Software ändern will, arbeitet am
  Repository und rollt selbst aus.
- **Kein Schema-Eingriff.** Neue Spalten und Tabellen entstehen nur durch Migrationen im Code,
  die beim Start laufen — nicht über einen Endpunkt.
- **Ein Administrator kann sich nicht selbst aussperren**: sich selbst degradieren oder
  deaktivieren antwortet mit `409`.
- **Das Protokoll ist nur lesbar.** Löschen oder ändern sieht der Endpunkt nicht vor.

## Wenn etwas nicht geht

| Antwort | Bedeutung |
| --- | --- |
| `401` | Schlüssel falsch, widerrufen, oder es wurde eine `sess_…`-Marke benutzt |
| `403` | Konto hat nicht die Rolle `admin` |
| `409` | Aktion würde den letzten Administrator aussperren |
| `422` | Nutzdaten passen nicht zum Schema (z. B. unbekannte Rolle) |

## Empfehlung für den Betrieb

- Ein **eigenes Konto** für den Agenten, nicht das persönliche. So steht im Protokoll, wer
  gehandelt hat, und ein Schlüsselwechsel trifft nicht den eigenen Zugang.
- Schlüssel regelmäßig erneuern; ein neuer Schlüssel entwertet die bisherigen `gpu_…`-Schlüssel
  desselben Kontos.
- Dem Agenten die Reihenfolge vorgeben: erst lesen (`GET`), dann eine Änderung, dann
  gegenprüfen. Die Endpunkte sind so gebaut, dass ein wiederholter Aufruf nicht doppelt bucht
  (`idempotency_key` bei den Schreibvorgängen) — trotzdem ist Prüfen billiger als Wiederholen.
