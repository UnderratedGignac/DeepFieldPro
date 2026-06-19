# DeepFieldPro — Project Description

**Last updated:** 2026-06-19  
**Status:** Active research platform — paper/shadow betting only

---

## What It Is

DeepFieldPro is a personal football (soccer) betting research and operations platform. It automatically scrapes live odds, runs machine-learning models to generate match probabilities, compares those probabilities to market prices to detect edge, and surfaces everything on a local web dashboard. Betting execution is **paper/shadow only** — no real money is ever staked without an explicit environment-variable gate that is kept unset.

The project covers the full pipeline from raw odds ingestion to model training to live prediction to bet settlement, and includes a large archive of experimental code (agents, portfolio optimisation, lineup prediction, etc.) built during the research phase.

---

## Architecture at a Glance

```
Betarabia/Kickertech ──► betarabia_scraper.py ──► odds_stream.db
                                                         │
                                                    daemon (loop)
                                                         │
                              ┌──────────────────────────┤
                              │   fetch fixtures          │   settle bets
                              ▼                          ▼
                         Dixon-Coles model          ESPN / Flashscore
                         + 1X2 calibration          API-Football
                         + STEAM detector           Sofascore (Playwright)
                              │
                              ▼
                   todays_dashboard_state.json
                              │
                    Flask live_dashboard_server.py
                              │
                    Browser ◄── /api/state  /api/stream (SSE)
                                /api/tracker  /api/settled_ledger
```

---

## Entry Points

| File | Purpose |
|------|---------|
| `src/live_dashboard_server.py` | Main Flask app. Starts the prediction daemon as a background thread. Dashboard at `http://127.0.0.1:5050`. |
| `src/live_predictions_daemon.py` | The prediction engine. Loops: scrape odds → fetch fixtures → predict → write state → settle bets. |
| `src/betarabia_scraper.py` | Background Playwright subprocess. Scrapes Betarabia/Kickertech odds into `data/odds_stream.db`. |
| `src/arena_betting.py` | Flask blueprint for the World Cup Arena (`/arena`). Stair AI + Polymarket integration. |
| `START_ALL.bat` | Windows launcher. Starts everything in one click. |

---

## How to Run

```powershell
# Dashboard + daemon (main way)
$env:DEEPFIELD_PORT="5051"        # optional, defaults to 5050
.venv\Scripts\python.exe src\live_dashboard_server.py

# UI only (no scraping, no bets)
$env:DEEPFIELD_DISABLE_DAEMON=1
.venv\Scripts\python.exe src\live_dashboard_server.py

# Daemon only
.venv\Scripts\python.exe src\live_predictions_daemon.py
```

Python interpreter: `.venv\Scripts\python.exe` (Python 3.12). Never use bare `python` — only the Windows Store stub is on PATH.

---

## Data Flow (Match → Dashboard)

1. **Scraping**: `betarabia_scraper.py` (Playwright headless Chromium) scrapes the Betarabia odds page every few minutes and writes rows to `data/odds_stream.db` — tables `fixture` (match metadata) and `market` (odds per selection).

2. **Fixture fetch**: The daemon calls Sofascore first; on 403/empty it falls back to `fetch_betarabia_odds()`, which reads `odds_stream.db` and returns `{home_vs_away: {kickoff, league, status}}`.

3. **Prediction**: `predict_match(home, away, league)` calls `_dc_expected_goals()` → Dixon-Coles model → Poisson convolution → raw 1X2 probabilities → Platt calibration → blended with de-vigged market via `market_blend_weight`. O/U 2.5 follows the same expected-goals estimate with its own calibrator.

4. **STEAM detection**: `_steam_moves(fixture_id, market_type)` compares the earliest vs latest logged price snapshot per selection. When the probability shift ≥ `steam_min_move_pct` (5%), it fires `log_steam_bet()` — a flat-$25 paper bet, deduped per fixture/market/selection.

5. **State write**: The daemon writes `data/todays_dashboard_state.json` — a JSON array the UI reads via `GET /api/state`. Live updates stream via `GET /api/stream` (Server-Sent Events).

6. **Settlement**: `settle_open_bets()` resolves open bets using a four-source waterfall:
   - **ESPN** (primary, keyless)
   - **Flashscore** (Playwright, second)
   - **API-Football** (bonus when daily quota allows)
   - **Sofascore** (Playwright page intercept, new)

---

## Databases

| File | Tables | Purpose |
|------|--------|---------|
| `data/odds_stream.db` | `fixture`, `market`, `odds_history` | Live scraped odds. `odds_history` logs every price snapshot for STEAM detection. |
| `data/bet_log.db` | `bet_log`, `predictions`, `steam_signals` | All paper bets, model predictions, raw STEAM signal ledger. |
| `data/bankroll.db` | `bankroll` | Paper bankroll balance history. Currently: **$127.13**. |
| `data/history.db` | `matches`, `odds` | 13,960 historical matches + closing odds (football-data.co.uk). Used for model training and backtesting. |
| `data/deepfield_browser_data/completed_fixtures.db` | `completed_fixtures`, `steam_signals` | Settlement results cache. STEAM signal dedup store. |
| `data/arena_ledger.db` | `orders` | World Cup Arena order history (Stair AI). |
| `data/corner_history.db` | `corners` | Historical corner data (research, not in active use). |
| `data/xg_history.db` | `xg` | Historical xG data from Understat (research). |
| `data/sync_state.db` | `sync_state` | Scraper sync checkpoints. |

