@echo off
setlocal enabledelayedexpansion
title DeepFieldPro — Launcher
cd /d "%~dp0"
color 0A

:: ════════════════════════════════════════════════════════════════════════
::  DEEPFIELDPRO UNIFIED LAUNCHER  v4.0  (2026-07-13)
::  Systems:
::    [S] SHADOW  — Paper bets, research, safe experiments
::    [D] DAEMON  — Prediction engine only, no UI
::    [A] ELIEATCH — AI REPL assistant
::  Research/paper mode only — no real-money execution path exists in this app.
:: ════════════════════════════════════════════════════════════════════════

echo.
echo  ########################################################################
echo  ##                                                                    ##
echo  ##               D E E P F I E L D  P R O  2 0 2 6                  ##
echo  ##                                                                    ##
echo  ##   Platform  : Football Betting Research ^& Operations               ##
echo  ##   WC 2026   : Round of 32  ^|  ~31 games  ^|  thru July 19           ##
echo  ##   Mode      : Research / paper only — no real money                ##
echo  ##                                                                    ##
echo  ########################################################################
echo.
echo   Choose a mode:
echo.
echo    [S]  SHADOW   — Paper mode, virtual bankroll, no real money
echo    [D]  DAEMON   — Prediction daemon only, no browser
echo    [A]  ELIEATCH — AI REPL assistant (tools/elieatch_tui_v2.py)
echo    [Q]  QUIT
echo.

:choose
set /p CHOICE="  Your choice [S/D/A/Q]: "
if /i "!CHOICE!"=="S" goto shadow
if /i "!CHOICE!"=="D" goto daemon_only
if /i "!CHOICE!"=="A" goto elieatch
if /i "!CHOICE!"=="Q" exit /b 0
echo   Invalid — type S, D, A or Q.
goto choose

:: ════════════════════════════════════════════════════════════════════════
::  MODE VARIABLES
:: ════════════════════════════════════════════════════════════════════════
:shadow
set MODE=SHADOW
set LOGFILE=logs\server_shadow.log
set WINTITLE=DeepFieldPro-SHADOW
goto preflight

:: ════════════════════════════════════════════════════════════════════════
::  SHARED PRE-FLIGHT
:: ════════════════════════════════════════════════════════════════════════
:preflight
title DeepFieldPro — Starting [!MODE!]
echo.
echo  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo   Starting in !MODE! mode...
echo  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.

:: ── STEP 1: Kill stale Python processes ──────────────────────────────
echo  [1/9] Cleaning up old Python processes...
powershell -NoProfile -Command ^
  "Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue"
timeout /t 2 /nobreak >nul
echo          OK
echo.

:: ── STEP 2: Validate virtual environment ─────────────────────────────
echo  [2/9] Checking Python environment...
if not exist ".venv\Scripts\python.exe" (
    echo.
    echo  [ERROR] .venv not found. Run once to fix:
    echo          python -m venv .venv
    echo          .venv\Scripts\pip install -r requirements.txt
    echo.
    pause & exit /b 1
)
for /f "tokens=*" %%v in ('".venv\Scripts\python.exe" --version 2^>^&1') do set PYVER=%%v
echo          OK  !PYVER!
echo.

:: ── STEP 3: Find a free port (5050-5065) ──────────────────────────────
echo  [3/9] Finding a free port...
set PORT=
for %%p in (5050 5051 5052 5053 5054 5055 5056 5057 5058 5059 5060 5061 5062 5063 5064 5065) do (
    if not defined PORT (
        netstat -ano 2>nul | findstr ":%%p " | findstr /i "LISTENING" >nul 2>&1
        if errorlevel 1 set PORT=%%p
    )
)
if not defined PORT set PORT=5070
echo !PORT!>current_port.txt
echo          OK  Port !PORT!
echo.

:: ── STEP 4: Database setup ────────────────────────────────────────────
echo  [4/9] Database setup...
".venv\Scripts\python.exe" tools\migrate_bet_log.py >nul 2>&1
if errorlevel 1 (echo          [warn] bet_log migration issue — continuing.) else (echo          bet_log OK.)

