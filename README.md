# 📖 DeepFieldPro: Comprehensive Master Documentation

## 🏗 Architectural Rationale: "Why I did it like this"

The DeepFieldPro system was originally designed with an extremely complex tech stack (PostgreSQL, TimescaleDB, Redis, Microservices). However, to make the system **highly robust, hyper-fast, and run smoothly on a local machine without Docker overhead**, the architecture was fundamentally refactored. Here is why the core decisions were made:

1. **SQLite3 over PostgreSQL:** We shifted to local SQLite databases (`bankroll.db`, `bet_log.db`, `odds_stream.db`). Why? Because for a single-node AI betting engine, network latency and database connection pooling to a heavy Postgres instance create unnecessary friction. SQLite provides lightning-fast reads/writes with zero setup required.

2. **Flat-File JSON State for UI (`todays_dashboard_state.json`):** Instead of hitting the database for every UI render, the background daemon periodically exports its entire mental model to a single JSON file. The Flask UI Server (`live_dashboard_server.py`) simply serves this file. Why? This completely decouples the heavy AI inference loop from the web server, ensuring the UI remains blazing fast and never causes database lock contention.

3. **Strict Lineup Validation (`has_lineup` rule):** The engine refuses to execute predictions on matches without confirmed starting XIs. Why? Because pre-match estimated lineups introduce massive variance. A key player getting benched destroys the statistical edge. By enforcing strict lineup checks, the AI only bets when it has absolute certainty of the field conditions.

4. **Kelly Criterion Fractional Sizing:** We integrated a strict bankroll tracker that sizes bets based on the mathematical edge (EV). Why? To mathematically guarantee long-term capital preservation and maximize compounding growth while strictly capping daily exposure to prevent catastrophic ruin.

5. **Expanded Prop Markets (Corners, Shots, Goalscorers):** While 1X2 and Over/Under are highly efficient markets (hard to beat), prop markets often have softer pricing due to bookmaker generalization. The AI specifically hunts for alphas in these secondary markets.


## 📂 File-by-File Codebase Audit

### 📁 Directory: `src`

#### 📄 `account_manager.py`
```python
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "book_accounts.db")
def init_account_db():
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
cursor.execute(
...
```

#### 📄 `add_passes_data.py`
```python
# Initialize FBref scraper
fbref = sd.FBref(
leagues=[
"ENG-Premier League",
"ESP-La Liga",
...
```

#### 📄 `advanced_training_pipeline.py`
```python
advanced_training_pipeline.py — DeepFieldPro Hierarchical Model Training
=========================================================================
Phase 1: Train player-level models (LightGBM classifiers for goal, assist probabilities)
Phase 2: Aggregate Out-Of-Fold (OOF) predictions up to team level
Phase 3: Train team-level models using aggregated player predictions as features

BUG FIX: numpy imported at module level (was erroneously inside __main__ block).
```

#### 📄 `alerter.py`
```python
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))
# Telegram configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")  # Add to .env
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")  # Add to .env
def send_telegram_message(message):
...
```

#### 📄 `app_config.py`
```python
class Config:
"""
Centralized configuration to remove hardcoded paths and values.
"""
# Base Paths
...
```

#### 📄 `audit_data.py`
```python
# Your main database
df = pd.read_csv(os.path.join(config.DATA_DIR, "csv/FULL_PLAYER_DATABASE_2026.csv"))
print(f"Total rows: {len(df)}")
print(f"Seasons: {df['season'].unique()}")
print(f"Leagues: {df['league'].unique()}")
...
```

#### 📄 `audit_wc_coverage.py`
```python
World Cup Player Coverage Audit
Performs fuzzy name matching to correctly measure WC player coverage in the dataset.
```

#### 📄 `backtester.py`
```python
backtester.py
--------------
STEP 2: Backtesting engine.

Replays historical StatsBomb match data to simulate the betting system
running live. Checks if our model's predicted pass distributions were
accurate and whether our bets would have been profitable (positive CLV).

Output:
  - backtest_results.csv  : Every simulated bet with outcome
  - backtest_summary.txt  : ROI, hit rate, avg CLV, Sharpe ratio
```

#### 📄 `bankroll_tracker.py`
```python
bankroll_tracker.py
-------------------
Tracks the system bankroll, enforces daily and total drawdown limits,
and manages the HALT flag.

CONVENTION (critical — must be consistent across all callers):
  - current_balance = liquid cash (money not currently at risk in open bets)
  - register_bet(stake):      deducts stake from current_balance (bet is now "at risk")
  - register_settlement(pnl): adds settlement back to current_balance.
      On WIN:  pnl = stake * (odds - 1)       → adds only the profit
      On LOSS: pnl = 0                         → stake was already deducted, nothing to add back
      On VOID: pnl = stake                     → refund the stake that was deducted

This means: current_balance = cash_in_hand (excludes stakes currently at risk).
```

#### 📄 `bet_logger.py`
```python
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "bet_log.db")
def init_bet_log_db():
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
cursor.execute(
...
```

#### 📄 `betarabia_scraper.py`
```python
betarabia_scraper.py — DeepFieldPro Live Odds Scraper
======================================================
Targets the Kickertech (websbkt.com) API that powers betarabia.com/sports/kickertech.
Strategy:
  1. Navigate to betarabia.com/sports/kickertech to trigger API calls.
  2. Intercept XHR responses from api-m-sp-cdl.websbkt.com and pre-88o-sp.websbkt.com.
  3. Parse events (with real kickoff times) + odds directly from those API responses.
  4. Filter to TODAY's fixtures only (by kickoff_time date == today UTC).
  5. Upsert into odds_stream.db (fixture + market tables).
  6. Falls back to HTML scraping if API interception yields nothing.

NAMING CONVENTIONS:
  Parameters: ProperCase _P  |  Variables: ProperCase _V  |  SQL: lowercase/UPPERCASE
```

#### 📄 `build_shots_training_dataset.py`
```python
build_shots_training_dataset.py
---------------------------------
Builds a clean training dataset for SHOTS and SHOTS ON TARGET (SoT)
using the 25/26 season match logs (49,004 rows).
Integrates real PPM (Passes Per Minute) from the player database to prevent feature mismatch.
```

#### 📄 `build_training_dataset.py`
```python
build_training_dataset.py
--------------------------
Builds the training dataset by combining:
- Match-level data (minutes, crosses, tackles, interceptions) from world_cup_players_match_logs.csv
- Season-level passing stats (Cmp, Cmp%) from FBref season stats

This gives us accurate per-match targets while using season-level
pass rates to build the passes_per_90 estimate.
```

#### 📄 `build_training_dataset_v2.py`
```python
build_training_dataset_v2.py
------------------------------
Builds a clean training dataset using REAL pass data from StatsBomb.
Merges with the FBref match logs to add opponent context features.
```

#### 📄 `calibration_backtester.py`
```python
sys.path.insert(0, os.path.dirname(__file__))
logging.basicConfig(level=logging.ERROR, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MATCH_LOGS_CSV = os.path.join(BASE_DIR, "data", "world_cup_players_match_logs.csv")
...
```

#### 📄 `calibration_trainer.py`
```python
sys.path.insert(0, os.path.dirname(__file__))
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MATCH_LOGS_CSV = os.path.join(BASE_DIR, "data", "world_cup_players_match_logs.csv")
...
```

#### 📄 `clv_tracker.py`
```python
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
BET_LOG_CSV = os.path.join(DATA_DIR, "bet_log.csv")
DB_ODDS = os.path.join(DATA_DIR, "odds_stream.db")
def init_csv():
...
```

#### 📄 `clv_updater.py`
```python
clv_updater.py
--------------
Fetches closing odds post-match and calculates Realized CLV for every bet.

CLV Convention:
  Positive CLV = you beat the closing line = long-run profitable signal.
  Formula: clv = (1 / closing_odds) - (1 / entry_odds)

  Example:
    Entry odds:   2.10  → implied prob = 0.476
    Closing odds: 1.90  → implied prob = 0.526
    CLV = 0.526 - 0.476 = +0.050  → You were RIGHT, market moved to agree with you.

  Anti-example (the OLD broken formula was reversed):
    OLD (wrong): clv = (1/entry) - (1/closing) = 0.476 - 0.526 = -0.050  ← WRONG SIGN
```

#### 📄 `dashboard.py`
```python
st.set_page_config(page_title="Deep Field Pro Dashboard", layout="wide")
DB_BANKROLL = os.path.join(os.path.dirname(__file__), "..", "data", "bankroll.db")
DB_BETLOG = os.path.join(os.path.dirname(__file__), "..", "data", "bet_log.db")
DB_ACCOUNTS = os.path.join(os.path.dirname(__file__), "..", "data", "book_accounts.db")
def get_db_connection(db_path):
...
```