---

## Machine Learning Models

### Active in the prediction loop

| Model | File | Description |
|-------|------|-------------|
| **Dixon-Coles** | `models/dixon_coles.json` | Team attack/defence strength ratings + home advantage + rho correlation per league. Trained on 13,960 matches. Powers all 1X2 and O/U 2.5 predictions. |
| **1X2 Calibrator** | `models/calibrator_1x2.json` | Platt scaling (logistic) fit on 22,878 DC predictions vs real outcomes (walk-forward). Converts raw DC probabilities to well-calibrated output. Currently near-identity — DC is already well calibrated. |
| **O/U 2.5 Calibrator** | `models/calibrator_ou25.json` | Platt scaling for over/under 2.5 predictions. Display-only — O/U betting is off the whitelist. |

### Player/prop models (research / not in active staking)

| Model | File | What it predicts |
|-------|------|-----------------|
| LightGBM 1X2 | `lgbm_1x2.pkl` | Match outcome (4.6 MB) |
| LightGBM Goals | `lgbm_goals.pkl` | Team goals scored |
| LightGBM Shots | `lgbm_shots.pkl` | Shots total |
| LightGBM Shots on Target | `lgbm_shots_on_target.pkl` | Shots on target |
| LightGBM Assists | `lgbm_assists.pkl` | Assists |
| LightGBM Minutes | `lgbm_minutes.pkl` | Player minutes played |
| LightGBM Yellow Cards | `lgbm_yellow_cards.pkl` | Yellow cards |
| LightGBM Player Goal | `player_goal_lgbm.pkl` | Individual player goal scorer |
| Bottom-up Match Model | `bottom_up_match_model.pkl` | Ensemble match outcome |
| Player Impact | `player_impact_model.pkl` | Player impact score |
| Lineup Model | `lineup_model.txt` | Starting lineup prediction |
| Minutes P10/P50/P90 | `minutes_p*.txt` | Quantile regression for player minutes |
| SOT P10/P50/P90 | `sot_p*.txt` | Quantile regression for shots on target |

---

## Active Betting Strategies

### STEAM (`bet_source = 'STEAM'`) — the only strategy placing stakes

Fires when Betarabia's 1X2 line moves ≥5% in probability toward a side (comparing earliest vs latest logged price snapshot). Validated in backtesting on 2,386 held-out matches:

| Move threshold | ROI | Hit rate |
|----------------|-----|---------|
| ≥1% | +0.7% | — |
| ≥2% | +3.5% | — |
| ≥3% | +8.8% | — |
| **≥5%** | **+20.9%** | **55%** |

**Live paper record (as of 2026-06-19):** 34 settled bets, net P&L **−$19.95** (still early — backtested edge needs hundreds of bets to manifest).

Settings: `steam_flat_stake: $25`, `steam_min_move_pct: 5.0%`, `require_steam_confirm: true`.

### AI Model (`bet_source = 'AI'`) — zero-stake tracking only

The daemon generates 1X2 predictions via Dixon-Coles for every match and logs them as `stake=0` tracking bets. Not staking real (paper) money because the 2,386-bet out-of-sample CLV test showed no genuine edge vs closing line (−4.3% to −6.9% ROI at all selectivity thresholds).

---

## Removed Strategies (see `docs/removed_features.md`)

| Strategy | Bets | ROI | Why removed |
|----------|------|-----|-------------|
| SHARP | 5 | −41.2% | Betarabia "lag" was thin-market noise, not real delay |
| SHARPV | 13 | −54.3% | Same root cause; chased underdogs with no real edge |
| Prop markets (Corners, Cards, Goalscorer, Shots, O/U, BTTS) | 429 | −57.8% | No player/event-level signal; hash-settle noise |

---

## World Cup Arena (`/arena`)

A separate Flask blueprint at `/arena` that connects to **Stair AI** (`https://stair-ai.com`) for World Cup 2026 value-betting. It:
- Fetches Stair AI's 1X2 Sportmonks model probability
- Fetches the live Polymarket midpoint for the same outcome
- Bets when `model_prob ≥ conf_min` AND `model_prob − mid ≥ edge_min`
- Uses real money via `/arena/api/place` with `{"confirm": true}`

**Hard gate**: `arena_betting.place_order()` refuses unless `DEEPFIELD_ARENA_LIVE=1`. This env var is kept **unset**. Wallet balance ~$53 is untouched.

---

## External APIs & Data Sources

