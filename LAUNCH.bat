@echo off
setlocal enabledelayedexpansion
title DeepFieldPro — Launcher
cd /d "%~dp0"
color 0A

:: ════════════════════════════════════════════════════════════════════════
::  DEEPFIELDPRO UNIFIED LAUNCHER  v3.0  (2026-06-30)
::  Systems:
::    [S] SHADOW  — Paper bets, research, safe experiments
::    [L] LIVE    — Stair AI WC2026 Arena, real USDC (armed)
::    [D] DAEMON  — Prediction engine only, no UI
::    [I] INSIGHTS — Quick market scan: steam moves, arb opportunities
::    [A] ELIEATCH — AI REPL assistant
:: ════════════════════════════════════════════════════════════════════════

echo.
echo  ########################################################################
echo  ##                                                                    ##
echo  ##               D E E P F I E L D  P R O  2 0 2 6                  ##
echo  ##                                                                    ##
echo  ##   Platform  : Football Betting Research ^& Operations               ##
echo  ##   WC 2026   : Round of 32  ^|  ~31 games  ^|  thru July 19           ##
echo  ##   Arena     : Stair AI  ^|  Polymarket YES tokens  ^|  real USDC     ##
echo  ##   Research  : Steam +20.9%%  ^|  Poly arb $40M/yr  ^|  half-Kelly    ##
echo  ##                                                                    ##
echo  ########################################################################
echo.
echo   Choose a mode:
echo.
echo    [S]  SHADOW   — Paper mode, virtual bankroll, no real money
echo    [L]  LIVE     — Stair AI WC2026 challenge (real USDC wallet)
echo    [D]  DAEMON   — Prediction daemon only, no browser
echo    [I]  INSIGHTS — Quick market scan: steam signals + arb opportunities
echo    [A]  ELIEATCH — AI REPL assistant (tools/elieatch_tui_v2.py)
echo    [Q]  QUIT
echo.

:choose
set /p CHOICE="  Your choice [S/L/D/I/A/Q]: "
if /i "!CHOICE!"=="S" goto shadow
if /i "!CHOICE!"=="L" goto live_confirm
if /i "!CHOICE!"=="D" goto daemon_only
if /i "!CHOICE!"=="I" goto insights
if /i "!CHOICE!"=="A" goto elieatch
if /i "!CHOICE!"=="Q" exit /b 0
echo   Invalid — type S, L, D, I, A or Q.
goto choose

:: ════════════════════════════════════════════════════════════════════════
::  LIVE MODE CONFIRMATION — extra gate before arming real money
:: ════════════════════════════════════════════════════════════════════════
:live_confirm
echo.
echo  ┌──────────────────────────────────────────────────────────────────────┐
echo  │  !!  LIVE MODE — REAL USDC WALLET                                  !!│
echo  │                                                                      │
echo  │  Arena autopilot places REAL orders on Polymarket via Stair AI.      │
echo  │  Your wallet USDC balance is at risk.                                │
echo  │                                                                      │
echo  │  Active strategy:                                                     │
echo  │    Coverage  : ALL WC R32 games (conf_min=0, edge_min=-1.0)          │
echo  │    Sizing    : Half-Kelly, max $5/bet, keep $1 wallet buffer          │
echo  │    Max bets  : 30 per autopilot run                                  │
echo  │    New signals: steam moves, de-vigged edge, real 3-way arb check    │
echo  │                                                                      │
echo  │  Polymarket arb threshold: sum(all 3 mids) ^< 0.94  (guaranteed win)  │
echo  │  Steam signal: ≥3%% price drift in 4h  (follows smart money)          │
echo  │                                                                      │
echo  │  Type  LIVE  to confirm, anything else to cancel:                    │
echo  └──────────────────────────────────────────────────────────────────────┘
echo.
set /p CONFIRM="  > "
if /i "!CONFIRM!"=="LIVE" goto live
echo   Cancelled. Returning to menu.
echo.
goto choose

:: ════════════════════════════════════════════════════════════════════════
::  MODE VARIABLES
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
echo  [1/10] Cleaning up old Python processes...
powershell -NoProfile -Command ^
  "Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue"
