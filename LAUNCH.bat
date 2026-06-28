@echo off
setlocal enabledelayedexpansion
title DeepFieldPro — Launcher
cd /d "%~dp0"
color 0A

:: ════════════════════════════════════════════════════════════════════════
::  DEEPFIELDPRO UNIFIED LAUNCHER
::  Two systems in one:
::    [S] SHADOW — paper bets, experiments, daemon research (safe)
::    [L] LIVE   — Stair AI World Cup challenge, real USDC (armed)
:: ════════════════════════════════════════════════════════════════════════

echo.
echo  ######################################################################
echo  ##                                                                  ##
echo  ##              D E E P F I E L D  P R O  2 0 2 6                  ##
echo  ##                                                                  ##
echo  ##   Platform     : Football Betting Research ^& Operations           ##
echo  ##   Systems      : Paper Research  ^|  Stair AI Challenge            ##
echo  ##                                                                  ##
echo  ######################################################################
echo.
echo  Choose a mode:
echo.
echo    [S]  SHADOW  — Paper mode, virtual bankroll, safe for experiments
echo    [L]  LIVE    — Stair AI World Cup challenge (real USDC wallet)
echo    [D]  DAEMON  — Prediction daemon only, no browser / UI
echo    [A]  ELIEATCH — AI REPL assistant (tools/elieatch_tui_v2.py)
echo    [Q]  QUIT
echo.

:choose
set /p CHOICE="  Your choice [S/L/D/A/Q]: "
if /i "!CHOICE!"=="S" goto shadow
if /i "!CHOICE!"=="L" goto live_confirm
if /i "!CHOICE!"=="D" goto daemon_only
if /i "!CHOICE!"=="A" goto elieatch
if /i "!CHOICE!"=="Q" exit /b 0
echo   Invalid — type S, L, D, A or Q.
goto choose

:: ════════════════════════════════════════════════════════════════════════
::  LIVE MODE CONFIRMATION — extra gate before arming real money
:: ════════════════════════════════════════════════════════════════════════
:live_confirm
echo.
echo  ┌─────────────────────────────────────────────────────────────────┐
echo  │  ⚠  LIVE MODE — REAL USDC WALLET                               │
echo  │                                                                 │
echo  │  The Arena autopilot will place REAL orders on Polymarket       │
echo  │  via Stair AI. Your wallet balance is at risk.                  │
echo  │                                                                 │
echo  │  Safeguards active: edge_min=5%%, conf_min=35%%, max 5 bets/run    │
echo  │  DFP sanity filter: model/market ratio cap at 3x               │
echo  │                                                                 │
echo  │  Type LIVE to confirm, anything else to cancel:                 │
echo  └─────────────────────────────────────────────────────────────────┘
echo.
set /p CONFIRM="  > "
if /i "!CONFIRM!"=="LIVE" goto live
echo   Cancelled. Returning to menu.
echo.
goto choose

:: ════════════════════════════════════════════════════════════════════════
::  SHARED PRE-FLIGHT (runs for both SHADOW and LIVE)
:: ════════════════════════════════════════════════════════════════════════
:shadow
set MODE=SHADOW
set ARENA_LIVE=0
set LOGFILE=logs\server_shadow.log
set WINTITLE=DeepFieldPro-SHADOW
goto preflight

:live
set MODE=LIVE
set ARENA_LIVE=1
set LOGFILE=logs\server_live.log
set WINTITLE=DeepFieldPro-LIVE
goto preflight

:preflight
title DeepFieldPro — Starting [!MODE!]
echo.
echo  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo   Starting in !MODE! mode...
echo  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.

:: ── STEP 1: Kill stale Python processes ──────────────────────────────
echo  [1/8] Cleaning up old Python processes...
powershell -NoProfile -Command ^
  "Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue"
timeout /t 2 /nobreak >nul
echo         OK
echo.

:: ── STEP 2: Validate virtual environment ─────────────────────────────
echo  [2/8] Checking Python environment...
if not exist ".venv\Scripts\python.exe" (
    echo.
    echo  [ERROR] .venv not found. Run once to fix:
    echo          python -m venv .venv
    echo          .venv\Scripts\pip install -r requirements.txt
    echo.
    pause & exit /b 1
)
for /f "tokens=*" %%v in ('".venv\Scripts\python.exe" --version 2^>^&1') do set PYVER=%%v
echo         OK  !PYVER!
echo.