#### 📄 `data_fetcher_all_leagues.py`
```python
DeepFieldPro — Global League Data Fetcher
==========================================
Industrial-grade scraper for API-Football that fetches ALL player data
across ALL leagues worldwide.

FEATURES:
- Uses SQLite to track progress (resumes automatically if interrupted)
- Handles API pagination automatically
- Respects rate limits (10 req/sec, tracks daily quota)
- Saves all player stats to a unified master CSV

NOTE: To fetch "all leagues in the world", you need a paid API-Football plan.
The Free plan (100 req/day) will take a very long time to complete.
```

#### 📄 `data_pipeline.py`
```python
data_pipeline.py — DeepFieldPro World Cup 2026 Player Data Pipeline
=====================================================================
Fetches real player data for all World Cup 2026 participants from:
  1. StatsBomb Open Data  (via statsbombpy - no key needed, WC 2022 historical)
  2. API-Football         (live squads & stats, 100 req/day free tier, key in .env)
  3. TheSportsDB          (player position/age enrichment, no key needed)

All data saved to:
  - data/odds_stream.db  (team_stats + player_stats tables)
  - data/worldcup_players.csv  (flat CSV cache)

Usage:
  python src/data_pipeline.py

Set API_FOOTBALL_KEY in .env to enable API-Football source.
```

#### 📄 `debug_backtest.py`
```python
sys.path.insert(0, ".")
df = pd.read_csv("../data/training_dataset.csv")
row = df.iloc[0]
MINUTES_FEATURES = [
"Age",
...
```

#### 📄 `engine_bettor.py`
```python
DeepFieldPro — Betting Engine (Module 2 of 3)
==============================================
Takes prediction probabilities from the Prediction Engine and compares
them against real bookmaker odds to identify +EV (positive expected value) bets.

INPUT:  predictions_df from engine_predictor.py
        bookmaker odds (live from API-Football or manual input)
OUTPUT: Ranked list of value bets with EV%, edge, and recommendation

No hardcoded values. No fake odds. Will only process real market lines.
If no bookmaker odds are available, it will clearly report that.
```

#### 📄 `engine_predictor.py`
```python
DeepFieldPro — Prediction Engine (Module 1 of 3)
=================================================
Generates probability distributions for every player prop market
from the trained LightGBM models using Monte Carlo simulation.

INPUT:  Date (default: today), optional nation codes to filter
OUTPUT: Structured DataFrame of player prop probabilities

No hardcoded values. All predictions driven from:
  - Real match logs (world_cup_players_match_logs_global.csv)
  - Real LightGBM models (models/lgb_*_final.txt)
  - Real live fixtures (API-Football)
```

#### 📄 `engine_staker.py`
```python
DeepFieldPro — Stake Sizing Engine (Module 3 of 3)
====================================================
Determines exactly how much to bet on each identified +EV opportunity
using the Fractional Kelly Criterion with dynamic bankroll management.

RISK RULES (institutional grade):
  - Quarter Kelly (25%) — prevents over-betting on variance
  - Hard cap: max 2% of bankroll per single bet
  - Hard cap: max 5% total exposure per match
  - Hard cap: max 10% daily total exposure
  - Drawdown halt: if daily P&L < -5%, stop for the day
  - Never bet with < 3% model edge after vig removal

INPUT:  value_bets_df from engine_bettor.py
        current bankroll (from bankroll_tracker.py DB or manual)
OUTPUT: Final bet slip with exact stake amounts in $

No hardcoded bankroll values in logic. Bankroll is read from DB or passed in.
```

#### 📄 `execution_engine.py`
```python
# -*- coding: utf-8 -*-
os.environ.setdefault("PYTHONUTF8", "1")
"""
execution_engine.py
--------------------
...
```

#### 📄 `fix_data_integrity.py`
```python
DeepFieldPro - Data Integrity Fix
Fixes unparseable date rows in the global CSV.
```

#### 📄 `fix_wc_name_mapping.py`
```python
Advanced WC Player Name Resolver
Uses multi-strategy matching:
1. Exact normalized match
2. Subset token match (FBref name tokens ⊆ legal name tokens)
3. Last-name + first-name-initial match
4. Single distinctive last name match (for mono-name players like Richarlison)
```

#### 📄 `free_scraper_module.py`
```python
def get_todays_fixtures_free():
today = datetime.datetime.now().strftime("%Y-%m-%d")
url = f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{today}"
with SB(uc=True, headless=True) as sb:
sb.open(url)
...
```

#### 📄 `full_system_audit.py`
```python
DeepFieldPro - Full System Audit
Checks: dataset integrity, WC player coverage, model readiness, hardcoded values, best practices.
```

#### 📄 `generate_datasets_and_reports.py`
```python
DeepFieldPro - Final Deliverables Generator
Compiles datasets and generates team projections, risk analysis, and final recommendations.
```

#### 📄 `generate_feature_importance.py`
```python
DeepFieldPro - Feature Importance & SHAP Analysis
Extracts global feature importances from the finalized LightGBM models.
```

#### 📄 `generate_predictions.py`
```python
# Add src root to pythonpath
sys.path.insert(0, os.path.dirname(__file__))
load_models,
get_player_historical_stats,
build_feature_vector,
...
```

#### 📄 `get_real_pass_data.py`
```python
get_real_pass_data.py
-----------------------
STEP 1: Get REAL per-match pass data from StatsBomb open data.
Uses FIFA World Cup 2022 + 2018 match event data to extract
actual completed passes per player per match.

This replaces the formula proxy with ground truth training data.
```

#### 📄 `goal_scraper.py`
```python
DeepFieldPro — Endless FBref Scraper (Goal Mode)
================================================
Scrapes match logs for missing leagues, handles rate-limits automatically,
and doesn't stop until all target leagues are downloaded and merged.
```

#### 📄 `heartbeat.py`
```python
def ping_api(url, headers=None, name="API"):
try:
response = requests.get(url, headers=headers, timeout=5)
if response.status_code == 200:
return True
...
```

#### 📄 `hyperparameter_optimization.py`
```python
DeepFieldPro - Hyperparameter Optimization & Grid Search
Tests different hyperparameter configurations for LightGBM and evaluates results.
```

#### 📄 `inject_real_odds.py`
```python
def run():
db = sqlite3.connect("data/odds_stream.db")
cursor = db.cursor()
with open("data/betarabia_api_responses.json", "r", encoding="utf-8") as f:
responses = json.load(f)
...
```

#### 📄 `inspect_odds.py`
```python
API_KEY = "4ae9f07e1ae1f775050015c50037a71d"
HEADERS = {"x-apisports-key": API_KEY}
BASE = "https://v3.football.api-sports.io"
r = requests.get(f"{BASE}/odds", headers=HEADERS, params={"fixture": 1528284})
data = r.json()
...
```

#### 📄 `institutional_deployment_lab.py`
```python
# Add src root to pythonpath
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)
class InstitutionalDeploymentLab:
...
```

#### 📄 `kelly_calculator.py`
```python
kelly_calculator.py
-------------------
Correct Kelly Criterion implementation.
- Takes fair_prob directly from model output (not derived from edge)
- Enforces minimum edge threshold before sizing
- Caps at 2% bankroll per bet
```

#### 📄 `lineup_monitor.py`
```python
lineup_monitor.py
-----------------
Polls for lineup confirmation and triggers the full downstream pipeline:
  1. Detects when the lineup payload is populated
  2. Parses the lineup (lineup_parser)
  3. Updates the role baseline (role_baseline_builder)
  4. Detects role shifts (role_shift_detector)
  5. Logs the latency

All processing is done immediately on lineup receipt to maximize
the survival window before the market reprices.
```

#### 📄 `lineup_parser.py`
```python
lineup_parser.py
----------------
Parses the API-Football v3 lineup payload into structured player roles.
Handles the REAL API response format:
  startXI[n]['player'] = {'id': 1234, 'name': 'Rodri', 'pos': 'M', 'grid': '4:1'}

Grid format: 'row:column' where row 1 = goalkeeper.
Storing the grid enables formation detection in the future.
```

#### 📄 `live_dashboard_server.py`
```python
app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
# Create default settings if not exists
...
```

#### 📄 `live_game_test.py`
```python
# Add src root to pythonpath
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
policy_agent,
)
logging.basicConfig(level=logging.INFO, format="%(message)s")
...
```

#### 📄 `live_predictions_daemon.py`
```python
# Unicode-safe print override for Windows console compatibility
_orig_print = print
def print(*args, **kwargs):
enc = sys.stdout.encoding or "utf-8"
cleaned = []
...
```

#### 📄 `match_odds_evaluator.py`
```python
DeepFieldPro — Match Odds Evaluator
====================================
Aggregates Player xG from our models into Team xG,
calculates match outcome probabilities using Poisson distributions,
and compares them against live API-Football match odds to find +EV bets.
```

#### 📄 `match_simulation_engine.py`
```python
DeepFieldPro - Match Simulation Engine (Production-Ready)
Runs 10,000 simulations per match using actual WC team rosters from the mapping CSV.
Players are looked up by their real national team assignments from the nation_ field.
```

