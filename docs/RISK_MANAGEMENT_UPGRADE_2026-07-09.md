# Arena Risk Management Upgrade — 2026-07-09

Implementation of the 14-phase risk-management program for `src/arena_betting.py`
(StairAI World Cup Arena, real USDC). Phases 1–14 below; each phase's code has unit
tests and was verified against real, live data before moving to the next.

## Context

This program started from a specific problem: Arena's live autopilot had a hardcoded
"never stake less than 40% of wallet" floor and zero drawdown protection, on an account
already down ~98% mark-to-market (see [ARENA_RISK_ANALYSIS_2026-07-09.md](ARENA_RISK_ANALYSIS_2026-07-09.md)).
Rather than implementing all 14 phases blindly in one pass on a live-armed real-money
system, each phase was scoped, implemented, unit-tested, and verified against real data
(where real data existed) before proceeding to the next — per the master prompt's own
rule: "implement the instrumentation necessary to measure it before changing production
behavior."

**Test suite: 182 passing (up from 91 baseline), 4 pre-existing failures unrelated to
this work** (`test_bet_filtering.py::TestSettingsDefaults` — confirmed via `git diff`
against `HEAD` that the values these tests check were already diverged before this
session started; not touched by any phase below).

## What changed, phase by phase

| Phase | Module(s) | What it does | Status |
|---|---|---|---|
| 1 | `arena_betting.py` (`_wallet_kelly_size`, `_update_drawdown_state`) | Removed the 40%-of-wallet floor; configurable Kelly fraction/min/max bet; daily drawdown tiers (10/20/30/40% → 0.75x/0.50x/0.25x/disable-directional); arbitrage never disabled | **Live** (default-on) |
| 2 | `execution_analytics.py` | Per-order execution log (signal price, fill, slippage, delay); pre-trade liquidity gate (order-book depth check) | **Live** (liquidity gate default-on) |
| 3 | `attribution_engine.py` | Actual vs midpoint vs zero-fee vs pure-Kelly counterfactual P&L attribution | Reporting only (0 settled Arena bets so far) |
| 4 | `calibration_metrics.py` | Brier score, log loss, ECE, MCE, reliability bins; optional Platt/isotonic/temperature rescaling | Reporting + optional rescaling tools |
| 5 | `edge_threshold_analysis.py` | ROI/Sharpe/Sortino/max-drawdown/Calmar/profit-factor/Kelly-growth/bootstrap-CI at 2–10% edge thresholds | Reporting only, recommends |
| 6 | `forebet_segmentation.py` | Forebet-confirmed vs non-confirmed vs high/low-edge/confidence segments | Reporting only |
| 7 | `clv_analysis.py` | 30min/1hr/pre-kickoff price snapshots; CLV vs closing price | Reporting only |
| 8 | `ensemble_optimizer.py` | Model-vs-market blend-weight sweep + logistic stacking, walk-forward | Reporting only, recommends |
| 9 | `feature_importance.py` | Random Forest / XGBoost / Logistic Regression importance ranking | Reporting only |
| 10 | `adaptive_kelly.py` | Composite sizing multiplier: Kelly × calibration × execution × liquidity × market-quality | **Off by default** (`arena_adaptive_kelly_enabled=false`), wired but unvalidated |
| 11 | `backtest_framework.py` | Combines Phase 5 metrics + Monte Carlo bankroll projection (prob. of ruin) | Reporting only |
| 12 | `reporting.py` | Daily/weekly/monthly report stitching Phases 2–9 together, capital curve | Reporting only |
| 13 | `arena_betting.py` (`_load_risk_settings`, `_forebet_gate_blocked`) | Forebet-required, arb-enabled, WC-model-weight now configurable (were hardcoded) | **Live** (defaults preserve prior behavior exactly) |
| 14 | this document + full test/lint pass | Final verification, docs, roadmap | Done |

## Configuration reference (`data/settings.json`)

