"""KEY=VALUE-Dateien einlesen - ohne Abhaengigkeiten.

Bewusst getrennt von `agent.py`: Diese Funktion braucht nur die Standardbibliothek und ist damit
ueberall pruefbar, auch dort, wo NVIDIA-Treiber oder psutil fehlen. Ein Test, der nur auf einem
GPU-Rechner laeuft, wird auf dem naechsten Rechner nicht ausgefuehrt und faellt nicht auf.

Wichtig ist die BOM-Behandlung: PowerShell 5.1 schreibt mit `Set-Content -Encoding utf8` ein BOM an
den Dateianfang. Ohne Entfernen wird der erste Schluessel zu "\\ufeffPORTAL_URL" - die Variable
landet unter falschem Namen, `PORTAL_URL` bleibt leer, und die Selbstregistrierung des Agenten wird
stillschweigend uebersprungen.
"""

import os


def load_env_file(path: str = ".env") -> None:
    """Liest KEY=VALUE-Zeilen aus *path* in os.environ, ohne vorhandene Werte zu ueberschreiben."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw_lines = fh.readlines()
    except OSError:
        return
    for raw in raw_lines:
        # BOM am Dateianfang entfernen (siehe Modulbeschreibung).
        line = raw.lstrip("\ufeff").strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value
