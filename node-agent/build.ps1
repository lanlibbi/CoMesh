<#
.SYNOPSIS
    Baut das CoMesh-Agent-Einzelbinary fuer Windows (comesh-agent.exe).

.DESCRIPTION
    Friert node-agent\agent.py mit PyInstaller ein. Der Rechner, auf dem das
    Binary spaeter laeuft, braucht danach **kein Python**.

        .\build.ps1              # Binary + Pruefsumme nach dist\
        .\build.ps1 -NoVenv      # vorhandenes PyInstaller im aktuellen Python nutzen

    Ergebnis (Name = was install.ps1 erwartet):

        dist\comesh-agent-windows-x86_64.exe  +  .exe.sha256

    Gebaut wird nur fuer die Architektur des Build-Rechners. Auf ARM64-Windows
    entsteht ein ARM64-Binary; install.ps1 laedt standardmaessig die x86_64-Fassung
    (die unter Windows-on-ARM emuliert laeuft). Wenn du ARM64 veroeffentlichen
    willst, lade die Datei entsprechend mit hoch - sonst baut bitte auf x64.

    Speicher: PyInstaller braucht beim Einfrieren rund 400-800 MB.
#>
param(
    [switch]$NoVenv
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$Version = "0.0.0"
$versionFile = Join-Path (Split-Path -Parent $PSScriptRoot) "VERSION"
if (Test-Path -LiteralPath $versionFile) {
    $Version = (Get-Content -LiteralPath $versionFile -Raw).Trim()
}

switch ($env:PROCESSOR_ARCHITECTURE) {
    "AMD64" { $Arch = "x86_64" }
    "ARM64" { $Arch = "arm64" }
    "x86"   { throw "32-Bit-Windows wird nicht unterstuetzt." }
    default { throw "Unbekannte Architektur: $env:PROCESSOR_ARCHITECTURE" }
}

$Artifact = Join-Path "dist" "comesh-agent-windows-$Arch.exe"

if (-not $NoVenv) {
    $venvPython = Join-Path ".venv-build" "Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $venvPython)) {
        Write-Host "==> Baust-venv anlegen (.venv-build, nicht systemweit)"
        $bootstrap = Get-Command py -ErrorAction SilentlyContinue
        if ($bootstrap) { & py -3 -m venv .venv-build } else { & python -m venv .venv-build }
        if (-not (Test-Path -LiteralPath $venvPython)) {
            throw "Konnte kein venv anlegen. Python 3.10+ installieren: winget install --id Python.Python.3.12 -e"
        }
    }
    $Python = $venvPython
    Write-Host "==> Abhaengigkeiten installieren (requirements-build.txt)"
    & $Python -m pip install --quiet --upgrade pip
    & $Python -m pip install --quiet -r requirements-build.txt
} else {
    $Python = "python"
    if (-not (Get-Command pyinstaller -ErrorAction SilentlyContinue)) {
        throw "pyinstaller fehlt - ohne -NoVenv installiert das Skript es selbst."
    }
}

Write-Host "==> Einfrieren (PyInstaller, onefile)"
& $Python -m PyInstaller --clean --noconfirm --distpath dist --workpath build comesh-agent.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller ist mit Exitcode $LASTEXITCODE gescheitert." }

$raw = Join-Path "dist" "comesh-agent.exe"
if (-not (Test-Path -LiteralPath $raw)) { throw "Build hat kein dist\comesh-agent.exe erzeugt." }
Move-Item -LiteralPath $raw -Destination $Artifact -Force

$hash = (Get-FileHash -LiteralPath $Artifact -Algorithm SHA256).Hash.ToLower()
$shaFile = "$Artifact.sha256"
# Format wie unter Linux: "<hex>  <dateiname>" - install.ps1 und install.sh
# lesen beide das erste Feld.
Set-Content -LiteralPath $shaFile -Value ("{0}  {1}" -f $hash, (Split-Path -Leaf $Artifact)) -Encoding ascii

$sizeMb = [math]::Round((Get-Item -LiteralPath $Artifact).Length / 1MB, 1)
Write-Host ""
Write-Host "Fertig: $Artifact (Version $Version, $sizeMb MB)"
Write-Host "Pruefsumme: $hash"
Write-Host ""
Write-Host "Ausliefern (beide Dateien zusammen, sonst verweigert der Installer):"
Write-Host "  $(Split-Path -Leaf $Artifact)"
Write-Host "  $(Split-Path -Leaf $Artifact).sha256"
