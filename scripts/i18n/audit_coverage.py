#!/usr/bin/env python3
"""LANA-63/LANA-65 — Abnahmeprüfer für die Übersetzung.

Dieser Prüfer liest die *ausgelieferten* Dateien (HTML + JS + i18n-catalog.js),
nicht einen Zwischenstand. Er prüft vier Dinge:

  0. Sprachblock-Seiten (guide.html): jeder Textknoten steht in einem
     `<… lang="…">`-Block. Dort gibt es keine Schlüssel; prüfbar ist die
     Gegenrichtung.
  1. Sichtbarer Text im Markup ohne data-i18n. Geschlossene Welt: ein Textknoten,
     der nicht durch data-i18n / data-i18n-html / x-text / x-html gedeckt ist,
     darf nur aus freigegebenen Wörtern bestehen (Fachbegriffe der Produktregel,
     Marke, Zahlen, Symbole). Alles andere ist eine Fundstelle — damit fallen
     auch deutsche EINZELWÖRTER auf ('Aktualisieren', 'Registrieren', 'Anmelden',
     'Protokoll', 'Wann', 'Werkzeuge', 'Registriert'), die ein Umlaut- oder
     Funktionswort-Filter übersieht.
  2. Attribute mit sichtbarem Text (placeholder, title, aria-label, alt) auf
     JEDEM Element: deutscher Wert ohne data-i18n-<attr>.
  3. Deutsche String-Literale in Anwendungs-JS: *.js (außer i18n-catalog.js) und
     die inline-<script>-Blöcke der Seiten, einschließlich der Alpine-Ausdrücke
     in Attributen (x-text, :title, :placeholder …). Kommentare zählen nicht,
     Schlüsselnamen in I18n.t(...) nicht, und Code-Literale (URLs, Pfade,
     Dateinamen, Selektoren) werden nach Form ausgenommen.
  4. Jeder im Markup oder Code benutzte Schlüssel löst im Katalog auf, und jeder
     Katalogschlüssel trägt alle vier Sprachen nicht leer.

Bis 0.6.15 prüfte der Prüfer nur (0), (1) mit einem Filter, der deutsche
Einzelwörter als Bezeichner verwarf, (2) nur auf fünf Tag-Typen und (3) gar
nicht. Das Gate war damit grün, obwohl 'Aktualisieren' sechsmal, 'Registrieren'
fünfmal und rund fünfzig Dialog- und Fehlertexte auf Deutsch im ausgelieferten
JS standen.

Fachbegriffe (Produktregel, in allen vier Sprachen gleich) melden wir NICHT als
Fundstelle — sie stehen als ausdrückliche Ausnahmeliste unten, nicht als
stillschweigendes Weglassen.
"""
import json, re, sys
from pathlib import Path

FE = Path(__file__).resolve().parents[2] / "frontend-alpine"

# Seiten, die je Sprache einen <div lang="…">-Block führen statt data-i18n.
LOCALE_BLOCK_PAGES = {"guide.html"}
# Nur der Katalog selbst ist keine Anwendung.
SKIP_JS = {"i18n-catalog.js"}

# --------------------------------------------------------------- Ausnahmelisten
# Fachbegriffe der Produktregel: bleiben in jeder Sprache gleich, sind also keine
# fehlende Übersetzung. Bewusst als Liste, damit ein neuer Begriff hier landet
# und nicht durch eine Lücke im Filter verschwindet.
TERMS = {
    "node", "nodes", "token", "tokens", "model", "models", "api", "api-key",
    "pool", "provider", "owner", "treasury", "vram", "tailscale", "credits",
    "status", "port", "chat", "admin", "admins", "profil", "konto", "passwort",
    "modell", "anfrage", "request", "requests",
}
# Fachbegriffe, die trotzdem übersetzt werden müssen: sie stehen in TERMS, weil
# die Produktregel sie dort führt, im Englischen heißen sie aber anders. Ihre
# ungekeyten Vorkommen meldet der Prüfer als Warnung (nicht als Fundstelle, um
# die Produktregel nicht zu verletzen) — damit diese Lücke nicht wieder
# stillschweigend deutsch bleibt.
TERMS_THAT_TRANSLATE = {"konto", "konten", "passwort", "profil", "modell"}

