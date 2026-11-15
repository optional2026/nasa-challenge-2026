# Start ASTRA in public-demo mode behind a Cloudflare Quick Tunnel.
#   - separate data folder (backend\data-public) and port, so your local database is never exposed
#   - fixed password for the Earth-side accounts (admin, ramirez) so judges can reuse it; change it with -Password
#   - the public database is wiped and re-seeded on every start (clean synthetic data for each session)
#   - prints the public https://*.trycloudflare.com URL and self-tests it (health, sign-in, WebSocket)
# Stop with tools\stop_public_demo.bat
param([int]$Port = 8010, [string]$Password = "AstraJudges2026")
$ErrorActionPreference = "Stop"

$Root    = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root "backend"
$State   = Join-Path $PSScriptRoot ".public_demo"
$Bin     = Join-Path $PSScriptRoot "bin"
$Cf      = Join-Path $Bin "cloudflared.exe"
New-Item -ItemType Directory -Force $State, $Bin | Out-Null

# Stop a previous run first
& (Join-Path $PSScriptRoot "stop_public_demo.ps1") -Quiet

# --- Python environment -------------------------------------------------------
$Py = Join-Path $Backend ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    Write-Host "Creating Python virtual environment..."
    python -m venv (Join-Path $Backend ".venv")
    & $Py -m pip install -q -r (Join-Path $Backend "requirements.txt")
}

# --- cloudflared ----------------------------------------------------------------
if (-not (Test-Path $Cf)) {
    Write-Host "Downloading cloudflared..."
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -UseBasicParsing -OutFile $Cf `
        "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
}

# --- Backend --------------------------------------------------------------------
$env:ASTRA_PUBLIC_DEMO   = "1"
$env:ASTRA_DEMO_PASSWORD = $Password
$env:ASTRA_DATA_DIR      = Join-Path $Backend "data-public"
$env:PYTHONUNBUFFERED    = "1"

$server = Start-Process -FilePath $Py -ArgumentList "run.py", "--port", $Port, "--reset-db" -WorkingDirectory $Backend `
    -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $State "server.log") -RedirectStandardError (Join-Path $State "server.err.log")
$server.Id | Set-Content (Join-Path $State "server.pid")

Write-Host "Starting ASTRA on 127.0.0.1:$Port ..."
$up = $false
for ($i = 0; $i -lt 60; $i++) {
    try { Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$Port/api/v1/health" -TimeoutSec 2 | Out-Null; $up = $true; break }
    catch { Start-Sleep -Milliseconds 500 }
}
if (-not $up) { Write-Host "ASTRA did not start. See $State\server.err.log" -ForegroundColor Red; exit 1 }

# --- Tunnel ---------------------------------------------------------------------
$TunnelLog = Join-Path $State "tunnel.log"
Remove-Item $TunnelLog -ErrorAction SilentlyContinue
$tunnel = Start-Process -FilePath $Cf -ArgumentList "tunnel", "--no-autoupdate", "--url", "http://127.0.0.1:$Port" `
    -WindowStyle Hidden -PassThru -RedirectStandardError $TunnelLog -RedirectStandardOutput (Join-Path $State "tunnel.out.log")
$tunnel.Id | Set-Content (Join-Path $State "tunnel.pid")

Write-Host "Opening Cloudflare tunnel..."
$Url = $null
for ($i = 0; $i -lt 60 -and -not $Url; $i++) {
    Start-Sleep -Seconds 1
    if (Test-Path $TunnelLog) {
        $m = Select-String -Path $TunnelLog -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" | Select-Object -First 1
        if ($m) { $Url = $m.Matches[0].Value }
    }
}
if (-not $Url) { Write-Host "Tunnel URL not received. See $TunnelLog" -ForegroundColor Red; exit 1 }

@"
URL:      $Url
Password: $Password   (Mission Control accounts: admin, ramirez)
Started:  $(Get-Date -Format s)
"@ | Set-Content (Join-Path $State "info.txt")

Write-Host "Self-testing the public link (DNS can take up to a minute)..."
& $Py (Join-Path $PSScriptRoot "check_public_url.py") $Url --password $Password
$ok = $LASTEXITCODE -eq 0

Write-Host ""
Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "  ASTRA public demo $(if ($ok) {'is LIVE'} else {'started (self-test failed - see above)'})"
Write-Host "  URL:       $Url" -ForegroundColor Green
Write-Host "  Crew (vega, okafor, mori): crew demo password (README)"
Write-Host "  Mission Control (admin / ramirez) password: $Password" -ForegroundColor Green
Write-Host "  Runs while this PC is on. Stop: tools\stop_public_demo.bat"
Write-Host "==================================================================" -ForegroundColor Cyan
