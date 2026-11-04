#!/usr/bin/env python3
"""LANA-63/LANA-65 — assemble i18n-catalog.js from i18n_parts/*.py and verify coverage.

Scope (LANA-65, binding decision by Christian 2026-09-29): exactly four locales,
EN (default), DE, ES, FR. PT and ZH are NOT implemented — ZH was built in
LANA-63 and has been removed here.

Checks performed (all must pass before the catalog is written):
  1. every key used by the markup (data-i18n / data-i18n-html / data-i18n-*)
     exists in the catalog;
  2. every catalog key is used somewhere (markup or code) — catches typos;
  3. every entry has all four locales, non-empty;
  4. the DE value of a markup key equals the string still present in the markup
     (so a "translation" that silently changed the German text is caught);
  5. html-mode entries' markup tags are identical across locales — a translator
     may not add or drop an element;
  6. no catalog value carries a character outside the supported scripts (a
     leftover CJK string would render as tofu without a CJK font fallback).
"""
import json, re, sys, importlib.util
from pathlib import Path

BASE = Path(__file__).resolve().parent            # scripts/i18n: parts + build inputs
FE = Path(__file__).resolve().parents[2] / "frontend-alpine"
LOCALES = ["en", "de", "es", "fr"]

META = [
    {"code": "en", "label": "English"},
    {"code": "de", "label": "Deutsch"},
    {"code": "es", "label": "Español"},
    {"code": "fr", "label": "Français"},
]

# CJK ideographs, CJK punctuation and full-width forms: no supported locale
# needs them, and style.css ships no CJK font fallback.
CJK = re.compile(r"[\u2e80-\u9fff\u3000-\u303f\uff00-\uffef]")