All new keys, with defaults chosen to reproduce PRIOR behavior exactly (except the 40%
floor removal itself, which is the one deliberate, unconditional behavior change):

```jsonc
// Phase 1 — Kelly sizing & drawdown
"arena_kelly_fraction": 0.25,
"arena_minimum_bet": 1.00,
"arena_maximum_bet": 100.00,
"arena_drawdown_protection_enabled": true,
"arena_drawdown_tiers": [ /* 10/20/30/40% -> 0.75x/0.50x/0.25x/disable */ ],

// Phase 2 — liquidity gate
"arena_liquidity_gate_enabled": true,
"arena_required_liquidity_multiple": 3.0,
"arena_liquidity_check_pct": 0.01,

// Phase 10 — adaptive Kelly (OFF by default — unvalidated)
"arena_adaptive_kelly_enabled": false,
"arena_adaptive_kelly_ece_cap": 0.15,
"arena_adaptive_kelly_slippage_cap": 0.05,
"arena_adaptive_kelly_vig_cap_pp": 10.0,

// Phase 13 — previously-hardcoded strategy values
"arena_forebet_required": true,
"arena_arb_enabled": true,
"arena_wc_model_weight": 0.65
```

**Deliberately NOT moved into settings.json**: `DEEPFIELD_ARENA_LIVE` (`.env`) — this is
the real-money kill switch and must stay separate from ordinary runtime config per its
existing hard-gate design (see `CLAUDE.md`).

## Reports available (all read-only, safe to run anytime)

```
tools/preview_stakes.py               # old-vs-new-vs-drawdown sizing, live picks
tools/attribution_report.py           # Phase 3
tools/calibration_report.py           # Phase 4 (Arena)
tools/edge_threshold_sweep.py         # Phase 5 (history.db)
tools/forebet_segmentation_report.py  # Phase 6 (bet_log.db, 1X2-only default)
tools/arena_clv_report.py             # Phase 7 (Arena)
tools/ensemble_optimization_report.py # Phase 8 (history.db)
tools/feature_importance_report.py    # Phase 9 (bet_log.db)
tools/backtest_framework_report.py    # Phase 11 (history.db)
tools/period_report.py [daily|weekly|monthly]  # Phase 12
```

## Before vs after (Phase 1, verified against live wallet)

`tools/preview_stakes.py` on the same live qualifying picks:

| Pick | Old (40% floor) | New (pure Kelly) |
|---|---|---|
| Norway v England (ENG, +26.0pp edge) | $45.27 | $15.35 |
| Spain v Belgium (BEL, -3.4pp edge) | $45.27 | $1.00 |
| Norway v England (draw, -14.1pp edge) | $45.27 | $1.00 |

The old logic staked the same ~$45 on a strong pick and a clearly negative-edge pick
alike; the new logic scales with actual edge.

## Key findings from real-data verification (the actionable part)

1. **The Forebet-confirm gate's validation doesn't hold up for the market it actually
   gates.** The documented "+41.7% ROI, CI entirely above zero, n=259" figure was computed
   over mixed 1X2 + Over/Under 2.5 data. Restricted to 1X2-only (what Arena's gate
   actually checks), n drops to 31 and the ROI CI **straddles zero** (-36.8% to +83.8%).
   See Phase 6's report. **This doesn't mean the gate is wrong — it means the specific
   statistical claim behind it is weaker than documented.**
2. **Model-vs-market blending: pure market beats every blend weight** on log-loss/Brier
   (Phase 8, real walk-forward on 3,042 held-out matches) — confirms, independently, this
   project's own prior finding that the model has no genuine edge over the market.
   `WC_MODEL_WEIGHT` (0.65) and `market_blend_weight` (0.5) are both skewed away from
   what the data supports (weight→0, i.e., trust the market more).
3. **Feature importance (n=64 real settled 1X2 bets)**: `forebet_agreement` (the binary
   flag) is the *least* important feature across all 3 methods (Random Forest, XGBoost,
   Logistic Regression) — `edge_pct` and `implied_confidence` dominate.