if not exist "data\history.db" (
    echo          history.db missing — ingesting football history ^(~2 min, first run only^)...
    ".venv\Scripts\python.exe" tools\ingest_history.py
    if errorlevel 1 echo          [warn] history ingest failed — DC model uses cached values.
) else (
    echo          history.db OK.
)

:: Seed FIFA ratings for Lineups page (first run only)
if not exist "data\fifa_ratings.db" (
    echo          Seeding FIFA ratings database ^(~920 players^)...
    ".venv\Scripts\python.exe" src\seed_fifa_ratings.py >nul 2>&1
    if errorlevel 1 (echo          [warn] FIFA ratings seed failed.) else (echo          FIFA ratings OK.)
) else (
    echo          FIFA ratings OK.
)
echo.

:: ── STEP 6: ML model refresh ──────────────────────────────────────────
echo  [5/9] Checking ML models...

set DC_FRESH=0
if exist "models\dixon_coles.json" (
    powershell -NoProfile -Command "if((Get-Date)-(Get-Item 'models\dixon_coles.json').LastWriteTime -lt [TimeSpan]::FromHours(24)){exit 0}else{exit 1}" >nul 2>&1
    if !errorlevel! == 0 set DC_FRESH=1
)
if "!DC_FRESH!"=="1" (
    echo          Dixon-Coles model fresh — skipping refit.
) else (
    if exist "data\history.db" (
        echo          Dixon-Coles stale — refitting...
        ".venv\Scripts\python.exe" tools\nightly_dc_refit.py >nul 2>&1
        if errorlevel 1 (echo          [warn] DC refit failed — using cached model.) else (echo          Dixon-Coles refit OK.)
    ) else (
        echo          [skip] No history.db for Dixon-Coles.
    )
)

if exist "models\lgbm_1x2.pkl" (
    echo          LightGBM OK ^(cached^).
) else (
    echo          Training LightGBM ^(~2 min, first run only^)...
    ".venv\Scripts\python.exe" tools\train_lgbm_model.py >nul 2>&1
    if errorlevel 1 echo          [warn] LightGBM training failed — falls back to DC.
)

set CAL_FRESH=0
if exist "models\calibrator_1x2.json" (
    powershell -NoProfile -Command "if((Get-Date)-(Get-Item 'models\calibrator_1x2.json').LastWriteTime -lt [TimeSpan]::FromHours(24)){exit 0}else{exit 1}" >nul 2>&1
    if !errorlevel! == 0 set CAL_FRESH=1
)
if "!CAL_FRESH!"=="1" (echo          1X2 calibrator fresh.) else (
    ".venv\Scripts\python.exe" tools\train_1x2_calibrator.py >nul 2>&1
    if errorlevel 1 (echo          [warn] 1X2 calibrator failed.) else (echo          1X2 calibrator OK.)
)

set OU_FRESH=0
if exist "models\calibrator_ou25.json" (
    powershell -NoProfile -Command "if((Get-Date)-(Get-Item 'models\calibrator_ou25.json').LastWriteTime -lt [TimeSpan]::FromHours(24)){exit 0}else{exit 1}" >nul 2>&1
    if !errorlevel! == 0 set OU_FRESH=1
)
if "!OU_FRESH!"=="1" (echo          O/U calibrator fresh.) else (
    ".venv\Scripts\python.exe" tools\train_ou_calibrator.py >nul 2>&1
    if errorlevel 1 (echo          [warn] O/U calibrator failed.) else (echo          O/U calibrator OK.)
)
echo.

:: ── STEP 7: Pre-flight check ──────────────────────────────────────────
echo  [6/9] Running pre-flight checks...
".venv\Scripts\python.exe" tools\preflight_check.py 2>nul
echo.

:: ── STEP 8: Launch server ─────────────────────────────────────────────
echo  [7/9] Launching dashboard + daemon [!MODE!]...
if not exist "logs" mkdir logs >nul 2>&1

