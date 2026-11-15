@echo off
REM ASTRA two-sided demonstration on ONE Windows computer:
REM   Crew Side  (onboard spacecraft server)  http://127.0.0.1:8000   astronauts + CMO
REM   Earth Side (ground operations server)   http://127.0.0.1:8100   administrator + ground flight surgeon
REM Separate processes, ports and databases (backend\data\onboard, backend\data\earth). Records travel between the
REM two databases only through the signed synchronization API. The CMO "Simulate Earth Connection Loss" control is
REM enabled for this DEMONSTRATION. Both databases are reset and re-seeded with the SYNTHETIC crew on every start.
cd /d "%~dp0backend"
if not exist .venv (
  echo Creating Python virtual environment...
  python -m venv .venv || (echo Python 3.10+ is required: https://www.python.org/downloads/ & pause & exit /b 1)
  call .venv\Scripts\activate.bat
  python -m pip install --upgrade pip
  pip install -r requirements.txt || (echo Package installation failed. & pause & exit /b 1)
) else (
  call .venv\Scripts\activate.bat
)
start "ASTRA Earth Side :8100" cmd /k python run.py --side earth --reset-db
timeout /t 4 /nobreak >nul
start "ASTRA Crew Side (onboard) :8000" cmd /k python run.py --side onboard --allow-link-simulation --reset-db
timeout /t 8 /nobreak >nul
start "" http://127.0.0.1:8000
start "" http://127.0.0.1:8100
echo.
echo Crew Side  : http://127.0.0.1:8000  (vega, okafor = astronauts; mori = CMO)
echo Earth Side : http://127.0.0.1:8100  (admin = administrator; ramirez = ground flight surgeon)
echo Close the two server windows to stop. See docs\CREW_EARTH_SYNC.md for the demonstration script.
pause
