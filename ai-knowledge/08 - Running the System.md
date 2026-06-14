---
title: Running the System
tags: [ops]
---

# 🚀 Running the System

Back to [[00 - Map of Content]] · User guide: [[USER_GUIDE]]

## Environment
- Python **3.12** in a project venv. Interpreter: `.venv\Scripts\python.exe`.
- Recreate the venv:
  ```powershell
  C:\Users\Anthony\AppData\Local\Programs\Python\Python312\python.exe -m venv .venv
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  ```

## Run the dashboard + prediction daemon (main way)
```powershell
$env:DEEPFIELD_PORT="5051"   # optional; default 5050
.venv\Scripts\python.exe src\live_dashboard_server.py
```
Dashboard → `http://127.0.0.1:<port>`. Daemon runs as a background thread.

## Variants
- **UI only** (no scraping/predictions/betting): set `DEEPFIELD_DISABLE_DAEMON=1` first.
- **Daemon only**: `.venv\Scripts\python.exe src\live_predictions_daemon.py`

## Windows launchers
`RUN_SYSTEM.bat` · `LAUNCH_DEEPFIELD.bat` · `START_AUTO_PREDICTOR.bat`

## Gotcha
If a restart fails to bind the port, an orphaned SSE connection may be holding it — launch on a fresh `DEEPFIELD_PORT`. See [[07 - Known Issues & Gotchas]].

Related: [[05 - Configuration]] · [[09 - Conventions]] · [[06 - Safety & Risk]]
