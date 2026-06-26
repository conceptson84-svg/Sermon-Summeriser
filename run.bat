@echo off
REM Church Sermon Summarizer launcher for Windows.
REM First run: creates a virtualenv, installs dependencies, copies the config.
REM Later runs: just launches the app.

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    py -3 -m venv .venv
    if errorlevel 1 (
        echo Could not create venv. Install Python 3.11+ from python.org and retry.
        pause
        exit /b 1
    )
    echo Installing dependencies (first run only, this can take a few minutes)...
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)

if not exist "config.json" (
    copy config.example.json config.json >nul
    echo Created config.json - add your API key, then run again.
    notepad config.json
    pause
    exit /b 0
)

".venv\Scripts\python.exe" run.py
pause
