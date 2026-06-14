# DeepFieldPro — Project Guide

Football (soccer) betting research & operations platform. It scrapes fixtures + odds,
runs ML models to produce probabilities, compares them to market prices, and surfaces
recommendations on a local web dashboard. **Local/research use. Betting execution is
SHADOW (paper) only — see Safety.**

## Environment / how to run

- **Python**: 3.12 in a project venv (the system only has the Windows Store stub).
  - Interpreter: `.venv\Scripts\python.exe`
  - Recreate: `C:\Users\Anthony\AppData\Local\Programs\Python\Python312\python.exe -m venv .venv`
    then `.venv\Scripts\python.exe -m pip install -r requirements.txt`
  - Extra dep NOT in requirements.txt but required by the daemon: **`pydantic-settings`**.
- **Run the dashboard + prediction daemon** (main way):
  ```powershell
  $env:DEEPFIELD_PORT="5051"   # optional; defaults to 5050
  .venv\Scripts\python.exe src\live_dashboard_server.py
  ```
  Dashboard → `http://127.0.0.1:<port>`. The daemon runs as a background thread.
- **UI only (no scraping/predictions/betting)**: set `DEEPFIELD_DISABLE_DAEMON=1` before launching.
- **Daemon only**: `.venv\Scripts\python.exe src\live_predictions_daemon.py`
- Windows launchers exist too: `RUN_SYSTEM.bat`, `LAUNCH_DEEPFIELD.bat`, `START_AUTO_PREDICTOR.bat`.

## Entry points & key modules (in `src/`)

- `live_dashboard_server.py` — Flask app. Serves the UI + `/api/*`. `if __name__=="__main__"`
  starts the daemon thread unless `DEEPFIELD_DISABLE_DAEMON=1`. Port reads `DEEPFIELD_PORT`
  (default 5050). `app.run(host="0.0.0.0", ...)`.
- `live_predictions_daemon.py` — the engine. `run_daemon()` loops: scrape odds → fetch
  fixtures → predict → write dashboard state → settle bets. Contains `fetch_betarabia_odds()`,
  `find_betarabia_odds()`, the STAIR-AI integration, and the `place_bet()` call site.
- `free_scraper_module.py` — Sofascore fixture fetch + the Betarabia fixture fallback builders.
- `betarabia_scraper.py` — background subprocess (launched via `subprocess.Popen`) that scrapes
  Betarabia/Kickertech odds into `data/odds_stream.db`.