# Marke und Wörter, die in allen vier Sprachen identisch sind.
BRAND = {"comesh", "online", "offline", "cloud", "usage", "sla", "starttls",
         "ssl", "tls", "smtp", "json", "http", "https", "gpu", "vram", "gb",
         "eur", "min", "sek", "h", "s", "kb", "mb"}
# Nicht-UI-Zeichenketten: Werte, die nie auf dem Bildschirm stehen.
CODE_STRINGS = {
    # CSS-Klasse, kein Text
    "is-online",
    # Nutzlast an die API (Spalte reason im Audit-Log), wird nicht angezeigt
    "manuell (admin)",
}

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr"}
RAW = {"script", "style"}
NOT_TEXT = {"script", "style", "pre", "code", "kbd", "samp", "title"}
# Nur ein Schlüssel für den *Inhalt* deckt einen Textknoten. data-i18n-title und
# data-i18n-placeholder übersetzen ein Attribut und lassen den Elementtext stehen —
# genau daran blieb 'Modelle' auf einem Knopf deutsch.
KEYATTR = re.compile(r"\b(?:data-i18n|data-i18n-html|x-text|x-html)\s*=")
TAG = re.compile(r"<[^>]+>")
WORD = re.compile(r"[A-Za-zÄÖÜäöüß][\wÄÖÜäöüß'’.-]*")
CJK = re.compile(r"[\u2e80-\u9fff\u3000-\u303f\uff00-\uffef]")

# ------------------------------------------------------------ Deutsch-Erkennung
# Drei Regeln zusammen: Umlaute, Lexikon, Wortbildung. Die Worthülle eines
# umlautfreien Wortes allein reicht nicht — deshalb das Lexikon.
DE_WORDS = set("""
der die das den dem des und oder nicht kein keine keinen keinem keiner wird
werden wurde wurden ist sind war waren für mit von vom auf aus bei nach über
unter noch jetzt schon nur alle alles mehr weniger sich beim wenn dann damit
bereits zuletzt diese dieser dieses diesen deine deinen dein meine meinen mein
eigene eigenen eigenes höchste auch aber als wie was wer wo wann warum welcher
welche welches ein eine einer einem einen eines im am an zum zur bis seit
während ohne gegen vor durch doch mal sehr viele wenige nichts etwas andere
anderen beide beides jeweils je ca etwa ungefähr insgesamt bitte danke gern
trotzdem wieder weiter zurück vorher nachher heute gestern morgen gleich bald
lädt laden lade geladen gespeichert speichern speichere gesetzt setzen setze
löschen gelöscht löscht abbrechen abgebrochen schließen geschlossen anlegen
angelegt anmelden angemeldet registrieren registriert aktualisieren aktualisiert
suchen gesucht senden gesendet nutzen genutzt nutzt anbieten angeboten bietet
entspricht entsprechen fehlgeschlagen erforderlich gesperrt pausiert pausieren
freigeben freigegeben freigabe ablehnen abgelehnt ausstehend genehmigt aktiviert
deaktiviert umschalten umgeschaltet gewählt ausgewählt auswählen angezeigt
anzeigen verbergen kopiert kopieren gelungen veraltet herzschlag bestand rechner
auslastung guthaben stundensatz kennwort absender absenderadresse absendername
benachrichtigung sicherheit werkzeuge werkzeug betrieb zustand aktion aktionen
ziel zeit zeitraum antwort antworten nachricht nachrichten unterhaltung verlauf
eintrag einträge zeile zeilen spalte spalten konten rollen besitzer adresse
adressen quelle protokoll gerät geräte schlüssel schlüsselwert nutzer nutzende
nutzung nutzerfilter stunde stunden tag tage woche monat jahr minute sekunden
stück anzahl menge summe anteil gesamt gesamtzahl rest restliche weitere kurz
kurze neue neuer neues neuester neueste letzte letzter letztes aktuell aktuelle
aktuelles aktives inaktiv gesperrte freie freien lokal lokale lokalen möglich
nötig nötigen falsch richtig zeichen zeichenfolge haken feld felder knopf taste
liste auswahl eingabe ausgabe ansicht bereich schritt schritte fenster leiste
frist dauer seite seitig stand manuell gesehen gemeldet gemeldete einmalig
sichtbar unsichtbar verfügbar verfügbarkeit dauerbetrieb zeitweise hochladen
herunterladen heruntergeladen hochgeladen löschung anmeldung registrierung
bestätigung bestätigen bestätigt abfrage abfragen aufforderung hinweis hinweise
meldung meldungen warnung fehler fehlermeldung speicherung ladung verbindung
verbindungen deaktivieren aktivieren entfernen entfernt hinzufügen hinzugefügt
ändern ändert geändert ausfüllen ausgewählte ausgewählten gewählte gewählten
gespeicherte angelegte angelegten ausgestellte ungültig gültig abziehen aufladen
aufgeladen gutschrift gutgeschrieben vorgemerkt simulieren freigeschaltet
einschränken abgerechnet abo mindestlaufzeit nebenbei gesamtkosten prozent
stückzahl dateien ordner gemeldeten erklärt erkläre schreibe gib drei ideen
sätze sätzen nebenprojekt nein antwortet gerade beginnt startet starten weitere weiteres zeigt zeigen waehlen wählen oeffnen öffnet verschwindet
""".split())
DE_SUFFIX = re.compile(
    r"(ung|ungen|lich|liche|licher|liches|lichen|keit|keiten|heit|heiten|isch"
    r"|ische|ischer|isches|ischen|iert|ierte|ierten|iertes|ieren|schaft"
    r"|schaften|zeug|zeuge|zeugen|zahl|zahlen|nahme|nahmen|weise|weisen|sicht"
    r"|sichten|seite|seiten|feld|felder|liste|listen|satz|sätze|ständig|mäßig)$",
    re.I)
