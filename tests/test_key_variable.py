"""Schluessel-Variable muss in allen Bloecken dieselbe sein.

In PowerShell sind `$accountKey` und `$ACCOUNT_KEY` zwei verschiedene Variablen (der Unterstrich
trennt, nicht die Schreibweise). Genau daran scheiterte der Installer: der Pruefblock las eine leere
Variable, meldete "0 Zeichen", schickte einen leeren Schluessel an /v1/me und erhielt 401 - obwohl
der eingegebene Schluessel gueltig war. Der Test verlangt eine einheitliche Schreibweise.
"""

import pathlib
import re

SKRIPT = pathlib.Path(__file__).resolve().parent.parent / "frontend-alpine" / "downloads" / "install-from-source.ps1"


def test_schluessel_variable_einheitlich():
    text = SKRIPT.read_text(encoding="utf-8")
    # Die Variable, die per Read-Host bzw. aus KeyFile/env gefuellt wird:
    assert "$accountKey =" in text, "erwartete Zuweisung an $accountKey fehlt"
    # Keine zweite Schreibweise derselben Variable:
    fremde = sorted(set(re.findall(r"\$(ACCOUNT_KEY|AccountKey|accountkey)\b", text)))
    assert not fremde, (
        "andere Schreibweise derselben Variable gefunden: "
        + ", ".join(fremde)
        + " - das ist in PowerShell eine andere Variable und liest einen leeren Wert"
    )


def test_pruefung_nutzt_dieselbe_variable():
    text = SKRIPT.read_text(encoding="utf-8")
    # Die Pruefung gegen /v1/me muss den eingegebenen Schluessel verwenden
    zeile = [z for z in text.splitlines() if "v1/me" in z and "Invoke-RestMethod" in z]
    assert zeile, "Aufruf von /v1/me fehlt"
    assert "accountKey" in zeile[0], "Pruefung verwendet nicht $accountKey: " + zeile[0].strip()[:90]
