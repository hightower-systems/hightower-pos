@echo off
REM Hightower POS print agent - manual launcher.
REM
REM Drop this folder onto the cashier's Windows desktop, double-click this
REM .bat to start the agent. Closing the black window stops the agent.
REM Phase 2 ships an installer that wires the agent into Windows Task
REM Scheduler so this manual step goes away.

setlocal
cd /d "%~dp0"

if not exist .venv\Scripts\python.exe (
    echo [setup] Creating venv and installing dependencies. One-time, ~30s...
    python -m venv .venv
    if errorlevel 1 (
        echo [setup] python is not on PATH. Install Python 3.11+ from python.org
        echo [setup] making sure "Add to PATH" is ticked, then run this again.
        pause
        exit /b 1
    )
    .venv\Scripts\pip install --disable-pip-version-check -r requirements.txt
    if errorlevel 1 (
        echo [setup] dependency install failed. Check the messages above.
        pause
        exit /b 1
    )
)

if not exist .env (
    if exist .env.example (
        echo [setup] Copying .env.example to .env. Edit .env if needed.
        copy /y .env.example .env >nul
    )
)

echo [run] Starting Hightower print agent on http://127.0.0.1:9100
.venv\Scripts\python -m print_agent.agent
echo [run] Agent stopped.
pause
