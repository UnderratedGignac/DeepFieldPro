@echo off
setlocal enabledelayedexpansion
REM ============================================================================
REM  RESTART_CLEAN.bat - the ONLY launcher you should use.
REM ----------------------------------------------------------------------------
REM  Handles this project's two chronic launch problems:
REM   1) venv python.exe is a redirector -> one server shows as two python.exe
REM      (a venv stub + its base child). Harmless; only the child serves.
REM   2) Repeated restarts can leave a ZOMBIE listening socket on the old port
REM      (accepts TCP but nothing serves -> the dashboard "hangs"). Unkillable
REM      without a reboot. So we auto-pick the first FREE port from a list and
REM      record it in current_port.txt (health_check.py reads it).
REM ============================================================================
cd /d "%~dp0"

echo [1/4] Stopping ALL python processes...
taskkill /F /IM python.exe >nul 2>&1
timeout /t 2 /nobreak >nul

echo [2/4] Finding a free port (avoids zombie-socket ports)...
set "PORT="
for %%p in (5050 5058 5059 5060 5061 5062) do (
    if not defined PORT (
        netstat -ano | findstr ":%%p " | findstr LISTENING >nul 2>&1
        if errorlevel 1 ( set "PORT=%%p" )
    )
)
if not defined PORT set "PORT=5063"
echo        using port !PORT!
echo|set /p="!PORT!" > current_port.txt

echo [3/4] Arming the StairAI Arena real-money gate...
REM  Remove the next line to run paper-only (Arena placement stays disabled).
set "DEEPFIELD_ARENA_LIVE=1"
set "DEEPFIELD_PORT=!PORT!"

echo [4/4] Launching ONE dashboard instance (daemon + autopilot + sharp + closing)...
start "DeepFieldPro" /MIN ".venv\Scripts\python.exe" src\live_dashboard_server.py

echo.
echo Done. Dashboard: http://127.0.0.1:!PORT!/
echo Health check:   .venv\Scripts\python.exe health_check.py
echo Stop everything: taskkill /F /IM python.exe
echo.
