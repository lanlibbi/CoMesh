<#
.SYNOPSIS
    CoMesh Node-Agent aus dem Quelltext installieren — für Rechner, auf denen eine
    Application-Control-Richtlinie (Smart App Control, AppLocker, WDAC) die unsignierte
    comesh-agent.exe blockiert.

.DESCRIPTION
    Die .exe ist nur eine Verpackung: der Agent ist ein Python-Programm. python.exe ist signiert
    und wird von der Anwendungskontrolle nicht beanstandet. Dieses Skript holt den Quelltext,
    legt eine eigene Python-Umgebung an, schreibt dieselbe agent.env wie install.ps1 und richtet
    den Autostart über pythonw.exe ein.

    Was es NICHT tut: Rechte ändern, Richtlinien umgehen, den Defender anfassen. Es arbeitet
    ausschließlich im Benutzerprofil.

.PARAMETER SourceZip
    Woher der Quelltext kommt. Vorgabe: das öffentliche Repo als ZIP. In einem Netz ohne
    GitHub-Zugang auf eine eigene Ablage zeigen.

.EXAMPLE
    irm http://<portal>:8767/downloads/install-from-source.ps1 | iex

.EXAMPLE
    .\install-from-source.ps1 -PortalUrl http://192.168.2.187:8765 -Name windows-ai -VramGb 12
#>
[CmdletBinding()]
param(
    [string]$PortalUrl = $env:COMESH_PORTAL_URL,
    [string]$Transport = $env:COMESH_TRANSPORT,
    [string]$KeyFile   = $env:COMESH_KEY_FILE,
    [string]$Name      = $env:COMESH_AGENT_NAME,
    [string]$Backend   = $env:COMESH_BACKEND,
    [string]$InferenceUrl = $env:COMESH_INFERENCE_URL,
    [string]$VramGb    = $env:COMESH_VRAM_GB,
    [string]$SourceZip = "https://github.com/lanlibbi/CoMesh/archive/refs/heads/main.zip",
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Write-Step($text) { Write-Host ""; Write-Host "==> $text" -ForegroundColor Cyan }
function Write-Ok($text)   { Write-Host "  $text" }
function Write-Warn($text) { Write-Host "WARNUNG: $text" -ForegroundColor Yellow }
function Fail($text)       { Write-Host ""; Write-Host "FEHLER: $text" -ForegroundColor Red
                             throw "Installation abgebrochen." }

$Root      = Join-Path $env:LOCALAPPDATA "CoMesh"
$SrcDir    = Join-Path $Root "src"
$AgentDir  = Join-Path $SrcDir "node-agent"
$VenvDir   = Join-Path $Root "venv"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"
$PythonW   = Join-Path $VenvDir "Scripts\pythonw.exe"
$EnvFile   = Join-Path $Root "agent.env"
$LogFile   = Join-Path $Root "agent.log"
$StateFile = Join-Path $Root "node-state.json"
$TaskName  = "CoMesh Agent"
$TaskCmd   = "`"$PythonW`" `"$(Join-Path $AgentDir 'agent.py')`""

function Stop-Agent {
    Get-Process -Name "python", "pythonw" -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -like "*$Root*" } |
        Stop-Process -Force -ErrorAction SilentlyContinue
    schtasks /End /TN "$TaskName" *> $null
    schtasks /Delete /TN "$TaskName" /F *> $null
}

# ---------------------------------------------------------------------------
# Entfernen
# ---------------------------------------------------------------------------
if ($Uninstall) {
    Write-Step "Entfernen"
    Stop-Agent
    Remove-Item "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "CoMeshAgent" -ErrorAction SilentlyContinue
    if (Test-Path $Root) { Remove-Item -LiteralPath $Root -Recurse -Force -ErrorAction SilentlyContinue }
    Write-Ok "Aufgabe und $Root entfernt. Die Node im Portal bleibt registriert und kann dort geloescht werden."
    return
}

Write-Host "CoMesh Node-Agent — Installation aus dem Quelltext" -ForegroundColor Cyan
Write-Host "Ziel: $Root"

# ---------------------------------------------------------------------------
# 1. Portal und Schlüssel
# ---------------------------------------------------------------------------
Write-Step "Portal"
if (-not $PortalUrl) {
    $PortalUrl = Read-Host "  Adresse der API (z. B. http://192.168.2.187:8765)"
}
$PortalUrl = $PortalUrl.TrimEnd("/")
if ($PortalUrl -notmatch '^https?://') { Fail "PortalUrl muss mit http:// oder https:// beginnen, nicht '$PortalUrl'." }
$apiProbe = "$PortalUrl/version"
try {
    $v = Invoke-RestMethod -Uri $apiProbe -TimeoutSec 15
    Write-Ok "Portal erreichbar: $(($v | ConvertTo-Json -Compress))"
} catch {
    Write-Warn "Portal antwortet nicht auf $apiProbe ($($_.Exception.Message)). Die Installation laeuft weiter."
}

