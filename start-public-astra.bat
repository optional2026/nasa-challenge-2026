@echo off
REM ASTRA public demonstration: Crew Side + Earth Side, each published through a Cloudflare Quick Tunnel.
REM Prints two https://*.trycloudflare.com links. Stop with stop-public-astra.bat
call "%~dp0tools\start_public_crew_earth.bat" %*