DE_PARTIZIP = re.compile(
    r"^(?:ab|an|auf|aus|bei|ein|fest|her|hin|los|mit|nach|vor|weg|weiter|zu"
    r"|zurück|zusammen)?ge[\wäöüß]{2,}(?:t|en|elt)$", re.I)
DE_INFINITIV = re.compile(
    r"^(?:ab|an|auf|aus|bei|ein|fest|her|hin|los|mit|nach|vor|weg|weiter|zu"
    r"|zurück|zusammen)[\wäöüß]{2,}(?:en|ern|eln)$", re.I)
UMLAUT = re.compile(r"[äöüßÄÖÜ]")


def german_words(text):
    """Deutsche Wörter im Text; leer heißt: kein Deutsch."""
    hits = []
    for t in WORD.findall(text):
        base = t.strip(".,:;!?()[]\"'")
        if not base:
            continue
        if UMLAUT.search(base):
            hits.append(base)
            continue
        low = base.lower()
        if low in TERMS or low in BRAND:
            continue
        if low in DE_WORDS or DE_SUFFIX.search(low) \
                or DE_PARTIZIP.match(low) or DE_INFINITIV.match(low):
            hits.append(base)
    return hits


# ------------------------------------------------------------------ Markup-Läufer
def iter_segments(src):
    """(kind, start, end, tag, attrs) — kind: open/close/text/raw/other."""
    i, n = 0, len(src)
    while i < n:
        if src[i] == "<":
            if src.startswith("<!--", i):
                j = src.find("-->", i)
                j = n if j < 0 else j + 3
                yield ("other", i, j, "", "")
                i = j
                continue
            if src.startswith("<!", i) or src.startswith("<?", i):
                j = src.find(">", i)
                j = n if j < 0 else j + 1
                yield ("other", i, j, "", "")
                i = j
                continue
            j, q = i + 1, None
            while j < n:
                c = src[j]
                if q:
                    if c == q:
                        q = None
                elif c in "\"'":
                    q = c
                elif c == ">":
                    break
                j += 1
            raw = src[i:j + 1]
            m = re.match(r"<\s*(/?)\s*([a-zA-Z][\w:-]*)", raw)
            if not m:
                yield ("other", i, j + 1, "", "")
                i = j + 1
                continue
            name = m.group(2).lower()
            if m.group(1):
                yield ("close", i, j + 1, name, raw[m.end():])
                i = j + 1
                continue
            yield ("open", i, j + 1, name, raw[m.end():])
            i = j + 1
            if name in RAW:
                end = src.lower().find("</" + name, i)
                end = n if end < 0 else end
                yield ("raw", i, end, name, "")
                i = end
            continue
        j = src.find("<", i)
        j = n if j < 0 else j
        yield ("text", i, j, "", "")
        i = j


