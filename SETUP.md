# DeepFieldPro — Setup (run it the same on another machine)

This repo already contains everything the app needs **except the Python virtualenv**
(`.venv/`), which is intentionally not committed — virtualenvs aren't portable across
machines (absolute paths + platform-specific binaries like Playwright's Chromium). You
recreate it from `requirements.txt`. Config and API keys live in `.env` (already in the repo).

## Prerequisites

- **Windows** with **Python 3.12** installed (the Windows Store "python" stub will not work).
  Check: `py -3.12 --version` should print `Python 3.12.x`.
- **Git**.

## First-time setup

```powershell
git clone https://github.com/UnderratedGignac/DeepFieldPro.git
cd DeepFieldPro

# 1) Create the virtualenv with Python 3.12
py -3.12 -m venv .venv

# 2) Install dependencies
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt

# 3) Install the Playwright browser used by the odds scraper
.venv\Scripts\python.exe -m playwright install chromium
```

## Run it

```powershell
# Easiest: the correct launcher (uses the venv interpreter, auto-scans ports 5052-5058)
START_DEEPFIELD.bat
```

Then open the dashboard at `http://127.0.0.1:<port>` (the port is printed on startup).

Equivalent manual launch:

```powershell
$env:DEEPFIELD_PORT="5052"
.venv\Scripts\python.exe src\live_dashboard_server.py
```

- UI only (no scraping/predictions/betting): set `DEEPFIELD_DISABLE_DAEMON=1` first.
- Always `taskkill /IM python.exe /F` before relaunching (orphaned processes can hold ports).

## Configuration (`.env`)

`.env` is committed (private repo) so the app runs without manual setup. It holds API keys
and risk params (`API_FOOTBALL_KEY`, `STAIR_AI_API_KEY`, `DEEPFIELD_*`, etc.). If the repo is
ever shared or made public, **rotate these keys** — they are in git history.

## Notes

- **Data travels with the repo.** `data/` (bet log, bankroll, history DBs, `settings.json`)
  is committed, so a fresh clone starts from this machine's current state. To start the paper
  bankroll fresh on the new machine: `.venv\Scripts\python.exe tools\reset_paper_bankroll.py`.
- **Safety.** Real-money betting is hard-gated off (`DEEPFIELD_ARENA_LIVE` must be unset; the
  daemon's live order POST is off by default). Everything here is SHADOW/paper.
- See `CLAUDE.md` for the full architecture, data flow, models, and known gotchas.
