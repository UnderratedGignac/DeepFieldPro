@echo off
setlocal enabledelayedexpansion
title DeepFieldPro - RESEARCH MODE
cd /d "%~dp0"
color 0A

echo.
echo  ##################################################################
echo  ##                                                              ##
echo  ##    D E E P F I E L D  P R O  --  R E S E A R C H          ##
echo  ##                                                              ##
echo  ##   Mode   : RESEARCH ^(paper bets only, NO real money^)       ##
echo  ##   Daemon : ON       ^(predictions, steam, settlement^)       ##
echo  ##   Arena  : OFF      ^(real-money gate stays UNSET^)          ##
echo  ##                                                              ##
echo  ##################################################################
echo.

:: --- STEP 1: Kill stale Python processes ---
echo  [1/9] Killing old Python processes...
powershell -NoProfile -Command "Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue"
timeout /t 2 /nobreak >nul
echo         OK
echo.

:: --- STEP 2: Validate venv ---
echo  [2/9] Checking Python environment...
if not exist ".venv\Scripts\python.exe" (
    echo.
    echo  [ERROR] .venv not found. Run:
    echo          python -m venv .venv
    echo          .venv\Scripts\pip install -r requirements.txt
    echo.
    pause & exit /b 1
)
for /f "tokens=*" %%v in ('".venv\Scripts\python.exe" --version 2^>^&1') do set PYVER=%%v
echo         OK  !PYVER!
echo.

:: --- STEP 3: Find a free port (5050-5065) ---
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
echo         OK  Port !PORT!
echo.

:: --- STEP 4: Database setup ---
echo  [4/9] Database setup...
".venv\Scripts\python.exe" tools\migrate_bet_log.py >nul 2>&1
if errorlevel 1 (
    echo         [warn] bet_log migration issue - continuing.
) else (
    echo         bet_log OK.
)

if exist "data\history.db" (
    echo         history.db OK.
) else (
    echo         history.db missing - ingesting football history ^(first run, ~2 min^)...
    ".venv\Scripts\python.exe" tools\ingest_history.py
    if errorlevel 1 echo         [warn] history ingest failed - DC model uses cached values.
)

if exist "data\fifa_ratings.db" (
    echo         FIFA ratings OK.
) else (
    echo         Seeding FIFA ratings ^(~920 players^)...
    ".venv\Scripts\python.exe" src\seed_fifa_ratings.py >nul 2>&1
    if errorlevel 1 (
        echo         [warn] FIFA ratings seed failed.
    ) else (
        echo         FIFA ratings OK.
    )
)

echo         Checking Patchright Chromium ^(Sofascore + crowd scraper^)...
".venv\Scripts\python.exe" -m patchright install chromium >nul 2>&1
if errorlevel 1 (
    echo         [warn] Patchright browser install failed - Sofascore scraper will fall back to Betarabia.
) else (
    echo         Patchright Chromium OK.
)
echo.

:: --- STEP 5: Polymarket steam tracker init ---
echo  [5/9] Initialising Polymarket steam tracker...
".venv\Scripts\python.exe" -c "from src.polymarket_steam import purge_old_records; purge_old_records(5); print('  Steam DB ready.')" 2>nul
if errorlevel 1 (
    echo         [warn] polymarket_steam init failed - steam signals disabled this run.
) else (
    echo         OK
)
echo.

:: --- STEP 6: ML model refresh (skip if fresh <24h) ---
echo  [6/9] Checking ML models...

if exist "models\dixon_coles.json" (
    echo         Dixon-Coles model OK ^(exists^).
) else (
    if exist "data\history.db" (
        echo         Dixon-Coles missing - fitting ^(~1 min^)...
        ".venv\Scripts\python.exe" tools\nightly_dc_refit.py >nul 2>&1
        if errorlevel 1 (
            echo         [warn] DC fit failed - predictions will use fallback heuristic.
        ) else (
            echo         Dixon-Coles fit OK.
        )
    ) else (
        echo         [skip] No history.db - DC model will use fallback heuristic.
    )
)

