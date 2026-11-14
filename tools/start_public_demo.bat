@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_public_demo.ps1" %*
pause
