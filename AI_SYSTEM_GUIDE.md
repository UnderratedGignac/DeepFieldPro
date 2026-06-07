# DeepFieldPro - AI Agent Handover & Maintenance Guide

## 🤖 For the Next AI Agent

Welcome! If you are reading this, the user has asked you to modify, debug, or extend the DeepFieldPro system. This document outlines the **current actual architecture** (which is much simpler than the legacy PostgreSQL/Microservices architecture mentioned in older READMEs).

### 1. Current Architecture Overview
The system has been heavily streamlined to run locally without complex infrastructure. It uses **SQLite** for storage and is split into two main processes:

1. **The Daemon (`src/live_predictions_daemon.py`)**
   - Runs in an infinite loop in the background.
   - Triggers the scraper (`src/betarabia_scraper.py` and `src/free_scraper_module.py`).
   - Generates predictions using the LightGBM models.
   - Logs recommended bets into `data/bet_log.db`.
   - Tracks the bankroll and enforces Kelly Criterion sizing in `data/bankroll.db`.
   - Writes state summaries to `todays_dashboard_state.json`.

2. **The Dashboard Server (`src/live_dashboard_server.py`)**
   - A Flask web server running on `0.0.0.0:5000`.
   - Serves the UI (`src/templates/index.html`).
   - Reads directly from `data/bankroll.db`, `data/bet_log.db`, and `todays_dashboard_state.json` to populate the frontend.
   - Provides endpoints under `/api/*` (e.g., `/api/state`, `/api/tracker`, `/api/comparison/<fixture_id>`).

### 2. The Databases (`/data` directory)
All state is stored in simple SQLite databases in the `/data` folder. If you ever need to reset the system, you can delete these `.db` files and run the scripts to recreate them.
- `bankroll.db`: Managed by `src/bankroll_tracker.py`. Tracks the starting balance, current liquid balance, and daily exposure.
- `bet_log.db`: Contains the `predictions` table (all generated AI probabilities) and the `bet_log` table (placed bets, odds, edges).
- `odds_stream.db`: Created by `src/betarabia_scraper.py`. Contains raw `fixture` and `market` data scraped from the bookmaker.

### 3. How to Add New Features

#### A. Adding a New UI Page
1. Add the route to `src/live_dashboard_server.py` (ensure you map it to `index.html` so the SPA works).
2. Modify `src/templates/index.html` to include the new UI components. (The UI uses Vanilla JS, HTML, and CSS. Tailwind is NOT used; custom CSS is in `<style>` blocks or `style.css`).

#### B. Changing the Bankroll Logic
Look at `src/bankroll_tracker.py`. 
*Note:* The UI currently assumes `STARTING_BANKROLL` is 100$. The system strictly enforces capital preservation: `log_ai_bet` directly invokes `register_bet()` to deduct stakes from the liquid balance. If the balance reaches 0, further bets are physically blocked. If you change the DB schema, you must manually run `python src/bankroll_tracker.py` to recreate the table.

#### C. Modifying the Betting Strategy
Look at `src/live_predictions_daemon.py`. 
- The system enforces a strict lineup validation rule (`has_lineup`). It completely skips prediction execution and betting for games lacking confirmed 11-man lineups.
- The `predict_match` function explicitly generates and exposes probabilities for **Corners (Over 8.5)**, **Player Shots (Over 1.5)**, and **Anytime Goalscorer** markets, in addition to standard 1X2 / Over-Under.
- The function `log_ai_bet` handles bet sizing (Kelly Criterion) and logs to `bet_log.db`, deducting the stake via `bankroll_tracker`.
- The function `find_betarabia_odds` calculates EV based on market prices vs AI probabilities.

### 4. Running the System
The user has two ways to start the system:
1. **Locally (Windows):** Double-click `LAUNCH_DEEPFIELD.bat`. This opens two CMD windows for the daemon and the server, then opens the browser.
2. **Docker:** `docker-compose up -d --build`. This builds the image defined in `Dockerfile` and runs both the daemon and dashboard as separate containers mapping the `./data` and `./models` directories.

### 5. Troubleshooting
- **404 Errors on Frontend:** If you added a new page to the JS SPA, you probably forgot to add the `@app.route('/your_page')` in `live_dashboard_server.py`.
- **Database Locks:** SQLite can lock if both the daemon and the server write at the exact same time. Usually, the server only *reads*, so locks are rare.
- **Empty UI:** Check if the daemon is actually running and if `data/todays_dashboard_state.json` is populated.

Good luck! Use your `grep_search` and `run_command` tools extensively to navigate the codebase.
