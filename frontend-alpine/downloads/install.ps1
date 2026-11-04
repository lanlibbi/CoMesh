<#
.SYNOPSIS
    CoMesh Node-Agent - Installation mit einem Befehl unter Windows.

.DESCRIPTION
    Aufruf in einer normalen PowerShell (kein Administrator noetig):

        irm https://<portal>/downloads/install.ps1 | iex

    Mit Parametern (dann als Datei speichern und aufrufen, weil `iex` keine
    Argumente durchreicht):

        .\install.ps1 -BaseUrl https://<portal>/downloads -PortalUrl https://<portal>/api

    Bei `irm | iex` kommen die Werte aus der Umgebung - vorher setzen:

        $env:COMESH_USER_KEY = "gpu_..."
        $env:COMESH_VRAM_GB  = "10"
        irm https://<portal>/downloads/install.ps1 | iex

    Was es tut:
      1. Architektur erkennen (nur x86_64 wird ausgeliefert)
      2. comesh-agent.exe + Pruefsumme laden, SHA-256 pruefen (ohne: Abbruch)
      3. nach %LOCALAPPDATA%\CoMesh\comesh-agent.exe legen
      4. Account-Schluessel verdeckt abfragen (nicht im Verlauf, nicht in argv)
      5. VRAM abfragen, wenn keine NVIDIA-GPU erkannt wird
      6. agent.env schreiben, Rechte auf das eigene Konto beschraenkt
      7. Aufgabe in der Aufgabenplanung: bei Anmeldung, ohne Adminrechte
      8. Status zeigen: Aufgabe, Portal, Node

    Transport ist WebSocket: der Agent waehlt sich ausgehend ein, es braucht
    keinen offenen Port und keine Firewall-Regel.

    Entfernen:   .\install.ps1 -Uninstall     (oder: irm ... | iex  mit $env:COMESH_UNINSTALL="1")

    Kein Python, kein Docker, kein Repo - nur das Binary.
