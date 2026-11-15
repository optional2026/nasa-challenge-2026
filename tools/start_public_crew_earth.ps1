# Publish the two-sided ASTRA demonstration (Crew Side + Earth Side) through two Cloudflare Quick Tunnels.
#
#   Crew Side  (onboard server)  127.0.0.1:8020  -> https://<random>.trycloudflare.com   astronauts + CMO
#   Earth Side (ground server)   127.0.0.1:8120  -> https://<random>.trycloudflare.com   administrator + flight surgeon
#
# * Separate data folders (backend\data-public\onboard, backend\data-public\earth): your local databases are never
#   exposed. Both public databases are wiped and re-seeded with SYNTHETIC data on every start.
# * The two servers synchronize with each other over loopback inside this PC (signed, fresh random key per session);
#   only the browser-facing web apps are published. Visitors reach them over HTTPS (Cloudflare edge).
# * Public-demo protections are on (ASTRA_PUBLIC_DEMO=1: rate limits, locked rule configuration).
# * The CMO "Simulate Earth Connection Loss" DEMONSTRATION control is enabled (judging); pass -NoLinkSimulation
#   to disable it.
# * Quick Tunnels need no Cloudflare account; the URLs change on every start and last while this PC runs the script.
#
# Usage:  tools\start_public_crew_earth.bat  [-EarthPassword X] [-CrewPassword Y] [-NoLinkSimulation] [-NoTunnel]
# Stop:   tools\stop_public_crew_earth.bat
param(
    [int]$CrewPort = 8020,
    [int]$EarthPort = 8120,
    [string]$EarthPassword = "AstraJudges2026",
    [string]$CrewPassword = "optionalwillwin",
    [switch]$NoLinkSimulation,
    [switch]$NoTunnel  # start both servers locally only (testing the script without publishing anything)
)
$ErrorActionPreference = "Stop"

$Root    = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root "backend"
$State   = Join-Path $PSScriptRoot ".public_crew_earth"
$Bin     = Join-Path $PSScriptRoot "bin"
$Cf      = Join-Path $Bin "cloudflared.exe"
$Data    = Join-Path $Backend "data-public"
New-Item -ItemType Directory -Force $State, $Bin, $Data | Out-Null

# stop a previous run of this script first
& (Join-Path $PSScriptRoot "stop_public_crew_earth.ps1") -Quiet

# --- Python environment -------------------------------------------------------------
$Py = Join-Path $Backend ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    Write-Host "Creating Python virtual environment..."
    python -m venv (Join-Path $Backend ".venv")
    & $Py -m pip install -q -r (Join-Path $Backend "requirements.txt")
}

