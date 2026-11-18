"""Windows-Skripte müssen reines ASCII sein.

PowerShell 5.1 liest eine `.ps1` ohne BOM als ANSI. Ein Umlaut oder Gedankenstrich im Skript wird
dann zu Buchstabensalat — im schlimmsten Fall in einem Variablennamen, was den Parser mit
„Unexpected token" abbricht. Genau das ist passiert: aus `$laeuft` wurde `$l\u00e4uft`, und der
Installer war auf Windows unbrauchbar.

Der Test hält die Skripte ASCII-rein. Wer Umlaute braucht, speichert die Datei mit BOM oder setzt
PowerShell 7 voraus — beides ist hier nicht der Fall, deshalb ASCII.
"""

import pathlib

BASIS = pathlib.Path(__file__).resolve().parent.parent
SKRIPTE = [
    BASIS / "frontend-alpine" / "downloads" / "install.ps1",
    BASIS / "frontend-alpine" / "downloads" / "install-from-source.ps1",
    BASIS / "node-agent" / "build.ps1",
]


def test_ps1_dateien_sind_reines_ascii():
    verstoesse = []
    for p in SKRIPTE:
        if not p.is_file():
            verstoesse.append(f"{p.name}: fehlt")
            continue
        text = p.read_text(encoding="utf-8")
        schlecht = sorted({z for z in text if ord(z) > 127})
        if schlecht:
            zeilen = [str(nr) for nr, z in enumerate(text.splitlines(), 1) if any(ord(c) > 127 for c in z)]
            verstoesse.append(f"{p.name}: {schlecht} in Zeile(n) {', '.join(zeilen[:6])}")
    assert not verstoesse, (
        "Nicht-ASCII in PowerShell-Skripten (PS 5.1 ohne BOM liest sie als ANSI): " + "; ".join(verstoesse)
    )