timeout /t 2 /nobreak >nul
echo          OK
echo.

:: ── STEP 2: Validate virtual environment ─────────────────────────────
echo  [2/10] Checking Python environment...
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
echo  [3/10] Finding a free port...
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
echo  [4/10] Database setup...
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

:: ── STEP 5: New — Polymarket steam tracker init ───────────────────────
echo  [5/10] Initialising Polymarket steam tracker...
".venv\Scripts\python.exe" -c ^
  "from src.polymarket_steam import purge_old_records; purge_old_records(5); print('  Steam DB ready — price history rolling 5-day window.')" ^
  2>nul
if errorlevel 1 (
    echo          [warn] polymarket_steam init failed — steam signals disabled this run.
) else (
    if not exist "data\polymarket_steam.db" (
        echo          [note] New steam DB created at data\polymarket_steam.db
    )
    echo          OK
)
echo.

:: ── STEP 6: ML model refresh ──────────────────────────────────────────
echo  [6/10] Checking ML models...

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
echo  [7/10] Running pre-flight checks...
".venv\Scripts\python.exe" tools\preflight_check.py 2>nul
echo.

:: ── STEP 8: Launch server ─────────────────────────────────────────────
echo  [8/10] Launching dashboard + daemon [!MODE!]...
if not exist "logs" mkdir logs >nul 2>&1

