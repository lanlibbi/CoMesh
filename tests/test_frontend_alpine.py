"""Wächter gegen stumm funktionslose Seiten: Alpine-Direktiven ohne Alpine-Skript.

Anlass: `setup.html` benutzte Alpine (`x-data`, `@submit.prevent`, `x-model`), lud das Skript aber
nie. Die Seite sah vollständig und normal aus — ohne JavaScript bleibt `@submit.prevent` aber
ungebunden, der Browser macht einen nativen GET-Submit auf die eigene Seite, die Eingabefelder
(ohne `name`-Attribut) gehen verloren. Ergebnis: `GET /setup.html?` im Log, kein POST an die API,
und die Erstinstallation war über mehrere Versionen unmöglich, ohne dass es jemandem auffiel.

Diese Tests prüfen das statisch über alle Seiten: jede Seite, die Alpine benutzt, muss das Skript
auch einbinden, und die eingebundene Datei muss im Repo liegen (sonst fehlt sie im Image).
"""

from __future__ import annotations

import pathlib
import re

FRONTEND = pathlib.Path(__file__).resolve().parent.parent / "frontend-alpine"

ALPINE_DIREKTIVEN = re.compile(
    r"""\bx-data=|\bx-model=|\bx-show=|\bx-text=|\bx-for=|\bx-if=|\bx-bind:|\bx-on:|@[a-z]+\.(prevent|stop|submit)=""",
    re.IGNORECASE,
)
SCRIPT_QUELLEN = re.compile(r"<script[^>]+src=[\"']([^\"']+)[\"']", re.IGNORECASE)

def _seiten() -> list[pathlib.Path]:
    """Alle echten Seiten im Frontend — Sicherungskopien (…bak-…) gehören nicht dazu."""
    return sorted(p for p in FRONTEND.glob("*.html") if ".bak-" not in p.name)

def test_frontend_verzeichnis_existiert():
    assert FRONTEND.is_dir(), f"Frontend-Verzeichnis fehlt: {FRONTEND}"
    assert _seiten(), "keine HTML-Seiten gefunden"

def test_keine_alpine_direktiven_ohne_alpine_skript():
    """Die eigentliche Regression: Seite benutzt Alpine, lädt es aber nicht."""
    fehlend = []
    for seite in _seiten():
        text = seite.read_text(encoding="utf-8", errors="ignore")
        if not ALPINE_DIREKTIVEN.search(text):
            continue
        quellen = SCRIPT_QUELLEN.findall(text)
        if not any("alpine" in q.lower() for q in quellen):
            fehlend.append(seite.name)
    assert not fehlend, (
        "Seiten benutzen Alpine-Direktiven, laden aber kein Alpine-Skript: "
        + ", ".join(fehlend)
        + " — solche Seiten sind ohne JavaScript vollständig funktionslos."
    )

def test_alpine_wird_lokal_ausgeliefert():
    """Kein CDN: eine Instanz ohne Internetzugang muss die Oberfläche laden können."""
    cdn = []
    for seite in _seiten():
        text = seite.read_text(encoding="utf-8", errors="ignore")
        for quelle in SCRIPT_QUELLEN.findall(text):
            if quelle.startswith(("http://", "https://", "//")):
                cdn.append(f"{seite.name}: {quelle}")
    assert not cdn, "Seiten laden Skripte von fremden Hosts: " + "; ".join(cdn)

def test_lokale_alpine_datei_ist_vorhanden():
    datei = FRONTEND / "vendor" / "alpine.min.js"
    assert datei.is_file(), "vendor/alpine.min.js fehlt — die Seiten liefen sonst ins Leere."
    assert datei.stat().st_size > 10_000, "vendor/alpine.min.js ist verdächtig klein."

def test_dockerfile_kopiert_vendor_verzeichnis():
    """Das Dockerfile kopiert Dateien einzeln — ein vergessenes vendor/ fehlt im Image."""
    dockerfile = (FRONTEND / "Dockerfile").read_text(encoding="utf-8")
    assert "vendor" in dockerfile, (
        "frontend-alpine/Dockerfile kopiert vendor/ nicht mit; im Container fehlt dann "
        "alpine.min.js und jede Seite bleibt ohne Funktion."
    )
