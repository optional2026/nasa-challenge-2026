@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_public_demo.ps1" %*
pause
