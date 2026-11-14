@echo off
REM Runs the backend test suite (46 tests). For browser tests see docs\TESTING.md.
cd /d "%~dp0backend"
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
pip install -r requirements-dev.txt
python -m pytest -q
pause