:: ── STEP 3: Find a free port (5050-5065) ─────────────────────────────
echo  [3/8] Finding a free port...
set PORT=
for %%p in (5050 5051 5052 5053 5054 5055 5056 5057 5058 5059 5060 5061 5062 5063 5064 5065) do (
    if not defined PORT (
        netstat -ano 2>nul | findstr ":%%p " | findstr /i "LISTENING" >nul 2>&1
        if errorlevel 1 set PORT=%%p
    )
)
if not defined PORT set PORT=5070
echo !PORT!>current_port.txt
echo         OK  Port !PORT!
echo.

:: ── STEP 4: DB migrations ────────────────────────────────────────────
echo  [4/9] Database setup...
".venv\Scripts\python.exe" tools\migrate_bet_log.py >nul 2>&1
if errorlevel 1 (echo         [warn] bet_log migration issue — continuing.) else (echo         bet_log OK.)

if not exist "data\history.db" (
    echo         history.db missing — ingesting football history ^(~2 min, first run only^)...
    ".venv\Scripts\python.exe" tools\ingest_history.py
    if errorlevel 1 echo         [warn] history ingest failed — DC model uses cached values.
) else (
    echo         history.db OK.
)

:: Seed FIFA ratings for Lineups page (first run only)
if not exist "data\fifa_ratings.db" (
    echo         Seeding FIFA ratings database ^(~920 players^)...
    ".venv\Scripts\python.exe" src\seed_fifa_ratings.py >nul 2>&1
    if errorlevel 1 (echo         [warn] FIFA ratings seed failed — Lineups page will have limited data.) else (echo         FIFA ratings OK.)
) else (
    echo         FIFA ratings OK.
)
echo.

:: ── STEP 5: Model refresh (skip if models are fresh — < 24h old) ─────
echo  [5/9] Checking ML models...

:: Dixon-Coles: only refit if model is missing or older than 24 hours
set DC_FRESH=0
if exist "models\dixon_coles.json" (
    powershell -NoProfile -Command "if((Get-Date)-(Get-Item 'models\dixon_coles.json').LastWriteTime -lt [TimeSpan]::FromHours(24)){exit 0}else{exit 1}" >nul 2>&1
    if !errorlevel! == 0 set DC_FRESH=1
)
if "!DC_FRESH!"=="1" (
    echo         Dixon-Coles model is fresh — skipping refit.
) else (
    if exist "data\history.db" (
        echo         Dixon-Coles model stale — refitting...
        ".venv\Scripts\python.exe" tools\nightly_dc_refit.py >nul 2>&1
        if errorlevel 1 (echo         [warn] Dixon-Coles refit failed — keeping cached model.) else (echo         Dixon-Coles refit OK.)
    ) else (
        echo         [skip] No history.db for Dixon-Coles.
    )
)

:: LightGBM: only train if missing (first run only — large training set)
if exist "models\lgbm_1x2.pkl" (
    echo         LightGBM OK ^(cached^).
) else (
    echo         Training LightGBM ^(~2 min, first run only^)...
    ".venv\Scripts\python.exe" tools\train_lgbm_model.py >nul 2>&1
    if errorlevel 1 echo         [warn] LightGBM training failed — falls back to DC.
)

:: 1X2 calibrator: only retrain if missing or older than 24 hours
set CAL_FRESH=0
if exist "models\calibrator_1x2.json" (
    powershell -NoProfile -Command "if((Get-Date)-(Get-Item 'models\calibrator_1x2.json').LastWriteTime -lt [TimeSpan]::FromHours(24)){exit 0}else{exit 1}" >nul 2>&1
    if !errorlevel! == 0 set CAL_FRESH=1
)
if "!CAL_FRESH!"=="1" (
    echo         1X2 calibrator is fresh — skipping.
) else (
    ".venv\Scripts\python.exe" tools\train_1x2_calibrator.py >nul 2>&1
    if errorlevel 1 (echo         [warn] 1X2 calibrator failed.) else (echo         1X2 calibrator OK.)
)