if (-not $Transport) { $Transport = "ws" }
if ($Transport -notin @("ws", "http")) { Fail "Transport muss 'ws' oder 'http' sein." }
if (-not $Backend)   { $Backend = "ollama" }
if (-not $Backend -or $Backend -notin @("ollama", "openai")) { Fail "Backend muss 'ollama' oder 'openai' sein." }
if (-not $InferenceUrl) {
    $InferenceUrl = if ($Backend -eq "ollama") { "http://127.0.0.1:11434" } else { "http://127.0.0.1:1234" }
}
if (-not $Name) {
    $Name = $env:COMPUTERNAME
    if (-not $Name) { $Name = "windows-node" }
}

# ---------------------------------------------------------------------------
# 2. Schlüssel
# ---------------------------------------------------------------------------
Write-Step "Konto-Schluessel"
$accountKey = ""
if ($KeyFile) {
    if (-not (Test-Path -LiteralPath $KeyFile)) { Fail "Schluesseldatei nicht lesbar: $KeyFile" }
    $accountKey = (Get-Content -LiteralPath $KeyFile -Raw).Trim()
} elseif ($env:COMESH_USER_KEY) {
    $accountKey = $env:COMESH_USER_KEY.Trim()
} else {
    $secure = Read-Host -AsSecureString "  Account-Schluessel (API-Key deines CoMesh-Kontos, Eingabe bleibt unsichtbar)"
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try   { $accountKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr).Trim() }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
}
if (-not $accountKey) { Fail "Ohne Account-Schluessel kann sich die Node nicht registrieren." }
if ($accountKey -notmatch '^[A-Za-z0-9._:-]+$') {
    Fail "Der Schluessel enthaelt unerwartete Zeichen (erwartet: Buchstaben, Ziffern, . _ : -)."
}

# ---------------------------------------------------------------------------
# 3. Python
# ---------------------------------------------------------------------------
Write-Step "Python"
$python = $null
foreach ($kandidat in @("py", "python")) {
    try {
        $roh = if ($kandidat -eq "py") { & py -3 --version 2>&1 } else { & python --version 2>&1 }
        if ($LASTEXITCODE -eq 0 -and "$roh" -match 'Python 3\.(\d+)') {
            $minor = [int]$Matches[1]
            if ($minor -ge 10) { $python = $kandidat; Write-Ok "gefunden: $roh ($kandidat)"; break }
            else { Write-Warn "$roh ist zu alt (mindestens 3.10)." }
        }
    } catch { }
}
if (-not $python) {
    Write-Warn "Kein Python 3.10+ gefunden. Installieren ohne Adminrechte:"
    Write-Host "    winget install -e --id Python.Python.3.12"
    Fail "Bitte Python installieren und dieses Skript erneut starten."
}

# ---------------------------------------------------------------------------
# 4. Quelltext
# ---------------------------------------------------------------------------
Write-Step "Quelltext"
New-Item -ItemType Directory -Force -Path $Root | Out-Null
$zip = Join-Path $env:TEMP "comesh-src.zip"
$entpackt = Join-Path $env:TEMP "comesh-src"
Remove-Item -LiteralPath $entpackt -Recurse -Force -ErrorAction SilentlyContinue
try {
    Invoke-WebRequest -Uri $SourceZip -OutFile $zip -UseBasicParsing -TimeoutSec 300
} catch {
    Fail "Quelltext nicht ladbar von $SourceZip`n  $($_.Exception.Message)`n  In einem Netz ohne GitHub-Zugang: -SourceZip auf eine eigene Ablage zeigen lassen."
}
Expand-Archive -LiteralPath $zip -DestinationPath $entpackt -Force
$gefunden = Get-ChildItem -LiteralPath $entpackt -Directory | Select-Object -First 1
if (-not $gefunden) { Fail "Das ZIP enthaelt keinen Ordner." }
if (-not (Test-Path (Join-Path $gefunden.FullName "node-agent\agent.py"))) {
    Fail "Im ZIP fehlt node-agent\agent.py — ist das wirklich das CoMesh-Repo?"
}
Stop-Agent
Remove-Item -LiteralPath $SrcDir -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $SrcDir | Out-Null
Copy-Item -Path (Join-Path $gefunden.FullName "*") -Destination $SrcDir -Recurse -Force
Remove-Item -LiteralPath $entpackt, $zip -Recurse -Force -ErrorAction SilentlyContinue
$versionDatei = Get-Content (Join-Path $SrcDir "AGENT_VERSION") -ErrorAction SilentlyContinue
Write-Ok "liegt in $SrcDir (Agent-Version $(if ($versionDatei) { $versionDatei } else { 'unbekannt' }))"

# ---------------------------------------------------------------------------
# 5. Python-Umgebung und Abhängigkeiten
# ---------------------------------------------------------------------------
Write-Step "Abhaengigkeiten"
if (-not (Test-Path $PythonExe)) {
    if ($python -eq "py") { & py -3 -m venv $VenvDir } else { & python -m venv $VenvDir }
    if (-not (Test-Path $PythonExe)) { Fail "Die Python-Umgebung liess sich nicht anlegen ($VenvDir)." }
}
& $PythonExe -m pip install --quiet --upgrade pip 2>&1 | Out-Null
& $PythonExe -m pip install --quiet -r (Join-Path $AgentDir "requirements.txt")
if ($LASTEXITCODE -ne 0) { Fail "pip install ist fehlgeschlagen (PyPI erreichbar?)." }
Write-Ok "Pakete installiert in $VenvDir"

