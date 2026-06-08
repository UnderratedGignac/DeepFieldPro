# DeepFieldPro Audit Report

Updated: 2026-06-08

This report summarizes the current validation posture of DeepFieldPro after repository inspection. It should be read together with `SYSTEM_AUDIT_DOCUMENTATION.md` for architecture and `FILE_INVENTORY_DEEPFIELDPRO.md` for the full file inventory.

## Current Platform Assessment

DeepFieldPro is no longer only a prototype plan. The repository now contains working modules for live acquisition, model inference, bankroll/risk tracking, CLV telemetry, dashboards, API health endpoints, and research/simulation layers. The codebase still has two active runtime styles:

- A service-oriented stack under `src/services/`, `src/api/`, `src/database/`, and `src/orchestrator.py`.
- A local SQLite/script workflow centered on `src/live_predictions_daemon.py`, `src/betarabia_scraper.py`, `src/model_runner.py`, `data/*.db`, and `models/*`.

## Feature Group Inventory

| Feature Group | Current Implementation | Data Source | Update Frequency | Primary Markets |
|---|---|---|---|---|
| Historical baseline | Training datasets, FBref/Sofascore/API-Football scripts, model artifacts | CSV, SQLite, FBref, Sofascore, API-Football | Batch/manual/daily depending on script | Props, match markets |
| Player form | Rolling feature scripts and LightGBM model inputs | CSV datasets, match logs | Batch/manual | Props |
| Team/opponent strength | Opponent profile DB, feature modules, team models | SQLite, CSV, API data | Batch/manual | 1X2, totals, props |
| Lineup intelligence | Lineup scraper/parser/monitor and live daemon checks | Sofascore/API-Football-style payloads | Live near kickoff | All lineup-sensitive markets |
| Odds/market intelligence | Betarabia scraper, odds DB, WebSocket service layer, CLV modules | Betarabia/Kickertech, Betfair scaffold, local DBs | Live/polling | Execution and EV validation |
| Risk/portfolio | Kelly calculator, bankroll tracker, no-bet filter, portfolio/capital modules | Bet log, bankroll DB, simulated state | Per candidate / daily | Bet sizing and exposure control |
| Telemetry/CLV | CLV tracker/updater, telemetry warehouse, live operations modules | Bet log, odds cache, account telemetry DBs | Live/scheduled | Model and execution validation |

## Model Inventory Summary

The repository includes LightGBM text boosters and serialized pickle/joblib artifacts for minutes, passes, shots, shots on target, goals, cards, offsides, bottom-up match prediction, player impact, and probability calibration.

Key model patterns observed:

- Quantile LightGBM models produce P10/P50/P90 bands for uncertainty-aware pricing.
- Regression boosters estimate count/rate-like targets such as goals, cards, offsides, and player performance fields.
- Serialized sklearn/LightGBM artifacts support bottom-up match and player-impact workflows.
- Poisson transforms convert predicted rates into over/under and anytime probabilities.

## Validation Findings

| Area | Status | Evidence in Repository | Risk |
|---|---|---|---|
| Expected minutes | Implemented as artifacts and `src/models/expected_minutes.py`; also used by live daemon initialization paths | `models/lgbm_minutes_v1.pkl`, `models/minutes_*`, `src/models/expected_minutes.py` | Feature schema/version drift can break inference |
| Probability calibration | Implemented | `src/models/calibration_engine.py`, `models/platt_scaler_sot.pkl`, `src/calibration_trainer.py` | Needs routine recalibration against settled bets |
| CLV tracking | Implemented in multiple modules | `src/clv_tracker.py`, `src/clv_updater.py`, `src/telemetry_warehouse/clv_tracker.py` | Closing odds source may be incomplete or simulated |
| No-bet filtering | Implemented | `src/risk_engine/no_bet_filter.py` | Must be wired consistently across all execution paths |
| Bankroll tracking | Implemented | `src/bankroll_tracker.py`, `data/bankroll.db` | Multiple DB schemas require consolidation |
| API health/metrics | Implemented | `src/api/main.py` | API currently lacks production auth |
| Betarabia acquisition | Implemented | `src/betarabia_scraper.py`, `src/odds_scraper_betarabia.py`, `data/odds_stream.db` | DOM/API schema drift and anti-bot blocking |
| Research governance | Implemented as modules/simulation labs | `src/research/`, `src/meta_research/`, `src/autonomous_portfolio_evolution/` | Some labs appear simulation-oriented rather than fully production-wired |

## Highest Impact Improvements

1. Consolidate the service stack and local SQLite daemon into one documented runtime contract.
2. Add model registry metadata for every artifact: feature schema, target, training snapshot, validation metrics, calibration date, and compatible code version.
3. Move hardcoded external API keys and credentials to environment variables.
4. Add authentication and rate limiting before exposing the FastAPI API outside localhost/private networks.
5. Add idempotent migrations for every SQLite schema and remove duplicate prediction/bet schemas where possible.
6. Add parser drift tests for Betarabia/Kickertech payloads and dashboard-state generation.
7. Make risk filters mandatory in all execution paths, including script-oriented paths.
8. Store high-frequency odds ticks in PostgreSQL/TimescaleDB or another production time-series store.
9. Add scheduled recalibration reports that compare model probability buckets against settled outcomes and CLV.
10. Keep the full system documentation and file inventory regenerated after major architectural changes.

## Current Audit Conclusion

DeepFieldPro has the core ingredients of an institutional sports-betting research and operations stack, but production readiness depends on reducing duplicate runtime paths, tightening secrets/security, versioning model artifacts, and making database migrations explicit. The most valuable edge drivers remain lineup intelligence, expected-minutes modeling, market/CLV feedback, uncertainty-aware sizing, and strict portfolio risk controls.