def walk(src):
    stack = []      # [(tag, keyed)]
    for kind, s, e, tag, attrs in iter_segments(src):
        if kind == "open":
            keyed = bool(KEYATTR.search(attrs))
            if not (attrs.rstrip().endswith("/>") or tag in VOID):
                stack.append((tag, keyed))
            continue
        if kind == "close":
            for k in range(len(stack) - 1, -1, -1):
                if stack[k][0] == tag:
                    del stack[k:]
                    break
            continue
        if kind != "text":
            continue
        covered = any(k for _, k in stack) or any(t in NOT_TEXT for t, _ in stack)
        yield dict(start=s, end=e, tag=(stack[-1][0] if stack else ""),
                   text=src[s:e], covered=covered)


# ------------------------------------------------------- Prüfung 1: Markuptext
def audit_markup():
    """Ungedeckter sichtbarer Text, der nicht nur aus freigegebenen Wörtern besteht."""
    problems = []
    for p in sorted(FE.glob("*.html")):
        if p.name in LOCALE_BLOCK_PAGES:
            continue
        src = p.read_text()
        for nd in walk(src):
            if nd["covered"]:
                continue
            body = " ".join(nd["text"].split())
            if not body:
                continue
            if re.fullmatch(r"[#./][\w./:#?=&%-]*", body):
                continue                      # Pfad/Kennung, kein Satz
            foreign = []
            for t in WORD.findall(body):
                base = t.strip(".,:;!?()[]\"'-")
                if not base or base.isdigit() or len(base) < 2:
                    continue
                low = base.lower()
                if low in TERMS or low in BRAND or low in CODE_STRINGS:
                    continue
                foreign.append(base)
            if not foreign:
                continue
            ln = src[:nd["start"]].count("\n") + 1
            problems.append((p.name, ln, nd["tag"], body[:90], foreign[:6]))
    return problems


# ------------------------------------------------- Prüfung 2: sichtbare Attribute
def audit_attrs():
    """placeholder/title/aria-label/alt mit deutschem Wert und ohne data-i18n-<attr>."""
    problems = []
    for p in sorted(FE.glob("*.html")):
        if p.name in LOCALE_BLOCK_PAGES:
            continue
        src = p.read_text()
        for kind, s, e, tag, attrs in iter_segments(src):
            if kind != "open":
                continue
            for am in re.finditer(r'\b(placeholder|title|aria-label|alt)="([^"]*)"', attrs):
                attr, val = am.group(1), am.group(2).strip()
                if len(val) < 3:
                    continue
                if not german_words(val) and val.lower() not in DE_WORDS:
                    continue
                if re.search(rf"data-i18n-{attr}=", attrs):
                    continue
                ln = src[:s].count("\n") + 1
                problems.append((p.name, ln, f"<{tag} {attr}>", val[:80]))
    return problems


# ------------------------------------------------------------ Prüfung 3: JS-Literale
def strip_js_comments(src):
    out, i, n, state = [], 0, len(src), None
    while i < n:
        c = src[i]
        if state is None:
            if c in "\"'`":
                state = c
                out.append(c)
                i += 1
                continue
            if src.startswith("//", i):
                j = src.find("\n", i)
                j = n if j < 0 else j
                out.append("\n" * src.count("\n", i, j))
                i = j
                continue
            if src.startswith("/*", i):
                j = src.find("*/", i)
                j = n if j < 0 else j + 2
                out.append("\n" * src.count("\n", i, j))
                i = j
                continue
            out.append(c)
            i += 1
            continue
        if c == "\\":
            out.append(src[i:i + 2])
            i += 2
            continue
        if c == state:
            state = None
        out.append(c)
        i += 1
    return "".join(out)


JS_LITERAL = re.compile(r"""(['"`])((?:\\.|(?!\1)[^\\])*)\1""", re.S)
I18N_CALL = re.compile(r"""I18n\.t\(\s*(['"])([^'"\n]+)\1""")
I18N_ANY = re.compile(r"""I18n\.t\(\s*['"][^'"\n]*['"]""")
HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
# Was offensichtlich Code ist: URL, Pfad, Dateiname, Selektor, Kennung.
CODEISH = re.compile(
    r"^(?:[#.][\w-]+"                                   # Selektor/Klasse
    r"|[\w-]+(?:\.[\w-]+)+"                            # Dateiname
    r"|[\w./:${}?=&%-]*/[\w./:${}?=&%-]*"               # Pfad/URL
    r"|\d+[a-z]*"                                        # Zahl
    r"|[\w-]*[-_][\w-]*"                                # Kennung mit Trenner
    r"|(?:GET|POST|PUT|PATCH|DELETE|OPTIONS)\b.*)$")


