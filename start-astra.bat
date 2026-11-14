@echo off
REM ASTRA one-click start for Windows. Creates a virtual environment on first run.
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
start "" http://127.0.0.1:8000
python run.py %*
pause
