# Fassung: 2026-11-18a -- reines ASCII (PowerShell 5.1 ohne BOM liest sonst Buchstabensalat)
<#
.SYNOPSIS
    CoMesh Node-Agent aus dem Quelltext installieren - fuer Rechner, auf denen eine
    Application-Control-Richtlinie (Smart App Control, AppLocker, WDAC) die unsignierte
    comesh-agent.exe blockiert.

.DESCRIPTION
    Die .exe ist nur eine Verpackung: der Agent ist ein Python-Programm. python.exe ist signiert
    und wird von der Anwendungskontrolle nicht beanstandet. Dieses Skript holt den Quelltext,
    legt eine eigene Python-Umgebung an, schreibt dieselbe agent.env wie install.ps1 und richtet
    den Autostart ueber pythonw.exe ein.

    Was es NICHT tut: Rechte aendern, Richtlinien umgehen, den Defender anfassen. Es arbeitet
    ausschliesslich im Benutzerprofil.

.PARAMETER SourceZip
    Woher der Quelltext kommt. Vorgabe: das oeffentliche Repo als ZIP. In einem Netz ohne
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
    # Externe Befehle einzeln absichern: unter $ErrorActionPreference = "Stop" wird jede
    # stderr-Zeile eines fremden Programms zum abbrechenden Fehler. "Aufgabe gibt es nicht"
    # ist hier aber der Normalfall, kein Fehler.
    $vorher = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    try {
        Get-Process -Name "python", "pythonw" -ErrorAction SilentlyContinue |
            Where-Object { $_.Path -like "*$Root*" } |
            Stop-Process -Force -ErrorAction SilentlyContinue
        & schtasks.exe /End /TN "$TaskName" 2>&1 | Out-Null
        & schtasks.exe /Delete /TN "$TaskName" /F 2>&1 | Out-Null
    } finally {
        $ErrorActionPreference = $vorher
    }
    return
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

Write-Host "CoMesh Node-Agent - Installation aus dem Quelltext" -ForegroundColor Cyan
Write-Host "Ziel: $Root"