4. **Early CLV signal is positive**: 7 Arena bets with usable price history show +1.98%
   average CLV, 85.7% beating the close — small n, but a genuine early positive read.
5. **Monte Carlo illustrates ruin risk concretely**: a -9.3% ROI strategy compounded at
   quarter-Kelly over ~2,360 sequential bets shows 100% probability of ending below 50%
   of starting bankroll in simulation — a vivid demonstration of why sizing discipline
   matters more as volume increases.

## Assumptions (stated explicitly per "verify assumptions")

- Historical wallet balance at bet-placement time isn't recorded per-bet; Phase 3's
  `pure_kelly` counterfactual uses the *current* balance as a stand-in.
- Polymarket/StairAI charge no separate visible fee; Phase 3's "fees" bucket is the
  `LIMIT_BUFFER` markup, not a platform fee — flagged as unconfirmed, not assumed zero.
- "Closing price" = last recorded pre-kickoff snapshot (no separate closing auction on
  Polymarket).
- Drawdown baseline (Phase 1) is a **fresh daily snapshot** — confirmed with the user;
  the pre-existing ~98% drawdown is treated as sunk, not counted against the new tiers.

## Remaining weaknesses

- **Zero settled Arena bets** as of this writing — Phases 3, 4, 9, 10's calibration/
  execution scores, and the capital curve, are all currently reporting "no data yet."
  They're real, tested, and ready — just unvalidated against actual outcomes.
- **Adaptive Kelly (Phase 10) is wired but never exercised on real settlement data.**
  Its neutral-on-missing-data design (score defaults to 1.0, not 0.0) was a deliberate
  choice to avoid silently zeroing out sizing while data is thin — worth re-checking
  once real calibration/execution data exists.
- **Ensemble optimization (Phase 8) doesn't test Elo-vs-Dixon-Coles specifically for
  World Cup matches** — it tests model-vs-market on league data (`history.db`), the best
  available real dataset; a true WC-specific ensemble test needs settled Arena volume.
- **Feature importance (Phase 9) uses only 3 features** (edge_pct, implied_confidence,
  forebet_agreement) because those are the only ones bet_log.db carries historically;
  liquidity/spread/time-to-kickoff/tournament-stage are captured going forward via
  Phase 2/7 but have no settled-bet history yet to fit against.
- **`xgboost` added as a new dependency** (`requirements.txt`) for Phase 9 — not
  previously in the project.
- **Backtest framework (Phase 11) replays the production model code, not the full Arena
  decision pipeline** — no historical WC2026 Polymarket order-book archive exists to
  replay gates/sizing/liquidity against (see `backtest_framework.py` docstring).

## Future roadmap

1. Let Arena accumulate settled bets; re-run Phases 3/4/6/9/10 once there's real
   settlement volume — the infrastructure is ready, the data isn't yet.
2. Consider whether `WC_MODEL_WEIGHT`/`market_blend_weight` should move toward the
   market given Phase 8's finding — a deliberate, human decision, not automated here.
3. Re-run Phase 6's Forebet segmentation periodically as 1X2-specific volume grows past
   n=31 — that's the number that matters for Arena's actual gate, not the mixed-market
   n=295.
4. Once Phase 10 has real calibration/execution/liquidity data, evaluate whether
   `arena_adaptive_kelly_enabled` should be turned on.
5. Phases 2–14 all also apply, in principle, to `run_autoplace()` (the manual/UI path,
   currently out of scope — see each phase's module docstring) — extend if that path
   sees real use.

## Verification commands

```powershell
.venv\Scripts\python.exe -m pytest -q          # 182 passed, 4 pre-existing unrelated failures
.venv\Scripts\python.exe -m ruff check src/ tools/   # clean
.venv\Scripts\python.exe -m mypy --ignore-missing-imports src/*.py   # clean
```