#### 📄 `match_simulator.py`
```python
match_simulator.py — DeepFieldPro Monte Carlo Simulation Engine
================================================================
Simulates a match N times (default 10,000) by:
  1. Drawing player-level events (goals, assists, shots, cards) using Poisson / Binomial distributions
  2. Aggregating player draws to team-level outcomes
  3. Computing match result probabilities, exact scorelines, Over/Under, BTTS

BUG FIXES vs previous version:
  - xg/xa/shots are per-90 values → converted to per-match using expected_minutes (default 75)
  - anytime_goal now derived from simulation (np.mean(goals > 0)), not from raw input
  - All player prop output values rounded to 1 decimal place
```

#### 📄 `migrate_bet_log.py`
```python
db_path = "data/bet_log.db"
conn = sqlite3.connect(db_path)
cur = conn.cursor()
# Check current columns in bet_log
cur.execute("PRAGMA table_info(bet_log)")
...
```

#### 📄 `minor_league_scraper_2025.py`
```python
DeepFieldPro - 2025 Minor Leagues Scraper
=========================================
Bypasses API rate limits and paywalls by directly querying the Sofascore API
via SeleniumBase (Undetected ChromeDriver).

This script targets the 2025 season data for leagues that FBref and API-Football
(Free) do not provide.
```

#### 📄 `model_comparison.py`
```python
DeepFieldPro - Extensive Model Comparison & Validation Suite
Evaluates XGBoost, LightGBM, Random Forest, and baseline models across all target variables.
Produces exhaustive feature importance and calibration metrics.
```

#### 📄 `model_runner.py`
```python
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))
BASE_DIR = config.BASE_DIR
MODEL_DIR = config.MODEL_DIR
DATA_DIR = config.DATA_DIR
DB_ODDS = os.path.join(DATA_DIR, "odds_stream.db")
...
```

#### 📄 `model_runner_v2.py`
```python
model_runner.py — DeepFieldPro Model Execution Engine
=====================================================
Loads LightGBM models, queries player DB, applies international normalization,
and routes to correct model based on competition_type.

NAMING CONVENTIONS:
- Parameters: ProperCase suffix _P  (e.g. FallbackLeague_P)
- Variables:  ProperCase suffix _V  (e.g. LamSot_V)
- SQL table/column names: lowercase
- SQL keywords: UPPERCASE
- Comments: single line, human-readable, max 1 line
```

#### 📄 `module_audit.py`
```python
Deep audit: checks every module claimed in the README actually exists and imports cleanly.
```

#### 📄 `odds_feed.py`
```python
odds_feed.py
------------
Live odds ingestion. Two modes:
  - Dev:  REST polling via The Odds API (no WebSocket, limited rate)
  - Prod: Betfair Exchange WebSocket stream via betfairlightweight 2.23+

BUG FIX (v2.23 API change):
  betfairlightweight 2.23 no longer passes raw JSON dicts to on_data().
  The library now handles parsing internally. Use listener.snap() to read
  MarketBook objects from the internal cache after streaming starts.

Performance fix:
  All DB writes are queued and written in batches by a background thread
  to avoid SQLite becoming a bottleneck under high-frequency tick data.
```

#### 📄 `odds_scraper_betarabia.py`
```python
odds_scraper_betarabia.py
--------------------------
STEP 4: Live odds feed from Betarabia.

Since Betarabia has no public API, this scraper:
1. Uses requests + BeautifulSoup to pull odds from their live match pages
2. Parses player prop markets (passes over/under lines)
3. Writes matching odds rows to odds_stream.db every 30 seconds

Usage: Run in background alongside lineup_monitor.py
  python odds_scraper_betarabia.py
```

#### 📄 `opponent_model_integrator.py`
```python
# Note: Ensure lightgbm and shap are installed: pip install lightgbm shap scikit-learn
# import lightgbm as lgb
# import shap
def prepare_training_data(training_csv, opponent_db_path):
"""
...
```

#### 📄 `opponent_scraper.py`
```python
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "opponent_profiles.db")
def init_db():
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
cursor.execute(
...
```

#### 📄 `orchestrator.py`
```python
DeepField Orchestrator - Production Grade

Main entry point for the DeepField sportsbook acquisition system.
Coordinates all services and manages the complete data acquisition pipeline.

Features:
- Service orchestration and lifecycle management
- Graceful shutdown handling
- Health monitoring
- Metrics collection
- Automatic recovery
```

#### 📄 `parlay_builder.py`
```python
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SINGLE_BETS_FILE = os.path.join(BASE_DIR, "data", "todays_single_bets.json")
def is_correlated(legs: List[Dict]) -> bool:
...
```

#### 📄 `predict_todays_games.py`
```python
DeepFieldPro - Today's Match Predictions (2026-06-05)
Fixes all audit issues and generates full predictions for today's games.

FIXES APPLIED:
  1. Team lookup uses nation_ field (not broken nation_code='UNK')
  2. Generates proper player-level projections with CI
  3. Fetches real fixture lineups/squads from API-Football
  4. No hardcoded data - everything driven from the verified DB
```

#### 📄 `pricing_engine.py`
```python
pricing_engine.py — DeepFieldPro Probability Calculator
========================================================
Calculates over/under probabilities using Pearson mean normalization
and Negative Binomial distribution.

NAMING CONVENTIONS:
- Parameters: ProperCase suffix _P
- Variables:  ProperCase suffix _V
- Comments: single line, max 1 line
```

#### 📄 `restore_api_rows.py`
```python
Fix the 44 API-Football rows that have no game_ date.
These are season-aggregate rows from the scrape_api_football.py run.
We assign them a synthetic game_ date of '2024-07-01 SeasonAggregate'
so they parse correctly and can be used as a season baseline.
```

#### 📄 `role_baseline_builder.py`
```python
role_baseline_builder.py
-------------------------
Builds and maintains each player's typical role profile from historical lineup data.

Minimum sample requirement: 3 starts per player before a baseline is set.
This prevents false role-shift alerts from players with very few data points.
```

#### 📄 `role_shift_detector.py`
```python
role_shift_detector.py
----------------------
Detects when a player's role in today's lineup differs from their historical baseline.

IMPORTANT — Multiplier Calibration Policy:
  The ROLE_SHIFT_MULTIPLIERS dict contains PLACEHOLDER values for initial testing.
  These must be replaced with empirically measured values from your historical data
  once you have >= 10 match samples per shift type.

  Until calibrated, uncalibrated shift types will be FLAGGED but NOT applied.
  Applying uncalibrated multipliers is worse than doing nothing.

  To calibrate: run this SQL against your historical data:
    SELECT old_role || '->' || new_role as shift_type,
           AVG(actual_passes / expected_passes_baseline) as empirical_multiplier,
           COUNT(*) as sample_size
    FROM historical_shift_outcomes
    GROUP BY shift_type
    HAVING COUNT(*) >= 10
```

#### 📄 `run_bottom_up_predictions_today.py`
```python
API_KEY = "4ae9f07e1ae1f775050015c50037a71d"
HEADERS = {"x-apisports-key": API_KEY, "x-apisports-host": "v3.football.api-sports.io"}
def get_todays_fixtures(only_friendlies=False):
today = datetime.datetime.now().strftime("%Y-%m-%d")
url = f"https://v3.football.api-sports.io/fixtures?date={today}"
...
```

#### 📄 `run_todays_predictions.py`
```python
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
...
```

#### 📄 `scheduler_daemon.py`
```python
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)
sys.path.insert(0, os.path.dirname(__file__))
class PipelineDaemon:
def __init__(self):
...
```

#### 📄 `scrape_api_football.py`
```python
DeepFieldPro - Bulletproof API-Football Scraper
1. Downloads all 830 World Cup players from API-Football (42 paginated requests).
2. Maps their API ID to our missing players list locally.
3. Fetches their 2024/2025 match logs/stats (1 request per missing player).
```

#### 📄 `scrape_league_worker.py`
```python
Single-league scraper template for parallel execution.
Usage: python scrape_league_worker.py <league> <season> <output_file>
```

#### 📄 `scrape_missing_wc_players.py`
```python
DeepFieldPro - Missing Leagues Scraper
Scrapes the 6 valid FBref leagues that were NOT in the original global scrape:
  - ARG-Primera Division
  - BEL-Pro League
  - BRA-Brasileirao
  - ENG-Championship
  - KSA-Saudi Pro League
  - USA-MLS

Appends all WC players found to world_cup_players_match_logs_global.csv
```

#### 📄 `scratch_inspect.py`
```python
data_dir = "data"
for db_name in ["odds_stream.db", "bet_log.db", "bankroll.db"]:
db_path = os.path.join(data_dir, db_name)
if not os.path.exists(db_path):
print(f"{db_name} does not exist.")
...
```

#### 📄 `scratch_inspect_api.py`
```python
with open("data/betarabia_api_responses.json", "r") as f:
responses = json.load(f)
for i, resp in enumerate(responses):
url = resp.get("url", "")
data = resp.get("data", {})
...
```

#### 📄 `scratch_inspect_event.py`
```python
with open("data/betarabia_api_responses.json", "r") as f:
responses = json.load(f)
for i, resp in enumerate(responses):
data = resp.get("data", {})
if (
...
```