| Source | Used for | Auth |
|--------|---------|------|
| Betarabia / Kickertech | Live odds scraping | Playwright (no key) |
| Stair AI (`stair-ai.com`) | World Cup Arena predictions + Polymarket mapping | `STAIR_AI_API_KEY` in `.env` |
| Polymarket CLOB | Live prediction market midpoints | Via Stair AI proxy |
| ESPN | Match results for settlement | Keyless |
| Sofascore | Match results fallback (Playwright bypass) + fixture fallback | Playwright (no key) |
| Flashscore | Match results fallback | Playwright (no key) |
| API-Football | Bonus settlement when daily quota allows | `API_FOOTBALL_KEY` in `.env` |
| football-data.co.uk | Historical match + odds data for training | CSV download |
| WhatsApp | Optional bet alerts | `WHATSAPP_*` keys in `.env` |

---

## Configuration

### `.env` (not committed)
Key variables:
- `STAIR_AI_API_KEY` — Stair AI authentication
- `API_FOOTBALL_KEY` — API-Football quota key
- `DEEPFIELD_PORT` — dashboard port (default 5050)
- `DEEPFIELD_DISABLE_DAEMON=1` — UI-only mode
- `DEEPFIELD_ARENA_LIVE=1` — **DO NOT SET** — enables real Arena orders
- `DEEPFIELD_DAEMON_LIVE_ORDERS=1` — **DO NOT SET** — enables daemon live orders

### `data/settings.json` (runtime, UI-editable)
```json
{
  "allowed_markets": ["1X2"],
  "exclude_draws": true,
  "steam_betting_enabled": true,
  "steam_flat_stake": 25.0,
  "steam_min_move_pct": 5.0,
  "kelly_multiplier": 0.2,
  "min_ev_threshold": 0.08,
  "min_confidence_pct": 60,
  "require_steam_confirm": true,
  "edge_cap_pct": 10.0,
  "market_blend_weight": 0.5
}
```

---

## Dashboard API Endpoints

| Endpoint | Method | Returns |
|----------|--------|---------|
| `/api/state` | GET | Today's match predictions array |
| `/api/stream` | GET | SSE stream of live state updates |
| `/api/tracker` | GET | Last 50 bets with kickoff timing |
| `/api/settled_ledger` | GET | All bets grouped by day with P&L |
| `/api/bankroll` | GET | Current paper bankroll balance |
| `/api/settings` | GET/POST | Read/write `settings.json` |
| `/arena/api/analyze` | GET | Arena opportunities (read-only) |
| `/arena/api/place` | POST | Place Arena order (gated) |

---

## Analytics Tools (`tools/`)

| Tool | What it does |
|------|-------------|
| `backtest.py` | Replay historical bets with configurable rules + staking |
| `backtest_1x2_model.py` | Walk-forward out-of-sample 1X2 model test (bets the EARLY line) |
| `backtest_1x2_lines.py` | CLV analysis: early vs close vs best-soft price on model picks |
| `backtest_market_signals.py` | Steam / soft-outlier / line-movement signal validation |
| `backtest_ou_model.py` | O/U 2.5 walk-forward validation (verdict: do not bet) |
| `train_dixon_coles.py` | Fits Dixon-Coles ratings from `history.db` |
| `train_1x2_calibrator.py` | Fits Platt scaler on DC predictions |
| `train_ou_calibrator.py` | Fits Platt scaler for O/U display |
| `steam_report.py` | STEAM signal ledger ROI + staked bet P&L |
| `clv_report.py` | Closing-line value analysis per bet |
| `league_report.py` | P&L breakdown by league |
| `settlement_audit.py` | Verify settled bets matched to real scores |
| `strategy_pnl.py` | P&L summary grouped by bet_source |
| `reset_paper_bankroll.py` | Restore paper bankroll (paper only) |
| `ingest_history.py` | Download + parse football-data.co.uk CSV into `history.db` |
| `nightly_dc_refit.py` | Nightly Dixon-Coles model refit |
| `steam_health.py` | STEAM signal pipeline diagnostics |
| `preflight_check.py` | System health check before launch |
| `void_stuck_bets.py` | Void bets that can never be settled (obscure leagues) |

---

## Safety Rules

1. **`SHADOW_MODE = True`** in `dfp_config.py` — `place_bet()` always goes to the SHADOW branch, which writes mock bets to DB only. The LIVE branch is an unimplemented placeholder.
2. **`DEEPFIELD_ARENA_LIVE`** must be **unset** — Arena `place_order()` hard-checks for this env var. Without it, no order is ever sent.
3. **`DEEPFIELD_DAEMON_LIVE_ORDERS`** must be **unset** — the daemon only writes `SHADOW_*` order IDs unless this is set.
4. **Betfair credentials** in `.env` are placeholder strings (`your_username`) — Betfair is not configured.
5. **Only 1X2 Home/Away** bets fire (draws excluded). All prop markets are blocked by `allowed_markets: ["1X2"]` in `settings.json`.

---

## Current Snapshot (2026-06-19)

| Metric | Value |
|--------|-------|
| Paper bankroll | $127.13 |
| Total bets in log | 166 |
| Open bets | 2 |
| STEAM bets settled | 34 |
| AI tracking bets | 124 |
| Fixtures scraped (lifetime) | 95 |
| Historical matches (training) | 13,960 |
| Models in `models/` | 50+ files |
| Active betting strategy | STEAM only |
| Real money at risk | $0 |