def _scan_literals(text, where, label, problems):
    clean = strip_js_comments(text)
    clean = HTML_COMMENT.sub(" ", clean)
    clean = I18N_ANY.sub("I18n.t(@)", clean)
    for m in JS_LITERAL.finditer(clean):
        lit = m.group(2)
        val = lit.strip()
        if len(val) < 3 or val in CODE_STRINGS:
            continue
        # Variablennamen in ${...} sind kein Anzeigetext.
        val = re.sub(r"\$\{[^}]*\}", " ", val)
        if CODEISH.match(val):
            continue
        words = german_words(val)
        if not words:
            continue
        ln = where + clean[:m.start()].count("\n") + 1
        problems.append((label, ln, words[:6], lit[:90]))


def audit_js():
    """Deutsche String-Literale in *.js, inline <script> und Alpine-Ausdrücken."""
    problems = []
    for p in sorted(FE.glob("*.js")):
        if p.name in SKIP_JS:
            continue
        _scan_literals(p.read_text(), 0, p.name, problems)
    for p in sorted(FE.glob("*.html")):
        if p.name in LOCALE_BLOCK_PAGES:
            continue
        src = p.read_text()
        for sm in re.finditer(r"<script\b[^>]*>(.*?)</script>", src, re.S):
            _scan_literals(sm.group(1), src[:sm.start(1)].count("\n"),
                           p.name + ":script", problems)
        for kind, s, e, tag, attrs in iter_segments(src):
            if kind != "open":
                continue
            for am in re.finditer(r'([\w:@.\[\]-]+)="([^"]*)"', attrs):
                attr, expr = am.group(1), am.group(2)
                if attr.startswith("data-i18n") or attr in ("class", "style", "href",
                                                            "src", "id", "x-for", "x-data"):
                    continue
                _scan_literals(expr, src[:s].count("\n"),
                               f"{p.name}:{attr}", problems)
    return problems


# ---------------------------------------------------- Sprachblock-Seiten (Prüfung 0)
def audit_locale_blocks(p):
    src = p.read_text()
    problems = []
    # <head> ist keine Seitenfläche: der <title> dieser Seiten steht in der
    # Ausgangssprache, weil guide.html ohne JS und ohne Katalog lesbar sein muss
    # (eigener Mechanismus: <div lang>-Blöcke im Body).
    head_end = src.lower().find("</head")
    head_end = 0 if head_end < 0 else head_end
    stack = []
    in_lang = 0
    i = 0
    while i < len(src):
        if src[i] == "<":
            m = TAG.match(src, i)
            if not m:
                i += 1
                continue
            tagtxt = m.group(0)
            tm = re.match(r"<\s*(/?)\s*([a-zA-Z][\w-]*)", tagtxt)
            if not tm:
                i = m.end()
                continue
            closing, tag = tm.group(1) == "/", tm.group(2).lower()
            if closing:
                if stack and stack.pop():
                    in_lang -= 1
                i = m.end()
                continue
            if tag in ("script", "style"):
                end = src.lower().find(f"</{tag}", m.end())
                i = src.find(">", end) + 1 if end > 0 else m.end()
                continue
            has_lang = False if tag == "html" else bool(re.search(r'\blang="', tagtxt))
            if not (tagtxt.rstrip().endswith("/>") or tag in VOID):
                stack.append(has_lang)
                if has_lang:
                    in_lang += 1
            i = m.end()
            continue
        nxt = src.find("<", i)
        if nxt < 0:
            nxt = len(src)
        body = " ".join(src[i:nxt].split())
        if i < head_end:
            i = nxt
            continue
        if body and in_lang == 0 and len(body) >= 3:
            words = german_words(body)
            if words:
                ln = src[:i].count("\n") + 1
                problems.append((p.name, ln, body[:90]))
        i = nxt
    return problems