#### 📄 `seed_comparisons.py`
```python
db_path = "data/bet_log.db"
conn = sqlite3.connect(db_path)
cur = conn.cursor()
# Ensure predictions table exists
cur.execute(
...
```

#### 📄 `seed_opponent_profiles.py`
```python
seed_opponent_profiles.py
--------------------------
Computes per-team PPDA proxy and possession-allowed proxy
directly from the scraped World Cup match logs.

PPDA proxy: We don't have true PPDA (passes allowed / defensive actions)
from summary logs, so we use passes conceded per game as a proxy
by grouping from the opponent's perspective.

Possession-allowed proxy: We estimate it from passes completed per game
relative to the overall average.
```

#### 📄 `show_tonights_bets.py`
```python
bets_data = json.load(open("data/todays_single_bets.json", encoding="utf-8"))
bets = bets_data["bets"]
batch = [b for b in bets if b["status"] == "BATCH"]
monitor = [b for b in bets if b["status"] == "MONITOR"]
print("=" * 64)
...
```

#### 📄 `similarity_engine.py`
```python
similarity_engine.py — DeepFieldPro Unknown Player Profiler
============================================================
When a player is not found in the stats DB (missing transfers, academy call-ups, etc.),
this engine finds the 5 most similar known players using K-Nearest Neighbors (cosine distance)
and synthesises estimated per-90 stats for them.

BUG FIX vs previous version:
  - Query vector now passed as a named pd.DataFrame to kneighbors() instead of a raw
    numpy array, eliminating the sklearn feature-name warning.
```

#### 📄 `simulation.py`
```python
simulation.py — DeepFieldPro World Cup Simulation
Runs a complete paper-trade simulation for today's international matches.
Uses the validated passes/Poisson model with real player stats from CSV.
Does NOT require live odds — outputs bets at target odds thresholds.

Run: python src/simulation.py --bankroll 500
```

#### 📄 `single_bet_predictor.py`
```python
# Today's date in UTC — used to filter only today's fixtures
TODAY_UTC = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, "src"))
...
```

#### 📄 `survival_window_analyzer.py`
```python
LOG_FILE = os.path.join(
os.path.dirname(__file__), "..", "data", "lineup_latency_log.csv"
)
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "odds_stream.db")
PLOTS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "plots")
...
```

#### 📄 `system_check.py`
```python
system_check.py - Full system health audit for DeepFieldPro
```

#### 📄 `test_model_prediction.py`
```python
Test model end-to-end prediction.
```

#### 📄 `test_odds_parsing.py`
```python
with open("data/betarabia_api_responses.json", "r") as f:
responses = json.load(f)
events_by_id = {}
markets_by_event = {}
# 1. Parse events
...
```

#### 📄 `test_pipeline.py`
```python
# mypy: ignore-errors
# Paths
BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "..", "data")
DB_LINEUPS = os.path.join(DATA_DIR, "parsed_lineups.db")
...
```

#### 📄 `train_all_betarabia_models.py`
```python
# mypy: ignore-errors
print("Building training dataset for all Betarabia props...")
try:
df = pd.read_csv(os.path.join(config.DATA_DIR, "world_cup_players_match_logs.csv"))
except FileNotFoundError:
...
```

#### 📄 `train_bottom_up_model.py`
```python
def load_and_preprocess():
print("[*] Loading global minor leagues data...")
df_minor = pd.read_csv("data/minor_leagues_2025.csv")
print("[*] Loading World Cup historical data...")
try:
...
```

#### 📄 `train_minutes_model.py`
```python
# mypy: ignore-errors
df = pd.read_csv(os.path.join(config.DATA_DIR, "training_dataset.csv"))
# Use Min% instead of Percentage of Minutes Played
# And rename if needed, but we can just use Min% directly
df["Percentage of Minutes Played"] = df["Min%"]
...
```

#### 📄 `train_models.py`
```python
train_models.py — DeepFieldPro Model Training Pipeline
======================================================
Trains all 4 LightGBM models with competition_type feature and international normalization.

NAMING CONVENTIONS:
- Parameters: ProperCase suffix _P  (e.g. CompType_P)
- Variables:  ProperCase suffix _V  (e.g. BrierScore_V)
- SQL table/column names: lowercase
- SQL keywords: UPPERCASE
- Comments: single line, human-readable, max 1 line
```

#### 📄 `train_passes_model.py`
```python
# mypy: ignore-errors
df = pd.read_csv(os.path.join(config.DATA_DIR, "training_dataset.csv"))
df["Percentage of Minutes Played"] = pd.to_numeric(df["Min%"], errors="coerce").fillna(
0.8
)
...
```

#### 📄 `train_shots_models.py`
```python
# mypy: ignore-errors
print("Loading shots training dataset...")
df = pd.read_csv(os.path.join(config.DATA_DIR, "shots_training_dataset.csv"))
df["Percentage of Minutes Played"] = df["Min%"]
# Encode Position
...
```

#### 📄 `train_wc_prop_models.py`
```python
DeepFieldPro - World Cup Player Prop Model Training (v2)
- Uses pre-built wc_player_name_mapping.csv for fast O(1) player lookups
- Trains LightGBM for Goals, Shots, Assists, SoT, Yellow Cards, Minutes
```

#### 📄 `utils.py`
```python
utils.py
--------
Shared utility functions used across the entire pipeline.
- Vig stripping (MUST be applied before any edge calculation)
- Overround calculation
- Decimal/probability conversions
```

#### 📄 `wc_scraper.py`
```python
print("Initializing Global World Cup 2026 Scraper...")
# The 48 countries qualified for the 2026 World Cup (FBref Nationality Codes)
WC_NATIONS = [
"ARG",
"BRA",
...
```

### 📁 Directory: `src\adversarial_detection`

#### 📄 `hidden_markov_throttle_detector.py`
```python
logger = logging.getLogger(__name__)
class HiddenMarkovThrottleDetector:
"""
Adversarial Sportsbook Detection Engine.
Uses Hidden Markov modeling heuristics to estimate P(account_restricted | recent_behavior).
...
```

### 📁 Directory: `src\api`

#### 📄 `main.py`
```python
FastAPI Application - Production Grade

Main FastAPI application for the DeepField sportsbook acquisition system.
Provides REST API endpoints for:
- Health monitoring
- Session management
- Browser control
- Live odds data
- Metrics export (Prometheus-compatible)
```

### 📁 Directory: `src\autonomous_portfolio_evolution`

#### 📄 `apel_engine.py`
```python
# mypy: ignore-errors
StrategyState,
StrategyStatus,
StrategyGenome,
)
...
```

#### 📄 `apel_simulation_lab.py`
```python
logging.basicConfig(level=logging.INFO, format="%(message)s")
class APELSimulationLab:
async def run_apel_cycle(self):
print("\n--- SCENARIO 1: Stable Portfolio ---")
# Simulate a good day for the core strategy
...
```

#### 📄 `schemas.py`
```python
class StrategyStatus(Enum):
ACTIVE = "ACTIVE"
PROBATION = "PROBATION"
RETIRED = "RETIRED"
class StrategyGenome(BaseModel):
...
```

### 📁 Directory: `src\capital_deployment_protocol`

#### 📄 `capital_ramp_controller.py`
```python
logger = logging.getLogger(__name__)
class CapitalRampController:
"""
Defines a safe, non-linear ramp function. Capital increases only if RVL is stable.
Uses Sigmoid/Logistic scaling rather than linear growth to prevent premature exposure.
...
```

#### 📄 `cdp_simulation_lab.py`
```python
# Add src root to pythonpath
sys.path.insert(0, "C:/Users/Elie/DeepFieldPro")
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)
class CDPSimulationLab:
...
```

#### 📄 `deployment_orchestrator.py`
```python
DeploymentState,
RolloutPhase,
HealthStatus,
CapitalAllocationRequest,
)
...
```

#### 📄 `live_capital_switch.py`
```python
logger = logging.getLogger(__name__)
class LiveCapitalSwitch:
"""
A hard boundary safety system. Instantly disables execution if critical thresholds are breached.
Overrides all ML, MGL, and APO systems.
...
```

#### 📄 `regime_sensitive_position_sizing.py`
```python
logger = logging.getLogger(__name__)
class RegimeSensitivePositionSizing:
"""
Dynamically sizes positions based on market regime and execution fragility.
"""
...
```

#### 📄 `rollout_state_machine.py`
```python
logger = logging.getLogger(__name__)
class RolloutStateMachine:
"""
Enforces strict transitions: SHADOW -> MICRO -> LIMITED -> FULL.
Cannot skip phases. Must support rollback.
...
```

#### 📄 `schemas.py`
```python
class RolloutPhase(str, Enum):
PHASE_0_SHADOW = "SHADOW"
PHASE_1_MICRO = "MICRO"
PHASE_2_LIMITED = "LIMITED"
PHASE_3_PRODUCTION = "PRODUCTION"
...
```

