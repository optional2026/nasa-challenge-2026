@echo off
REM Publish the two-sided ASTRA demo (Crew Side + Earth Side) through Cloudflare Quick Tunnels.
REM Options are passed on, e.g.:  start_public_crew_earth.bat -EarthPassword MyPass -NoLinkSimulation
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_public_crew_earth.ps1" %*
pause
