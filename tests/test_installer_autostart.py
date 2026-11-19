"""Waechter: der Autostart im Installer darf nur EINEN Weg haben.

Hintergrund: Auf einer Kundenmaschine starteten nach der Installation zwei Agenten. Ursache waren
zwei Autostart-Pfade mit drei Namen ("CoMesh Agent" als Aufgabe, "CoMesh Agent" und "CoMeshAgent"
im Run-Schluessel) — der jeweils andere Eintrag blieb stehen.

Dieser Test liest das PowerShell-Skript als Text und haelt die Struktur fest. Er ersetzt keinen
Test auf Windows, verhindert aber, dass die Doppelung zurueckkommt.
"""

import re
from pathlib import Path

SKRIPT = Path(__file__).resolve().parents[1] / "frontend-alpine" / "downloads" / "install-from-source.ps1"


def _text() -> str:
    return SKRIPT.read_text(encoding="utf-8")


def test_genau_ein_autostart_weg():
    """Nur eine Stelle legt die Aufgabe an — zwei Pfade waren die Ursache."""
    t = _text()
    assert t.count("/SC ONLOGON") == 1, "es gibt mehr als eine Stelle, die den Autostart anlegt"


def test_genau_ein_schreibzugriff_auf_den_run_schluessel():
    """Genau eine Zeile schreibt einen Autostart-Eintrag (die Namen stehen in einer Variablen,
    deshalb wird zeilenweise nach ItemProperty + Run-Name gesucht)."""
    t = _text()
    treffer = [
        zeile for zeile in t.splitlines()
        if ("ItemProperty" in zeile) and (("CoMesh Agent" in zeile) or ("CoMeshAgent" in zeile))
    ]
    assert len(treffer) == 1, f"{len(treffer)} Schreibzugriffe: {treffer}"


def test_beide_altnamen_werden_entfernt():
    """Der Wert ohne Leerzeichen stammt aus einer aelteren Fassung und muss mit weg."""
    t = _text()
    assert "Remove-AutostartRunEntries" in t
    assert "CoMesh Agent" in t and "CoMeshAgent" in t
    # Die Liste der Namen steht an einer Stelle, nicht verstreut.
    assert "$script:RunValueNames" in t
    treffer = re.search(r"RunValueNames\s*=\s*@\(([^)]*)\)", t)
    assert treffer, "RunValueNames ist keine Liste"
    namen = treffer.group(1)
    assert "CoMesh Agent" in namen and "CoMeshAgent" in namen, namen


def test_schritt_8_benutzt_die_funktion():
    t = _text()
    assert "Set-Autostart" in t
    # Der Aufruf im Ablauf, nicht nur die Definition
    assert re.search(r"set-autostart", t, re.IGNORECASE)
    assert t.lower().count("set-autostart") >= 2, "Set-Autostart wird definiert, aber nicht aufgerufen"


def test_deinstallation_raeumt_den_autostart():
    t = _text()
    # Der Uninstall-Zweig muss die Aufraeumfunktion benutzen, nicht einen einzelnen Namen loeschen.
    i = t.index("if ($Uninstall)")
    zweig = t[i:i + 900]
    assert "Remove-AutostartRunEntries" in zweig, "Uninstall loescht den Run-Schluessel nicht auf"
    assert "Stop-Agent" in zweig


def test_vor_dem_anlegen_wird_aufgeraeumt():
    t = _text()
    i = t.index("function Set-Autostart")
    koerper = t[i:i + 2000]
    assert koerper.index("Remove-AutostartRunEntries") < koerper.index("schtasks.exe /Create"), \
        "vor dem Anlegen muss aufgeraeumt werden"