#### 📄 `state_persistence.py`
```python
W1 FIX: State Persistence Layer
Persists DeploymentState to SQLite so process restarts don't reset to Day 0.
Also persists the daily drift budget for GlobalSafetyConstraints.
```

### 📁 Directory: `src\capital_scaling_intelligence`

#### 📄 `acsi_engine.py`
```python
ACSIScalingState,
ScalingDecision,
)
compounding_detector,
)
...
```

#### 📄 `acsi_simulation_lab.py`
```python
# Add src root to pythonpath
sys.path.insert(0, "C:/Users/Elie/DeepFieldPro")
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)
class ACSISimulationLab:
...
```

#### 📄 `capital_velocity_controller.py`
```python
logger = logging.getLogger(__name__)
class CapitalVelocityController:
"""
Controls HOW FAST capital is increased or decreased over time.
Prevents exponential runaway scaling and sudden capital doubling events.
...
```

#### 📄 `growth_vs_risk_optimizer.py`
```python
logger = logging.getLogger(__name__)
class GrowthVsRiskOptimizer:
"""
The Core Decision Engine of ACSI.
Maximizes: long_term_growth - drawdown_penalty - regime_instability_penalty
...
```

#### 📄 `long_horizon_ev_forecaster.py`
```python
logger = logging.getLogger(__name__)
class LongHorizonEVForecaster:
"""
Forecasts expected EV trajectory over rolling windows, explicitly modeling
EV decay under scaling pressure.
...
```

#### 📄 `regime_compounding_detector.py`
```python
W3 FIX: Probabilistic Regime Compounding Detector.
Replaces hard boolean thresholds with a soft-score model that outputs a
continuous decay_probability in [0, 1]. COMPOUNDING/NEUTRAL/DECAY zones
are determined by probability bands, not crisp if/else boundaries.
```

#### 📄 `schemas.py`
```python
class CompoundingRegime(str, Enum):
COMPOUNDING = "COMPOUNDING"
NEUTRAL = "NEUTRAL"
DECAY = "DECAY"
class ScalingDecision(str, Enum):
...
```

### 📁 Directory: `src\config`

#### 📄 `settings.py`
```python
Application Settings and Configuration

Centralized configuration management using environment variables.
```

### 📁 Directory: `src\data`

#### 📄 `advanced_fbref_scraper.py`
```python
def scrape_advanced_tables(leagues: list, seasons: list) -> pd.DataFrame:
"""
Expands the baseline 'summary' scraper to pull the deep tactical tables.
WARNING: FBref rate limits heavily. This must be run with time.sleep()
and ideally cached heavily.
...
```

### 📁 Directory: `src\data_acquisition`

#### 📄 `betarabia_scraper.py`
```python
logger = logging.getLogger(__name__)
class BetarabiaAPIClient:
def __init__(self):
self.playwright = None
self.browser = None
...
```

#### 📄 `clv_engine.py`
```python
# clv_engine.py
logger = logging.getLogger(__name__)
class CLVEngine:
"""
Formalizes Closing Line Value tracking.
...
```

#### 📄 `db_writer.py`
```python
logger = logging.getLogger(__name__)
DB_PATH = os.path.join(config.BASE_DIR + "/src", "live_data.db")
def init_db():
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
...
```

#### 📄 `dynamic_repricer.py`
```python
# mypy: ignore-errors
# dynamic_repricer.py
# from src.model_runner import get_base_predictions (Conceptual import)
logger = logging.getLogger(__name__)
class DynamicRepricingEngine:
...
```

#### 📄 `edge_engine.py`
```python
# mypy: ignore-errors
# edge_engine.py
logger = logging.getLogger(__name__)
class MarketEdgeEngine:
"""
...
```

#### 📄 `event_dispatcher.py`
```python
# mypy: ignore-errors
# New Lineup Architecture Modules
logger = logging.getLogger(__name__)
@dataclass
class LineupConfirmedEvent:
...
```

#### 📄 `execution_queue.py`
```python
# execution_queue.py
logger = logging.getLogger(__name__)
class ExecutionRouteOptimizer:
"""
Ranks executable edges based on Market Microstructure intelligence.
...
```

#### 📄 `execution_simulator.py`
```python
# execution_simulator.py
logger = logging.getLogger(__name__)
class ExecutionSimulator:
"""
Replaces the live Betarabia execution engine during backtests.
...
```

#### 📄 `expected_lineup_predictor.py`
```python
# expected_lineup_predictor.py
logger = logging.getLogger(__name__)
class ExpectedLineupPredictor:
"""
Massive future edge.
...
```

#### 📄 `fixtures_monitor.py`
```python
logger = logging.getLogger(__name__)
class FixturesMonitor:
def __init__(self):
self.monitored_fixtures = {}  # fixture_id -> dict of metadata
def add_fixture_to_monitor(self, fixture_id: str, kickoff_utc: str):
...
```

#### 📄 `formation_impact_engine.py`
```python
# formation_impact_engine.py
logger = logging.getLogger(__name__)
class FormationImpactEngine:
"""
Translates formation and positional context into statistical multipliers for the Pricing Engine.
...
```

#### 📄 `historical_batch_simulator.py`
```python
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
# Add src root to pythonpath
logging.basicConfig(
level=logging.WARNING
)  # Suppress info to prevent flooding, only show report
...
```

#### 📄 `latency_stress_test.py`
```python
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
# Add src root to pythonpath
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)
MARKETS = [
...
```

#### 📄 `latency_telemetry.py`
```python
logger = logging.getLogger(__name__)
class LatencyTelemetry:
"""
Provides nanoscopic visibility into the Live Execution DOM interactions.
Tracks Detection-to-Confirmed-Bet Latency as the ultimate KPI.
...
```

#### 📄 `lineup_change_detector.py`
```python
# mypy: ignore-errors
# lineup_change_detector.py
logger = logging.getLogger(__name__)
class LineupChangeDetector:
def __init__(self):
...
```

#### 📄 `lineup_confidence_engine.py`
```python
# lineup_confidence_engine.py
logger = logging.getLogger(__name__)
class LineupConfidenceEngine:
def __init__(self):
# Tracking seen lineups per fixture to compute multi-source agreement
...
```

#### 📄 `lineup_scraper.py`
```python
logger = logging.getLogger(__name__)
class LineupScraper:
def __init__(self):
# Configuration for rotating proxies, user-agents, etc.
pass
...
```

#### 📄 `lineup_sources.py`
```python
# lineup_sources.py
LINEUP_SOURCES = {
"official_club_socials": {"reliability": 1.0, "latency_score": 1.0},
"official_league_feed": {"reliability": 1.0, "latency_score": 0.9},
"sofascore": {"reliability": 0.95, "latency_score": 0.8},
...
```

#### 📄 `lineup_telemetry.py`
```python
# lineup_telemetry.py
logger = logging.getLogger(__name__)
class LineupTelemetry:
"""
Handles tracking latency of lineup detection vs official release,
...
```

#### 📄 `live_execution_manager.py`
```python
logger = logging.getLogger(__name__)
class LiveExecutionManager:
"""
Manages persistent, fully-authenticated, warm browser sessions.
Maintains parallel execution lanes to bypass serial clicking bottlenecks.
...
```

#### 📄 `market_mapper.py`
```python
# mypy: ignore-errors
BETARABIA_MARKET_MAP = {
# Goalscorer Markets
"Anytime Goalscorer": "player_goal_anytime",
"Player will score a goal": "player_goal_anytime",
...
```

#### 📄 `normalization_engine.py`
```python
# mypy: ignore-errors
class NormalizationEngine:
def __init__(self, alias_dict=None):
self.alias_dict = alias_dict or {}
def normalize_name(self, raw_name: str) -> str:
...
```

#### 📄 `odds_monitor.py`
```python
logger = logging.getLogger(__name__)
class OddsMonitor:
def __init__(self):
self.active_fixtures = {}  # fixture_id -> { "starters": [...] }
def start_monitoring_fixture(
...
```

#### 📄 `player_position_normalizer.py`
```python
# player_position_normalizer.py
POSITION_MAP = {
"GK": "goalkeeper",
"CB": "center_back",
"LCB": "center_back",
...
```

#### 📄 `replay_analytics.py`
```python
# mypy: ignore-errors
# replay_analytics.py
logger = logging.getLogger(__name__)
class ReplayAnalyticsDashboard:
"""
...
```

#### 📄 `replay_engine.py`
```python
# mypy: ignore-errors
# replay_engine.py
logger = logging.getLogger(__name__)
class ReplayEngine:
"""
...
```

#### 📄 `risk_engine.py`
```python
# risk_engine.py
logger = logging.getLogger(__name__)
class PortfolioRiskEngine:
"""
Prevents catastrophic ruin by enforcing strict exposure limits,
...
```

#### 📄 `run_trial_simulation.py`
```python
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
# Add src root to pythonpath
# Setup logging to see the full event stream in the console
logging.basicConfig(
level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
...
```