#>
[CmdletBinding()]
param(
    [string]$BaseUrl   = $env:COMESH_BASE_URL,
    [string]$PortalUrl = $env:COMESH_PORTAL_URL,
    [string]$Transport = $env:COMESH_TRANSPORT,
    [string]$KeyFile   = $env:COMESH_KEY_FILE,
    [string]$VramGb    = $env:COMESH_VRAM_GB,
    [string]$Name      = $env:COMESH_AGENT_NAME,
    [string]$Backend   = $env:COMESH_BACKEND,
    [string]$InferenceUrl = $env:COMESH_INFERENCE_URL,
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # Invoke-WebRequest ist sonst quaelend langsam

# ---------------------------------------------------------------------------
# Vorgaben
# ---------------------------------------------------------------------------
$Origin      = if ($env:COMESH_ORIGIN) { $env:COMESH_ORIGIN } else { "https://comesh.lanlibbilab.me" }
if (-not $BaseUrl)   { $BaseUrl   = "$Origin/downloads" }
if (-not $PortalUrl) { $PortalUrl = "$Origin/api" }
if (-not $Transport) { $Transport = "ws" }
if (-not $Backend)   { $Backend   = "ollama" }
if ($env:COMESH_UNINSTALL -eq "1") { $Uninstall = $true }

$BaseUrl   = $BaseUrl.TrimEnd("/")
$PortalUrl = $PortalUrl.TrimEnd("/")

$TaskName = "CoMesh Agent"
$Root     = Join-Path $env:LOCALAPPDATA "CoMesh"
$Exe      = Join-Path $Root "comesh-agent.exe"
$EnvFile  = Join-Path $Root "agent.env"
$StateFile = Join-Path $Root "node-state.json"
$LogFile  = Join-Path $Root "agent.log"

if ($Transport -notin @("ws", "http")) { throw "Transport muss 'ws' oder 'http' sein, nicht '$Transport'." }
if ($Backend   -notin @("ollama", "openai")) { throw "Backend muss 'ollama' oder 'openai' sein." }
if ($PortalUrl -notmatch '^https?://') { throw "PortalUrl muss mit http:// oder https:// beginnen: $PortalUrl" }
if ($BaseUrl   -notmatch '^https?://') { throw "BaseUrl muss mit http:// oder https:// beginnen: $BaseUrl" }

function Write-Step($text) { Write-Host ""; Write-Host "==> $text" -ForegroundColor Cyan }
function Write-Ok($text)   { Write-Host "  $text" }
function Write-Warn($text) { Write-Host "WARNUNG: $text" -ForegroundColor Yellow }
# Bewusst `throw` statt `exit`: bei `irm ... | iex` beendet `exit` die ganze
# PowerShell-Sitzung des Nutzers - nach einer Fehlermeldung ist das eine Frechheit.
function Fail($text) {
    Write-Host ""
    Write-Host "FEHLER: $text" -ForegroundColor Red
    throw "Installation abgebrochen."
}

# TLS 1.2 erzwingen: Windows PowerShell 5.1 verhandelt sonst je nach Fassung
# noch TLS 1.0, und der Portal-Name antwortet darauf nicht mehr.
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch { }

# ---------------------------------------------------------------------------
# Architektur
# ---------------------------------------------------------------------------
$archRaw = $env:PROCESSOR_ARCHITECTURE
switch ($archRaw) {
    "AMD64" { $Arch = "x86_64" }
    "ARM64" { $Arch = "arm64" }
    default { Fail "Nicht unterstuetzte Architektur: $archRaw (erwartet AMD64/ARM64)." }
}
if ($Arch -ne "x86_64") {
    Write-Warn "Dies ist ein ARM64-Windows. Ausgeliefert wird zurzeit nur comesh-agent-windows-x86_64.exe"
    Write-Warn "(laeuft unter Windows-on-ARM emuliert). Bei Problemen bitte auf einem x64-Rechner installieren."
}

# ---------------------------------------------------------------------------
# Deinstallation
# ---------------------------------------------------------------------------
if ($Uninstall) {
    Write-Step "CoMesh-Agent entfernen"
    Get-Process -Name "comesh-agent" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    & schtasks.exe /Delete /F /TN $TaskName 2>$null | Out-Null
    foreach ($f in @($Exe, $EnvFile, $LogFile, "$LogFile.1", "$LogFile.2", $StateFile)) {
        if (Test-Path -LiteralPath $f) { Remove-Item -LiteralPath $f -Force; Write-Ok "entfernt: $f" }
    }
    Write-Ok "Aufgabe '$TaskName' entfernt."
    Write-Host ""
    Write-Host "Im Portal steht die Node weiterhin in der Geraeteliste - dort loeschen,"
    Write-Host "sonst bleibt sie als offline sichtbar."
    return
}

# ---------------------------------------------------------------------------
# 1. Binary laden und pruefen
# ---------------------------------------------------------------------------
Write-Step "Binary laden (windows/$Arch)"
$asset    = "comesh-agent-windows-$Arch.exe"
$assetUrl = "$BaseUrl/$asset"
$shaUrl   = "$assetUrl.sha256"

New-Item -ItemType Directory -Path $Root -Force | Out-Null
$tmpDir = Join-Path $env:TEMP ("comesh-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
New-Item -ItemType Directory -Path $tmpDir -Force | Out-Null
$tmpExe = Join-Path $tmpDir $asset
$tmpSha = "$tmpExe.sha256"

try {
    Invoke-WebRequest -UseBasicParsing -Uri $shaUrl -OutFile $tmpSha
} catch {
    Fail "Pruefsumme nicht ladbar: $shaUrl`nOhne Pruefsumme wird nichts installiert."
}

$expected = ((Get-Content -LiteralPath $tmpSha -Raw).Trim() -split '\s+')[0].ToLower()
if ($expected -notmatch '^[0-9a-f]{64}$') {
    Fail "Die Datei $asset.sha256 enthaelt keine gueltige SHA-256-Summe (gelesen: '$expected')."
}

# Pruefsumme als Cache-Schluessel: Cloudflare liefert `.exe` aus dem eigenen
# Edge-Cache (gemessen 04.11.2026: nach dem Austausch des Windows-Binaries kam
# ueber HTTPS weiter die alte Datei, cf-cache-status HIT, TTL 4 h, waehrend die
# .sha256 daneben schon die neue Summe trug). Der Query aendert sich mit dem
# Inhalt und macht den Cache-Treffer damit unmoeglich.
$dlUrl = "$assetUrl" + "?sha=" + $expected.Substring(0, 12)
try {
    Invoke-WebRequest -UseBasicParsing -Uri $dlUrl -OutFile $tmpExe
} catch {
    Fail "Download fehlgeschlagen: $dlUrl`n$($_.Exception.Message)`nPruefe -BaseUrl und ob die Datei dort liegt."
}
$actual = (Get-FileHash -LiteralPath $tmpExe -Algorithm SHA256).Hash.ToLower()
if ($actual -ne $expected) {
    Fail "Pruefsumme stimmt nicht.`n  erwartet: $expected`n  erhalten: $actual`nDie Datei wurde unterwegs veraendert oder ist unvollstaendig. Nicht installiert."
}
Write-Ok "SHA-256 geprueft: $actual"

# Laufende Instanz vor dem Ersetzen beenden (Windows sperrt die .exe sonst).
Get-Process -Name "comesh-agent" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 800
Copy-Item -LiteralPath $tmpExe -Destination $Exe -Force
Remove-Item -LiteralPath $tmpDir -Recurse -Force -ErrorAction SilentlyContinue

$versionLine = & $Exe --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Fail "Das Binary startet nicht:`n$versionLine"
}
Write-Ok "installiert: $Exe - $versionLine"

# ---------------------------------------------------------------------------
# 2. Account-Schluessel
# ---------------------------------------------------------------------------
Write-Step "Portal-Konto"
if ($KeyFile) {
    if (-not (Test-Path -LiteralPath $KeyFile)) { Fail "Schluesseldatei nicht lesbar: $KeyFile" }
    $accountKey = (Get-Content -LiteralPath $KeyFile -Raw).Trim()
} elseif ($env:COMESH_USER_KEY) {
    $accountKey = $env:COMESH_USER_KEY.Trim()
} elseif ((Test-Path -LiteralPath $EnvFile) -and (Select-String -LiteralPath $EnvFile -Pattern '^PORTAL_USER_KEY=(.+)$' -Quiet)) {
    $accountKey = (Select-String -LiteralPath $EnvFile -Pattern '^PORTAL_USER_KEY=(.+)$').Matches[0].Groups[1].Value
    Write-Ok "Vorhandener Account-Schluessel wird beibehalten (neu setzen: `$env:COMESH_USER_KEY)."
} else {
    if (-not [Environment]::UserInteractive) {
        Fail "Keine Konsole fuer die Eingabe. Setze den Schluessel vorher:`n  `$env:COMESH_USER_KEY = 'gpu_...'"
    }
    $secure = Read-Host -AsSecureString "  Account-Schluessel (API-Key deines CoMesh-Kontos, Eingabe bleibt unsichtbar)"
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try   { $accountKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr).Trim() }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
}

