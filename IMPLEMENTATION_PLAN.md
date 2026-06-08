# DeepFieldPro Implementation Plan

Updated: 2026-06-08

This plan reflects the current repository state. Several items from the older plan have already been implemented; the remaining work is mostly consolidation, hardening, migration, validation, and production readiness.

## Current State

| Area | Current Status | Evidence |
|---|---|---|
| Expected minutes | Implemented | `src/models/expected_minutes.py`, `models/lgbm_minutes_v1.pkl`, `models/minutes_*` |
| Calibration | Implemented | `src/models/calibration_engine.py`, `src/calibration_trainer.py`, `models/platt_scaler_sot.pkl` |
| No-bet filtering | Implemented | `src/risk_engine/no_bet_filter.py` |
| CLV tracking | Implemented in multiple places | `src/clv_tracker.py`, `src/clv_updater.py`, `src/telemetry_warehouse/clv_tracker.py` |
| Bankroll tracking | Implemented | `src/bankroll_tracker.py`, `data/bankroll.db` |
| Live prediction daemon | Implemented | `src/live_predictions_daemon.py` |
| Service-oriented acquisition | Implemented | `src/orchestrator.py`, `src/services/*`, `src/api/main.py` |
| Betarabia acquisition | Implemented | `src/betarabia_scraper.py`, `src/odds_scraper_betarabia.py`, `data/odds_stream.db` |
| Dashboard/API surfaces | Implemented | `src/dashboard.py`, `src/live_dashboard_server.py`, `src/api/main.py` |

## Phase 1: Runtime Consolidation

Goal: make one supported production path clear.

1. Decide whether production runtime is the service stack, the live daemon, or a hybrid.
2. Document the canonical startup order in `README.md` and `SYSTEM_AUDIT_DOCUMENTATION.md`.
3. Route shared behavior through one set of modules for odds, prediction, risk, logging, and CLV.
4. Mark legacy scripts as research-only, smoke-test-only, or deprecated.
5. Add a small `system_check` command that validates required files, DBs, env vars, and model artifacts.

## Phase 2: Database And Migration Hardening

Goal: remove schema drift and make setup repeatable.

1. Create migrations for all operational SQLite schemas, not only SQLAlchemy `src/data/deepfield.db`.
2. Consolidate duplicate `bet_log` and `predictions` schemas between `data/bet_log.db`, `src/data/bet_log.db`, and SQLAlchemy models.
3. Add indexes for common dashboard and settlement queries.
4. Add DB backup/restore procedures for `data/`, `db/`, and telemetry parquet.
5. Define retention policy for raw frames and odds ticks.

## Phase 3: Model Registry And Validation

Goal: make every model artifact auditable.

For every file under `models/`, record:

- Model name and version
- Target variable
- Feature list and feature order
- Training dataset snapshot
- Training script
- Validation split
- Metrics
- Calibration status
- Compatible inference module

Add a `models/MODEL_REGISTRY.md` or structured JSON registry and make inference fail fast when the feature schema does not match.

## Phase 4: Security And Configuration

Goal: remove production blockers.

1. Move hardcoded external keys from source into `.env`.
2. Add authentication and rate limiting to `src/api/main.py`.
3. Redact credentials from logs and generated reports.
4. Separate local development profiles from production browser/sportsbook profiles.
5. Add a secret-check step to CI.

## Phase 5: Test Coverage

Goal: catch regressions in the workflows that matter.

Add or expand tests for:

- Betarabia parser schema drift
- Odds DB writes
- Prediction DB writes
- Model artifact loading
- No-bet filter decisions
- Kelly/stake sizing
- CLV settlement updates
- FastAPI health/metrics endpoints
- Dashboard state JSON generation

## Phase 6: Production Data And Scaling

Goal: make live acquisition reliable at higher frequency.

1. Move high-frequency odds ticks from local SQLite to PostgreSQL/TimescaleDB or another production time-series backend.
2. Run scrapers, inference, settlement, and dashboards as separate workers.
3. Add queueing between acquisition and inference.
4. Add service-level metrics for freshness, latency, dropped frames, parser errors, and DB write failures.
5. Add alerts for stale odds, missing lineups, failed settlement, and low account health.

## Phase 7: Documentation Maintenance

Goal: keep docs synced with the codebase.

1. Regenerate `SYSTEM_AUDIT_DOCUMENTATION.md` after architecture changes.
2. Regenerate `FILE_INVENTORY_DEEPFIELDPRO.md` after large file additions/removals.
3. Update `README.md` when startup commands or supported runtime paths change.
4. Update `USER_GUIDE.md` when dashboard behavior changes.
5. Update this plan when phases are completed.

## Near-Term Priority Order

1. Secrets cleanup.
2. Runtime path decision.
3. DB migration consolidation.
4. Model registry.
5. Parser drift tests.
6. API auth.
7. Production time-series storage.