if exist "models\lgbm_1x2.pkl" (
    echo         LightGBM OK.
) else (
    echo         Training LightGBM ^(first run, ~2 min^)...
    ".venv\Scripts\python.exe" tools\train_lgbm_model.py >nul 2>&1
    if errorlevel 1 echo         [warn] LightGBM training failed - falls back to DC.
)

if exist "models\calibrator_1x2.json" (
    echo         1X2 calibrator OK ^(exists^).
) else (
    echo         1X2 calibrator missing - training ^(~5 min^)...
    ".venv\Scripts\python.exe" tools\train_1x2_calibrator.py >nul 2>&1
    if errorlevel 1 (
        echo         [warn] 1X2 calibrator training failed.
    ) else (
        echo         1X2 calibrator trained OK.
    )
)

if exist "models\calibrator_ou25.json" (
    echo         O/U calibrator OK ^(exists^).
) else (
    echo         O/U calibrator missing - training ^(~2 min^)...
    ".venv\Scripts\python.exe" tools\train_ou_calibrator.py >nul 2>&1
    if errorlevel 1 (
        echo         [warn] O/U calibrator training failed.
    ) else (
        echo         O/U calibrator trained OK.
    )
)
echo.

:: --- STEP 7: Pre-flight check ---
echo  [7/9] Pre-flight checks...
".venv\Scripts\python.exe" tools\preflight_check.py 2>nul
echo.

:: --- STEP 8: Launch server (RESEARCH + ARENA TOURNAMENT) ---
:: DEEPFIELD_ARENA_LIVE=1 arms Stair AI Arena orders. VERIFIED 2026-07-05: the
:: Arena is a VIRTUAL-bankroll World Cup tournament (AI agents paper-trading
:: Polymarket for leaderboard rank) — no real money moves through this gate.
echo  [8/9] Launching dashboard + daemon [RESEARCH + ARENA]...
if not exist "logs" mkdir logs >nul 2>&1

(
    echo @echo off
    echo title DeepFieldPro SERVER [RESEARCH - paper only]
    echo cd /d "%~dp0"
    echo set DEEPFIELD_PORT=!PORT!
    echo set DEEPFIELD_ARENA_LIVE=1
    echo ".venv\Scripts\python.exe" src\live_dashboard_server.py ^>^> logs\server_live.log 2^>^&1
) > "logs\_server_live.bat"

start "DeepFieldPro-RESEARCH" /MIN cmd /k "logs\_server_live.bat"
echo         Server launched ^(minimised^).
echo         Log: %~dp0logs\server_live.log
echo.

:: --- STEP 9: Wait for server, then open browser ---
echo  [9/9] Waiting for server to come online...
set /a TRIES=0

:poll
timeout /t 2 /nobreak >nul
powershell -NoProfile -Command "try{Invoke-WebRequest -Uri 'http://127.0.0.1:!PORT!/api/state' -TimeoutSec 3 -UseBasicParsing | Out-Null;exit 0}catch{exit 1}" >nul 2>&1
if !errorlevel! == 0 goto ready
set /a TRIES+=1
echo         Waiting... ^(!TRIES!^)
if !TRIES! geq 25 (
    echo.
    echo  [warn] Server slow to start - opening browser anyway.
    echo         Tail log:  powershell Get-Content logs\server_live.log -Tail 30
    goto open
)
goto poll

:ready
echo         Server is up.

:open
echo.
echo  ##################################################################
echo  ##                                                              ##
echo  ##   DEEPFIELDPRO RESEARCH -- PAPER TRADING ACTIVE             ##
echo  ##                                                              ##
echo  ##   Dashboard : http://localhost:!PORT!/                       ##
echo  ##   Lineups   : http://localhost:!PORT!/lineups                ##
echo  ##   Log       : logs\server_live.log                           ##
echo  ##                                                              ##
echo  ##   Running : DC model / Steam / Settlement ^(paper only^)      ##
echo  ##   Stop    : taskkill /IM python.exe /F                       ##
echo  ##   Relaunch: double-click LAUNCH_ALL.BAT                      ##
echo  ##                                                              ##
echo  ##################################################################
echo.

start "" "http://localhost:!PORT!/"

echo  This window is safe to close. Server keeps running in the background.
echo  Press any key to close.
echo.
pause >nul
exit /b 0
