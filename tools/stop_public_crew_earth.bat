@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_public_crew_earth.ps1" %*
pause