# --- cloudflared -------------------------------------------------------------------------
if (-not $NoTunnel -and -not (Test-Path $Cf)) {
    $onPath = Get-Command cloudflared -ErrorAction SilentlyContinue
    if ($onPath) { $Cf = $onPath.Source }
    else {
        Write-Host "Downloading cloudflared (official Cloudflare release)..."
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -UseBasicParsing -OutFile $Cf `
            "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
    }
}

# --- shared settings for both servers (inherited by the child processes) -------------------
$bytes = New-Object byte[] 48
[Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
$env:ASTRA_SYNC_KEY            = [Convert]::ToBase64String($bytes)   # fresh server-to-server key per session
$env:ASTRA_PUBLIC_DEMO         = "1"
$env:ASTRA_DEMO_PASSWORD       = $EarthPassword
$env:ASTRA_CREW_DEMO_PASSWORD  = $CrewPassword
$env:PYTHONUNBUFFERED          = "1"
Remove-Item Env:ASTRA_SYNC_KEY_FILE, Env:ASTRA_EARTH_URL, Env:ASTRA_DEPLOYMENT, Env:ASTRA_DB_PATH -ErrorAction SilentlyContinue
if ($NoLinkSimulation) { Remove-Item Env:ASTRA_ALLOW_LINK_SIMULATION -ErrorAction SilentlyContinue }
else { $env:ASTRA_ALLOW_LINK_SIMULATION = "1" }

function Start-Side([string]$Side, [int]$Port, [string[]]$Extra) {
    $env:ASTRA_DATA_DIR = Join-Path $Data $Side
    $argList = @("run.py", "--side", $Side, "--port", $Port, "--reset-db") + $Extra
    $p = Start-Process -FilePath $Py -ArgumentList $argList -WorkingDirectory $Backend -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $State "$Side.log") -RedirectStandardError (Join-Path $State "$Side.err.log")
    $p.Id | Set-Content (Join-Path $State "server-$Side.pid")
    for ($i = 0; $i -lt 120; $i++) {
        try { Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$Port/api/v1/health" -TimeoutSec 2 | Out-Null; return }
        catch { Start-Sleep -Milliseconds 500 }
    }
    throw "ASTRA $Side server did not start. See $State\$Side.err.log"
}

Write-Host "Starting Earth Side server on 127.0.0.1:$EarthPort ..."
Start-Side "earth" $EarthPort @()
Write-Host "Starting Crew Side (onboard) server on 127.0.0.1:$CrewPort ..."
Start-Side "onboard" $CrewPort @("--earth-url", "http://127.0.0.1:$EarthPort")
Remove-Item Env:ASTRA_DATA_DIR -ErrorAction SilentlyContinue

if ($NoTunnel) {
    Write-Host "Both servers are running locally (no tunnel): Crew http://127.0.0.1:$CrewPort  Earth http://127.0.0.1:$EarthPort"
    exit 0
}

# --- tunnels --------------------------------------------------------------------------------
function Start-Tunnel([string]$Name, [int]$Port) {
    $log = Join-Path $State "tunnel-$Name.log"
    Remove-Item $log -ErrorAction SilentlyContinue
    $t = Start-Process -FilePath $Cf -ArgumentList "tunnel", "--no-autoupdate", "--url", "http://127.0.0.1:$Port" `
        -WindowStyle Hidden -PassThru -RedirectStandardError $log -RedirectStandardOutput (Join-Path $State "tunnel-$Name.out.log")
    $t.Id | Set-Content (Join-Path $State "tunnel-$Name.pid")
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Seconds 1
        if (Test-Path $log) {
            $m = Select-String -Path $log -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" | Select-Object -First 1
            if ($m) { return $m.Matches[0].Value }
        }
    }
    throw "Tunnel URL for $Name not received. See $log"
}

Write-Host "Opening Cloudflare tunnels..."
$CrewUrl  = Start-Tunnel "crew" $CrewPort
$EarthUrl = Start-Tunnel "earth" $EarthPort

@"
Crew Side  (astronauts vega, okafor; CMO mori)        : $CrewUrl
  crew password                                       : $CrewPassword
Earth Side (administrator admin; flight surgeon ramirez): $EarthUrl
  Earth password                                      : $EarthPassword
CMO link simulation                                   : $(if ($NoLinkSimulation) {'disabled'} else {'enabled (demonstration)'})
Started                                               : $(Get-Date -Format s)
"@ | Set-Content (Join-Path $State "info.txt")

Write-Host "Self-testing the public links (DNS can take up to a minute)..."
Write-Host " Crew Side:"
& $Py (Join-Path $PSScriptRoot "check_public_url.py") $CrewUrl --user mori --password $CrewPassword
$okCrew = $LASTEXITCODE -eq 0
Write-Host " Earth Side:"
& $Py (Join-Path $PSScriptRoot "check_public_url.py") $EarthUrl --user admin --password $EarthPassword
$okEarth = $LASTEXITCODE -eq 0

Write-Host ""
Write-Host "=====================================================================================" -ForegroundColor Cyan
Write-Host "  ASTRA public two-sided demo $(if ($okCrew -and $okEarth) {'is LIVE'} else {'started (a self-test failed - see above)'})"
Write-Host "  Crew Side  : $CrewUrl" -ForegroundColor Green
Write-Host "               vega, okafor (astronauts), mori (CMO)  -  password: $CrewPassword"
Write-Host "  Earth Side : $EarthUrl" -ForegroundColor Green
Write-Host "               admin (administrator), ramirez (flight surgeon)  -  password: $EarthPassword"
Write-Host "  Synthetic data only. Runs while this PC is on. Details: tools\.public_crew_earth\info.txt"
Write-Host "  Stop: tools\stop_public_crew_earth.bat"
Write-Host "=====================================================================================" -ForegroundColor Cyan