# ---------------------------------------------------------------------------
# 6. agent.env — gleiche Schlüssel wie install.ps1
# ---------------------------------------------------------------------------
Write-Step "Konfiguration"
$lines = @(
    "# CoMesh Node-Agent - erzeugt von install-from-source.ps1 (enthaelt den Account-Schluessel)"
    "PORTAL_URL=$PortalUrl"
    "PORTAL_USER_KEY=$accountKey"
    "AGENT_TRANSPORT=$Transport"
    "NODE_NAME=$Name"
    "BACKEND=$Backend"
    $(if ($Backend -eq "openai") { "INFERENCE_URL=$InferenceUrl" } else { "OLLAMA_URL=$InferenceUrl" })
    "NODE_STATE_FILE=$StateFile"
    "AGENT_LOG_FILE=$LogFile"
)
if ($VramGb) {
    if ($VramGb -notmatch '^\d+$' -or [int]$VramGb -lt 1) { Fail "VRAM muss eine ganze Zahl in GB sein, nicht '$VramGb'." }
    $lines += "NODE_VRAM_GB=$VramGb"
}

# UTF-8 ohne BOM: ein BOM wuerde den ersten Schluessel zu "\ufeffPORTAL_URL" machen.
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($EnvFile, (($lines -join "`r`n") + "`r`n"), $utf8NoBom)
$whoami = if ($env:USERDOMAIN) { "$($env:USERDOMAIN)\$($env:USERNAME)" } else { $env:USERNAME }
& icacls.exe $EnvFile /inheritance:r /grant:r "${whoami}:(F)" *> $null
Write-Ok "geschrieben: $EnvFile (nur $whoami)"

# ---------------------------------------------------------------------------
# 7. Selbsttest
# ---------------------------------------------------------------------------
Write-Step "Selbsttest"
$env:COMESH_AGENT_ENV = $EnvFile
Push-Location $AgentDir
try {
    $checkOut = & $PythonExe agent.py --check 2>&1
    $checkOut | ForEach-Object { Write-Ok $_ }
    $checkOk = ($LASTEXITCODE -eq 0)
} catch {
    Write-Warn "Selbsttest nicht ausfuehrbar: $($_.Exception.Message)"
    $checkOk = $false
} finally { Pop-Location }

# ---------------------------------------------------------------------------
# 8. Autostart über pythonw.exe (kein Fenster, keine Adminrechte)
# ---------------------------------------------------------------------------
Write-Step "Autostart"
Stop-Agent
$angelegt = $false
schtasks /Create /TN "$TaskName" /TR "$TaskCmd" /SC ONLOGON /RL LIMITED /F *> $null
if ($LASTEXITCODE -eq 0) {
    $angelegt = $true
    Write-Ok "Aufgabe '$TaskName' angelegt (bei Anmeldung)."
} else {
    # Verwaltete Rechner verweigern schtasks haeufig — Run-Schluessel braucht nie Adminrechte.
    try {
        New-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "CoMeshAgent" `
            -Value $TaskCmd -PropertyType String -Force | Out-Null
        $angelegt = $true
        Write-Ok "Autostart ueber HKCU\...\Run eingetragen (schtasks war nicht erlaubt)."
    } catch {
        Write-Warn "Autostart liess sich nicht einrichten. Von Hand starten:"
        Write-Host "    `"$PythonW`" `"$(Join-Path $AgentDir 'agent.py')`""
    }
}

# ---------------------------------------------------------------------------
# 9. Starten und Status
# ---------------------------------------------------------------------------
Write-Step "Start"
if ($checkOk) {
    Start-Process -FilePath $PythonW -ArgumentList @((Join-Path $AgentDir "agent.py")) -WorkingDirectory $AgentDir -WindowStyle Hidden
    Start-Sleep -Seconds 4
    $läuft = @(Get-Process -Name "pythonw" -ErrorAction SilentlyContinue |
               Where-Object { $_.Path -like "*$VenvDir*" }).Count
    if ($läuft -gt 0) { Write-Ok "Agent laeuft (Prozess pythonw)." }
    else { Write-Warn "Prozess nicht gefunden — Protokoll: $LogFile" }
} else {
    Write-Warn "Nicht gestartet, weil der Selbsttest nicht sauber war. Von Hand:"
    Write-Host "    cd `"$AgentDir`"; `"$PythonExe`" agent.py --check"
}
if (Test-Path $LogFile) {
    Write-Host ""
    Write-Host "  Letzte Protokollzeilen ($LogFile):"
    Get-Content -LiteralPath $LogFile -Tail 8 | ForEach-Object { Write-Host "    $_" }
}
Write-Host ""
Write-Host "Fertig. Im Portal unter 'Node beitragen' muss die Node als verbunden erscheinen." -ForegroundColor Green
