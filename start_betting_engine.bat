@echo off
setlocal EnableDelayedExpansion

echo ==========================================
echo   HIGH-FREQUENCY VALUE BETTING ENGINE
echo   Status: Initializing Production Mode
echo ==========================================

REM --- Configuration ---
set PYTHON_CMD=python
set VENV_DIR=.venv
set LOG_FILE=logs/engine_startup.log

REM --- Step 1: Environment Check ---
echo [1/5] Checking Python environment...
if not exist "%VENV_DIR%" (
    echo ERROR: Virtual environment not found. Run 'python -m venv .venv' first.
    pause
    exit /b 1
)

call %VENV_DIR%\Scripts\activate.bat
if errorlevel 1 (
    echo ERROR: Failed to activate virtual environment.
    pause
    exit /b 1
)

REM --- Step 2: Dependency Check ---
echo [2/5] Verifying dependencies...
%PYTHON_CMD% -c "import pandas, numpy, requests, aiohttp" 2>nul
if errorlevel 1 (
    echo ERROR: Missing dependencies. Run 'pip install -r requirements.txt'.
    pause
    exit /b 1
)

REM --- Step 3: Database Migration/Sanity Check ---
echo [3/5] Running database sanity check...
%PYTHON_CMD% src/utils/db_check.py
if errorlevel 1 (
    echo WARNING: Database check returned issues. Proceeding with caution...
)

REM --- Step 4: Pre-Flight Simulation (Safety Net) ---
echo [4/5] Running rapid Monte Carlo stress test (1000 iterations)...
%PYTHON_CMD% src/simulation/safety_check.py --quick
if errorlevel 1 (
    echo CRITICAL: Strategy failed stress test. ABORTING to prevent losses.
    echo Check logs for details.
    pause
    exit /b 1
)
echo >> Safety check passed. Expected Value is positive.

REM --- Step 5: Start Core Engines ---
echo [5/5] Launching core modules...

REM Create logs directory if not exists
if not exist "logs" mkdir logs

echo Starting Scrapers, Strategy, and Settler...
REM Run the main orchestrator which handles concurrency
start "Scraper Service" %PYTHON_CMD% src/main_scraper.py
timeout /t 5 /nobreak >nul
start "Strategy Engine" %PYTHON_CMD% src/main_strategy.py
timeout /t 5 /nobreak >nul
start "Settlement Agent" %PYTHON_CMD% src/main_settler.py

echo.
echo ==========================================
echo   SYSTEM ONLINE
echo   Monitoring logs/logs/engine_startup.log
echo   Press Ctrl+C in individual windows to stop services.
echo ==========================================
pause