(
    echo @echo off
    echo title DeepFieldPro SERVER [SHADOW]
    echo cd /d "%~dp0"
    echo set DEEPFIELD_PORT=!PORT!
    echo :: DEEPFIELD_ARENA_LIVE intentionally unset — paper mode only
    echo ".venv\Scripts\python.exe" src\live_dashboard_server.py ^>^> logs\server_shadow.log 2^>^&1
) > "logs\_server.bat"

start "!WINTITLE!" /MIN cmd /k "logs\_server.bat"
echo          Server window launched ^(minimised^).
echo          Log: %~dp0!LOGFILE!
echo.

:: ── STEP 9: Wait for server ───────────────────────────────────────────
echo  [8/9] Waiting for server to come online...
set /a TRIES=0
:poll
timeout /t 2 /nobreak >nul
powershell -NoProfile -Command ^
  "try{$r=Invoke-WebRequest -Uri 'http://127.0.0.1:!PORT!/api/state' -TimeoutSec 3 -UseBasicParsing;exit 0}catch{exit 1}" ^
  >nul 2>&1
if !errorlevel! == 0 goto ready
set /a TRIES+=1
<nul set /p="."
if !TRIES! geq 20 (
    echo.
    echo.
    echo  [warn] Server is slow. Opening browser anyway.
    echo         If dashboard doesn't load, tail the log:
    echo           powershell Get-Content !LOGFILE! -Tail 30
    goto open
)
goto poll

:ready
echo.
echo          Server is up and responding.

:open
echo.
echo  [9/9] Launch complete!
echo.

:: ── Open browser tabs ─────────────────────────────────────────────────
echo  ┌──────────────────────────────────────────────────────────────────────┐
echo  │  SHADOW — Paper Research Mode                                        │
echo  │                                                                      │
echo  │  Dashboard     http://localhost:!PORT!/                              │
echo  │  Lineups       http://localhost:!PORT!/lineups                       │
echo  │  Log           !LOGFILE!                                             │
echo  │                                                                      │
echo  │  No real money. Virtual $5,000 bankroll.                             │
echo  │  To stop: taskkill /IM python.exe /F                                 │
echo  └──────────────────────────────────────────────────────────────────────┘
start "" "http://localhost:!PORT!/"
echo.
echo  This window is safe to close. Server keeps running in the background.
echo  Press any key to close this launcher.
echo.
pause >nul
exit /b 0

:: ════════════════════════════════════════════════════════════════════════
::  DAEMON ONLY (no Flask server, no browser)
:: ════════════════════════════════════════════════════════════════════════
:daemon_only
title DeepFieldPro — Daemon Only
echo.
echo  [DAEMON] Starting prediction daemon ^(no dashboard^)...
if not exist ".venv\Scripts\python.exe" (
    echo  [ERROR] .venv not found.
    pause & exit /b 1
)
if not exist "logs" mkdir logs >nul 2>&1
echo  Log: %~dp0logs\daemon.log
echo  Press Ctrl+C in the daemon window to stop.
echo.
start "DeepFieldPro-DAEMON" cmd /k ^
  "cd /d %~dp0 && set DEEPFIELD_DISABLE_DAEMON=0 && .venv\Scripts\python.exe src\live_predictions_daemon.py >> logs\daemon.log 2>&1"
echo  Daemon launched. This window is safe to close.
pause >nul
exit /b 0

:: ════════════════════════════════════════════════════════════════════════
::  ELIEATCH AI REPL
:: ════════════════════════════════════════════════════════════════════════
:elieatch
title DeepFieldPro — ElieAtch AI REPL
echo.
echo  [ELIEATCH] Launching AI REPL assistant...
if not exist ".venv\Scripts\python.exe" (
    echo  [ERROR] .venv not found.
    pause & exit /b 1
)
echo  Type /help inside the REPL for available commands.
echo.
.venv\Scripts\python.exe tools\elieatch_tui_v2.py
pause
exit /b 0
