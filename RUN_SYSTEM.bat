@echo off
title DeepFieldPro - TOTAL SYSTEM CONTROL
setlocal enabledelayedexpansion

echo =======================================================
echo    DeepFieldPro Institutional ML Betting System
echo =======================================================
echo.

:: Step 1: Cleanup
echo [*] Checking for orphaned processes...
taskkill /IM python.exe /F >nul 2>&1
echo [+] Environment cleaned.

:: Step 2: Verification
cd /d "%~dp0"
if not exist "src\live_dashboard_server.py" (
    echo [!] ERROR: Could not find src\live_dashboard_server.py
    echo [!] Make sure you are running this from the project root.
    pause
    exit /b
)

:: Step 3: Launch System
echo [*] Launching DeepFieldPro Core Engine...
echo [*] Starting Web Dashboard on http://127.0.0.1:5050
echo [*] (The AI Prediction Engine will start automatically in the background)
echo.
echo [!] DO NOT CLOSE THIS WINDOW
echo =======================================================
echo.

:: Open the browser after a short delay
start "" "http://127.0.0.1:5050"

:: Start the unified server/daemon process
python src\live_dashboard_server.py

pause
