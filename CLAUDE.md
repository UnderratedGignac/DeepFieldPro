# Agentic Engineering Operating System

## Core Identity

Claude is the **Orchestrator / Architect / Reviewer**.
**AGY** (Antigravity/Gemini CLI) and **Qwen3.5** (NVIDIA NIM API) are the **Execution Workers**.

Claude implements code directly only when:
- The task touches a single file and fewer than ~20 lines change
- A worker is unavailable or inappropriate (security-sensitive, secret-handling)

Otherwise **delegate to AGY or Qwen3.5**.

## Roles

| Claude | AGY | Qwen3.5 (NVIDIA) |
|--------|-----|------------------|
| Requirements analysis | Coding & refactoring | Coding & refactoring |
| Specification generation | File modifications | File modifications (write_file tool) |
| Architecture design | Bulk implementation | Code execution (run_python tool) |
| Task decomposition | Repository scanning | Independent second opinions |
| Skill selection | Code generation | Parallel workloads alongside AGY |
| Security review | Documentation generation | Analysis & synthesis |
| Evaluation & QA | Repetitive execution | Autonomous build tasks |
| Orchestration | Autonomous build tasks | |

**Worker selection heuristic:**
- Run both in parallel for independent sub-tasks → **AGY + Qwen3.5 simultaneously**
- Either worker for pure implementation → **AGY** (battle-tested for large loops)
- Analysis / second opinion → **Qwen3.5** (NVIDIA NIM, fast API)
- Secret/credential work → **Claude directly**

## Qwen3.5 Worker Integration

Qwen bridge: `tools/openrouter_worker.py` — `run_task(prompt)` / `run_build_task(task)`.
Provider: NVIDIA NIM (`qwen/qwen3.5-122b-a10b`) with OpenRouter fallback.
Keys: `NVIDIA_API_KEY` / `OPENROUTER_API_KEY` in `.env`.

**Parallel dispatch (AGY + Qwen3.5 simultaneously):**
```python
import concurrent.futures
from tools.agy_bridge import run_build_task as agy_task
from tools.openrouter_worker import run_build_task as qwen_task

with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
    f1 = ex.submit(agy_task,  "Task A — implement feature in src/module_a.py")
    f2 = ex.submit(qwen_task, "Task B — write tests for src/module_b.py")
    r1, r2 = f1.result(timeout=300), f2.result(timeout=300)
```

## Mandatory Workflow

Every non-trivial request follows this pipeline — do not skip phases:

```
Request → Requirements → Specification → Architecture
       → Execution Plan → Agent Selection → Execution
       → Evaluation → Completion
```

**Spec-first rule**: no implementation begins before acceptance criteria exist. If the spec is incomplete, STOP and request clarification.

## AGY Worker Integration

AGY bridge: `tools/agy_bridge.py` — `run_task(prompt)` / `run_build_task(task)`.

**AGY dispatch sequence:**
1. Determine if task is AGY-suitable (multi-file, generative, repetitive).
2. Write precise execution instructions (include file paths, constraints, expected output format).
3. Call `run_build_task(instructions)` or `run_task(prompt)`.
4. Wait for result; read `AgyResult.text`.
5. Review output against acceptance criteria.
6. Evaluate (see Evaluation Requirements below).
7. If output fails evaluation: correct instructions and re-dispatch, or escalate to Claude direct.

**AGY delegation heuristic:**

Default to AGY when:
- More than one file will change
- Large code generation is required
- Repository-wide analysis is needed
- Repetitive implementation work exists

Default to Claude when:
- Designing systems or reviewing architecture
- Evaluating quality or security
- Writing specifications
- Planning execution strategy

## MCP First Rule

Before building any integration:
1. Search installed MCP servers (already loaded in session).
2. Search available MCP registry (`mcp-registry` MCP).
3. Search internal tools (`tools/`).
4. Reuse existing capability.

Only create custom integrations when no MCP solution exists.

## Skill Loading Policy

Load only skills required for the current task. Required foundational skills for orchestration work:

- `orchestrator` · `sdd` · `architecture` · `security-review`
- `eval-engine` · `context-minimizer` · `mcp-discovery`

## Security Requirements

Every action requires:
1. Structural validation (schema / type)
2. Semantic validation (intent vs. effect)
3. Risk assessment