#### 📄 `settlement_engine.py`
```python
# settlement_engine.py
logger = logging.getLogger(__name__)
class SettlementEngine:
"""
Handles post-match outcomes, ROI tracking, and model calibration logic.
...
```

#### 📄 `simulation_clock.py`
```python
# simulation_clock.py
logger = logging.getLogger(__name__)
class SimulationClock:
"""
Overrides system time during backtesting.
...
```

#### 📄 `validation_engine.py`
```python
logger = logging.getLogger(__name__)
class ValidationEngine:
@staticmethod
def validate_lineup(lineup_payload: Dict[str, Any]) -> bool:
"""
...
```

#### 📄 `websocket_parser.py`
```python
# mypy: ignore-errors
logger = logging.getLogger(__name__)
RAW_FRAMES_DIR = os.path.join(config.BASE_DIR + "/src", "data_acquisition/raw_frames")
os.makedirs(RAW_FRAMES_DIR, exist_ok=True)
@dataclass
...
```

### 📁 Directory: `src\data_acquisition\live_execution`

#### 📄 `dom_interaction_engine.py`
```python
# dom_interaction_engine.py
logger = logging.getLogger(__name__)
class DomInteractionEngine:
"""
Retry-safe wrappers around Playwright actions to protect against Asynchronous DOM Race Conditions.
...
```

#### 📄 `live_paper_trader.py`
```python
sys.path.insert(
0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
)
# live_paper_trader.py
# Add src root to pythonpath
...
```

#### 📄 `selector_registry.py`
```python
# selector_registry.py
logger = logging.getLogger(__name__)
class SelectorRegistry:
"""
Centralized selector management.
...
```

### 📁 Directory: `src\data_acquisition\live_execution\adaptive_layer`

#### 📄 `adaptive_events.py`
```python
@dataclass
class MarketVelocityChangedEvent:
fixture_id: str
market_type: str
velocity_score: float
...
```

#### 📄 `adaptive_execution_engine.py`
```python
logger = logging.getLogger(__name__)
class AdaptiveExecutionEngine:
"""
The orchestrator of the Adaptive Market Intelligence Layer.
Ties together the queue optimizer, stake allocator, and live execution wrappers.
...
```

#### 📄 `adaptive_latency_controller.py`
```python
logger = logging.getLogger(__name__)
class AdaptiveLatencyController:
"""
Dynamically adjusts the queue delay and execution aggressiveness
based on the current market velocity and bookmaker profile.
...
```

#### 📄 `adaptive_simulation_harness.py`
```python
sys.path.insert(
0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
)
MarketVelocityChangedEvent,
)
...
```

#### 📄 `autonomous_queue_optimizer.py`
```python
logger = logging.getLogger(__name__)
class AutonomousQueueOptimizer:
"""
Self-learning queue that dynamically reranks bets based on expected decay speed,
historical fill probability, and current market regime.
...
```

#### 📄 `autonomous_stake_allocator.py`
```python
logger = logging.getLogger(__name__)
class AutonomousStakeAllocator:
"""
Dynamic stake sizing (Kelly Criterion + Execution Friction modification).
Adjusts stake based on edge confidence, market survivability, and latency regime.
...
```

#### 📄 `edge_decay_predictor.py`
```python
# mypy: ignore-errors
logger = logging.getLogger(__name__)
class EdgeDecayPredictor:
"""
Builds mathematical edge decay curves Edge(t).
...
```

#### 📄 `execution_behavior_memory.py`
```python
logger = logging.getLogger(__name__)
class ExecutionBehaviorMemory:
"""
Persists execution outcomes, suspension patterns, failed clicks, and bookmaker processing latency.
Serves as the foundational dataset for all adaptive models and machine learning pipelines.
...
```

#### 📄 `execution_failure_classifier.py`
```python
logger = logging.getLogger(__name__)
class ExecutionFailureClassifier:
"""
Automatically classifies execution failures to guide the adaptive learning loops.
Distinguishes between odds crashes, suspensions, network timeouts, and anti-bot flags.
...
```

#### 📄 `execution_heatmap_engine.py`
```python
logger = logging.getLogger(__name__)
class ExecutionHeatmapEngine:
"""
Generates multidimensional heatmaps of fill-rates, slippage, and rejections.
Useful for visualizing Market Microstructure performance.
...
```

#### 📄 `execution_survivability_model.py`
```python
logger = logging.getLogger(__name__)
class ExecutionSurvivabilityModel:
"""
Estimates the probability that a bet survives execution friction before we even attempt it.
"""
...
```

#### 📄 `live_execution_feedback_loop.py`
```python
# mypy: ignore-errors
logger = logging.getLogger(__name__)
class LiveExecutionFeedbackLoop:
"""
Closes the loop between execution outcome and adaptive models.
...
```

#### 📄 `market_regime_classifier.py`
```python
# mypy: ignore-errors
logger = logging.getLogger(__name__)
class MarketRegimeClassifier:
"""
Classifies markets into structural regimes: stable, reactive, panic, frozen, stale, high-frequency-volatility.
...
```

#### 📄 `market_velocity_tracker.py`
```python
# mypy: ignore-errors
logger = logging.getLogger(__name__)
class MarketVelocityTracker:
"""
Tracks odds acceleration and update frequency to determine Market Velocity.
...
```

#### 📄 `smart_market_skipper.py`
```python
# mypy: ignore-errors
logger = logging.getLogger(__name__)
class SmartMarketSkipper:
"""
Learns to SKIP markets that are too volatile, have low survivability,
...
```

### 📁 Directory: `src\data_acquisition\live_execution\predictive_layer`

#### 📄 `execution_policy_agent.py`
```python
logger = logging.getLogger(__name__)
class ExecutionPolicyAgent:
"""
Reinforcement-Learned Execution Policy.
Learns optimal actions: instant execute, batch execute, skip, split stake, etc.
...
```

#### 📄 `execution_research_lab.py`
```python
sys.path.insert(
0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
)
# Add src root to pythonpath
policy_agent,
...
```

#### 📄 `market_microstructure_embeddings.py`
```python
logger = logging.getLogger(__name__)
class MarketMicrostructureEmbeddings:
"""
Creates dense vector embeddings for leagues, markets, and players based on historical telemetry.
Useful for clustering, anomaly detection, and discovering structural inefficiencies.
...
```

#### 📄 `market_movement_forecaster.py`
```python
logger = logging.getLogger(__name__)
class MarketMovementForecaster:
"""
Predicts odds direction, odds acceleration, and volatility bursts BEFORE they occur.
"""
...
```

#### 📄 `real_time_edge_decay_forecaster.py`
```python
decay_predictor,
)
logger = logging.getLogger(__name__)
class RealTimeEdgeDecayForecaster:
"""
...
```

#### 📄 `suspension_probability_model.py`
```python
logger = logging.getLogger(__name__)
class SuspensionProbabilityModel:
"""
Estimates P(suspension within t).
Suspensions destroy execution survivability. If probability is high, we must front-run execution.
...
```

### 📁 Directory: `src\data_acquisition\live_execution\shadow_mode`

#### 📄 `account_behavior_profile.py`
```python
logger = logging.getLogger(__name__)
class AccountBehaviorProfile:
"""
Longitudinal telemetry to detect sportsbook adaptation signatures.
Measures confirmation delays over time, rejection rates, and account throttling.
...
```

#### 📄 `browser_rotation_controller.py`
```python
logger = logging.getLogger(__name__)
class BrowserRotationController:
"""
Rotates browser contexts, session identities, and timing profiles
to prevent deterministic behavioral fingerprinting by the sportsbook.
...
```

#### 📄 `execution_drift_monitor.py`
```python
# mypy: ignore-errors
logger = logging.getLogger(__name__)
class ExecutionDriftMonitor:
"""
Detects when live execution quality degrades over time.
...
```

#### 📄 `self_healing_browser_manager.py`
```python
logger = logging.getLogger(__name__)
class SelfHealingBrowserManager:
"""
Production engineering to handle Operational Entropy.
Autonomously recovers from stale sessions, memory leaks, and DOM deadlocks.
...
```

#### 📄 `shadow_deployment_lab.py`
```python
sys.path.insert(
0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
)
# Add src root to pythonpath
drift_monitor,
...
```

#### 📄 `shadow_execution_mode.py`
```python
logger = logging.getLogger(__name__)
class ShadowExecutionMode:
"""
Advanced Paper Trading Layer.
Executes EVERYTHING: real browser, real market selection, real queue timing,
...
```

#### 📄 `sportsbook_adversarial_model.py`
```python
logger = logging.getLogger(__name__)
class SportsbookAdversarialModel:
"""
Predicts how Betarabia responds specifically to OUR behavior.
Builds an Adversarial Market Ecology.
...
```

### 📁 Directory: `src\database`

#### 📄 `migrate.py`
```python
Database Migration Script

Creates all database tables defined in models.py.
Supports PostgreSQL (production) and SQLite (development/testing).
```

