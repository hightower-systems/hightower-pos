@echo off
REM AvidMax POS print agent - one-time installer for autostart on Windows.
REM
REM Wires the agent into Windows Task Scheduler so it launches on every
REM logon. Run this once per cashier desktop. Re-running re-creates the
REM task with the latest paths.

setlocal
cd /d "%~dp0"

echo === AvidMax Print Agent Installer ===
echo.

echo [1/4] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo  Python is not on PATH.
    echo  Install Python 3.11 or newer from https://www.python.org/downloads/
    echo  and tick "Add Python to PATH" during the installer. Then re-run this.
    pause
    exit /b 1
)
python --version

echo.
echo [2/4] Setting up virtual environment and dependencies...
if not exist .venv\Scripts\python.exe (
    python -m venv .venv
    if errorlevel 1 (
        echo  Failed to create the virtual environment.
        pause
        exit /b 1
    )
)
.venv\Scripts\pip install --disable-pip-version-check --quiet -r requirements.txt
if errorlevel 1 (
    echo  Failed to install dependencies. Check the error above.
    pause
    exit /b 1
)
echo  Dependencies installed.

if not exist .env (
    if exist .env.example (
        copy /y .env.example .env >nul
        echo  Copied .env.example -> .env. Edit .env if the printer USB ids
        echo  or POS web app URL differ from defaults.
    )
)

echo.
echo [3/4] Registering Windows Task Scheduler entry...
set "TASK_NAME=AvidMax POS Print Agent"
set "AGENT_CMD=\"%CD%\.venv\Scripts\pythonw.exe\" -m print_agent.agent"

schtasks /Query /TN "%TASK_NAME%" >nul 2>&1
if not errorlevel 1 (
    schtasks /Delete /TN "%TASK_NAME%" /F >nul
)

schtasks /Create /TN "%TASK_NAME%" /TR %AGENT_CMD% /SC ONLOGON /RL HIGHEST /F >nul
if errorlevel 1 (
    echo  Failed to register the Task Scheduler task.
    echo  Try running this installer as an Administrator: right-click ^&
    echo  "Run as administrator".
    pause
    exit /b 1
)
echo  Task registered: "%TASK_NAME%"
echo  The agent will start automatically on next user logon.

echo.
echo [4/4] Printing a test receipt to verify the printer wiring...
.venv\Scripts\python -c "from print_agent.escpos_client import StarTSP100; from print_agent.config import get_settings; s = get_settings(); p = StarTSP100.open_usb(vendor_id=s.printer_vendor_id, product_id=s.printer_product_id, profile=s.printer_profile); p.print_text('AvidMax Print Agent installed.\nIf you see this, the printer\nis wired correctly.\n', cut=True); p.close()"
if errorlevel 1 (
    echo  Test print failed. The Task Scheduler entry was still created;
    echo  fix the printer wiring then run start_print_agent.bat to retry.
    pause
    exit /b 1
)

echo.
echo === Installation complete. ===
echo The agent will autostart on next login. To start it now without
echo signing out, run:  schtasks /Run /TN "%TASK_NAME%"
echo Or double-click start_print_agent.bat for an interactive run.
pause