High-risk actions require explicit review before execution:
- Production deployments · database schema changes · credential modifications · financial actions
- **Real-money gate**: `DEEPFIELD_ARENA_LIVE` must remain unset/`0`. There is currently no
  real-money execution path anywhere in this app — the Stair AI World Cup Arena (the only one
  that ever existed) was fully removed 2026-07-13 after the user lost most of the account's real
  money chasing a #1 leaderboard rank; see `docs/removed_features.md` §4 for the full removal
  record. `src/gatekeeper.py`'s `check_real_money_gate()` remains as a general kill switch for
  any future real-money path — its first check is `DEEPFIELD_ARENA_LIVE == "1"` — but nothing
  currently calls it. `SHADOW_MODE=True` governs the separate `execution_engine.py` path (paper
  only; its LIVE branch is an unimplemented placeholder). Never re-introduce real-money order
  placement without the user's explicit, in-the-moment go-ahead.

## Evaluation Requirements

Nothing is complete until evaluated against:

| Dimension | Threshold |
|-----------|-----------|
| Requirement satisfaction | All ACs met |
| Security | No new attack surface |
| Maintainability | Follows project conventions |
| Correctness | Tests pass / manual check passes |

If any dimension fails: return for correction before reporting done.

## Context Management

Minimize token usage. Prefer: Skills · Scripts · MCP tools · Summaries.

Avoid: giant prompts · repeated context · unnecessary history.

When context grows large: summarize completed work, preserve decisions + specifications, discard stale details.

## Self-Audit Checklist

Before every response, verify:
- [ ] Is the specification complete?
- [ ] Was the correct skill selected?
- [ ] Should AGY perform this task?
- [ ] Is there an MCP alternative?
- [ ] Has the result been evaluated?
- [ ] Does output satisfy all requirements?

If any box is unchecked, correct before continuing.

---

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
  `find_betarabia_odds()`, and the `place_bet()` call site.
- `free_scraper_module.py` — Sofascore fixture fetch + the Betarabia fixture fallback builders.
- `betarabia_scraper.py` — background subprocess (launched via `subprocess.Popen`) that scrapes
  Betarabia/Kickertech odds into `data/odds_stream.db`.
- `execution_engine.py` — `place_bet()`; SHADOW vs LIVE branch (LIVE is an unimplemented placeholder).
- `dfp_config.py` — settings incl. `SHADOW_MODE` (default **True**).
- `api/main.py`, `orchestrator.py` — newer service-oriented stack (FastAPI/uvicorn), separate path.
- ~~`arena_betting.py`~~ — **removed 2026-07-13.** Was the Stair AI World-Cup Arena real-money
  value-betting page (Flask blueprint at `/arena`). See `docs/removed_features.md` §4.

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
  `WHATSAPP_*`, `DEEPFIELD_*` risk params, `BROWSER_*`, etc. Betfair (`BETFAIR_*`) is configured
  (real login, read-only "Delayed (free)" key — odds retrieval only, no order placement).
- ML models/artifacts live in `models/`.

## Safety (important)

- **No real-money betting.** `place_bet()` runs the **SHADOW_MODE** branch (default `True` in
  `dfp_config.py`) → records mock "SHADOW" bets to DB only. The LIVE branch is an unimplemented
  placeholder ("Real capital execution not yet fully linked"). `auto_place_bets` in settings.json
  does NOT actually gate placement. There is no other real-money path in the app (Stair AI Arena
  removed 2026-07-13 — see `docs/removed_features.md` §4).
- The daemon DOES make external calls when running: optional WhatsApp alerts and live web
  scraping (Playwright/Chromium). Keep this in mind before running.

## Known issues / gotchas

- **Missing dep**: `pydantic-settings` is required by the daemon — now pinned in `requirements.txt`.
- **Sofascore — CORRECTED 2026-07-11 (this said "returns empty / 403 bot-blocked"; that is
  now STALE).** The `patchright` (stealth-Playwright) path bypasses the block:
  `sofascore_patchright_scraper.py` is the **primary fixture source** today
  (`live_predictions_daemon.py:301` — its import succeeds because patchright is installed, so
  the Betarabia fixture fallback is rarely reached; today's dashboard state carries
  Sofascore-style fixture IDs), and `sofascore_results_scraper.py` is a live settlement source
  (per-date `data/sofascore_cache_*.json` refresh each cycle). Verified by a 9-scraper live
  health check 2026-07-11. The plain-`requests` Sofascore path may still 403 — the note only
  applies to that, not the patchright path.