#### 📄 `models.py`
```python
Database Models - Production Grade

SQLAlchemy models for the DeepField betting system with support for:
- Immutable odds tick storage
- WebSocket event tracking
- Session health monitoring
- Line movement history
- TimescaleDB-compatible patterns
```

### 📁 Directory: `src\execution_cluster`

#### 📄 `actor_orchestrator.py`
```python
# mypy: ignore-errors
logger = logging.getLogger(__name__)
class CircuitBreaker:
"""
Prevents cascading failures in the execution cluster.
...
```

### 📁 Directory: `src\features`

#### 📄 `availability.py`
```python
def calculate_availability_features(
df: pd.DataFrame, key_players_dict: dict = None
) -> pd.DataFrame:
"""
Calculates lineup, availability, and key-teammate absence features.
...
```

#### 📄 `fatigue.py`
```python
def calculate_fatigue_features(
df: pd.DataFrame, venue_coordinates: dict = None
) -> pd.DataFrame:
"""
Engineers fatigue and scheduling context features.
...
```

#### 📄 `generate_all.py`
```python
# Import our custom modules
def main():
data_path = os.path.join(
os.path.dirname(__file__), "../../data/world_cup_players_match_logs_global.csv"
)
...
```

#### 📄 `market_intelligence.py`
```python
def calculate_market_intelligence(df: pd.DataFrame) -> pd.DataFrame:
"""
Engineers betting-market features based on historical odds data.
Expected Input DataFrame `df`:
Must contain match-level odds data merged onto the player log:
...
```

#### 📄 `opponent_features.py`
```python
def calculate_opponent_features(df: pd.DataFrame) -> pd.DataFrame:
"""
Calculates rolling defensive statistics for opponents to measure Opponent Strength.
Crucially, these features are calculated using ONLY data available BEFORE kickoff.
Expected Input DataFrame `df`:
...
```

#### 📄 `player_rolling_form.py`
```python
def calculate_player_rolling_form(df: pd.DataFrame) -> pd.DataFrame:
"""
Calculates rolling performance metrics for individual players (Rolling Form).
Crucially, these features are calculated using ONLY data available BEFORE kickoff.
Expected Input DataFrame `df`:
...
```

#### 📄 `referee.py`
```python
def calculate_referee_features(df: pd.DataFrame) -> pd.DataFrame:
"""
Engineers referee tendency features to predict card and penalty probabilities.
Expected Input DataFrame `df`:
Must contain match-level logs including the Referee's name:
...
```

#### 📄 `team_tactics.py`
```python
def calculate_team_tactics(df: pd.DataFrame) -> pd.DataFrame:
"""
Calculates team-level tactical metrics to establish the environment the player operates in.
Crucially, features are calculated using ONLY data available BEFORE kickoff.
Expected Input DataFrame `df`:
...
```

#### 📄 `venue_effects.py`
```python
def calculate_venue_effects(df: pd.DataFrame) -> pd.DataFrame:
"""
Calculates venue-specific player averages and international context.
Crucially, features are calculated using ONLY data available BEFORE kickoff.
Expected Input DataFrame `df`:
...
```

#### 📄 `weather.py`
```python
def fetch_weather_data(lat: float, lon: float, match_date: str) -> dict:
"""
Example integration with the Open-Meteo Historical Weather API.
Open-Meteo is free for non-commercial use and doesn't require an API key.
Returns: temperature (C), humidity (%), wind_speed (km/h), rain (mm)
...
```

### 📁 Directory: `src\live_operations`

#### 📄 `account_health_engine.py`
```python
Account Health Engine
Tracks sportsbook account trust score (0-100) based on bet acceptance rate,
limits applied, and restriction signals. Triggers alerts when score drops.
```

#### 📄 `alerting_system.py`
```python
Alerting System — multi-channel alert dispatcher for kill-switch events,
edge collapse, account restrictions, and infrastructure failures.
```

#### 📄 `edge_decay_live.py`
```python
Edge Decay Live Monitor
Snapshots EV at T0, T+1s, T+5s, T_exec, T_close and computes EV half-life.
```

#### 📄 `live_clv_tracker.py`
```python
Live CLV Tracker — rolling weighted CLV by sportsbook/market/latency.
```

#### 📄 `shadow_deployment_orchestrator.py`
```python
Shadow Deployment Orchestrator
Continuously generates paper bets from live signals, simulates fills,
and tracks CLV on every position for statistical validation.
```

### 📁 Directory: `src\meta_research`

#### 📄 `meta_research_governor.py`
```python
# mypy: ignore-errors
logger = logging.getLogger(__name__)
class MetaResearchGovernor:
"""
Meta-Research Control Engine.
...
```

### 📁 Directory: `src\ml\online_learning`

#### 📄 `concept_drift_monitor.py`
```python
logger = logging.getLogger(__name__)
class ConceptDriftMonitor:
"""
Online Learning Pipeline: Detects concept drift in live execution telemetry.
Uses Population Stability Index (PSI) and KL-Divergence to monitor when
...
```

### 📁 Directory: `src\models`

#### 📄 `expected_minutes.py`
```python
def prepare_minutes_features(df: pd.DataFrame) -> pd.DataFrame:
"""
Engineers the specific features required to predict Expected Minutes.
Requires 'Min', 'Start', 'Pos', 'Comp' from base dataframe.
"""
...
```

#### 📄 `train_prop_model.py`
```python
def build_unified_feature_store(
df_base, opponent_df, rolling_df, venue_df, tactics_df, market_df, fatigue_df
):
"""
Combines all engineered features into a unified 150+ feature modeling dataset.
...
```

### 📁 Directory: `src\portfolio_optimization`

#### 📄 `bayesian_confidence_engine.py`
```python
logger = logging.getLogger(__name__)
class BayesianConfidenceEngine:
"""
Replaces static point estimates with posterior uncertainty.
If the system has very few data points on a specific execution route,
...
```

#### 📄 `capital_allocation_engine.py`
```python
logger = logging.getLogger(__name__)
class CapitalAllocationEngine:
"""
The True Portfolio Brain.
Jointly optimizes: f(EV, FillProbability, Volatility, Correlation, Liquidity, Latency, DrawdownRisk).
...
```

#### 📄 `drawdown_governor.py`
```python
# mypy: ignore-errors
logger = logging.getLogger(__name__)
class DrawdownGovernor:
"""
Dynamically reduces system aggressiveness during poor execution regimes,
...
```

#### 📄 `dynamic_bankroll_allocator.py`
```python
logger = logging.getLogger(__name__)
class DynamicBankrollAllocator:
"""
Allocates capital using a combination of Kelly Criterion, Correlation Penalties,
and Regime-Aware Exposure Control.
...
```

#### 📄 `liquidity_impact_model.py`
```python
logger = logging.getLogger(__name__)
class LiquidityImpactModel:
"""
Prevents the system from assuming infinite scalability.
Estimates market impact and suspension risk derived directly from stake size.
...
```

#### 📄 `portfolio_correlation_engine.py`
```python
logger = logging.getLogger(__name__)
class PortfolioCorrelationEngine:
"""
Detects hidden exposure overlaps dynamically.
Instead of static limits, we use a Graph representation of Player/Market/Match relationships.
...
```

#### 📄 `portfolio_research_lab.py`
```python
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
# Add src root to pythonpath
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)
class PortfolioResearchLab:
...
```

### 📁 Directory: `src\research\meta_governor`

#### 📄 `global_safety_constraints.py`
```python
# mypy: ignore-errors
logger = logging.getLogger(__name__)
class GlobalSafetyConstraints:
"""
MGL Hard Constraints.
...
```

#### 📄 `learning_rate_controller.py`
```python
logger = logging.getLogger(__name__)
class LearningRateController:
"""
Controls the learning speed of the APO (Policy Updates) and SCG (Stability Damping).
Adapts the update magnitude based on the System Health and Meta-Regret.
...
```

#### 📄 `meta_regret_engine.py`
```python
logger = logging.getLogger(__name__)
@dataclass
class MetaRegretMetrics:
baseline_ev: float
adaptive_system_ev: float
...
```

#### 📄 `mgl_engine.py`
```python
logger = logging.getLogger(__name__)
class MetaGovernorLayer:
"""
The MGL Engine.
Governs ALL lower layers (POA, APO, SCG) to ensure the adaptive system
...
```

#### 📄 `mgl_simulation_lab.py`
```python
sys.path.insert(
0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
)
# Add src root to pythonpath
logging.basicConfig(level=logging.INFO, format="%(message)s")
...
```

#### 📄 `system_health_scorer.py`
```python
logger = logging.getLogger(__name__)
@dataclass
class SystemHealthState:
score: float
is_collapsing: bool
...
```

### 📁 Directory: `src\research\policy_outcome_auditor`

#### 📄 `autonomous_policy_optimizer.py`
```python
logger = logging.getLogger(__name__)
class AutonomousPolicyOptimizer:
"""
The Next Step: Autonomous Policy Optimizer (APO).
Reads POA regrets, detects systematic mistakes, and automatically adjusts:
...
```

