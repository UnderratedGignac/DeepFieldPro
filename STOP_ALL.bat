@echo off
title DeepFieldPro - Stopping...
echo.
echo [*] Stopping all DeepFieldPro processes...

:: Kill every Python process (server + daemon + betarabia_scraper subprocess)
powershell -NoProfile -Command ^
  "Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue"

:: Kill any leftover cmd windows we opened
powershell -NoProfile -Command ^
  "Get-Process cmd -ErrorAction SilentlyContinue ^| Where-Object {$_.MainWindowTitle -like '*DeepFieldPro*'} ^| Stop-Process -Force -ErrorAction SilentlyContinue"

:: Wait for OS to release the listening sockets
timeout /t 2 /nobreak >nul

echo [+] All stopped.
echo.