- `execution_engine.py` — `place_bet()`; SHADOW vs LIVE branch (LIVE is an unimplemented placeholder).
- `dfp_config.py` — settings incl. `SHADOW_MODE` (default **True**) and `STAIR_AI_API_KEY`.
- `api/main.py`, `orchestrator.py` — newer service-oriented stack (FastAPI/uvicorn), separate path.
- `arena_betting.py` — Stair AI **World-Cup Arena** value-betting page (Flask blueprint, registered in
  `live_dashboard_server.py`). Standalone at `/arena` and embedded in the dashboard as the
  "World Cup Arena" sidebar tab (iframe in `index.html`'s `arena-view`). Compares the Sportmonks 1X2
  model probability to the live Polymarket midpoint and bets only when `model_prob >= conf` AND
  `model_prob - mid >= edge`. World-Cup-only (season `26618`) and only BEFORE kickoff (upcoming
  fixtures filter + a placement-time `kickoff_ts > now` re-check).
  Production API base `https://stair-ai.com`, auth header `x-api-key` (`STAIR_AI_API_KEY` in `.env`),
  season `26618`. **REAL MONEY**: `/arena/api/analyze` is read-only; `/arena/api/place` only acts on a
  POST with `{"confirm": true}`, capped at $5/order, a wallet buffer, and `MAX_BETS_PER_RUN`. Endpoints:
  schedule/fixture proxies, `/api/v1/web/mapping` (→ per-outcome Polymarket YES tokens),
  `/api/v1/data/proxy/polymarket-clob/midpoint`, `/api/v1/arena/orders`, `/api/v1/arena/ledger/records/batch`.

## Data flow (how matches reach the dashboard)

1. `betarabia_scraper.py` (background subprocess) writes fixtures + markets into
   `data/odds_stream.db` (tables: `fixture`, `market`).
2. The daemon calls `get_todays_fixtures()` → Sofascore. **Sofascore frequently returns empty.**
3. On empty, it falls back to `fetch_betarabia_odds()`, which reads `data/odds_stream.db`
   `fixture` rows and returns a dict keyed by `"Home vs Away"`, each value carrying
   `{kickoff, league, status}`. The fallback builders turn those into fixture dicts.
4. The daemon runs models, then writes **`data/todays_dashboard_state.json`** (the array the UI shows).
5. UI reads it via `GET /api/state`; live updates stream via `GET /api/stream` (SSE).

So: **empty dashboard ⇒ the daemon isn't running or the state file is `[]`.** The UI alone never
populates matches.

## Databases & data (in `data/`)

- `odds_stream.db` — scraped fixtures/markets (`fixture`: fixture_id, home_team, away_team,
  kickoff_time, kickoff_date, league_id, tournament_name, scraped_at; plus `market`).
- `bet_log.db` — bets, parlays, ledger, settlement.
- `bankroll.db` — bankroll history.
- `todays_dashboard_state.json` — current dashboard match/prediction state (UI source of truth).
- `settings.json` — runtime UI settings (kelly, EV/confidence thresholds, `auto_place_bets`, etc.).

## Config

- `.env` (loaded via python-dotenv / pydantic-settings). Keys: `API_FOOTBALL_KEY`,
  `STAIR_AI_API_KEY`, `WHATSAPP_*`, `DEEPFIELD_*` risk params, `BROWSER_*`, etc.
  NOTE: `BETFAIR_*` values are placeholders (`your_username`), i.e. Betfair is not configured.
- ML models/artifacts live in `models/`.

## Safety (important)

- **No real-money betting.** `place_bet()` runs the **SHADOW_MODE** branch (default `True` in
  `dfp_config.py`) → records mock "SHADOW" bets to DB only. The LIVE branch is an unimplemented
  placeholder ("Real capital execution not yet fully linked"). `auto_place_bets` in settings.json
  does NOT actually gate placement.
- The daemon DOES make external calls when running: STAIR-AI order POSTs (to `staging.stair-ai.com`),
  optional WhatsApp alerts, and live web scraping (Playwright/Chromium). Keep this in mind before running.

## Known issues / gotchas

- **Missing dep**: `pydantic-settings` is required by the daemon — now pinned in `requirements.txt`.
- **Sofascore returns empty** (its API is 403 bot-blocked) → fixtures fall back to Betarabia,
  and settlement no longer uses it.
- **Settlement results source**: `free_results_scraper.py` (`get_finished_results()`) provides free,
  key-less finished scores from **ESPN** (broad league coverage incl. minor leagues) + **TheSportsDB**
  fallback, cached per-date. `settle_open_bets()` uses it as the primary feed (API-Football is only a
  bonus when its daily quota allows). This is what makes win/loss settlement actually work.
- **`fetch_betarabia_odds()` was originally undefined** (called by `free_scraper_module.py` and the
  daemon). It is now implemented in `live_predictions_daemon.py` and returns kickoff/league/status
  from `odds_stream.db`. The fallback builders (daemon + `free_scraper_module.py`) use that metadata —
  do NOT revert them to stamping `now()` / `"NS"` / `"Betarabia"` (that caused the "all kickoffs show
  the scrape time" glitch).
- **STAIR-AI**: FIXED. The daemon + dashboard now talk to **production `https://stair-ai.com`**
  (the old hardcoded `staging.stair-ai.com` was dead). The key is resolved resiliently
  (`_stair_api_key()`: env → read `.env`), because `.env` is NOT loaded into `os.environ` at
  daemon-thread startup — so `os.getenv` alone returned empty and auth 401'd. Agent init now
  logs "Agent profile updated successfully."
- **Daemon real-money gate (IMPORTANT)**: the paper daemon bets across ALL markets, most of which
  are heavily -EV in the realized record (Goalscorer −80%, Player Shots −62%, O/U −70%, BTTS −59%).
  Its arena order-POST is therefore **gated OFF** — it only writes `SHADOW_*` order ids unless
  `DEEPFIELD_DAEMON_LIVE_ORDERS=1` (do NOT set this). Real money flows ONLY through the disciplined
  1X2-only `arena_betting.py` path (caps + `confirm:true` + paused-by-default autopilot).
- **scikit-learn version**: RESOLVED — `requirements.txt` now pins `scikit-learn==1.8.0` (matches the
  calibrators) and the two legacy 1.6.1 tree models were re-pickled under 1.8.0 (`*.sk161.bak` backups
  kept in `models/`). All 15 artifacts now load with zero `InconsistentVersionWarning`. The daemon's
  `joblib.load` calls are wrapped in try/except so a bad unpickle degrades instead of crashing startup.
- **Orphaned port on restart**: if the dashboard tab keeps an SSE (`/api/stream`) connection open,
  the listening socket on the old port can linger after the process dies. Easiest workaround: launch
  on a fresh port via `DEEPFIELD_PORT`.

## Profitability upgrade (2026-06-14) — `tools/`

Edge analysis showed only **1X2 is +EV** (+151%); all prop markets lose, and ~57% of the old
record was **hash-settled noise** (props fall back to `hash(bet_id)` when stats are missing — 1X2
is settled from real scores). Changes made:

- **Market whitelist + draw exclusion** (`settings.json`: `allowed_markets:["1X2"]`, `exclude_draws:true`,
  `league_blocklist:[]`). The daemon's `is_recommended` gate now enforces these. Props are off.
- **1X2 calibration**: `models/calibrator_1x2.json` (Platt), trained by `tools/train_1x2_calibrator.py`,
  auto-applied in `predict_match` via `_calibrate_1x2()` — fixes favourite-overconfidence (raw 66%→cal 38%).
- **Real CLV**: `bet_log` gained `fixture_id`+`league` (migration `tools/migrate_bet_log.py`); `log_ai_bet`
  records them; settlement computes `clv = entry/closing-1` from `odds_history`. Historical bets have no
  link so CLV fills going forward.
- **Tools** (all read-only analytics unless noted): `backtest.py` (replay rules + staking),
  `train_1x2_calibrator.py`, `clv_report.py`, `league_report.py`, `settlement_audit.py`,
  `migrate_bet_log.py`, `reset_paper_bankroll.py` (paper-only bankroll restore).
- **Paper bankroll gotcha**: `bankroll.db` `current_balance` is liquid cash; when it hits $0 (all staked in
  open bets) the daemon silently places nothing. `tools/reset_paper_bankroll.py` restores it (PAPER ONLY).
- Staking is already fractional-Kelly in `log_ai_bet` (`kelly_multiplier`, `max_exposure_pct`).
- Real money (Arena) remains paused/gated; none of this arms it.

## Advanced model upgrade (2026-06-14) — Dixon-Coles + safety

- **1X2 model replaced.** The old core set hardcoded expected goals by a 3-way bucket
  (`exp_h=2.1/0.8/1.2`...). Now `predict_match` calls `_dc_expected_goals(home,away,league)` →
  **Dixon-Coles** continuous team-strength ratings (`models/dixon_coles.json`, per-league att/def +
  home_adv + rho), with team-name normalization + fuzzy match and **fallback to the heuristic** for
  unknown leagues/teams (e.g. World Cup internationals). O/U 2.5 + BTTS ride the same expected goals.
- **Data foundation**: `data/history.db` — 13k matches + closing odds from football-data.co.uk
  (`tools/ingest_history.py`). Train model: `tools/train_dixon_coles.py`.
- **Validated**: `tools/backtest_1x2_model.py` (out-of-sample on held-out season) — DC beats the
  heuristic (log-loss 1.001 vs 1.059) and approaches the market (0.968). Nobody beats Pinnacle's
  CLOSE (both ~-6.5% into it); the edge is in softer/earlier books.
- **Calibrator** now fit on **22,878** DC predictions vs real outcomes (`tools/train_1x2_calibrator.py`,
  walk-forward) — DC is already near-perfectly calibrated, so it's ~identity (vs the old 53-bet fit).
- **Market blending**: `settings.market_blend_weight` (default 0.5) shades model prob toward the
  de-vigged market in the daemon EV path — lower variance, fewer model-error bets.
- **Real-money HARD GATE (critical)**: `arena_betting.place_order()` refuses unless
  `DEEPFIELD_ARENA_LIVE=1`; `autopilot_cycle` is paused unless that env AND `enabled` are both set.
  Fail-safe defaults flipped from True→False. Multiple orphaned daemons had been re-enabling the
  state file; the env gate makes real bets impossible regardless of flag/zombie/frontend. Keep
  `DEEPFIELD_ARENA_LIVE` UNSET. Wallet ~$53 untouched.
- **Ops gotcha**: orphaned python can leave zombie LISTENING sockets; the bat now auto-scans
  5052-5058 for a free port. Always `taskkill /IM python.exe /F` before relaunch.

## Over/Under 2.5 validation (2026-06-14) — VALIDATED, stays OFF the betting whitelist

The next planned step ("ingest O/U closing odds + validate the DC-derived O/U before
enabling it") is done. Verdict: **do NOT bet O/U** — kept off `allowed_markets`.

- **Data**: `tools/ingest_history.py` now also captures O/U 2.5 **closing** odds into
  `data/history.db` (`odds_o25`, `odds_u25`; Pinnacle-Closing `PC>2.5`/`PC<2.5` preferred,
  then B365C/AvgC/MaxC, then non-closing). All 13,960 matches have O/U closing odds.
- **Validation** (`tools/backtest_ou_model.py`, walk-forward, test season held out):
  the DC O/U has real discriminative signal but **loses into the close** — log-loss
  worse than market (raw 0.691 / calibrated 0.681 vs market **0.670**) and betting into
  the closing line is **−2.1% (raw) / −3.1% (calibrated)** ROI over ~2.1–2.4k bets. The
  market simply prices totals better than a team-strength model. So O/U is NOT +EV.
- **Bias found + fixed for DISPLAY only**: raw DC under-estimates total goals (~2.56 vs
  2.76 actual) → under-calls "over" (predicts 46.5%, actual 52.4%). `tools/train_ou_calibrator.py`
  → `models/calibrator_ou25.json` (Platt, n=8350) removes the bias; the daemon applies it
  via `_calibrate_over25()` so the dashboard's O/U numbers are honest. **This does NOT enable
  betting** — `allowed_markets` stays `["1X2"]`; calibration is display-only and Under is
  derived as `100 − Over` to stay complementary.
- Tools added: `tools/backtest_ou_model.py`, `tools/train_ou_calibrator.py`.

## 1X2 line/CLV analysis (2026-06-14) — the model does NOT beat the market

Tested the project's core hypothesis ("edge is in softer/earlier books") properly for the
first time. KEY DATA FIX: football-data's `PSH/PSD/PSA` are the **early** Pinnacle odds, not
closing — the old `backtest_1x2_model.py` bet the early line but *labelled* it the close.
`ingest_history.py` now stores early (`odds_h/d/a`), **closing** (`odds_ch/cd/ca`, Pinnacle
preferred), and **best-early-across-books** (`odds_maxh/d/a`) so CLV is computable.

`tools/backtest_1x2_lines.py` (walk-forward, held-out season, ~2,386 qualifying picks) settles
the SAME model picks at three prices and measures CLV (= price_taken/closing_price − 1):

| price taken | ROI | avg CLV | beats close |
|---|---|---|---|
| Pinnacle close | −5.5% | 0 | — |
| Pinnacle early | −6.9% | −1.3% | 45% |
| **best soft early** | **−4.3%** | **+1.9%** | **57%** |

- **Selectivity sweep is the verdict**: raising the edge bar makes ROI *worse* (−3.4% @2% →
  −19.7% @20%) and CLV *shrink*. A real edge improves with selectivity; this degrades — so the
  model's biggest disagreements with the market are where it's most WRONG, i.e. **no genuine
  1X2 edge**. (Blending model↔market only rescales the edge threshold, so it can't fix this —
  the whole threshold range is already -EV in the sweep.)
- The earlier "**1X2 is +EV +151%**" came from 53 paper bets w/ hash-settled noise; this 2,386-bet
  out-of-sample test at realistic prices supersedes it. DC is well-calibrated and more *accurate*
  than the old heuristic, but accuracy ≠ a betting edge.
- The ONLY positive signal is **line-shopping** (take the best price across books): +1.9% CLV,
  beats the close 57%. Real but too small to make -EV picks profitable on its own.
- **Implication**: real money stays OFF (already hard-gated). If the system ever bets, it must
  (a) take the best available price, not Pinnacle, and (b) not chase the model's high-conviction
  disagreements. Accumulate clean shadow data; treat 1X2 as not-yet-profitable, not proven +EV.
- Tools: `tools/backtest_1x2_lines.py` (new); `backtest_1x2_model.py` relabelled (it bets the
  EARLY line, not the close).

## Market-structure signals + conviction cap (2026-06-14)

Two changes following the "model has no 1X2 edge" finding above.

**(a) Market signals tested** (`tools/backtest_market_signals.py`, held-out season, no model):
- **STEAM (line movement) WORKS and is the strongest lead found.** Betting the side the
  market moved toward (early→close), at the EARLY price: ROI rises monotonically with move
  size — +0.7% (≥1% move) → +3.5% (≥2%) → +8.8% (≥3%) → **+20.9% (≥5%, 55% hit, beats the
  close)**. This is the OPPOSITE of the model (where more conviction = worse), confirming line
  movement carries real signal. CAVEAT: as written it peeks at the close (diagnostic ceiling,
  not directly tradable). A live version is buildable from the `odds_history` table the daemon
  already logs (earliest vs latest pre-kickoff price per selection) — **now built (see below).**
- **Soft-outlier value-hunting does NOT work** (−6%→−12%, worse with bigger "value"): chasing
  generous soft prices just selects losing longshots. Line-shopping only helps as "best price
  on a pick you'd make anyway," not as a standalone signal.
- Lineup/team-news signals can't be backtested here (no lineups in football-data history); they
  need a live feed.

**(b) Conviction cap wired into the daemon.** `is_recommended` now also requires `conviction_ok`:
skip bets where the blended model prob exceeds the de-vigged market prob by more than
`settings.edge_cap_pct` (default **10**). Directly implements the line/CLV finding (the model's
biggest disagreements are model error). `market_blend_weight` (0.5) means a 10% blended cap ≈ 20%
raw-model cap — it trims only the worst-performing high-conviction tail. Real money stays gated off.

## Real-time STEAM detector (2026-06-14) — live, in the daemon

Turns the validated line-movement edge into a live signal. The daemon already logs every
scraped price into `odds_history` (fixture_id, market, selection, odds, timestamp).

- **Detector** (`live_predictions_daemon._steam_moves(fid, m_type)`): de-vigs the EARLIEST vs
  LATEST logged snapshot per selection and returns the probability move per selection. Returns
  `{}` until a fixture has ≥2 snapshots at different timestamps (no move yet). 1X2 only.
- **Capture (zero risk to staking)**: in the bet gate, when the move toward a selection is
  ≥ `settings.steam_min_move_pct` (default **3.0**), `_record_steam_signal()` writes it to a
  dedicated `steam_signals` ledger (in `completed_fixtures.db`, one row per fixture/market/
  selection — first detection's price sticks). This is a SHADOW research ledger, fully separate
  from the model bet path / Kelly staking; it stakes nothing.
- **Opt-in confirm filter**: `settings.require_steam_confirm` (default **False**). When True, a
  model 1X2 pick must ALSO be steaming toward it (`steam_move ≥ steam_min`) to be recommended.
  Off by default → no change to existing behaviour. Every candidate is annotated with
  `sel["steam_move"]` (%) for the dashboard/analysis regardless.
- **Flat-stake bet path (NEW)**: `log_steam_bet()` places a real PAPER bet for each fired steam
  signal — `bet_source='STEAM'`, a FLAT stake (`settings.steam_flat_stake`, default 25; Kelly
  doesn't apply since the edge is the move, not a model prob), deduped per fixture/market/selection,
  registered with the bankroll tracker and written to `bet_log`. It is settled automatically by
  `settle_open_bets()` (1X2 settles by score regardless of bet_source). Gated by
  `settings.steam_betting_enabled` (default True). This is a SEPARATE strategy from the model
  ('AI' source) — filter by `bet_source` to compare. Paper only; real money stays gated off.
- **Evaluation**: `tools/steam_report.py` — (1) settles the `steam_signals` ledger vs real scores
  at flat 1u for the raw-signal ROI, and (2) summarizes the STAKED STEAM bets in `bet_log`
  (daemon-settled) for the actual paper-strategy P&L. Needs the daemon to run a while first
  (≥2 snapshots/fixture) to accumulate signals.
- New settings: `steam_min_move_pct` (3.0), `require_steam_confirm` (false),
  `steam_betting_enabled` (true), `steam_flat_stake` (25.0). New tool: `tools/steam_report.py`.
  NOTE: the backtested steam edge is the diagnostic ceiling; let the live ledger accumulate a few
  hundred settled bets before trusting the production ROI. Disable anytime via `steam_betting_enabled`.

## Conventions

- Run Python via the venv interpreter explicitly (`.venv\Scripts\python.exe`), not bare `python`.
- This is a Windows machine; shell is PowerShell. Background the server; tail `server*.log`.