if (-not $accountKey) { Fail "Ohne Account-Schluessel kann sich die Node nicht registrieren." }
if ($accountKey -notmatch '^[A-Za-z0-9._:-]+$') {
    Fail "Der Schluessel enthaelt unerwartete Zeichen (erwartet: Buchstaben, Ziffern, . _ : -)."
}

# Vorpruefung: stimmt Schluessel + Portal-URL? Der haeufigste Fehlschlag zeigt sich
# damit sofort statt fuenf Minuten spaeter im Aufgaben-Protokoll.
$role = ""
try {
    $headers = @{ Authorization = "Bearer $accountKey" }
    $me = Invoke-RestMethod -Uri "$PortalUrl/v1/me" -Headers $headers -TimeoutSec 20 -Method Get
    if ($me.email) { $role = [string]$me.role }
    if ($role) { Write-Ok "Konto erkannt: $($me.email) (Rolle: $role)." }
} catch {
    Write-Warn "Vorpruefung des Schluessels fehlgeschlagen ($($_.Exception.Message)). Die Installation laeuft weiter."
}
if ($role -eq "consumer") {
    Write-Warn "Das Konto hat die Rolle 'consumer'. Eine Node registriert nur ein Konto mit 'provider' oder 'both'."
}

# ---------------------------------------------------------------------------
# 3. VRAM
# ---------------------------------------------------------------------------
Write-Step "VRAM"
if (-not $VramGb) {
    $detected = $null
    $smi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
    if ($smi) {
        try {
            $mb = (& nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>$null | Select-Object -First 1)
            $mb = ($mb -replace '[^0-9]', '')
            if ($mb -and [int]$mb -gt 0) { $detected = [int]([int]$mb / 1024) }
        } catch { }
    }
    if ($detected) {
        Write-Ok "NVIDIA-GPU erkannt: $detected GB. Der Agent misst selbst - kein Eintrag noetig."
    } else {
        $totalGb = [int]([math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB))
        $suggest = if ($totalGb -gt 2) { [int]($totalGb * 3 / 4) } else { 8 }
        Write-Ok "Keine NVIDIA-GPU erkannt. Ohne Angabe meldet der Agent 1 GB, und das Portal"
        Write-Ok "weist dann JEDEN Auftrag ab - die Node steht online und bekommt nichts."
        if ([Environment]::UserInteractive) {
            $answer = Read-Host "  VRAM, den diese Node anbieten darf (GB) [$suggest]"
            $VramGb = if ([string]::IsNullOrWhiteSpace($answer)) { "$suggest" } else { $answer.Trim() }
        } else {
            $VramGb = "$suggest"
        }
    }
}
if ($VramGb) {
    if ($VramGb -notmatch '^\d+$' -or [int]$VramGb -lt 1) { Fail "VRAM muss eine ganze Zahl in GB sein, nicht '$VramGb'." }
    Write-Ok "gemeldeter VRAM: $VramGb GB (Uebersteuerung)"
}

