# Diagnostics from a remote instance / Diagnose aus der Ferne

When a CoMesh instance runs somewhere you cannot reach yourself, the fastest way to debug is a
report produced **on that machine**. A report with real credentials is a data leak: it ends up in
chats, tickets and repositories. `scripts/sammle-diagnose.sh` therefore collects only what helps
diagnosis — versions, state, structure, log lines — and masks everything that looks like a secret.

```bash
bash scripts/sammle-diagnose.sh > bericht.md          # IP addresses masked
bash scripts/sammle-diagnose.sh --mit-adressen       # keep IP addresses
bash scripts/sammle-diagnose.sh --projekt ~/pfad     # other project directory
```

The script changes nothing. It reads files, asks Docker and the database, and prints Markdown.

**Masked:** `gpu_`/`node_`/`sess_` keys, `*KEY`/`*TOKEN`/`*SECRET`/`*PASSWORD` values, `Bearer`
values, credentials inside URLs, hex strings of 32+ characters, and (by default) IPv4 addresses.

**Never masked, on purpose:** variable *names* from `.env`, version numbers, commit hashes, node
counts, states. That is the information needed; the values are not.

**What it does not do:** it does not read `.env` values, does not dump key hashes from the
database, and does not call any write endpoint. If a specific value is needed to debug, ask for
that value explicitly — do not send the whole file.

For an agent that has shell access to the machine, hand it exactly this script and nothing else.
That keeps the useful part (the report) and removes the risk (an agent with credentials in reach).

---

# Diagnose aus der Ferne

Wenn eine CoMesh-Instanz irgendwo läuft, wo du selbst nicht hinkommst, ist der schnellste Weg zur
Fehlersuche ein Bericht, der **auf der Maschine** entsteht. Ein Bericht mit echten Zugangsdaten ist
aber ein Datenleck — er landet in Chats, Tickets und Repositories. `scripts/sammle-diagnose.sh`
sammelt deshalb nur, was zur Diagnose taugt — Versionen, Zustand, Struktur, Logzeilen — und maskiert
alles, was nach Geheimnis aussieht.

```bash
bash scripts/sammle-diagnose.sh > bericht.md          # IP-Adressen maskiert
bash scripts/sammle-diagnose.sh --mit-adressen       # IP-Adressen behalten
bash scripts/sammle-diagnose.sh --projekt ~/pfad     # anderes Projektverzeichnis
```

Das Skript ändert nichts. Es liest Dateien, fragt Docker und die Datenbank ab und schreibt Markdown.

**Wird maskiert:** `gpu_`/`node_`/`sess_`-Schlüssel, Werte von `*KEY`/`*TOKEN`/`*SECRET`/`*PASSWORD`,
`Bearer`-Werte, Zugangsdaten in URLs, Hex-Zeichenketten ab 32 Zeichen und (voreingestellt)
IPv4-Adressen.

**Bleibt bewusst stehen:** Variablen*namen* aus `.env`, Versionsnummern, Commit-Kennungen,
Node-Zahlen, Zustände. Das ist die Information, die gebraucht wird — die Werte nicht.

**Was es nicht tut:** keine Werte aus `.env` lesen, keine Schlüssel-Hashes aus der Datenbank
ausgeben, keinen schreibenden Endpunkt aufrufen. Wird ein bestimmter Wert zur Fehlersuche gebraucht,
dann gezielt danach fragen — nicht die ganze Datei schicken.

Einem Agenten mit Shell-Zugriff auf der Maschine gibt man genau dieses Skript und sonst nichts.
Damit bleibt der nützliche Teil (der Bericht) und der riskante Teil (ein Agent mit erreichbaren
Zugangsdaten) fällt weg.
