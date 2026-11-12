# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller-Spezifikation für den CoMesh-Node-Agenten.

Erzeugt **ein** Binary (`comesh-agent` bzw. `comesh-agent.exe`), das ohne
Python-Installation und ohne Quellbaum läuft. Build über `build.sh` (macOS,
Linux) bzw. `build.ps1` (Windows) — die Skripte benennen das Ergebnis nach
Betriebssystem und Architektur um und legen die `.sha256`-Datei daneben.

Warum die Hidden Imports nötig sind: uvicorn zieht seine Implementierungen erst
zur Laufzeit über `importlib` (`uvicorn.loops.auto`,
`uvicorn.protocols.http.auto`, `uvicorn.protocols.websockets.auto`, …).
PyInstaller sieht diese Namen in keinem `import`-Statement und lässt sie weg.
Das Ergebnis startet dann scheinbar normal und stirbt beim ersten Request mit
`ModuleNotFoundError: No module named 'uvicorn.protocols.http.h11_impl'` —
im Dienst-Log, nicht im Terminal. Dasselbe gilt für `websockets`, das der
WS-Transport lokal importiert.
"""
import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

HERE = os.path.abspath(SPECPATH)          # …/node-agent
ROOT = os.path.dirname(HERE)              # Repo-Wurzel (VERSION liegt dort)

# --- Hidden Imports ---------------------------------------------------------
hiddenimports = []

# uvicorn: alle Untermodule, weil die Auswahl über Strings passiert.
hiddenimports += collect_submodules("uvicorn")
hiddenimports += collect_submodules("websockets")

# Die Namen, die uvicorn per Zeichenkette auflöst — doppelt, damit auch ein
# umbenanntes Untermodul nicht still fehlt.
hiddenimports += [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "h11",
    "anyio",
    "sniffio",
    "httpx",
    "httpcore",
    "psutil",
    "pynvml",
    "netinfo",
]

# --- Mitgelieferte Dateien --------------------------------------------------
# Die VERSION-Datei wandert mit, damit `comesh-agent --version` und die
# FastAPI-Kennung dieselbe Nummer melden wie das Portal (`/version`).
datas = []
# AGENT_VERSION (zuletzt ausgelieferte Artefakt-Version) hat Vorrang vor VERSION.
# Beide wandern mit, damit ein Binary aus einem neueren Repo trotzdem die richtige
# Agent-Version meldet.
for _name in ("AGENT_VERSION", "VERSION"):
    _pfad = os.path.join(ROOT, _name)
    if os.path.isfile(_pfad):
        datas.append((_pfad, "."))

# CA-Bündel für HTTPS zum Portal (httpx -> certifi). Ohne das scheitert jede
# TLS-Verbindung im Binary mit SSLCertVerificationError.
try:
    datas += collect_data_files("certifi")
except Exception:  # pragma: no cover - certifi ist immer da, aber nie erzwingen
    pass

a = Analysis(
    ["agent.py"],
    pathex=[HERE],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Grobe Kostentreiber, die ein Proxy nicht braucht. Spart ~20 MB.
    excludes=[
        "tkinter",
        "matplotlib",
        "numpy",
        "pandas",
        "pytest",
        "IPython",
        "PyQt5",
        "PySide6",
        "setuptools",
        "pip",
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="comesh-agent",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX bricht unter Windows die Code-Signatur und nervt Virenscanner
    upx_exclude=[],
    runtime_tmpdir=None,
    # Konsole, kein Fenster: unter Windows ist genau das der Punkt — die
    # Ausgabe landet in der Logdatei der Aufgabe, und `--check` lässt sich
    # in einer PowerShell aufrufen.
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,   # macOS: kein Finder-Start nötig, launchd übergibt Argumente
    target_arch=None,       # native Architektur des Build-Rechners
    codesign_identity=None, # unsigniert; siehe docs/install.md (Gatekeeper)
    entitlements_file=None,
)
