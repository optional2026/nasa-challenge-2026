# Stop the public two-sided demo: both tunnels first, then both servers.
param([switch]$Quiet)
$State = Join-Path $PSScriptRoot ".public_crew_earth"
foreach ($name in "tunnel-crew", "tunnel-earth", "server-onboard", "server-earth") {
    $pidFile = Join-Path $State "$name.pid"
    if (Test-Path $pidFile) {
        $procId = Get-Content $pidFile
        try { Stop-Process -Id $procId -Force -ErrorAction Stop; if (-not $Quiet) { Write-Host "Stopped $name (PID $procId)" } } catch {}
        Remove-Item $pidFile -Force
    }
}
if (-not $Quiet) { Write-Host "Public Crew Side / Earth Side demo stopped." }
