#!/bin/bash
# Bericht für ein Agenten-Konto: Verbrauch und Protokoll als CSV holen und kurz zusammenfassen.
#
#   scripts/agent-report.sh <portal-adresse> <schlüsseldatei> [fenster]
#
# Beispiel:
#   scripts/agent-report.sh https://comesh.example.net ~/.config/comesh/agent.key 30d
#
# Achtung: die Admin-API liegt unter /api/admin, die Mandanten-API unter /api/v1.
# Ein Aufruf auf /admin/... liefert die HTML-Oberflaeche mit Status 200 -- kein Fehler,
# aber auch keine Daten.
#
# Der Schlüssel wird nur aus einer Datei gelesen (chmod 600), nie als Argument — sonst steht
# er in der Prozessliste. Die CSVs landen im aktuellen Verzeichnis.
set -euo pipefail

BASE="${1:?Portal-Adresse fehlt (z. B. https://comesh.example.net)}"
KEYFILE="${2:?Schlüsseldatei fehlt}"
FENSTER="${3:-7d}"

if [ ! -r "$KEYFILE" ]; then
  echo "Schlüsseldatei nicht lesbar: $KEYFILE" >&2
  exit 1
fi
KEY="$(tr -d '\r\n' < "$KEYFILE")"

ZIEL="${PWD}/comesh-bericht-$(date +%Y%m%d-%H%M)"
mkdir -p "$ZIEL"

echo "== Konto"
curl -sS --fail-with-body "$BASE/api/v1/me" -H "Authorization: Bearer $KEY" |
  sed -n 's/.*"email"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/  angemeldet als: \1/p'

echo
echo "== Wartende Freigaben"
curl -sS --fail-with-body "$BASE/api/admin/registrations?status=pending" \
  -H "Authorization: Bearer $KEY" |
  python3 -c 'import json,sys; d=json.load(sys.stdin); u=d.get("items") or d.get("users") or []; print("  ", len(u), "ausstehend"); [print("   -", x.get("email")) for x in u[:10]]'

echo
echo "== Verbrauch (Fenster $FENSTER)"
curl -sS --fail-with-body "$BASE/api/admin/usage/export.csv?window=$FENSTER" \
  -H "Authorization: Bearer $KEY" -o "$ZIEL/verbrauch.csv"
echo "  $(($(wc -l < "$ZIEL/verbrauch.csv") - 1)) Konten → $ZIEL/verbrauch.csv"

echo
echo "== Protokoll"
curl -sS --fail-with-body "$BASE/api/admin/audit/export.csv?limit=2000" \
  -H "Authorization: Bearer $KEY" -o "$ZIEL/protokoll.csv"
echo "  $(($(wc -l < "$ZIEL/protokoll.csv") - 1)) Einträge → $ZIEL/protokoll.csv"

echo
echo "Fertig. Beide Dateien: Semikolon als Trenner, Komma als Dezimalzeichen."