if "!ARENA_LIVE!"=="1" (
    (
        echo @echo off
        echo title DeepFieldPro SERVER [LIVE - WC2026]
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
echo          Server window launched ^(minimised^).
echo          Log: %~dp0!LOGFILE!
echo.

:: ── STEP 9: Wait for server ───────────────────────────────────────────
echo  [9/10] Waiting for server to come online...
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
echo  [10/10] Launch complete!
echo.

:: ── Open browser tabs ─────────────────────────────────────────────────
if "!ARENA_LIVE!"=="1" (
    echo  ┌──────────────────────────────────────────────────────────────────────┐
    echo  │  LIVE — Stair AI World Cup 2026 Arena                                │
    echo  │                                                                      │
    echo  │  Dashboard     http://localhost:!PORT!/                              │
    echo  │  Arena Panel   http://localhost:!PORT!/arena                         │
    echo  │  Market Intel  http://localhost:!PORT!/arena/api/insights            │
    echo  │  Lineups       http://localhost:!PORT!/lineups                       │
    echo  │  Log           !LOGFILE!                                             │
    echo  │                                                                      │
    echo  │  Active signals:                                                     │
    echo  │    Steam detector   — ≥3%% price drift in 4h = smart money signal    │
    echo  │    Real arb check   — sum^(3 mids^)^<0.94 = risk-free 3-way position   │
    echo  │    De-vigged edge   — model vs fair market prob ^(no overround bias^)  │
    echo  │    Half-Kelly size  — max $5/bet, $1 wallet buffer                   │
    echo  │    Bet priority     : arb first → steam → highest edge               │
    echo  │                                                                      │
    echo  │  WC 2026: ~31 R32 games remain  ^|  thru July 19                     │
    echo  │  To stop: taskkill /IM python.exe /F                                 │
    echo  └──────────────────────────────────────────────────────────────────────┘
    start "" "http://localhost:!PORT!/"
    timeout /t 1 /nobreak >nul
    start "" "http://localhost:!PORT!/arena"
) else (
    echo  ┌──────────────────────────────────────────────────────────────────────┐
    echo  │  SHADOW — Paper Research Mode                                        │
    echo  │                                                                      │
    echo  │  Dashboard     http://localhost:!PORT!/                              │
    echo  │  Arena Panel   http://localhost:!PORT!/arena  ^(read-only^)           │
    echo  │  Market Intel  http://localhost:!PORT!/arena/api/insights            │
    echo  │  Lineups       http://localhost:!PORT!/lineups                       │
    echo  │  Log           !LOGFILE!                                             │
    echo  │                                                                      │
    echo  │  No real money. Virtual $5,000 bankroll.                             │
    echo  │  To stop: taskkill /IM python.exe /F                                 │
    echo  └──────────────────────────────────────────────────────────────────────┘
    start "" "http://localhost:!PORT!/"
)
echo.
echo  This window is safe to close. Server keeps running in the background.
echo  Press any key to close this launcher.
echo.
pause >nul
exit /b 0

:: ════════════════════════════════════════════════════════════════════════
::  QUICK INSIGHTS — scan Polymarket without launching the full server
:: ════════════════════════════════════════════════════════════════════════
:insights
title DeepFieldPro — Market Insights
echo.
echo  ────────────────────────────────────────────────────────────────────────
echo   POLYMARKET MARKET INTELLIGENCE SCAN
echo   Steam signals  ^|  Arb opportunities  ^|  Market health
echo  ────────────────────────────────────────────────────────────────────────
echo.

if not exist ".venv\Scripts\python.exe" (
    echo  [ERROR] .venv not found.
    pause & exit /b 1
)

".venv\Scripts\python.exe" -c ^
"import sys, os; sys.stdout.reconfigure(encoding='utf-8'); os.chdir(r'%~dp0')
from dotenv import load_dotenv; load_dotenv()
from src.arena_betting import analyze, get_wallet

wallet = get_wallet()
bal = float(wallet['available_balance_usdc']) if wallet else 0.0
print(f'Wallet: ${bal:.2f} USDC\n')

print('Scanning all upcoming WC fixtures...')
candidates = analyze(limit=60, wallet_balance=bal or None)

# Group by fixture
seen = {}
for c in candidates:
    fid = c.get('fixture_id', '?')
    if fid not in seen:
        seen[fid] = {'match': c['match'], 'kickoff': c['kickoff'],
                     'vig': c.get('market_vig_pp'), 'arb': c.get('real_arb'),
                     'arb_pp': c.get('arb_profit_pp'), 'outcomes': []}
    seen[fid]['outcomes'].append({
        'outcome': c['outcome'],
        'mid': c['market_mid'],
        'dv': c.get('devigged_mid'),
        'edge': c['edge_pp'],
        'steam': c.get('steam_move'),
        'model': c['model_prob'],
    })

print()
print('=== MARKET OVERVIEW ===')
for fid, f in seen.items():
    vig_str = f'{f[\"vig\"]:+.1f}pp' if f['vig'] is not None else '?'
    arb_str = f'  ARB +{f[\"arb_pp\"]:.1f}pp' if f['arb'] else ''
    print(f'  {f[\"match\"][:35]:35s} | vig={vig_str:7s}{arb_str}')
    for o in f['outcomes']:
        steam_str = f'  steam={o[\"steam\"]:+.1f}%%' if o['steam'] else ''
        dv_str = f'  dv={o[\"dv\"]:.1%}' if o['dv'] else ''
        print(f'    {o[\"outcome\"]:5s} mid={o[\"mid\"]:.2f}{dv_str} edge={o[\"edge\"]:+.1f}pp model={o[\"model\"]:.1%}{steam_str}')
    print()

steam_any = [c for c in candidates if c.get('steam_confirmed')]
if steam_any:
    print('=== ACTIVE STEAM SIGNALS ===')
    for c in steam_any:
        print(f'  {c[\"match\"]} | {c[\"outcome\"].upper()} | {c[\"steam_move\"]:+.1f}%% drift | edge={c[\"edge_pp\"]:+.1f}pp')
    print()

arb_any = [c for c in candidates if c.get('real_arb')]
if arb_any:
    print('=== REAL ARB OPPORTUNITIES ===')
    for c in arb_any:
        print(f'  {c[\"match\"]} | profit={c[\"arb_profit_pp\"]:+.1f}pp — buy all 3 outcomes')
    print()

print(f'Total WC fixtures scanned: {len(seen)}')
print(f'Steam signals: {len(steam_any)}  |  Arb opps: {len(arb_any)}')
" 2>&1
echo.
echo  Scan complete. Press any key to return to menu.
pause >nul
goto choose

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
