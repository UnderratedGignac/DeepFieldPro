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
echo [1/7] Cleaning up old processes...
powershell -NoProfile -Command "Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue"
powershell -NoProfile -Command "Get-Process cmd -ErrorAction SilentlyContinue | Where-Object {$_.MainWindowTitle -like '*DeepFieldPro*'} | Stop-Process -Force -ErrorAction SilentlyContinue"
timeout /t 2 /nobreak >nul
echo [OK] Processes cleared.
echo.

:: ----------------------------------------------------------------
:: 2. Validate the venv interpreter
:: ----------------------------------------------------------------
echo [2/7] Checking Python environment...
if not exist ".venv\Scripts\python.exe" (
    echo.
    echo [ERROR] .venv\Scripts\python.exe not found.
    echo.
    echo         Recreate it:
    echo           python -m venv .venv
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
echo [3/7] Finding a free port...
set PORT=
for %%p in (5050 5051 5052 5053 5054 5055 5056 5057 5058 5059 5060) do (
    if not defined PORT (
        netstat -ano 2>nul | findstr ":%%p " | findstr /i "LISTENING" >nul 2>&1
        if errorlevel 1 set PORT=%%p
    )
)
if not defined PORT (
    echo [WARN] All ports 5050-5060 appear busy. Forcing 5061.
    set PORT=5061
)
echo [OK] Port !PORT! is free.
echo !PORT!>current_port.txt
echo.

:: ----------------------------------------------------------------
:: 4. One-time / idempotent setup steps
:: ----------------------------------------------------------------
echo [4/7] Running setup and model checks...
echo.

:: -- Bet log migration (adds fixture_id, league, best_odds, best_book, CLV columns)
echo   [setup] bet_log migration...
".venv\Scripts\python.exe" tools\migrate_bet_log.py
if errorlevel 1 echo     [warn] migration had an issue (continuing).

:: -- History database: ingest if missing; re-ingest if referee column is absent
::    (ingest_history.py downloads ~40 league-seasons of CSVs from football-data.co.uk)
echo.
if not exist "data\history.db" (
    echo   [setup] history.db missing -- ingesting history ^(~2 min, first run only^)...
    ".venv\Scripts\python.exe" tools\ingest_history.py
    if errorlevel 1 echo     [warn] history ingest had an issue.
) else (
    :: Check if referee column exists; if not, re-run ingest to add it
    ".venv\Scripts\python.exe" -c "import sqlite3,sys; c=sqlite3.connect('data/history.db'); cols=[r[1] for r in c.execute('PRAGMA table_info(matches)')]; c.close(); sys.exit(0 if 'referee' in cols else 1)" >nul 2>&1
    if errorlevel 1 (
        echo   [setup] Adding referee/card columns to history.db ^(one-time, ~2 min^)...
        ".venv\Scripts\python.exe" tools\ingest_history.py
        if errorlevel 1 echo     [warn] ingest had an issue.
    ) else (
        echo   [ok] history.db present with referee data.
    )
)

:: -- Dixon-Coles team strength model
echo.
if not exist "models\dixon_coles.json" (
    if exist "data\history.db" (
        echo   [setup] Training Dixon-Coles model ^(first run^)...
        ".venv\Scripts\python.exe" tools\train_dixon_coles.py
        if errorlevel 1 echo     [warn] DC training failed.
    ) else (
        echo   [info] No history.db yet - run ingest_history.py then train_dixon_coles.py.
    )
) else (
    echo   [ok] Dixon-Coles model present.
)

:: -- LightGBM ensemble (DC + form + market probs, 21 features)
echo.
if not exist "models\lgbm_1x2.pkl" (
    echo   [setup] Training LightGBM ensemble ^(first run, ~2 min^)...
    ".venv\Scripts\python.exe" tools\train_lgbm_model.py
    if errorlevel 1 echo     [warn] LightGBM training failed (daemon falls back to DC).
) else (
    echo   [ok] LightGBM model present.
)

:: -- 1X2 Platt calibrator (fixes favourite-overconfidence; trained on DC output vs real scores)
echo.
echo   [setup] Refreshing 1X2 calibrator...
".venv\Scripts\python.exe" tools\train_1x2_calibrator.py
if errorlevel 1 echo     [warn] 1X2 calibrator failed (daemon falls back to raw DC probs).

:: -- O/U 2.5 calibrator (display-only; fixes DC under-estimation of total goals)
echo.
echo   [setup] Refreshing O/U 2.5 calibrator...
".venv\Scripts\python.exe" tools\train_ou_calibrator.py
if errorlevel 1 echo     [warn] O/U calibrator failed (daemon shows uncalibrated O/U probs).

:: -- Corner model (team-specific Poisson rates; trained from corner history)
echo.
if not exist "models\corner_model.json" (
    if exist "data\corner_history.db" (
        echo   [setup] Training corner model...
        ".venv\Scripts\python.exe" tools\train_corner_model.py
        if errorlevel 1 echo     [warn] corner model training failed.
    ) else (
        echo   [info] No corner_history.db - run tools\ingest_corner_data.py to enable team corner rates.
    )
) else (
    echo   [ok] Corner model present.
)

echo.
echo [OK] Setup complete.
echo.

:: ----------------------------------------------------------------
:: 5. Pre-flight checks (non-blocking, informational)
:: ----------------------------------------------------------------
echo [5/7] Pre-flight checks...

:: Check key env vars
".venv\Scripts\python.exe" -c "
import os, sys
from dotenv import load_dotenv
load_dotenv()
ok = True
if not os.getenv('STAIR_AI_API_KEY'):
    print('  [warn] STAIR_AI_API_KEY missing in .env')
    ok = False
betfair_ok = all(os.getenv(k) for k in ['BETFAIR_USERNAME','BETFAIR_PASSWORD','BETFAIR_APP_KEY'])
if betfair_ok:
    print('  [ok] Betfair credentials present')
else:
    print('  [info] Betfair not configured (line-shopping disabled until activated)')
print('  [ok] Environment OK' if ok else '  [warn] Some env vars missing - check .env')
" 2>nul

echo.
echo [OK] Pre-flight done.
echo.

:: ----------------------------------------------------------------
:: 6. Launch dashboard + daemon
:: ----------------------------------------------------------------
echo [6/7] Launching dashboard + daemon...
if not exist "logs" mkdir logs >nul 2>&1

set DEEPFIELD_PORT=!PORT!
set DEEPFIELD_DISABLE_DAEMON=

".venv\Scripts\python.exe" -c "open('logs\\_launch.bat','w').write('@echo off\r\ncd /d \"%~dp0\"\r\nset DEEPFIELD_PORT=!PORT!\r\n.venv\\Scripts\\python.exe src\\live_dashboard_server.py >>logs\\server.log 2>&1\r\n')"

start "DeepFieldPro" /MIN cmd /c "logs\_launch.bat"

echo [OK] Server process started.
echo      Dashboard : http://localhost:!PORT!
echo      Log file  : %~dp0logs\server.log
echo.

:: ----------------------------------------------------------------
:: 7. Poll /api/state until the server responds, then open browser.
:: ----------------------------------------------------------------
echo [7/7] Waiting for server to be ready...
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
echo.
echo   Dashboard : http://localhost:!PORT!
echo   Log       : %~dp0logs\server.log
echo   Mode      : SHADOW ^(paper^) - real-money Arena stays PAUSED
echo.
echo   Signals active:
echo     - Fatigue detector   ^(fixture congestion penalty^)
echo     - Weather adjuster   ^(Open-Meteo, no API key needed^)
echo     - Referee stats      ^(74 refs from history.db^)
echo     - Arb detector       ^(Pinnacle vs Betarabia near-arb flags^)
echo     - Steam detector     ^(line movement, validated +20.9%% ROI@5%%^)
echo     - LightGBM ensemble  ^(21 features: DC + market + form^)
echo     - Dixon-Coles model  ^(team strength, DC calibrated^)
echo     - Asian Handicap     ^(opt-in via ah_betting_enabled in settings^)
echo ================================================================
echo.
start "" "http://localhost:!PORT!/"
echo   Press any key to stop all services and exit.
echo   ^(Close this window to leave everything running in the background.^)
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
