# 🛠️ DeepFieldPro: Technical Implementation Plan

This document outlines the exact, file-by-file engineering steps required to transition DeepFieldPro into an institutional-grade, prop-specialized betting platform.

---

## Phase 1: Database & Telemetry Upgrades
Before we can track Closing Line Value (CLV) or filter bad bets, we must upgrade our SQLite schemas.

### 1. `bet_log.db` Migration
**Action:** Add new columns to track market movement and confidence.
- `closing_odds` (Float): The odds exactly 1 second before kickoff.
- `clv_percentage` (Float): `(closing_odds / bet_odds) - 1`.
- `uncertainty_spread` (Float): The difference between the P90 and P10 model outputs.

### 2. `data_quality.db` (New)
**Action:** Create a new local SQLite database to monitor API health.
- **Table `api_latency`:** Tracks the timestamp of lineup releases vs. kickoff.
- **Table `odds_staleness`:** Tracks the last time a market line ticked.

---

## Phase 2: Building the New Core Modules
We will create four new specialized modules in the `src/` directory.

### 1. `src/models/expected_minutes.py` (The xMin Engine)
**Purpose:** Replace hardcoded `career_min` with a probabilistic model.
- **Input:** Player historical usage, days of rest, manager substitution history.
- **Output:** Returns a dictionary: `{"p10": 45, "p50": 78, "p90": 95}`.
- **Integration:** This must be the very first model called by the daemon.

### 2. `src/models/calibration_engine.py` (The Calibrator)
**Purpose:** Force LightGBM outputs to reflect true real-world probability.
- **Logic:** Wraps the trained LightGBM models in `sklearn.calibration.CalibratedClassifierCV` (Isotonic Regression).
- **Integration:** The daemon passes raw model probabilities to this engine before deciding if there is an edge.

### 3. `src/risk_engine/no_bet_filter.py` (The Gatekeeper)
**Purpose:** Reject bets even if the EV is technically positive.
- **Rules:**
  - `reject_if_uncertainty_high()`: Blocks bet if P90 - P10 xMin spread is > 30 mins.
  - `reject_if_stale_odds()`: Blocks bet if the odds haven't changed in 15+ minutes.
  - `reject_if_correlated()`: Blocks a bet if we already have exposure to the same team/player in another market.

### 4. `src/telemetry_warehouse/clv_tracker.py` (The CLV Scraper)
**Purpose:** The ultimate source of truth for model performance.
- **Logic:** Runs a background async thread that wakes up 60 seconds before a match starts, queries Betarabia/Pinnacle for the final odds, and writes them to the `bet_log.db`.

---

## Phase 3: The Great Refactor
We will modify the existing orchestration scripts to utilize the new modules.

### 1. `src/live_predictions_daemon.py`
**The new execution flow:**
1. Scrape Live Games & Lineups (Block execution if Lineups = False).
2. Call `expected_minutes.py` to get xMin for all starting players.
3. Pass xMin into the Shots / SoT LightGBM Models.
4. Pass raw probabilities through `calibration_engine.py`.
5. Compare Calibrated Probability vs Bookmaker Odds to find EV.
6. Pass the proposed bet through `no_bet_filter.py`.
7. If approved, calculate fractional stake using `kelly_calculator.py`.
8. Execute Bet & Log.
9. Schedule `clv_tracker.py` to fire exactly at kickoff.

### 2. `src/live_dashboard_server.py` & `index.html`
**UI Upgrades:**
- Build a new tab: **"Data Quality & Health"**. Displays API latency and missing lineups.
- Update the **"Bet Tracker"** tab to include a CLV column (green if we beat the closing line, red if we lost to it).
- Update the **"Live Predictions"** tab to show the P10/P90 Uncertainty spread for each player.

---

## Phase 4: Deprecation (Maintenance Mode)
**Action:** We will remove the active execution calls for Match Winner (1X2) and Over/Under models from the live daemon. 
- The Python files (e.g., `predict_todays_games.py` for team stats) will not be deleted, but they will be isolated to the `/research` folder. They will only be used to generate contextual features (e.g., Team Implied Win Probability) for the Player Prop models.
