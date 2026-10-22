# RESTART_CLEAN.ps1 — reliable kill + single clean relaunch (PowerShell).
# Use this instead of RESTART_CLEAN.bat when launching from an automated/tool context:
# `cmd /c RESTART_CLEAN.bat` can silently fail to run (only prints the cmd banner), leaving
# the OLD server alive on stale code while health checks still pass. PowerShell kills + relaunches
# reliably and prints the new process StartTime so you can confirm the restart actually took.
Set-Location -Path $PSScriptRoot

Write-Host "[1/4] Killing all python..."
try { Stop-Process -Name python -Force -ErrorAction Stop; Write-Host "      killed" } catch { Write-Host "      none running" }
Start-Sleep -Seconds 2

Write-Host "[2/4] Picking a free port..."
$port = $null
foreach ($p in 5058, 5059, 5060, 5061, 5062, 5063) {
    $busy = Get-NetTCPConnection -State Listen -LocalPort $p -ErrorAction SilentlyContinue
    if (-not $busy) { $port = $p; break }
}
if (-not $port) { $port = 5063 }
"$port" | Out-File -FilePath "current_port.txt" -Encoding ascii -NoNewline
Write-Host "      using port $port"

Write-Host "[3/4] Launching ONE instance (PAPER mode — no real-money path exists)..."
$env:DEEPFIELD_ARENA_LIVE = "0"
$env:DEEPFIELD_PORT = "$port"
Start-Process -FilePath ".\.venv\Scripts\python.exe" -ArgumentList "src\live_dashboard_server.py" -WindowStyle Hidden
Start-Sleep -Seconds 6

Write-Host "[4/4] Verify (StartTime must be fresh):"
Get-Process python -ErrorAction SilentlyContinue | Select-Object Id, StartTime | Format-Table -AutoSize
Write-Host "Dashboard: http://127.0.0.1:$port/   Health: .venv\Scripts\python.exe health_check.py"
