# DeepFieldPro — Project Context & Living Reference
# AI Agents: Read this file first. Summarises the entire system so you can
# start working without reading 100+ source files. Keep it updated on changes.

## 1. What This System Does

DeepFieldPro is a quantitative football betting research & live prediction platform.
- Scrapes live odds from Betarabia via Selenium (betarabia_scraper.py)
- Fetches fixtures via 3-tier fallback: API-Football -> ESPN free API -> Betarabia DB
- Generates AI predictions: 1X2, Over/Under, BTTS, Corners, Cards, Goalscorer
- Serves a live Flask dashboard on port 5050 with SSE streaming
- Logs predictions, bets, bankroll to SQLite DBs

## 2. Critical File Map

  src/live_predictions_daemon.py      <- Main daemon loop (start first)
  src/live_dashboard_server.py        <- Flask UI on port 5050
  src/api_football_client.py          <- 3-tier fixture fetcher (updated 2026-06-12)
  src/betarabia_scraper.py            <- Selenium Betarabia odds scraper
  src/betarabia_betting_engine.py     <- Personal virtual $500 system (updated 2026-06-12)
  src/execution_engine.py             <- Bet placement + Kelly sizing
  src/dfp_config.py                   <- Pydantic settings from .env
  src/templates/index.html            <- Full SPA dashboard UI
  models/*.pkl                        <- player_impact, bottom_up_match, lgbm_minutes, platt_scaler
  data/todays_dashboard_state.json    <- Live state written each daemon cycle
  data/odds_stream.db                 <- Betarabia odds: fixture + market tables
  data/bet_log.db                     <- predictions + bet_log tables
  data/bankroll.db                    <- bankroll table
  data/betarabia_bets.db              <- BetArabia virtual bets & bankroll (updated 2026-06-12)
  data/settings.json                  <- Runtime: EV threshold, confidence, kelly
  data/deepfield_browser_data/completed_fixtures.db  <- odds_history (peak sniper)
  .env                                <- API keys and env vars (gitignored)
  LAUNCH_DEEPFIELD.bat                <- Starts daemon + server
  PROJECT_CONTEXT.md                  <- This file

## 3. Start the System

  LAUNCH_DEEPFIELD.bat                        # recommended: starts both
  python src/live_predictions_daemon.py       # daemon only
  python src/live_dashboard_server.py         # Flask :5050 only
  Dashboard: http://localhost:5050

## 4. Fixture Fetch: 3-Tier Architecture (api_football_client.py)

  get_todays_fixtures_api() priority chain:

  TIER 1: API-Football v3
    Key: API_FOOTBALL_KEY in .env (free tier = 100 req/day)
    Detects rate-limit via errors.requests in JSON body (HTTP 200 but empty response)
    If rate-limited -> falls through to Tier 2 automatically

  TIER 2: ESPN public API (FREE, no key, no rate limit)
    URL: https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard
    Param: dates=YYYYMMDD for today and tomorrow
    Returns ~70 fixtures/day across major leagues
    Status map: STATUS_SCHEDULED->NS, STATUS_FINAL->FT, STATUS_IN_PROGRESS->1H

  TIER 3: Betarabia odds_stream.db (always merged in)
    ~86 fixtures today+tomorrow, scraped live by betarabia_scraper.py
    Smart status computed from elapsed_min since kickoff

  Result when API rate-limited: ~149 total fixtures (83 today + 54 tomorrow)

## 5. Database Schemas

  odds_stream.db:
    fixture: fixture_id, home_team, away_team, kickoff_time, kickoff_date,
             league_id, tournament_name, scraped_at
    IMPORTANT: Use tournament_name NOT league_name
    market: fixture_id, market_name, selection_name, raw_odds, scraped_at

  bet_log.db:
    predictions: fixture_id, match_name, league, kickoff, prediction, expected_score,
      home_prob, draw_prob, away_prob, over_prob, under_prob, btts_yes_prob,
      btts_no_prob, has_lineup, predicted_at, extra_json, model_version
    bet_log: bet_id, match_id, market_type, line, side, entry_odds, fair_odds,
      edge_pct, stake, placed_at, closing_odds, clv, result (W/L/OPEN)

  bankroll.db:
    bankroll: starting_balance, current_balance, peak_balance,
              daily_exposure, daily_pnl, system_status (ACTIVE/HALTED)

  completed_fixtures.db (data/deepfield_browser_data/):
    odds_history: fixture_id, market, selection, odds, recorded_at

## 6. Configuration

  .env (key values):
    API_FOOTBALL_KEY=4ae9f07e1ae1f775050015c50037a71d
    FLASK_PORT=5050 / FLASK_HOST=0.0.0.0
    WHATSAPP_PHONE=96171089646 / WHATSAPP_API_KEY=6478085

  data/settings.json:
    min_ev_threshold: 0.05  (5% minimum EV for recommendation)
    min_confidence_pct: 55  (minimum model probability %)
    kelly_fraction: 0.25    (quarter-Kelly stake sizing)
    max_daily_exposure: 500 (USD)

  dfp_config.py (Pydantic, from .env):
    MODEL_MIN_ODDS = 2.00
    MODEL_KELLY_FRACTION = 0.20
    MODEL_THRESHOLD_MIN_EDGE = 0.05

## 7. Daemon Cycle (each loop iteration, every 3 minutes)

  1. Start betarabia_scraper.py as background subprocess
  2. refresh_completed_comparisons() + settle_open_bets()
  3. get_todays_fixtures() via 3-tier fetch
  4. EARLY WRITE: update_dashboard_json(fixtures, []) pre-lineup
  5. Identify fixtures within 45 min of kickoff for lineup check
  6. Lineup fetch via get_fixture_lineups_batch_api() with 90s thread timeout
  7. predict_match() for each fixture
  8. FINAL WRITE: update_dashboard_json(fixtures, []) with predictions
  9. Sleep 180 seconds

## 8. Odds Injection Pipeline

  betarabia_scraper.py -> odds_stream.db
    -> find_betarabia_odds(home, away) in daemon (fuzzy name match)
    -> odds_dict injected into prediction[markets][type][sel][odds]
    -> EV = (prob/100) * odds - 1.0
    -> recommended = EV>=min_ev AND prob>=threshold AND odds>=MODEL_MIN_ODDS AND is_at_peak
    -> update_dashboard_json() -> todays_dashboard_state.json
    -> Flask /api/state -> UI renders

## 9. Recommendation Logic (bet gets recommended=True when ALL of:)

  1. ev >= min_ev_threshold (default 5%)
  2. prob >= conf_threshold (default 55%; drops to 30% if ev >= 15%)
  3. odds >= MODEL_MIN_ODDS (2.00)
  4. is_at_peak: current_odds >= 98% of max_seen_odds in odds_history
  Placement requires: has_lineup=True OR time_to_kickoff <= 10 min

## 10. Troubleshooting Matrix

  Dashboard shows ~13 matches         -> API-Football rate-limited. ESPN fallback fixed this 2026-06-12.
  API-Football HTTP 200 but 0 fixtures -> errors.requests rate-limit. ESPN Tier 2 auto-handles.
  Market odds show None/0             -> Check find_betarabia_odds() + update_dashboard_json()
  OperationalError: no column league_name -> Use tournament_name in odds_stream.db queries
  Daemon hangs on lineups             -> 90s threading timeout. Check if still hanging.
  Port conflict on 5050               -> netstat -ano | findstr 5050 -> kill PID
  todays_dashboard_state.json stale   -> Daemon not running. Start it.
  Recommended bets = 0                -> Lower min_ev_threshold in data/settings.json

## 11. Bug Fix History

  2026-06-11: sel[odds] only injected when has_lineup=True -> Fixed for ALL matches
  2026-06-11: fetch_betarabia_odds() (nonexistent) called -> Replaced with DB query
  2026-06-11: DB column league_name -> Fixed to tournament_name
  2026-06-11: DB fallback only today UTC -> Fixed to today + tomorrow window
  2026-06-11: Lineup fetch blocked indefinitely -> 90s threading timeout
  2026-06-11: Dashboard JSON only written after lineup fetch -> Early write added
  2026-06-12: API rate-limit not detected (HTTP 200 + errors.requests) -> Detection added
  2026-06-12: Date window was yesterday+today -> Fixed to today+tomorrow
  2026-06-12: ESPN free API added as Tier 2 fallback (get_fixtures_from_espn())

## 12. Live Status Detection

  elapsed_min = (now_utc - kickoff_utc).total_seconds() / 60.0
  > 95 min  -> FT
  > 45 min  -> 2H
  > 0 min   -> 1H
  otherwise -> NS

## 13. Free Fixture Sources (No API Key)

  ESPN: https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard
    - No auth. ~14 major leagues. dates=YYYYMMDD. ~70 fixtures/day.
  Betarabia DB: data/odds_stream.db (local, scraped live)
  football-data.org: https://api.football-data.org/v4/matches (free, key optional)

## 14. Stair AI Integration & World Cup Arena

  - **Production Base URL:** `https://stair-ai.com`
  - **API Key:** `zppYmElHFokPQMMhHarWOygViHWDBduLPAuvTXcvCUFlbrdgkQhqnLlefmLzNisn` (DeepFieldPro AI wallet)
  - **Betting Platform:** Polymarket YES tokens. Implied probabilities are fetched via `/api/v1/data/proxy/polymarket-clob/midpoint` for home, draw, and away outcomes.
  - **Order Sizing:** kelly criterion based on the agent's available USDC wallet balance, rounded up to a minimum of **$1.00 USD** (Polymarket requirement).
  - **Execution Flow:**
    1. Discovers mappings at `/api/v1/web/mapping`
    2. Fetches midpoints, Sportmonks pre-match detail, and Supabase country style priors
    3. Evaluates edge: bets on any positive edge, falling back to a minimum $1.00 bet on the highest relative edge outcome to guarantee prize qualification
    4. Places order at `/api/v1/arena/orders`
    5. Submits 14-record Reasoning-Ledger trace (Trigger, Thinking, ToolCalling, Acting, Strategy) to `/api/v1/arena/ledger/records/batch`
  - **Single Page UI Consolidation:**
    - Sidebar menu item for Stair AI has been removed.
    - Wallet available/locked balances are displayed in the main KPI grid on the **Bankroll & ROI** tab.
    - Stair AI bets are rendered in a nested tab ("Stair AI Bets") directly next to "Local Bets" inside the **Active Execution Ledger** card on the **Bet Tracker** tab.
    - Direct visits to `/stair` render the Bet Tracker and automatically open the Stair AI tab.

## 15. WhatsApp CallMeBot Alerting

  - **API Key:** `6478085`
  - **Phone:** `96171089646`
  - **Alert Types:**
    1. **Daily Performance Audit:** Sent every night at 23:55 by the daemon via `src/services/daily_audit.py` to deliver a summary report of the past 24 hours.
    2. **Massive Edge Alert (+100% EV):** Instantly sent to WhatsApp when a recommended AI bet from Betarabia is discovered with `ev >= 1.0` (100% EV or higher) to alert the user of a massive mispriced line.


## 16. BetArabia Virtual Betting System

  - **File:** `src/betarabia_betting_engine.py`
  - **Database:** `data/betarabia_bets.db`
  - **Virtual Bankroll:** Starting balance $500.00 USD.
  - **Rules:**
    1. Only bet if odds >= 1.40
    2. Only bet if EV >= 5%
    3. Max stake sizing: Quarter-Kelly, up to 5% of bankroll per bet
    4. Max 10 simultaneous open bets
  - **Execution Flow:**
    1. Daemon runs `run_betarabia_engine()` every cycle.
    2. Reads scraped odds from `odds_stream.db`.
    3. Finds match predictions in `bet_log.db` and calculates edge/EV.
    4. Sizes and logs the virtual bet to `betarabia_bets`.
    5. Settle bets automatically after match finishes (uses API-Football and ESPN scorers to check results).
  - **Dashboard Integration:**
    - Sidebar menu item "BetArabia System".
    - Dedicated view page (`betarabia-view`) showing Bankroll & ROI stats, a rolling bankroll growth chart, a detailed list of all-time virtual bets, and manual "Run AI Engine" and "Check & Settle" trigger buttons.

---
Last updated: 2026-06-12 by Antigravity agent (Antigravity pairs with Elie).
Update this file whenever you make significant changes.