- **Settlement results source**: `free_results_scraper.py` (`get_finished_results()`) provides free,
  key-less finished scores from **ESPN** (broad league coverage incl. minor leagues) + **TheSportsDB**
  fallback, cached per-date. `settle_open_bets()` uses it as the primary feed (API-Football is only a
  bonus when its daily quota allows). This is what makes win/loss settlement actually work.
- **`fetch_betarabia_odds()` was originally undefined** (called by `free_scraper_module.py` and the
  daemon). It is now implemented in `live_predictions_daemon.py` and returns kickoff/league/status
  from `odds_stream.db`. The fallback builders (daemon + `free_scraper_module.py`) use that metadata —
  do NOT revert them to stamping `now()` / `"NS"` / `"Betarabia"` (that caused the "all kickoffs show
  the scrape time" glitch).
- **Daemon bet-source note**: the paper daemon bets across ALL markets, most of which are heavily
  -EV in the realized record (Goalscorer −80%, Player Shots −62%, O/U −70%, BTTS −59%). Every AI
  bet gets a `SHADOW_*` order id — there is no real order path left to gate.
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
- No real-money path exists in this app (see Safety above).

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
- **Real-money HARD GATE**: `src/gatekeeper.py`'s `check_real_money_gate()` refuses unless
  `DEEPFIELD_ARENA_LIVE=1` (currently unset/`0`, and nothing calls this gate — see Safety above).
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

## Settlement integrity + memory (2026-08-24)

**Settlement was grading 88% of bets by fuzzy team name.** `_fid_to_score` was built
only from `todays_dashboard_state.json` (rewritten each cycle, today only) while
settlement looks back 7 days, so fid-direct went 14.9% same-day → 5.7% (+1d) → **0.0%
(+2d and beyond)**. Splitting realized P&L by `settle_source` shows the returns track the
GRADING METHOD, not betting skill: `fid-direct` is **−19.6%** ROI across every strategy
(n=406), `name-match` +1.7%, `deep-lookup` +43.9%. Within MODEL_VALUE_ALIGN alone — same
window, same stakes — fid-direct +2.7%, name-match +45.4%, deep-lookup +93.3%.
**Treat any apparent edge as a grading artifact until it survives `settle_source='fid-direct'`.**

- **`src/fixture_results.py` (new)** — durable `fixture_results(namespace, fixture_id,
  home_score, away_score, status, seen_at)` table in `completed_fixtures.db`. Fed each
  cycle from the dashboard state and from `sofascore_results_scraper.get_events()` across
  the whole lookback; 30-day retention. `load_flat_scores()` serves legacy bets that have
  no namespace and **drops any id meaning different results in two namespaces**.
  Live effect: fid index **13 → 359 fixture_ids** on the first cycle.
- **`fixture_ns` everywhere** — fixture dicts, dashboard state entries, and a `bet_log`
  column (migrated via `settlement_provenance.PROVENANCE_COLUMNS`). Ids are NOT one space:
  Sofascore 14–17M, Betarabia/Kickertech 27–29M, ESPN 4xxxxxxxx, plus md5 fallbacks now
  stamped `synthetic:<source>` so they can never be cross-joined.
- **`fetch_betarabia_odds()` now returns the real Kickertech `fixture_id`** (it selected
  every column except that one), so the fallback builders stop minting md5 ids.
- **`tools/edge_milestone_check.py`**: strategy list hoisted to a module constant `TRACKED`;
  MODEL_VALUE_ALIGN, PINNACLE_VALUE and STAIR_AI were never tracked. MODEL_VALUE_ALIGN is
  the only strategy to clear t≥2.0 (t=+3.52, n=190/300) — but see the settle_source caveat.

**Memory: peak 5.9 GB → 4.0 GB, avg system free 1.8 GB → 2.8 GB** (16 GB machine).
- `sharp_odds_history` grew unbounded to **65M rows / 16.6 GB** (~1.03M rows/day, no purge
  while sibling `odds_history` had one). `pinnacle_feed` now dedups unchanged prices with a
  300s heartbeat and purges past `SHARP_ODDS_RETENTION_DAYS` (14) each cycle.
  `tools/prune_sharp_odds_history.py --archive` reclaimed **16.09 GB** (16.64 → 0.55 GB),
  archiving all 62.3M dropped rows losslessly to `sharp_odds_history_archive.db`.
- `betarabia_scraper` retained every JSON response while driving one page through 50 event
  navigations → a single renderer at **1.34 GB**. Now `_ResponseStore` keeps only payloads
  the parsers read (deduped by URL), and the page recycles every `_PAGE_RECYCLE_EVERY` (3)
  navigations (~120 MB of renderer heap per event page is never released).
- The completion scan launched **one Chromium per finished fixture**; now one batched
  session via `get_fixture_stats_free_batch()`.
- `sofascore_results_scraper` trims+dedups events on arrival (`_EventCollector`) instead of
  holding raw payloads, and `_mem_cache` is bounded.
- `tools/score_lookup.py` gained a negative-result cache — one cycle did 27 Chromium spawns
  re-checking fixtures Flashscore does not carry. `NEG_CACHE_TTL` is **7200s (2h), which
  MUST stay above the daemon's own `_DEEP_LOOKUP_INTERVAL` (1800s)** — a TTL at or below
  that expires exactly when the throttle lifts and suppresses nothing. Guarded by
  `tests/test_score_lookup_negcache.py::test_ttl_exceeds_the_daemons_own_deep_lookup_throttle`.

## Daemon supervision + /api/health (2026-08-25)

**The prediction worker could die silently, and did.** On 2026-08-24 23:02 `run_daemon`
raised `TypeError: log_pinnacle_value_bet() got an unexpected keyword argument
'fixture_ns'` and the thread exited. It was started as a bare
`threading.Thread(target=run_daemon, daemon=True)`, so nothing restarted it and nothing
reported it. Flask kept answering `/api/state` every 30 minutes; the dashboard looked
perfectly healthy while nothing was scraped, predicted or settled for ~10 hours.

- **`src/daemon_supervisor.py` (new)** — `start_supervised(run_daemon, name="predictions")`
  replaces the bare thread in `live_dashboard_server.start_background_prediction_worker()`.
  Crashes are logged, counted and retried with capped exponential backoff; the backoff
  RESETS after a healthy run so a crash six hours in retries immediately. A clean return
  is also treated as a fault (run_daemon must loop forever). Never re-raises.
- **`GET /api/health`** — `{alive, ok, restarts, last_crash, last_crash_at,
  state_age_sec, state_stale}`. `ok` is false when the worker is dead OR
  `todays_dashboard_state.json` is >30 min stale, so a wedged-but-alive thread also reads
  as broken. **`/api/state` returning 200 proves nothing about the engine — check this.**
- **`tests/test_call_signature_guard.py` (new)** — AST-checks every keyword call site in
  the daemon against the callee's real signature. The outage came from a bulk text replace
  of `fixture_id=fid,` that hit two functions taking no `fixture_ns`; one killed the
  thread, the other (`is_good_time_to_bet`) sat inside a bare `except` and silently left
  the bet-timing filter failing open. `py_compile` cannot catch this.

**Debugging a quiet daemon**: `py-spy` is installed in the venv —
`.venv\Scripts\py-spy.exe dump --pid <pid>`. It distinguishes *blocked* from *dead*: if
`Thread-N (run_daemon)` is missing entirely, it crashed, and the traceback is in the
server's **stderr** log, not stdout. Launch with `python -u` so stdout is not
block-buffered (a stalled thread otherwise leaves its last lines unflushed).

## odds_fresh traced — it was a kickoff guard in disguise (2026-08-25)

Gate telemetry showed `odds_fresh` rejecting 54 of 127 selections (43%) while only 9% of
fixtures in `odds_stream.db` were older than the 60-minute limit. Chasing that produced
two findings.

**1. The apparent 43% was correct, and every one of those rejections was an
already-kicked-off match.** The prediction loop only skips a fixture when `status in
("FT","AET","PEN")` AND kickoff was >12h ago, so 17 South American fixtures from the
previous day — kicked off 9–13h earlier, carrying 13-hour-old prices — reached the bet
gate. `odds_fresh` was the ONLY thing stopping bets on them. That is far too load-bearing
for a defence-in-depth check, and it **fails open exactly when it matters**: an in-play
price is fresh by definition. `_kickoff_passed(match_time, grace_min=0.0)` now gates both
bet chains explicitly. Live proof — the two gates reject an identical set:

```
[GATES] MODEL: 1/127 | blocked_by: ev=96, odds_fresh=54, not_kicked_off=54, prob=46
```

**2. A real staleness leak, separate from the above.** `_betarabia_odds_age_min` is a
module global that `find_betarabia_odds()` set only on its Betarabia branch, near the END
of the function. The Tier-1 **Kambi** branch returns early (Kambi serves ~164 fixtures, the
majority of the slate), so every Kambi-priced fixture inherited whatever staleness the
previous fixture left behind. Fixed: the global is reset on entry and set on every return
path; `kambi_scraper.cache_age_min()` reports Kambi's true age (its own TTL is 90s).
**Any module-global written on one branch and read by another is a leak waiting to happen
— set it on entry.**

Tests: `tests/test_kickoff_guard.py` (13), `tests/test_odds_freshness.py` (9).

**Note on reading gate telemetry**: `blocked_by` counts SELECTIONS, `odds_stream.db` rows
are FIXTURES. Comparing the two directly is apples-to-oranges — roughly 5 selections per
fixture reach the gate, so ~10 stale fixtures produce ~50 selection rejections.

## Settlement crash loop + SKILL strategies removed (2026-10-22/23)

A short-lived set of `SKILL_*` paper strategies (`src/skill_strategies.py`) logged its
parlays with legs that had no `market`/`selection`, so `settle_open_bets()` raised
`KeyError('market')` in the parlay loop **every cycle** — rolling back that cycle's W/L
grades AFTER `register_settlement` had already credited `bankroll.db`. The same payouts
were re-credited each cycle: the research ledger went $885.65 → $3,224.51 in a day with
only $4.91 of real payouts committed (≥ ~$2.3k phantom; **NOT repaired** — per-bet stakes
use strategy_ledger and settings.json disables register_bet's caps, so the damage is the
dashboard/ledger figure, not stake sizes).

- **Kept (crash guard):** the settler commits single-bet grades **before** the parlay loop,
  and each parlay is wrapped so a malformed one is skipped (logged, left OPEN) instead of
  aborting the cycle. Test: `test_settlement_grading.py::TestParlaySettlement::
  test_malformed_parlay_does_not_roll_back_single_bet_grades`.
- **Removed 2026-10-23 at the user's request:** the SKILL strategies and all their records
  (184 bets, 33 parlays, 89 review-queue rows), archived to
  `data/skill_strategies_archive_2026-10-22.db` — see `docs/removed_features.md` §5.
- **Any ledger credit written before its bet_log commit is a re-credit loop waiting to
  happen** — keep `conn.commit()` ahead of anything that can raise.

## Server watchdog — Task Scheduler (2026-10-23)

The server died silently on 2026-10-23: started from a Claude session, it was killed when
the session restarted (~5 h with no bets or settlement). Fix: **scheduled task
"DeepFieldPro Watchdog"** runs `.venv\Scripts\pythonw.exe tools\watchdog.py` every 5 min
(and at logon; runs on battery; never overlaps; 4-min run cap).

- `tools/watchdog.py` (rewritten) is a **one-shot** check: reads `/api/health` on the port the
  server is actually listening on, then does nothing, starts, or kills-and-restarts. Restart
  only on sustained failure: health unreachable 3 checks in a row, worker `alive=false` twice,
  or state stale >90 min after >60 min uptime (the first cycle after a gap takes ~30 min, so
  stale-on-boot is NOT a fault). Two server chains = twin daemons → collapsed to one.
- It launches the server via **WMI `Win32_Process.Create`** so the parent is `WmiPrvSE.exe`,
  independent of the watchdog, the scheduler and any terminal. **Restart the server the same
  way by hand** — `Start-Process` from a Claude/agent shell dies with that session.
- It only ever kills DeepFieldPro server processes (the old version killed every python.exe).
- Log: `logs/watchdog.log` (only WAIT/restart/recovery lines; silent while healthy).
  State: `logs/watchdog_state.json`. Dry run: `.venv\Scripts\python.exe tools\watchdog.py --dry-run`.
- The task previously pointed at `AppData\Local\hermes\scripts\deepfield_watchdog_silent.vbs`
  (disabled since 2026-09-11; hardwired to port 5050, so with the server on 5058 it would have
  launched a twin). Those files are untouched but no longer referenced.
- Verified live: killed the server at 16:53:08, watchdog restarted it at 16:53:19, health OK at
  16:53:26. Tests: `tests/test_watchdog.py` (14).