# ------------------------------------------------------------- Prüfung 4: Katalog
def audit_catalog():
    cat = (FE / "i18n-catalog.js").read_text()
    data = json.loads(cat.split("window.GP_I18N = ", 1)[1].rstrip().rstrip(";"))
    keys = data["catalog"]
    locales = data["locales"]
    missing = []
    for p in sorted(FE.glob("*.html")):
        src = p.read_text()
        for m in re.finditer(r'data-i18n(?:-html|-placeholder|-title|-aria-label)?="([^"]+)"', src):
            if m.group(1) not in keys:
                missing.append((p.name, m.group(1)))
        for m in re.finditer(r'[a-z-]+-i18n="([^"]+)"', src):
            k = m.group(1)
            if k and k not in keys:
                missing.append((p.name, "alt:" + k))
    for p in sorted(FE.glob("*.js")):
        if p.name in SKIP_JS:
            continue
        for m in I18N_CALL.finditer(p.read_text()):
            k = m.group(2)
            if k.endswith((".", "_")):
                continue
            if k not in keys:
                missing.append((p.name, k))
    incomplete = [k for k, v in keys.items() if set(v) != set(locales)
                  or any(not v[loc] for loc in locales)]
    cjk = [k for k, v in keys.items() if any(CJK.search(x) for x in v.values())]
    return keys, locales, missing, incomplete, cjk


def main():
    print("=== 0. Seiten mit <div lang>-Blöcken ===")
    block_probs = []
    for name in sorted(LOCALE_BLOCK_PAGES):
        found = audit_locale_blocks(FE / name)
        for f, ln, body in found:
            print(f"  {f}:{ln}  {body!r}")
        print(f"  {name}: {len(found)} Textstellen außerhalb eines Sprachblocks")
        block_probs += found

    print("\n=== 1. sichtbarer Markuptext ohne Schlüssel ===")
    probs = audit_markup()
    for f, ln, tag, body, foreign in probs:
        print(f"  {f}:{ln}  <{tag}>  {body!r}  [{', '.join(foreign)}]")
    print(f"  -> {len(probs)} findings")

    print("\n=== 1b. Warnung: Fachbegriff im Markup ohne Schlüssel, der übersetzt wird ===")
    warn = []
    for p in sorted(FE.glob("*.html")):
        if p.name in LOCALE_BLOCK_PAGES:
            continue
        src = p.read_text()
        for nd in walk(src):
            if nd["covered"]:
                continue
            body = " ".join(nd["text"].split())
            hits = sorted({w.lower().strip(".,:;!?()[]\"'-")
                           for w in WORD.findall(body)} & TERMS_THAT_TRANSLATE)
            if hits:
                ln = src[:nd["start"]].count("\n") + 1
                warn.append((p.name, ln, body[:60], hits))
    for f, ln, body, hits in warn:
        print(f"  WARNUNG {f}:{ln}  {body!r}  [{', '.join(hits)}]")
    print(f"  -> {len(warn)} Stellen (kein Gate-Kriterium, siehe TERMS_THAT_TRANSLATE)")

    print("\n=== 2. sichtbare Attribute ohne Schlüssel ===")
    aps = audit_attrs()
    for f, ln, a, val in aps:
        print(f"  {f}:{ln}  {a}=  {val!r}")
    print(f"  -> {len(aps)} findings")

    print("\n=== 3. deutsche String-Literale in Anwendungs-JS ===")
    jss = audit_js()
    for f, ln, words, lit in jss:
        print(f"  {f}:{ln}  [{', '.join(words)}]  {lit!r}")
    print(f"  -> {len(jss)} findings")

    print("\n=== 4. Katalogauflösung ===")
    keys, locales, missing, incomplete, cjk = audit_catalog()
    print(f"  keys: {len(keys)}   locales: {locales}")
    for f, k in missing:
        print(f"  UNRESOLVED {f}: {k}")
    for k in incomplete[:10]:
        print(f"  INCOMPLETE {k}")
    for k in cjk[:5]:
        print(f"  CJK {k}")
    print(f"  -> {len(missing)} unresolved, {len(incomplete)} incomplete, {len(cjk)} CJK")

    ok = not probs and not aps and not jss and not missing and not incomplete \
        and not cjk and not block_probs
    total = len(probs) + len(aps) + len(jss) + len(missing) + len(incomplete) \
        + len(cjk) + len(block_probs)
    print(f"\nFundstellen gesamt: {total}")
    print("GATE:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
