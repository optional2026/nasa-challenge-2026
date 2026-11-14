# Stop the public demo (tunnel first, then the server).
param([switch]$Quiet)
$State = Join-Path $PSScriptRoot ".public_demo"
foreach ($name in "tunnel", "server") {
    $pidFile = Join-Path $State "$name.pid"
    if (Test-Path $pidFile) {
        $procId = Get-Content $pidFile
        try { Stop-Process -Id $procId -Force -ErrorAction Stop; if (-not $Quiet) { Write-Host "Stopped $name (PID $procId)" } } catch {}
        Remove-Item $pidFile -Force
    }
}
if (-not $Quiet) { Write-Host "Public demo stopped." }