def load_parts():
    cat = {}
    for p in sorted((BASE / "i18n_parts").glob("*.py")):
        spec = importlib.util.spec_from_file_location(p.stem, p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for k, v in mod.KEYS.items():
            if k in cat and cat[k] != v:
                print(f"  !! key {k} redefined with a different value in {p.name}")
            cat[k] = v
    return cat


def norm(s):
    """Collapse whitespace, including the NBSP the markup uses before units."""
    return " ".join(s.replace("\u00a0", " ").replace("\u202f", " ").split())


def used_keys():
    """key -> (source string, kind) as referenced from the markup."""
    used = {}
    for p in sorted(FE.glob("*.html")):
        s = p.read_text()
        for m in re.finditer(r'data-i18n-html="([^"]+)"', s):
            used[m.group(1)] = ("html", p.name)
        for m in re.finditer(r'data-i18n-(?:placeholder|title|aria-label)="([^"]+)"', s):
            used.setdefault(m.group(1), ("attr", p.name))
        for m in re.finditer(r'data-i18n="([^"]+)"', s):
            used.setdefault(m.group(1), ("text", p.name))
    return used


# A literal argument to I18n.t(...) in either quote style. Double quotes were
# the only ones counted until 04.11.2026; single-quoted calls are the house
# style in the Alpine markup (x-text="I18n.t('verbergen')"), so their keys
# looked unreferenced and were pruned — the page then rendered the raw key in
# every locale. Both styles are the same call and must count the same.
I18N_CALL = re.compile(r"""I18n\.t\(\s*(["'])([^"'\n]+)\1""")


def code_refs_from(pages):
    """Literal keys the JS/HTML asks for, split into exact keys and prefixes.

    `I18n.t("admin.quota." + mode)` ends on a separator: it references a whole
    family, not one key. Those are checked separately so a missing family is
    reported instead of silently rendering raw keys.
    """
    exact, prefixes = set(), set()
    for p in pages:
        for m in I18N_CALL.finditer(p.read_text()):
            key = m.group(2)
            if key.endswith(".") or key.endswith("_"):
                prefixes.add((key, p.name))
            else:
                exact.add(key)
    return exact, prefixes


def main():
    cat = load_parts()
    used = used_keys()
    errs = []

    # 1 + 2 — coverage both ways
    missing = sorted(k for k in used if k not in cat)
    if missing:
        errs.append(f"{len(missing)} markup keys without a translation: {missing}")

    # keys referenced only from code
    code_refs, dynamic_prefixes = code_refs_from(list(FE.glob("*.js")) + list(FE.glob("*.html")))
    # A key the code asks for but the catalog does not carry renders as the raw
    # key name in every locale — that is just as broken as missing markup text.
    unlit = sorted(k for k in code_refs if k not in cat)
    if unlit:
        errs.append(f"{len(unlit)} code keys without a translation: {unlit}")
    for pref, page in sorted(dynamic_prefixes):
        family = [k for k in cat if k.startswith(pref)]
        if not family:
            errs.append(f'{page}: I18n.t("{pref}" + …) matches no catalog key')
        # The family is reachable through the prefix; keep it through pruning.
        code_refs |= set(family)
    # keys the code applies through a variable (window.titleKey, nav items, ...)
    code_refs |= set(json.loads((BASE / "keys.json").read_text()).keys())
    # Unreferenced entries are pruned rather than kept as dead weight: a key that
    # no markup and no code asks for would silently rot. They are reported so a
    # rename that missed the markup still shows up in the build output.
    orphan = sorted(k for k in cat if k not in used and k not in code_refs)
    for k in orphan:
        cat.pop(k, None)

    # 3 — completeness
    for k, v in cat.items():
        for loc in LOCALES:
            if not v.get(loc):
                errs.append(f"key {k} missing locale {loc}")

    # 4 + 5 — German fidelity and markup stability
    src = json.loads((BASE / "catalog-source.json").read_text())["keys"]
    bad_de, bad_tags = [], []
    for k, (kind, page) in used.items():
        if k not in cat or k not in src:
            continue
        expected = norm(src[k]["src"])
        got = norm(cat[k]["de"])
        if kind == "text":
            # the element text may carry leading/trailing whitespace in source
            exp_inner = " ".join(re.sub(r"<[^>]+>", "", expected).split())
            got_inner = " ".join(re.sub(r"<[^>]+>", "", got).split())
            if exp_inner != got_inner:
                bad_de.append((k, exp_inner[:70], got_inner[:70]))
        if kind == "html":
            tags = {loc: tuple(re.findall(r"</?[a-zA-Z][^>]*>", v)) for loc, v in cat[k].items()}
            ref = tags["de"]
            for loc, t in tags.items():
                if t != ref:
                    bad_tags.append((k, loc, ref, t))
    if bad_de:
        errs.append(f"{len(bad_de)} German values diverge from the markup text")
    if bad_tags:
        errs.append(f"{len(bad_tags)} html entries where locales disagree on markup")

    # 6 — script scope: nothing but latin/cyrillic-free latin text may ship.
    cjk_hits = [(k, loc) for k, v in cat.items() for loc, val in v.items() if CJK.search(val)]
    if cjk_hits:
        errs.append(f"{len(cjk_hits)} catalog values carry CJK characters: {cjk_hits[:5]}")

    print(f"catalog keys: {len(cat)}   markup keys used: {len(used)}   code refs: {len(code_refs)}")
    if orphan:
        print(f"  pruned {len(orphan)} unreferenced entries: {orphan}")
    for e in errs:
        print("  ERROR:", e)
    for k, a, b in bad_de[:12]:
        print(f"   de-mismatch {k}: markup={a!r} catalog={b!r}")
    for k, loc, ref, t in bad_tags[:6]:
        print(f"   tag-mismatch {k} [{loc}]: de={ref} {loc}={t}")

    if errs:
        print("\nNOT writing the catalog — fix the errors above.")
        return 1

    body = json.dumps({"locales": LOCALES, "meta": META, "catalog": cat},
                      ensure_ascii=False, indent=1)
    out = (FE / "i18n-catalog.js").write_text(
        "// CoMesh — string catalog for the supported languages.\n"
        "// Generated from i18n_parts/*.py; do not hand-edit here, the coverage\n"
        "// checks in build_catalog.py are what keep markup and catalog in sync.\n"
        "//\n"
        "// Scope: exactly EN (default), DE, ES, FR. PT and ZH are deliberately NOT\n"
        "// implemented (LANA-65) — do not add a locale without that decision being\n"
        "// re-made and the four-locale check in build_catalog.py being updated.\n"
        "//\n"
        "// Fachbegriffe (Node, Token, Model, API-Key, Pool, Provider,\n"
        "// Owner, Treasury, VRAM, Tailscale) are deliberately identical in every\n"
        "// locale — that is the product rule, not missing translations.\n"
        "window.GP_I18N = " + body + ";\n")
    print(f"\nwrote i18n-catalog.js ({len(cat)} keys x {len(LOCALES)} locales)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