# ---------------------------------------------------------------------------
# 4. Konfiguration
# ---------------------------------------------------------------------------
Write-Step "Konfiguration"
if (-not $Name) { $Name = $env:COMPUTERNAME }
if (-not $InferenceUrl) {
    $InferenceUrl = if ($Backend -eq "openai") { "http://127.0.0.1:1234" } else { "http://127.0.0.1:11434" }
}

$lines = @(
    "# CoMesh Node-Agent - erzeugt von install.ps1 (enthaelt den Account-Schluessel)"
    "# Ein erneuter Lauf von install.ps1 ueberschreibt diese Datei."
    "PORTAL_URL=$PortalUrl"
    "PORTAL_USER_KEY=$accountKey"
    "AGENT_TRANSPORT=$Transport"
    "NODE_NAME=$Name"
    "BACKEND=$Backend"
    $(if ($Backend -eq "openai") { "INFERENCE_URL=$InferenceUrl" } else { "OLLAMA_URL=$InferenceUrl" })
)
if ($VramGb)      { $lines += "NODE_VRAM_GB=$VramGb" }
$lines += "NODE_STATE_FILE=$StateFile"
$lines += "AGENT_LOG_FILE=$LogFile"

# UTF-8 ohne BOM: ein BOM wuerde den ersten Schluessel zu "\ufeffPORTAL_URL"
# machen, und der Agent faende seine Portal-Adresse nicht mehr.
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllLines($EnvFile, $lines, $utf8NoBom)

# Rechte: nur das eigene Konto. `icacls` ist der Weg ohne Adminrechte; die
# Vererbung wird entfernt, sonst liest jeder lokale Administrator mit.
$whoami = if ($env:USERDOMAIN) { "$($env:USERDOMAIN)\$($env:USERNAME)" } else { $env:USERNAME }
& icacls.exe $EnvFile /inheritance:r /grant:r "${whoami}:(F)" *> $null
Write-Ok "geschrieben: $EnvFile (nur $whoami)"

# Selbsttest mit genau dieser Konfiguration, bevor die Aufgabe startet.
$env:COMESH_AGENT_ENV = $EnvFile
$checkOut = & $Exe --check 2>&1
$checkOut | ForEach-Object { Write-Ok $_ }
$checkOk = ($LASTEXITCODE -eq 0)
Remove-Item Env:\COMESH_AGENT_ENV -ErrorAction SilentlyContinue
if (-not $checkOk) { Write-Warn "Selbsttest meldet eine unvollstaendige Konfiguration. Die Aufgabe wird trotzdem eingerichtet." }

