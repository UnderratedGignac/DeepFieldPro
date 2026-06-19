@echo off
setlocal enabledelayedexpansion
title DeepFieldPro — SHADOW
cd /d "%~dp0"

echo.
echo  ╔══════════════════════════════════════════════════════════════╗
echo  ║      DeepFieldPro  ^|  SHADOW MODE  ^|  Paper bets only        ║
echo  ║      No real money. Safe for research and observation.       ║
echo  ╚══════════════════════════════════════════════════════════════╝
echo.

:: ────────────────────────────────────────────────────────────────────
:: STEP 1  Kill stale Python processes
:: ────────────────────────────────────────────────────────────────────
echo  [1/8] Cleaning up old Python processes...
powershell -NoProfile -Command ^
  "Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue"
timeout /t 2 /nobreak >nul
echo         OK
echo.

:: ────────────────────────────────────────────────────────────────────
:: STEP 2  Validate virtual environment
:: ────────────────────────────────────────────────────────────────────
echo  [2/8] Checking Python environment...
if not exist ".venv\Scripts\python.exe" (
    echo.
    echo  [ERROR] .venv not found.
    echo          Fix: python -m venv .venv
    echo               .venv\Scripts\pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('".venv\Scripts\python.exe" --version 2^>^&1') do set PYVER=%%v
echo         OK  !PYVER!
echo.

:: ────────────────────────────────────────────────────────────────────
:: STEP 3  Find a free port (5050–5064)
:: ────────────────────────────────────────────────────────────────────
echo  [3/8] Finding a free port...
set PORT=
for %%p in (5050 5051 5052 5053 5054 5055 5056 5057 5058 5059 5060 5061 5062 5063 5064) do (
    if not defined PORT (
        netstat -ano 2>nul | findstr ":%%p " | findstr /i "LISTENING" >nul 2>&1
        if errorlevel 1 set PORT=%%p
    )
)
if not defined PORT set PORT=5065
echo !PORT!>current_port.txt
echo         OK  Port !PORT!
echo.

:: ────────────────────────────────────────────────────────────────────
:: STEP 4  DB migrations + history ingestion
:: ────────────────────────────────────────────────────────────────────
echo  [4/8] Database setup...

echo         bet_log migration...
".venv\Scripts\python.exe" tools\migrate_bet_log.py >nul 2>&1
if errorlevel 1 echo         [warn] migration issue — continuing.

if not exist "data\history.db" (
    echo         history.db missing — ingesting ^(~2 min, first run only^)...
    ".venv\Scripts\python.exe" tools\ingest_history.py
    if errorlevel 1 echo         [warn] history ingest failed.
) else (
    ".venv\Scripts\python.exe" tools\check_referee_col.py >nul 2>&1
    if errorlevel 1 (
        echo         Updating history.db schema ^(~2 min^)...
        ".venv\Scripts\python.exe" tools\ingest_history.py
    ) else (
        echo         history.db OK.
    )
)
echo.

:: ────────────────────────────────────────────────────────────────────
:: STEP 5  Model refresh
:: ────────────────────────────────────────────────────────────────────
echo  [5/8] Refreshing models...

if exist "data\history.db" (
    echo         Dixon-Coles rolling refit...
    ".venv\Scripts\python.exe" tools\nightly_dc_refit.py >nul 2>&1
    if errorlevel 1 echo         [warn] DC refit issue — keeping existing model.
) else (
    echo         [skip] No history.db — Dixon-Coles skipped.
)

if not exist "models\lgbm_1x2.pkl" (
    echo         Training LightGBM ^(~2 min, first run only^)...
    ".venv\Scripts\python.exe" tools\train_lgbm_model.py
    if errorlevel 1 echo         [warn] LightGBM failed — falls back to DC.
) else (
    echo         LightGBM OK.
)

echo         1X2 calibrator...
".venv\Scripts\python.exe" tools\train_1x2_calibrator.py >nul 2>&1
if errorlevel 1 echo         [warn] 1X2 calibrator failed.

echo         O/U 2.5 calibrator...
".venv\Scripts\python.exe" tools\train_ou_calibrator.py >nul 2>&1
if errorlevel 1 echo         [warn] O/U calibrator failed.

if exist "data\corner_history.db" (
    if not exist "models\corner_model.json" (
        echo         Corner model...
        ".venv\Scripts\python.exe" tools\train_corner_model.py >nul 2>&1
        if errorlevel 1 echo         [warn] corner model failed.
    ) else (
        echo         Corner model OK.
    )
)
echo         Models done.
echo.

:: ────────────────────────────────────────────────────────────────────
:: STEP 6  Pre-flight checks
:: ────────────────────────────────────────────────────────────────────
echo  [6/8] Pre-flight checks...
".venv\Scripts\python.exe" tools\preflight_check.py
echo.

:: ────────────────────────────────────────────────────────────────────
:: STEP 7  Launch dashboard + daemon  [SHADOW — no real money]
:: ────────────────────────────────────────────────────────────────────
echo  [7/8] Launching dashboard + daemon  ^(SHADOW^)...
if not exist "logs" mkdir logs >nul 2>&1

(
    echo @echo off
    echo cd /d "%~dp0"
    echo set DEEPFIELD_PORT=!PORT!
    echo :: DEEPFIELD_ARENA_LIVE intentionally unset — paper mode only
    echo ".venv\Scripts\python.exe" src\live_dashboard_server.py^>^>logs\server_shadow.log 2^>^&1
) > "logs\_server.bat"

start "DeepFieldPro-SHADOW" /MIN cmd /k "logs\_server.bat"
echo         OK  Server launching ^(SHADOW^).
echo         Log: %~dp0logs\server_shadow.log
echo.

:: ────────────────────────────────────────────────────────────────────
:: STEP 8  Poll until server responds
:: ────────────────────────────────────────────────────────────────────
echo  [8/8] Waiting for server...
set /a TRIES=0
:poll
timeout /t 2 /nobreak >nul
powershell -NoProfile -Command ^
  "try{$null=Invoke-WebRequest -Uri 'http://127.0.0.1:!PORT!/api/state' -TimeoutSec 2 -UseBasicParsing;exit 0}catch{exit 1}" ^
  >nul 2>&1
if !errorlevel! == 0 goto ready
set /a TRIES+=1
if !TRIES! geq 25 (
    echo.
    echo         [warn] Server slow — opening browser anyway.
    echo                Check logs\server_shadow.log if the dashboard doesn't load.
    goto open
)
<nul set /p="."
goto poll

:ready
echo.
echo         Server is responding.

:open
echo.
echo  ╔══════════════════════════════════════════════════════════════╗
echo  ║  DeepFieldPro  ^|  SHADOW                                     ║
echo  ║                                                              ║
echo  ║   Dashboard    http://localhost:!PORT!                           ║
echo  ║   Log          logs\server_shadow.log                        ║
echo  ║                                                              ║
echo  ║   Mode         SHADOW  ^(paper bets only, no real money^)      ║
echo  ║   Arena        GATED OFF  ^(DEEPFIELD_ARENA_LIVE unset^)       ║
echo  ║                                                              ║
echo  ║   To stop: taskkill /IM python.exe /F                        ║
echo  ╚══════════════════════════════════════════════════════════════╝
echo.
start "" "http://localhost:!PORT!/"

echo   This window is safe to close.  Server keeps running.
echo   Press any key to close.
echo.
pause >nul
exit /b 0
