@echo off
title DeepFieldPro - Full System
setlocal enabledelayedexpansion

:: =====================================================================
::  DeepFieldPro all-in-one launcher
::  - kills any old python processes (e.g. after a power cut / re-run)
::  - applies the bet_log migration + trains the 1X2 calibrator (idempotent)
::  - starts the Flask dashboard + prediction daemon (one process)
::  Dashboard: http://127.0.0.1:%DEEPFIELD_PORT%   (default 5052)
::  Betting is SHADOW (paper) only. The real-money Arena stays PAUSED.
:: =====================================================================

cd /d "%~dp0"

:: ---- pick a FREE port (override by setting DEEPFIELD_PORT first) -----
::   orphaned sockets can linger on a port after a crash; scan for a free one.
if not "%DEEPFIELD_PORT%"=="" goto :haveport
for %%P in (5052 5053 5054 5055 5056 5057 5058) do (
    netstat -ano | findstr /R /C:":%%P .*LISTENING" >nul || ( set DEEPFIELD_PORT=%%P & goto :haveport )
)
set DEEPFIELD_PORT=5052
:haveport

:: ---- locate the venv interpreter (system python is only a stub) ------
set PY=.venv\Scripts\python.exe
if not exist "%PY%" (
    echo [!] ERROR: venv interpreter not found at %PY%
    echo [!] Recreate it:
    echo     C:\Users\Anthony\AppData\Local\Programs\Python\Python312\python.exe -m venv .venv
    echo     %PY% -m pip install -r requirements.txt
    pause
    exit /b 1
)
if not exist "src\live_dashboard_server.py" (
    echo [!] ERROR: run this from the project root ^(src\live_dashboard_server.py missing^).
    pause
    exit /b 1
)

echo =======================================================
echo    DeepFieldPro - ML Betting Research System
echo    Port   : %DEEPFIELD_PORT%
echo    Mode   : SHADOW (paper) - real-money Arena stays PAUSED
echo =======================================================
echo.

:: ---- 1) kill old processes (frees the port + daemon threads) --------
echo [1/4] Stopping any old python processes...
taskkill /IM python.exe /F >nul 2>&1
echo       done.

:: ---- 2) one-time setup: schema migration (idempotent) ---------------
echo [2/4] Applying bet_log migration...
"%PY%" tools\migrate_bet_log.py
if errorlevel 1 echo       [warn] migration step had an issue ^(continuing^).

:: ---- 2b) ensure the Dixon-Coles model exists (train if missing) -----
if not exist "models\dixon_coles.json" (
    if exist "data\history.db" (
        echo [2b ] Training Dixon-Coles model ^(first run^)...
        "%PY%" tools\train_dixon_coles.py
    ) else (
        echo [2b ] No history.db yet — run tools\ingest_history.py then tools\train_dixon_coles.py
        echo       ^(daemon falls back to the heuristic until then^).
    )
)

:: ---- 3) (re)train the 1X2 calibrator from the latest results --------
echo [3/4] Training 1X2 calibrator...
"%PY%" tools\train_1x2_calibrator.py
if errorlevel 1 echo       [warn] calibrator step had an issue ^(daemon falls back to raw probs^).

:: ---- 4) launch the unified server + daemon --------------------------
echo [4/4] Launching server + prediction daemon...
echo       Opening http://127.0.0.1:%DEEPFIELD_PORT% shortly. Keep this window open.
echo.
start "" /B cmd /c "ping -n 8 127.0.0.1 >nul && start http://127.0.0.1:%DEEPFIELD_PORT%"

:: foreground so you see live output; Ctrl+C to stop the system.
"%PY%" src\live_dashboard_server.py

echo.
echo [!] Server process exited.
pause