:: O/U calibrator: only retrain if missing or older than 24 hours
set OU_FRESH=0
if exist "models\calibrator_ou25.json" (
    powershell -NoProfile -Command "if((Get-Date)-(Get-Item 'models\calibrator_ou25.json').LastWriteTime -lt [TimeSpan]::FromHours(24)){exit 0}else{exit 1}" >nul 2>&1
    if !errorlevel! == 0 set OU_FRESH=1
)
if "!OU_FRESH!"=="1" (
    echo         O/U calibrator is fresh — skipping.
) else (
    ".venv\Scripts\python.exe" tools\train_ou_calibrator.py >nul 2>&1
    if errorlevel 1 (echo         [warn] O/U calibrator failed.) else (echo         O/U calibrator OK.)
)

echo.

:: ── STEP 6: Pre-flight check ─────────────────────────────────────────
echo  [6/9] Running pre-flight checks...
".venv\Scripts\python.exe" tools\preflight_check.py 2>nul
echo.

:: ── STEP 7: Launch server ────────────────────────────────────────────
echo  [7/9] Launching dashboard + daemon [!MODE!]...
if not exist "logs" mkdir logs >nul 2>&1

:: Write the inner runner script so the server window has correct env vars
if "!ARENA_LIVE!"=="1" (
    (
        echo @echo off
        echo title DeepFieldPro SERVER [LIVE]
        echo cd /d "%~dp0"
        echo set DEEPFIELD_PORT=!PORT!
        echo set DEEPFIELD_ARENA_LIVE=1
        echo ".venv\Scripts\python.exe" src\live_dashboard_server.py ^>^> logs\server_live.log 2^>^&1
    ) > "logs\_server.bat"
) else (
    (
        echo @echo off
        echo title DeepFieldPro SERVER [SHADOW]
        echo cd /d "%~dp0"
        echo set DEEPFIELD_PORT=!PORT!
        echo :: DEEPFIELD_ARENA_LIVE intentionally unset — paper mode only
        echo ".venv\Scripts\python.exe" src\live_dashboard_server.py ^>^> logs\server_shadow.log 2^>^&1
    ) > "logs\_server.bat"
)

start "!WINTITLE!" /MIN cmd /k "logs\_server.bat"
echo         Server window launched ^(minimized^).
echo         Log: %~dp0!LOGFILE!
echo.

:: ── STEP 8: Wait for server to respond ───────────────────────────────
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
echo         Server is up and responding.

:open
echo.
echo  [9/9] Launch complete!
echo.
if "!ARENA_LIVE!"=="1" (
    echo  ┌─────────────────────────────────────────────────────────────────┐
    echo  │  LIVE — Stair AI World Cup Challenge                            │
    echo  │                                                                 │
    echo  │  Dashboard     http://localhost:!PORT!/                         │
    echo  │  Arena Panel   http://localhost:!PORT!/arena                    │
    echo  │  Lineups       http://localhost:!PORT!/lineups                  │
    echo  │  Log           !LOGFILE!                                        │
    echo  │                                                                 │
    echo  │  Arena autopilot: CHECK the Arena panel before leaving          │
    echo  │  Max 5 bets/scan  •  5%% edge min  •  35%% confidence min         │
    echo  │                                                                 │
    echo  │  To stop: taskkill /IM python.exe /F                            │
    echo  └─────────────────────────────────────────────────────────────────┘
) else (
    echo  ┌─────────────────────────────────────────────────────────────────┐
    echo  │  SHADOW — Paper Research Mode                                   │
    echo  │                                                                 │
    echo  │  Dashboard     http://localhost:!PORT!/                         │
    echo  │  Arena Panel   http://localhost:!PORT!/arena  ^(read-only^)      │
    echo  │  Lineups       http://localhost:!PORT!/lineups                  │
    echo  │  Log           !LOGFILE!                                        │
    echo  │                                                                 │
    echo  │  No real money. Virtual bankroll only.                          │
    echo  │  To stop: taskkill /IM python.exe /F                            │
    echo  └─────────────────────────────────────────────────────────────────┘
)
echo.
start "" "http://localhost:!PORT!/"
echo  This window is safe to close. Server keeps running in background.
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
echo  [DAEMON] Starting prediction daemon (no dashboard)...
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
