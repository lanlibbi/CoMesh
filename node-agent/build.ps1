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

# pip und PyInstaller schreiben ihren Fortschritt nach stderr. PowerShell 5.1
# macht daraus bei $ErrorActionPreference = "Stop" einen terminierenden Fehler
# ("NativeCommandError"), der Bau stirbt also an der ersten INFO-Zeile, bevor
# PyInstaller arbeitet. Externe Programme laufen deshalb mit "Continue", und
# was sie geleistet haben, sagt der Exitcode.
function Invoke-Native {
    param([scriptblock]$Block, [string]$What)
    $ErrorActionPreference = "Continue"
    & $Block
    if ($LASTEXITCODE -ne 0) { throw "$What ist mit Exitcode $LASTEXITCODE gescheitert." }
}

$Version = "0.0.0"
# AGENT_VERSION (zuletzt ausgelieferte Artefakt-Version) hat Vorrang vor VERSION -
# sonst nennt der Bericht die Portal-Version, waehrend das Binary die Agent-Version meldet.
$root = Split-Path -Parent $PSScriptRoot
$versionFile = Join-Path $root "AGENT_VERSION"
if (-not (Test-Path $versionFile)) { $versionFile = Join-Path $root "VERSION" }
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
        if ($bootstrap) { Invoke-Native { & py -3 -m venv .venv-build } "venv anlegen" }
        else { Invoke-Native { & python -m venv .venv-build } "venv anlegen" }
        if (-not (Test-Path -LiteralPath $venvPython)) {
            throw "Konnte kein venv anlegen. Python 3.10+ installieren: winget install --id Python.Python.3.12 -e"
        }
    }
    $Python = $venvPython
    Write-Host "==> Abhaengigkeiten installieren (requirements-build.txt)"
    Invoke-Native { & $Python -m pip install --quiet --upgrade pip } "pip-Aktualisierung"
    Invoke-Native { & $Python -m pip install --quiet -r requirements-build.txt } "pip install -r requirements-build.txt"
} else {
    $Python = "python"
    if (-not (Get-Command pyinstaller -ErrorAction SilentlyContinue)) {
        throw "pyinstaller fehlt - ohne -NoVenv installiert das Skript es selbst."
    }
}

Write-Host "==> Einfrieren (PyInstaller, onefile)"
Invoke-Native { & $Python -m PyInstaller --clean --noconfirm --distpath dist --workpath build comesh-agent.spec } "PyInstaller"

$raw = Join-Path "dist" "comesh-agent.exe"
if (-not (Test-Path -LiteralPath $raw)) { throw "Build hat kein dist\comesh-agent.exe erzeugt." }
Move-Item -LiteralPath $raw -Destination $Artifact -Force