#### 📄 `clv_validation_layer.py`
```python
logger = logging.getLogger(__name__)
class CLVValidationLayer:
"""
Phase 4: CLV Validation Layer (Ground Truth Check).
Builds the contradiction detector identifying situations where the RL agent's
...
```

#### 📄 `counterfactual_engine.py`
```python
logger = logging.getLogger(__name__)
@dataclass
class CounterfactualOutcome:
execute_ev: float
skip_ev: float
...
```

#### 📄 `decision_store.py`
```python
PolicyDecisionEvent,
ExecutionOutcomeEvent,
MarketSnapshotEvent,
)
logger = logging.getLogger(__name__)
...
```

#### 📄 `event_schema.py`
```python
class PolicyDecisionEvent(BaseModel):
"""
Phase 0: Standardize event logging.
Every bet decision MUST carry a trace_id to link decision -> execution -> outcome.
"""
...
```

#### 📄 `poa_simulation_lab.py`
```python
sys.path.insert(
0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
)
# Add src root to pythonpath
logging.basicConfig(level=logging.INFO, format="%(message)s")
...
```

#### 📄 `policy_scoring_system.py`
```python
counterfactual_engine,
)
logger = logging.getLogger(__name__)
class PolicyScoringSystem:
"""
...
```

#### 📄 `regret_engine.py`
```python
logger = logging.getLogger(__name__)
class RegretEngine:
"""
Phase 3: Regret Engine (The Heart).
Regret is NOT loss. It is: BestPossibleOutcome - ChosenOutcome.
...
```

### 📁 Directory: `src\research\real_world_validation`

#### 📄 `baseline_comparison_engine.py`
```python
logger = logging.getLogger(__name__)
class BaselineComparisonEngine:
"""
Compares DeepFieldPro's Realized EV against static baselines in shadow mode.
Baselines:
...
```

#### 📄 `execution_friction_analyzer.py`
```python
logger = logging.getLogger(__name__)
class ExecutionFrictionAnalyzer:
"""
Measures real-world degradation.
Analyzes latency drift, odds movement during the decision window, and fill probabilities.
...
```

#### 📄 `performance_attribution_engine.py`
```python
logger = logging.getLogger(__name__)
class PerformanceAttributionEngine:
"""
Breaks down system performance to isolate WHERE alpha is coming from or being lost.
"""
...
```

#### 📄 `reality_alignment_check.py`
```python
logger = logging.getLogger(__name__)
class RealityAlignmentCheck:
"""
Detects simulation vs reality divergence.
Flags hidden degradation masked by risk controls or overly stabilized SCG/MGL dampening.
...
```

#### 📄 `rvl_simulation_lab.py`
```python
sys.path.insert(
0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
)
# Add src root to pythonpath
logging.basicConfig(level=logging.INFO, format="%(message)s")
...
```

#### 📄 `statistical_significance_tester.py`
```python
logger = logging.getLogger(__name__)
class StatisticalSignificanceTester:
"""
Answers: "Is observed performance statistically meaningful or just noise?"
W4 FIX: Implements bootstrap permutation test instead of assuming paired t-test.
...
```

#### 📄 `system_readiness_gate.py`
```python
baseline_engine,
)
stat_tester,
)
attribution_engine,
...
```

### 📁 Directory: `src\research\validation_framework`

#### 📄 `combinatorial_purged_cv.py`
```python
# mypy: ignore-errors
logger = logging.getLogger(__name__)
class CombinatorialPurgedCV:
"""
Scientific Backtest Validation Framework.
...
```

### 📁 Directory: `src\research_os`

#### 📄 `experiment_registry.py`
```python
Experiment Registry
Immutable tracking of research hypotheses, parameters, and results.
Every strategy begins here before advancing through the lifecycle.
```

#### 📄 `strategy_graveyard.py`
```python
Strategy Graveyard — permanent immutable record of all retired/rejected strategies.
Every strategy that dies gets an autopsy entry explaining why.
```

#### 📄 `strategy_lifecycle.py`
```python
Strategy Lifecycle Manager
Manages state transitions: RESEARCH → VALIDATION → SHADOW → LIMITED_CAPITAL → PRODUCTION → DEGRADED → RETIRED
Promotion/demotion decisions are based on CLV thresholds and statistical significance.
```

### 📁 Directory: `src\risk_engine`

#### 📄 `conditional_var_simulator.py`
```python
# mypy: ignore-errors
logger = logging.getLogger(__name__)
class ConditionalVaRSimulator:
"""
Institutional Risk Engine.
...
```

### 📁 Directory: `src\services\backtesting`

#### 📄 `execution_simulator.py`
```python
Execution Simulator

Realistic sportsbook execution simulation modeling:
- Line movement during delay
- Sportsbook rejection
- Max stake limits
- Stale odds
- Slippage
- Market liquidity
- Execution latency
```

#### 📄 `historical_replay.py`
```python
Historical Market Replay Engine

Replays historical odds ticks chronologically to reconstruct market state
at any point in time. Supports accelerated replay, deterministic mode,
and event-driven architecture.
```

### 📁 Directory: `src\services\clv`

#### 📄 `engine.py`
```python
Closing Line Value (CLV) Engine

Calculates and tracks CLV metrics:
- Standard CLV
- Weighted CLV
- Market-adjusted CLV
- Bookmaker-specific CLV
- Prediction timing analysis
```

### 📁 Directory: `src\services\market_intelligence`

#### 📄 `engine.py`
```python
Market Intelligence Engine

Generates advanced market microstructure features:
- Line velocity and acceleration
- Reverse line movement
- Steam moves
- Cross-book disagreement
- Sharp consensus signals
- Market pressure indicators
- Liquidity imbalance
- Volatility regimes
```

### 📁 Directory: `src\services\normalizer`

#### 📄 `engine.py`
```python
Odds Normalization Engine

Normalizes odds data from different sportsbooks into a consistent format.
Handles market mapping, odds conversion, and data validation.
```

### 📁 Directory: `src\services\odds_acquisition`

#### 📄 `collector.py`
```python
Odds Acquisition Collector

Collects odds data from multiple sportsbooks using browser sessions.
Normalizes and streams odds data for downstream processing.
```

#### 📄 `websocket_ingestor.py`
```python
WebSocket Ingestion Service - Production Grade

Handles live WebSocket connections to sportsbooks for real-time odds updates.
Implements automatic reconnection, stream health monitoring, and tick persistence.

Features:
- WebSocket frame interception and decoding
- Automatic reconnection with exponential backoff
- Stream staleness detection
- Market movement tracking
- Immutable odds tick storage
```

### 📁 Directory: `src\services\risk_engine`

#### 📄 `engine.py`
```python
Risk Management Engine

Implements professional risk management:
- Fractional Kelly sizing
- Bankroll state machine
- Exposure caps
- Correlated bet detection
- Drawdown protection
- Volatility adjustment
- Risk-of-ruin estimation
```

### 📁 Directory: `src\services\session_manager`

#### 📄 `browser_engine.py`
```python
Browser Engine for Session Management - Production Hardened

Handles browser automation for odds acquisition from various sportsbooks.
Manages browser instances, sessions, and headless browsing operations.

Production Features:
- Persistent Chromium profiles with state preservation
- Advanced stealth fingerprinting
- Automatic crash recovery
- Session restoration from persisted state
- Network interception for API discovery
- WebSocket monitoring
```

#### 📄 `service.py`
```python
Session Manager Service - Production Hardened

Coordinates browser sessions for odds acquisition across multiple sportsbooks.
Manages session lifecycle, authentication, rate limiting, and automatic recovery.

Production Features:
- Session health scoring and monitoring
- Automatic re-authentication on expiration
- Exponential backoff retry logic
- Circuit breaker pattern for failing sportsbooks
- Graceful degradation under load
- Comprehensive metrics and observability
```

### 📁 Directory: `src\services\shadow_execution`

#### 📄 `engine.py`
```python
Shadow Execution System

Paper betting system for simulating bet placement without real money.
Tracks bet lifecycle, line movement after prediction, and expected vs realized edge.
```

### 📁 Directory: `src\telemetry_warehouse`

#### 📄 `adversarial_pattern_miner.py`
```python
logger = logging.getLogger(__name__)
class AdversarialPatternMiner:
"""
Uses clustering, anomaly detection, and sequence mining to detect
bookmaker countermeasures from the telemetry warehouse.
...
```

#### 📄 `execution_ecology_engine.py`
```python
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
self_healer,
)
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)
...
```

#### 📄 `sportsbook_behavior_fingerprinter.py`
```python
# mypy: ignore-errors
logger = logging.getLogger(__name__)
class SportsbookBehaviorFingerprinter:
"""
Discovers hidden bookmaker behavior signatures from the Parquet data lake.
...
```

#### 📄 `telemetry_archiver.py`
```python
logger = logging.getLogger(__name__)
class TelemetryArchiver:
"""
Transitions DeepFieldPro into an institutional data-harvesting organism.
Dumps SQLite fast-memory into partitioned, compressed Parquet files for heavy ML mining.
...
```
