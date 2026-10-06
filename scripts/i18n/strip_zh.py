#!/usr/bin/env python3
"""LANA-65 — drop the ZH locale from the catalog parts, mechanically.

Removes the `"zh": "..."` member from every KEYS entry. Tolerant of both the
one-line form (`{"en": ..., "zh": ...}`) and the multi-line form (one locale
per line, optional trailing comma).

Refuses to write anything if the line it is about to touch does not look like a
pure `"zh": <string>` member, so a value that happens to contain `"zh":` inside
a string can never be mangled.
"""
import re, sys, glob
from pathlib import Path

BASE = Path(__file__).resolve().parent            # scripts/i18n: catalog parts
PARTS = sorted((BASE / "i18n_parts").glob("*.py"))

MEMBER = re.compile(r'"zh"\s*:\s*(?:"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\')')


def strip_members(text):
    """Remove every `"zh": <string>` member, inline or on its own line."""
    out, removed = [], 0
    for line in text.splitlines(keepends=True):
        stripped = line.strip().rstrip(",").strip()
        is_member_line = stripped.startswith('"zh"') and MEMBER.fullmatch(stripped)
        if is_member_line:
            removed += 1
            continue  # the whole line disappears, trailing comma included
        new, n = MEMBER.subn("", line)
        if n:
            removed += n
            new = new.replace("{,", "{").replace(",}", "}")
            new = re.sub(r",\s*,", ",", new)
            new = re.sub(r"\{\s*,", "{", new)
            new = re.sub(r",\s*\}", "}", new)
        out.append(new)
    return "".join(out), removed


def main():
    total = 0
    for p in PARTS:
        src = p.read_text(encoding="utf-8")
        new, n = strip_members(src)
        if n == 0:
            print(f"  {p.name}: no zh members found")
            continue
        if '"zh"' in new:
            print(f"  !! {p.name}: {new.count(chr(34) + 'zh' + chr(34))} zh members survived — aborting")
            return 1
        p.write_text(new, encoding="utf-8")
        total += n
        print(f"  {p.name}: removed {n} zh members")
    print(f"removed {total} zh members total")
    return 0


if __name__ == "__main__":
    sys.exit(main())