# ---------------------------------------------------------------------------
# 1. Portal und Schluessel
# ---------------------------------------------------------------------------
Write-Step "Portal"
if (-not $PortalUrl) {
    $PortalUrl = Read-Host "  Adresse der API (z. B. http://192.168.2.187:8765)"
}
$PortalUrl = $PortalUrl.TrimEnd("/")
if ($PortalUrl -notmatch '^https?://') { Fail "PortalUrl muss mit http:// oder https:// beginnen, nicht '$PortalUrl'." }
# /health ist der einzige lebende Endpunkt am Frontend-Port. /version gehoert nicht zu den
# Pfaden, die nginx an die API durchreicht - dort antwortet die HTML-Ersatzseite mit 200, und ein
# reines Statuscode-Pruefen haelt das fuer Erfolg. Deshalb: JSON verlangen, Ausgabe kurz halten.
$apiProbe = "$PortalUrl/health"
try {
    $antwort = Invoke-WebRequest -Uri $apiProbe -TimeoutSec 15 -UseBasicParsing
    $istJson = "$($antwort.Headers['Content-Type'])" -match 'json'
    if (-not $istJson) {
        Write-Warn "$apiProbe antwortet mit $($antwort.Headers['Content-Type']) statt JSON - das ist die HTML-Ersatzseite."
        Write-Warn "Pruefe die Adresse: sie muss auf die API zeigen, z. B. http://<host>:8765 oder http://<host>:8767/api"
    } else {
        $v = $antwort.Content | ConvertFrom-Json
        $stand = if ($v.status) { $v.status } elseif ($v.ok -ne $null) { "ok=$($v.ok)" } else { "JSON ohne status/ok" }
        Write-Ok "Portal erreichbar: $stand"
    }
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
# 2. Schluessel
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

# Format pruefen, ohne den Wert auszugeben: gueltig ist gpu_ + 43 Zeichen (token_urlsafe(32)).
# Weicht die Laenge ab, wurde beim Kopieren abgeschnitten - der haeufigste Fall.
$ACCOUNT_KEY = "$ACCOUNT_KEY".Trim()
$hatPraefix = $ACCOUNT_KEY.StartsWith("gpu_")
if (-not $hatPraefix -or $ACCOUNT_KEY.Length -ne 47) {
    Write-Warn "Format ungewoehnlich: $($ACCOUNT_KEY.Length) Zeichen, Praefix gpu_ = $hatPraefix."
    Write-Host "  Ein gueltiger Schluessel ist 47 Zeichen lang (gpu_ + 43)."
    Write-Host "  Kuerzer heisst: beim Kopieren abgeschnitten. Laenger/zwei Zeilen: nur den Wert kopieren."
}

# Schluessel vor dem Einrichten pruefen. Ohne das faellt ein falscher Schluessel erst im
# Agenten-Protokoll auf ("Self-registration failed (401)"), gefolgt von einer WebSocket-Schleife
# mit 403 - das sieht nach Netzproblem aus, ist aber ein abgelehnter Schluessel.
try {
    $me = Invoke-RestMethod -Uri "$PortalUrl/v1/me" -Headers @{ Authorization = "Bearer $ACCOUNT_KEY" } -TimeoutSec 20
    Write-Ok "Schluessel gueltig: $($me.email) (Rolle: $($me.role))"
    Write-Host "  Geprueft gegen: $PortalUrl"
    if ($me.role -eq "consumer") {
        Write-Warn "Dieses Konto hat die Rolle 'consumer'. Eine Node registriert nur ein Konto mit"
        Write-Warn "'provider' oder 'both' - im Profil umstellen, dann den Agenten neu starten."
    }
} catch {
    $code = $null
    try { $code = [int]$_.Exception.Response.StatusCode } catch { }
    if ($code -eq 401) {
        Write-Host ""
        Write-Warn "Der Account-Schluessel wird abgelehnt (401 Invalid API key)."
        Write-Host "  Im Portal unter Profil -> Schluessel verwalten einen NEUEN gpu_-Schluessel ausstellen."
        Write-Host "  Ein Sitzungswert (sess_...) aus dem Browser ist kein API-Schluessel."
        Write-Host "  Achtung: ein neuer Schluessel entwertet alle aelteren desselben Kontos."
        Write-Host "  Und: ein Schluessel gilt nur in der Instanz, die ihn ausgestellt hat."
        Write-Host "  Gegen diese Adresse wurde geprueft: $PortalUrl"
        Fail "Nicht installiert - erst einen gueltigen Schluessel besorgen."
    }
    Write-Warn "Vorpruefung nicht moeglich ($($_.Exception.Message)). Die Installation laeuft weiter."
}

if ($accountKey -notmatch '^[A-Za-z0-9._:-]+$') {
    Fail "Der Schluessel enthaelt unerwartete Zeichen (erwartet: Buchstaben, Ziffern, . _ : -)."
}

# ---------------------------------------------------------------------------
# 3. Python
# ---------------------------------------------------------------------------
Write-Step "Python"
# Reihenfolge: py -0p, dann py/python/python3 im PATH, dann die ueblichen
# Installationspfade. Der Store-Platzhalter python.exe meldet keinen Versionsstring -
# er faellt damit automatisch raus.
# Quelle 0: `py -0p` nennt jede Installation mit Pfad und Version, ohne sie zu starten.
# Zeilenform: " -V:3.12 *        C:\Users\...\Python312\python.exe"
$pythonPfad = $null
try {
    $liste = (& py -0p 2>&1 | Out-String)
    foreach ($zeile in ($liste -split "`r?`n")) {
        if ($zeile -match '-V:3\.(\d+)') {
            $minorGefunden = [int]$Matches[1]
            $kandidatPfad = ($zeile.Trim() -split '\s+')[-1]
            if ($minorGefunden -ge 10 -and $kandidatPfad -and (Test-Path -LiteralPath $kandidatPfad)) {
                $pythonPfad = $kandidatPfad
                Write-Ok "gefunden: Python 3.$minorGefunden ($kandidatPfad)"
                break
            }
        }
    }
} catch { }

# Erst wenn py -0p nichts geliefert hat: PATH durchsuchen.
$kandidaten = if ($pythonPfad) { @() } else { @("py", "python", "python3") }
$pfade = @()
if (-not $pythonPfad) {
    foreach ($muster in @("$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe",
                          "C:\Python3*\python.exe",
                          "$env:ProgramFiles\Python3*\python.exe")) {
        $pfade += @(Get-ChildItem -Path $muster -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName)
    }
    $kandidaten += $pfade
}

foreach ($kandidat in $kandidaten) {
    if (-not $kandidat) { continue }
    try {
        $roh = if ($kandidat -eq "py") { & py -3 --version 2>&1 } else { & $kandidat --version 2>&1 }
        if ("$roh" -match 'Python 3\.(\d+)') {
            $minor = [int]$Matches[1]
            if ($minor -ge 10) { $pythonPfad = $kandidat; Write-Ok "gefunden: $roh ($kandidat)"; break }
            else { Write-Warn "$roh ist zu alt (mindestens 3.10): $kandidat" }
        }
    } catch { }
}
if (-not $pythonPfad) {
    # Befund statt Raetsel: zeigen, was die Suche gesehen hat.
    Write-Host "  Gefunden wurde:"
    $gefunden = $false
    foreach ($befehl in @("python", "py", "python3")) {
        try {
            $pfad = (Get-Command $befehl -ErrorAction Stop).Source
            $gefunden = $true
            $version = (& $befehl --version 2>&1 | Out-String).Trim()
            Write-Host "    $befehl -> $pfad  ($version)"
        } catch { Write-Host "    $befehl -> nicht im PATH" }
    }
    try {
        $launcher = (& py -0p 2>&1 | Out-String).Trim()
        if ($launcher) { Write-Host "    py -0p meldet:"; ($launcher -split "`n") | ForEach-Object { Write-Host "      $($_.Trim())" } }
    } catch { }
    try {
        $store = @(Get-AppxPackage -Name "*Python*" -ErrorAction SilentlyContinue)
        if ($store.Count) {
            Write-Host "    Store-Paket: $($store[0].Name) $($store[0].Version) - dessen python.exe ist nur ein Platzhalter"
        }
    } catch { }
    if (-not $gefunden) {
        Write-Host "    (keine Python-Installation im PATH und nichts an den ueblichen Orten)"
        Write-Host "    Haeufige Ursache: Python wurde NACH dem Oeffnen dieses Fensters installiert."
        Write-Host "    Dann ein neues PowerShell-Fenster oeffnen - der PATH wird nur beim Start gelesen."
    }
    Write-Host ""
    Write-Warn "Kein brauchbares Python 3.10+ gefunden. Zwei Wege, beide ohne Administratorrechte:"
    Write-Host "    winget install -e --id Python.Python.3.12"
    Write-Host "    oder direkt von python.org (signiert, Smart App Control laesst es durch):"
    Write-Host '      $u = "https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe"'
    Write-Host '      irm $u -OutFile "$env:TEMP\py.exe"; & "$env:TEMP\py.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_pip=1'
    Write-Host "    Danach ein NEUES PowerShell-Fenster oeffnen (PATH) und dieses Skript erneut starten."
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
    Fail "Im ZIP fehlt node-agent\agent.py - ist das wirklich das CoMesh-Repo?"
}
Stop-Agent
Remove-Item -LiteralPath $SrcDir -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $SrcDir | Out-Null
Copy-Item -Path (Join-Path $gefunden.FullName "*") -Destination $SrcDir -Recurse -Force
Remove-Item -LiteralPath $entpackt, $zip -Recurse -Force -ErrorAction SilentlyContinue
$versionDatei = Get-Content (Join-Path $SrcDir "AGENT_VERSION") -ErrorAction SilentlyContinue
Write-Ok "liegt in $SrcDir (Agent-Version $(if ($versionDatei) { $versionDatei } else { 'unbekannt' }))"

# ---------------------------------------------------------------------------
# 5. Python-Umgebung und Abhaengigkeiten
# ---------------------------------------------------------------------------
Write-Step "Abhaengigkeiten"
if (-not (Test-Path $PythonExe)) {
    & $pythonPfad -m venv $VenvDir
    if (-not (Test-Path $PythonExe)) { Fail "Die Python-Umgebung liess sich nicht anlegen ($VenvDir)." }
}
& $PythonExe -m pip install --quiet --upgrade pip 2>&1 | Out-Null
& $PythonExe -m pip install --quiet -r (Join-Path $AgentDir "requirements.txt")
if ($LASTEXITCODE -ne 0) { Fail "pip install ist fehlgeschlagen (PyPI erreichbar?)." }
Write-Ok "Pakete installiert in $VenvDir"

# ---------------------------------------------------------------------------
# 6. agent.env - gleiche Schluessel wie install.ps1
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
$vorher = $ErrorActionPreference; $ErrorActionPreference = "SilentlyContinue"
try { & icacls.exe $EnvFile /inheritance:r /grant:r "${whoami}:(F)" 2>&1 | Out-Null }
finally { $ErrorActionPreference = $vorher }
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
# 8. Autostart ueber pythonw.exe (kein Fenster, keine Adminrechte)
# ---------------------------------------------------------------------------
Write-Step "Autostart"
Stop-Agent
$angelegt = $false
# Auch hier: ein refusal von schtasks (verwaltete Rechner) darf nicht abbrechen, wir haben
# einen Rueckfall ueber den Run-Schluessel.
$vorher = $ErrorActionPreference
$ErrorActionPreference = "SilentlyContinue"
$taskRc = 1
try { & schtasks.exe /Create /TN "$TaskName" /TR "$TaskCmd" /SC ONLOGON /RL LIMITED /F 2>&1 | Out-Null; $taskRc = $LASTEXITCODE }
catch { $taskRc = 1 }
finally { $ErrorActionPreference = $vorher }
if ($taskRc -eq 0) {
    $angelegt = $true
    Write-Ok "Aufgabe '$TaskName' angelegt (bei Anmeldung)."
} else {
    # Verwaltete Rechner verweigern schtasks haeufig - Run-Schluessel braucht nie Adminrechte.
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
    $laeuft = @(Get-Process -Name "pythonw" -ErrorAction SilentlyContinue |
               Where-Object { $_.Path -like "*$VenvDir*" }).Count
    if ($laeuft -gt 0) { Write-Ok "Agent laeuft (Prozess pythonw)." }
    else { Write-Warn "Prozess nicht gefunden - Protokoll: $LogFile" }
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
