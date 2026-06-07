@echo off
title DeepFieldPro Live Match AI Predictor
echo =======================================================
echo    DeepFieldPro Autonomous Live Predictor Daemon
echo =======================================================
echo.
echo Starting the AI Engine in the background...
echo This terminal will remain open to show you live updates.
echo Do not close this window if you want predictions to continue.
echo.
cd /d "%~dp0"
python src\live_predictions_daemon.py
pause
