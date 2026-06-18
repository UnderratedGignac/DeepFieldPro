@echo off
title DeepFieldPro - Stop
cd /d "%~dp0"

echo.
echo [*] Stopping DeepFieldPro...

:: Kill Python processes (server + daemon)
powershell -NoProfile -Command "Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue"

:: Close the server window by title
powershell -NoProfile -Command "Get-Process cmd -ErrorAction SilentlyContinue | Where-Object {$_.MainWindowTitle -like 'DeepFieldPro-Server*'} | Stop-Process -Force -ErrorAction SilentlyContinue"

echo [+] All DeepFieldPro processes stopped.
echo.
timeout /t 2 /nobreak >nul
