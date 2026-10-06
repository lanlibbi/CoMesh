#!/usr/bin/env python3
"""LANA-63/LANA-65 — coverage audit: find user-visible German text in the rendered markup
that did NOT get a data-i18n key, and check that every data-i18n key resolves in
the shipped catalog.

This is the acceptance gate for "all views complete". It reads the *shipped* files
(HTML + i18n-catalog.js), not the intermediate extraction state.
"""
import json, re, sys
from pathlib import Path

FE = Path(__file__).resolve().parents[2] / "frontend-alpine"

# German markers: umlauts, sharp s, or common German function words.
GERMAN = re.compile(
    r"[äöüßÄÖÜ]|"
    r"\b(der|die|das|den|dem|des|und|oder|nicht|kein|keine|keinen|wird|werden|wurde|"
    r"ist|sind|für|mit|von|vom|auf|aus|bei|nach|über|unter|noch|jetzt|schon|nur|"
    r"alle|alles|mehr|weniger|Lädt|Fehler|Anmeldung|Konto|Passwort|Nutzer|Zeitraum|"
    r"Modell|Modelle|Status|Setze|Bitte|Danke|Speichern|Löschen|Abbrechen|Schließen|"
    r"Gesamt|Anfrage|Anteil|Einträge|Stunden|Tage|eigene|eigenen|höchste|deine|deinen|"
    r"meine|meinen|dieser|diese|dieses|sich|beim|wenn|dann|damit|bereits|zuletzt)\b",
    re.I)

# Text that is not UI copy: code samples, ids, units, keys, symbols.
IGNORE = re.compile(
    r"^(?:[\s\W]*|"
    r"[A-Za-z0-9_./:{}<>\-]*|"                       # identifiers, paths
    r"#.*|"                                          # comments
    r".*(?:https?://|/v1/|/api/|localhost|\.html|\.js|\.css|Bearer|curl|docker|npm|"
    r"tailscale|Tailscale|ollama|Ollama|compose|GET |POST |PUT |DELETE ).*"
    r")$")


def strip_html(s):
    return re.sub(r"<[^>]+>", " ", s)


def audit_markup():
    """Text nodes with no data-i18n ancestor and no x-text, that look German."""
    problems = []
    for p in sorted(FE.glob("*.html")):
        src = p.read_text()
        # walk elements: find tags and whether they carry data-i18n
        for m in re.finditer(r"<([a-zA-Z][\w-]*)\b([^>]*)>([^<]*)", src):
            tag, attrs, text = m.group(1), m.group(2), m.group(3)
            if tag.lower() in ("script", "style", "title"):
                continue
            if not text.strip():
                continue
            if "data-i18n" in attrs or "x-text" in attrs or "x-html" in attrs:
                continue
            body = strip_html(text).strip()
            if len(body) < 3:
                continue
            if IGNORE.match(body):
                continue
            if GERMAN.search(body):
                ln = src[:m.start()].count("\n") + 1
                problems.append((p.name, ln, tag, body[:100]))
    return problems


def audit_attrs():
    """placeholder/title/aria-label values that are German but unkeyed."""
    problems = []
    for p in sorted(FE.glob("*.html")):
        src = p.read_text()
        for m in re.finditer(r'<(?:input|textarea|button|img|a|div|select)\b([^>]*)>', src):
            attrs = m.group(1)
            for am in re.finditer(r'\b(placeholder|title|aria-label)="([^"]*)"', attrs):
                val = am.group(2).strip()
                if len(val) < 3 or IGNORE.match(val) or not GERMAN.search(val):
                    continue
                keyed = re.search(
                    rf'\b(placeholder|title|aria-label)-i18n="[^"]*"', attrs)
                if not keyed:
                    ln = src[:m.start()].count("\n") + 1
                    problems.append((p.name, ln, am.group(1), val[:80]))
    return problems


def audit_catalog():
    cat = (FE / "i18n-catalog.js").read_text()
    data = json.loads(cat.split("window.GP_I18N = ", 1)[1].rstrip().rstrip(";"))
    keys = data["catalog"]
    locales = data["locales"]
    missing = []
    for p in sorted(FE.glob("*.html")):
        src = p.read_text()
        for m in re.finditer(r'data-i18n(?:-html)?="([^"]+)"', src):
            k = m.group(1)
            if k not in keys:
                missing.append((p.name, k))
        for m in re.finditer(r'[a-z-]+-i18n="([^"]+)"', src):
            k = m.group(1)
            if k not in keys and k != "":
                missing.append((p.name, m.group(0).split("=")[0] + ":" + k))
    # every key must carry every locale
    incomplete = [k for k, v in keys.items() if set(v) != set(locales)]
    return keys, locales, missing, incomplete


def main():
    print("=== 1. unkeyed German text in markup ===")
    probs = audit_markup()
    for f, ln, tag, body in probs:
        print(f"  {f}:{ln}  <{tag}>  {body!r}")
    print(f"  -> {len(probs)} findings")

    print("\n=== 2. unkeyed German attributes ===")
    aps = audit_attrs()
    for f, ln, a, val in aps:
        print(f"  {f}:{ln}  {a}=  {val!r}")
    print(f"  -> {len(aps)} findings")

    print("\n=== 3. catalog resolution ===")
    keys, locales, missing, incomplete = audit_catalog()
    print(f"  keys: {len(keys)}   locales: {locales}")
    for f, k in missing:
        print(f"  UNRESOLVED {f}: {k}")
    print(f"  -> {len(missing)} unresolved, {len(incomplete)} incomplete entries")

    ok = not probs and not aps and not missing and not incomplete
    print("\nGATE:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