# ---------------------------------------------------------------------------
# 5. Aufgabe in der Aufgabenplanung (ohne Adminrechte)
# ---------------------------------------------------------------------------
Write-Step "Autostart"
# /SC ONLOGON legt die Aufgabe im Konto des Angemeldeten an - dafuer braucht es
# keine Administratorrechte. Der Pfad steht in Anfuehrungszeichen, weil
# "C:\Users\Vorname Nachname\..." Leerzeichen enthalten kann.
$taskRun = '"{0}"' -f $Exe
& schtasks.exe /Create /F /SC ONLOGON /TN $TaskName /TR $taskRun 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Fail "Die Aufgabe '$TaskName' liess sich nicht anlegen (schtasks Exitcode $LASTEXITCODE)."
}
& schtasks.exe /Run /TN $TaskName 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Warn "Die Aufgabe wurde angelegt, startet aber nicht auf Anhieb. Start von Hand: schtasks /Run /TN `"$TaskName`""
}
Write-Ok "Aufgabe '$TaskName': bei Anmeldung, ohne Adminrechte"

# ---------------------------------------------------------------------------
# 6. Status
# ---------------------------------------------------------------------------
Write-Step "Status"
$deadline = (Get-Date).AddSeconds(45)
while ((Get-Date) -lt $deadline) {
    if ((Test-Path -LiteralPath $LogFile) -and (Select-String -LiteralPath $LogFile -Pattern "WS welcome received" -Quiet -ErrorAction SilentlyContinue)) { break }
    Start-Sleep -Seconds 3
}

$proc = Get-Process -Name "comesh-agent" -ErrorAction SilentlyContinue
$svc = if ($proc) { "laeuft (PID $($proc[0].Id))" } else { "laeuft NICHT" }

try { $health = (Invoke-WebRequest -UseBasicParsing -Uri "$PortalUrl/health" -TimeoutSec 10).StatusCode }
catch { $health = "000" }

$appears = "noch nicht"
try {
    $myNodes = Invoke-RestMethod -Uri "$PortalUrl/nodes/my" -Headers @{ Authorization = "Bearer $accountKey" } -TimeoutSec 15
    if ($myNodes | Where-Object { $_.name -eq $Name }) { $appears = "ja (Name: $Name)" }
} catch { }

$wsState = if ((Test-Path -LiteralPath $LogFile) -and (Select-String -LiteralPath $LogFile -Pattern "WS welcome received" -Quiet -ErrorAction SilentlyContinue)) { "verbunden" } else { "nicht verbunden" }

Write-Host "  Aufgabe       : $TaskName"
Write-Host "  Prozess       : $svc"
if ($Transport -eq "ws") { Write-Host "  Transport     : ws (WebSocket $wsState)" } else { Write-Host "  Transport     : http" }
Write-Host "  Portal        : $PortalUrl/health -> HTTP $health"
# Das Backend ist die zweithaeufigste Ursache fuer "Node online, aber nie ein
# Auftrag": der Agent steht, nur rechnen kann er nichts.
$backendProbe = if ($Backend -eq "openai") { "$InferenceUrl/v1/models" } else { "$InferenceUrl/api/tags" }
try { $backendCode = (Invoke-WebRequest -UseBasicParsing -Uri $backendProbe -TimeoutSec 5).StatusCode }
catch { $backendCode = "000" }
Write-Host "  Backend       : $InferenceUrl -> HTTP $backendCode"
if ("$backendCode" -ne "200") {
    Write-Warn "Das Backend antwortet nicht ($InferenceUrl). Die Node ist dann online, bekommt"
    Write-Warn "aber keinen Auftrag - erst Ollama/LM Studio starten, dann den Dienst neu starten."
}
Write-Host "  Node im Portal: $appears"
Write-Host ""
Write-Host "  Protokoll     : $LogFile"
Write-Host "  Aufgabe       : schtasks /Query /TN `"$TaskName`" /V /FO LIST"

if (-not $proc -or $appears -eq "noch nicht") {
    Write-Host ""
    Write-Warn "Noch nicht vollstaendig. Die letzten Protokollzeilen:"
    if (Test-Path -LiteralPath $LogFile) { Get-Content -LiteralPath $LogFile -Tail 15 | ForEach-Object { Write-Host "    $_" } }
    Write-Host ""
    Write-Host "Haeufige Ursachen (ausfuehrlich: docs/install.md):"
    Write-Host "  - Konto nicht fuer Provider freigegeben (Rolle 'provider' oder 'both')"
    Write-Host "  - Schluessel falsch oder widerrufen -> neu ausstellen, `$env:COMESH_USER_KEY setzen, erneut laufen"
    Write-Host "  - Backend laeuft nicht ($InferenceUrl)"
    return
}

Write-Host ""
Write-Host "Fertig. Die Node ist im Portal unter 'Geraete' sichtbar, sobald das Backend antwortet."