# ---------------------------------------------------------------------------
# Optionale Signatur - MUSS vor dem Hashen passieren
# ---------------------------------------------------------------------------
# Signiert wird mit dem Zertifikat des BETREIBERS, nicht mit einem gemeinsamen: eine Instanz, die
# ihre Nodes selbst ausliefert, muss auch selbst der Herausgeber sein. Ein geteiltes Zertifikat
# waere ein Generalschluessel - ein Leck kompromittiert dann jede Installation.
#
#   $env:COMESH_SIGN_THUMBPRINT = "<Cert-Thumbprint>"      # Zertifikat im Zertifikatsspeicher
#   $env:COMESH_SIGN_PFX        = "C:\pfad\sign.pfx"       # oder eine PFX-Datei
#   $env:COMESH_SIGN_PFX_PASS   = "<Kennwort der PFX>"     # nur bei PFX noetig
#
# Ohne diese Variablen passiert nichts - der Build bleibt wie bisher. Der Agent ist dann
# unsigniert und auf Windows 11 mit aktivem Smart App Control nicht startbar; dort ist der
# Quelltext-Weg (downloads/install-from-source.ps1) die Antwort.
$signiert = $false
if ($env:COMESH_SIGN_THUMBPRINT -or $env:COMESH_SIGN_PFX) {
    Write-Host "==> Signieren (Code-Signing-Zertifikat des Betreibers)"
    $signtool = $null
    foreach ($kandidat in @(
        "${env:ProgramFiles(x86)}\Windows Kits\10\bin\x64\signtool.exe",
        "$env:ProgramFiles\Windows Kits\10\bin\x64\signtool.exe"
    )) { if (Test-Path -LiteralPath $kandidat) { $signtool = $kandidat; break } }
    if (-not $signtool) {
        $cmd = Get-Command signtool.exe -ErrorAction SilentlyContinue
        if ($cmd) { $signtool = $cmd.Source }
    }
    if (-not $signtool) {
        throw "signtool.exe nicht gefunden. Es kommt mit dem Windows SDK; ohne SDK keine Signatur."
    }

    $arguments = @("sign", "/fd", "sha256", "/td", "sha256",
                   "/tr", "http://timestamp.digicert.com")
    if ($env:COMESH_SIGN_PFX) {
        if (-not (Test-Path -LiteralPath $env:COMESH_SIGN_PFX)) {
            throw "PFX nicht gefunden: $env:COMESH_SIGN_PFX"
        }
        $arguments += @("/f", $env:COMESH_SIGN_PFX)
        if ($env:COMESH_SIGN_PFX_PASS) { $arguments += @("/p", $env:COMESH_SIGN_PFX_PASS) }
    } else {
        $arguments += @("/sha1", $env:COMESH_SIGN_THUMBPRINT)
    }
    $arguments += @("/v", $Artifact)

    Invoke-Native { & $signtool @arguments } "signtool sign"
    Write-Host "  signiert: $Artifact"

    # Signatur gegenpruefen, nicht annehmen
    $pruefung = & $signtool verify /pa /v $Artifact 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0) {
        throw "Signaturpruefung fehlgeschlagen:`n$pruefung"
    }
    $zeile = ($pruefung -split "`n" | Where-Object { $_ -match "Issued to|Ausgestellt fuer" } | Select-Object -First 1)
    if ($zeile) { Write-Host "  Signatur gueltig - $($zeile.Trim())" }
    else        { Write-Host "  Signatur gueltig" }

    # Das oeffentliche Zertifikat gehoert neben das Binary: Clients brauchen es als
    # Herausgeber-Vertrauen (GPO/Intune), sonst hilft die Signatur dort nichts.
    try {
        $cert = $null
        if ($env:COMESH_SIGN_PFX) {
            $pass = if ($env:COMESH_SIGN_PFX_PASS) {
                ConvertTo-SecureString $env:COMESH_SIGN_PFX_PASS -AsPlainText -Force
            } else { $null }
            $cert = if ($pass) { Get-PfxCertificate -FilePath $env:COMESH_SIGN_PFX -Password $pass }
                    else        { Get-PfxCertificate -FilePath $env:COMESH_SIGN_PFX }
        } else {
            $cert = Get-ChildItem Cert:\CurrentUser\My, Cert:\LocalMachine\My -ErrorAction SilentlyContinue |
                    Where-Object { $_.Thumbprint -eq $env:COMESH_SIGN_THUMBPRINT } |
                    Select-Object -First 1
        }
        if ($cert) {
            Export-Certificate -Cert $cert -FilePath "$Artifact.cer" -Type CERT | Out-Null
            Write-Host "  Herausgeber-Zertifikat: $Artifact.cer (auf den Zielrechnern unter"
            Write-Host "  'Vertrauenswuerdige Herausgeber' verteilen - per GPO oder Intune)"
        } else {
            Write-Host "  Hinweis: Zertifikat nicht exportierbar; .cer bitte von Hand neben das Binary legen."
        }
    } catch {
        Write-Host "  Hinweis: .cer konnte nicht geschrieben werden ($($_.Exception.Message))."
    }
    $signiert = $true
}

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
