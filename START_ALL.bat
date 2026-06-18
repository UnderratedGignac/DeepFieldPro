@echo off
setlocal enabledelayedexpansion
title DeepFieldPro - Launcher
cd /d "%~dp0"

echo.
echo ================================================================
echo   DeepFieldPro  ^|  ML Betting Research System  ^|  PAPER ONLY
echo ================================================================
echo.

:: ----------------------------------------------------------------
:: 1. Kill every existing Python process and any leftover cmd windows.
::    This clears orphaned listening sockets on 5050-5060.
:: ----------------------------------------------------------------
echo [1/6] Cleaning up old processes...
powershell -NoProfile -Command "Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue"
powershell -NoProfile -Command "Get-Process cmd -ErrorAction SilentlyContinue | Where-Object {$_.MainWindowTitle -like '*DeepFieldPro*'} | Stop-Process -Force -ErrorAction SilentlyContinue"
timeout /t 2 /nobreak >nul
echo [OK] Processes cleared.
echo.

:: ----------------------------------------------------------------
:: 2. Validate the venv interpreter
:: ----------------------------------------------------------------
echo [2/6] Checking Python environment...
if not exist ".venv\Scripts\python.exe" (
    echo.
    echo [ERROR] .venv\Scripts\python.exe not found.
    echo.
    echo         Recreate it:
    echo           C:\Users\Anthony\AppData\Local\Programs\Python\Python312\python.exe -m venv .venv
    echo           .venv\Scripts\pip.exe install -r requirements.txt
    echo.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('".venv\Scripts\python.exe" --version 2^>^&1') do set PYVER=%%v
echo [OK] !PYVER!
echo.

:: ----------------------------------------------------------------
:: 3. Find the first free port starting at 5050.
:: ----------------------------------------------------------------
echo [3/6] Finding a free port...
set PORT=
for %%p in (5050 5051 5052 5053 5054 5055 5056 5057 5058 5059 5060) do (
    if not defined PORT (
        netstat -ano 2>nul | findstr ":%%p " | findstr /i "LISTENING" >nul 2>&1
        if errorlevel 1 set PORT=%%p
    )
)
if not defined PORT (
    echo [WARN] All ports 5050-5060 appear busy. Forcing 5050.
    set PORT=5050
)
echo [OK] Port !PORT! is free.
echo !PORT!>current_port.txt
echo.

:: ----------------------------------------------------------------
:: 4. One-time / idempotent setup steps
:: ----------------------------------------------------------------
echo [4/6] Running setup steps...

echo   - Applying bet_log migration ^(idempotent^)...
".venv\Scripts\python.exe" tools\migrate_bet_log.py
if errorlevel 1 echo     [warn] migration step had an issue ^(continuing^).

if not exist "models\dixon_coles.json" (
    if exist "data\history.db" (
        echo   - Training Dixon-Coles model ^(first run^)...
        ".venv\Scripts\python.exe" tools\train_dixon_coles.py
    ) else (
        echo   [info] No history.db yet. Run tools\ingest_history.py then tools\train_dixon_coles.py.
    )
)

if not exist "models\lgbm_1x2.pkl" (
    echo   - Training LightGBM ensemble model (first run, ~2 min)...
    ".venv\Scripts\python.exe" tools\train_lgbm_model.py
    if errorlevel 1 echo     [warn] LightGBM training failed (daemon falls back to DC model).
)

echo   - Training 1X2 calibrator...
".venv\Scripts\python.exe" tools\train_1x2_calibrator.py
if errorlevel 1 echo     [warn] calibrator step had an issue ^(daemon falls back to raw probs^).

echo [OK] Setup done.
echo.

:: ----------------------------------------------------------------
:: 5. Launch dashboard + daemon
:: ----------------------------------------------------------------
echo [5/6] Launching dashboard + daemon...
if not exist "logs" mkdir logs >nul 2>&1

set DEEPFIELD_PORT=!PORT!
set DEEPFIELD_DISABLE_DAEMON=

".venv\Scripts\python.exe" -c "open('logs\\_launch.bat','w').write('@echo off\r\n.venv\\Scripts\\python.exe src\\live_dashboard_server.py >>logs\\server.log 2>&1\r\n')"

start "DeepFieldPro" /MIN cmd /c "logs\_launch.bat"

echo [OK] Server process started.
echo      Dashboard : http://localhost:!PORT!
echo      Log file  : %~dp0logs\server.log
echo.

:: ----------------------------------------------------------------
:: 6. Poll /api/state until the server responds, then open browser.
:: ----------------------------------------------------------------
echo [6/6] Waiting for server to be ready...
set /a TRIES=0
:poll
timeout /t 2 /nobreak >nul
powershell -NoProfile -Command "try{$null=Invoke-WebRequest -Uri 'http://127.0.0.1:!PORT!/api/state' -TimeoutSec 2 -UseBasicParsing;exit 0}catch{exit 1}" >nul 2>&1
if !errorlevel! == 0 goto ready
set /a TRIES+=1
if !TRIES! geq 20 (
    echo.
    echo [WARN] Server is slow to start. Opening browser anyway.
    echo        Check %~dp0logs\server.log for errors.
    goto open
)
<nul set /p="."
goto poll

:ready
echo.
echo [OK] Server is responding!

:open
echo.
echo ================================================================
echo   DeepFieldPro is LIVE
echo   Dashboard : http://localhost:!PORT!
echo   Log       : %~dp0logs\server.log
echo   Mode      : SHADOW ^(paper^) - real-money Arena stays PAUSED
echo ================================================================
echo.
start "" "http://localhost:!PORT!/"
echo   Press any key to stop all services and exit.
echo   (Close this window to leave everything running in the background.)
echo.
pause >nul

:: ----------------------------------------------------------------
:: Graceful shutdown on keypress
:: ----------------------------------------------------------------
echo.
echo [*] Stopping all services...
powershell -NoProfile -Command "Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue"
echo [+] Done. Goodbye.
timeout /t 2 /nobreak >nul
