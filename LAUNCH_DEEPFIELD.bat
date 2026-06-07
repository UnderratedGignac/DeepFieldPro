@echo off
title DeepFieldPro AI Launcher
echo =======================================================
echo    DeepFieldPro Full System Launcher
echo =======================================================
echo.
cd /d "%~dp0"

echo [1/3] Starting the AI Engine Daemon...
start "DeepFieldPro Daemon" cmd /k "python src\live_predictions_daemon.py"

echo [2/3] Starting the Web Dashboard...
start "DeepFieldPro Web Dashboard Server" cmd /k "python src\live_dashboard_server.py"

echo [3/3] Waiting for the server to spin up...
timeout /t 3 /nobreak > nul

echo Opening the dashboard in your default browser...
start http://127.0.0.1:5000/

echo.
echo =======================================================
echo System is now running! 
echo.
echo Note: Two new terminal windows have opened. Do not close them if you want the predictions and website to keep working.
echo You can close this launcher window safely.
echo =======================================================
pause
