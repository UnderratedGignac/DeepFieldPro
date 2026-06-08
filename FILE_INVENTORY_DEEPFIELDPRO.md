# DeepFieldPro File Inventory

Generated 2026-06-08. Total files listed: 2098. Python files parsed: 359.

Every visible repository file outside `.git` is listed. Python files include AST-derived imports/classes/functions. Binary/archive files are classified by type.

## Python File Analysis

### `check_db.py`
- Lines: 6
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: sqlite3
- Classes: none
- Functions: none
- Called services/storage signals: sqlite3.connect
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `schema.py`
- Lines: 5
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: sqlite3
- Classes: none
- Functions: none
- Called services/storage signals: sqlite3.connect
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\account_manager.py`
- Lines: 117
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: datetime, os, sqlite3
- Classes: none
- Functions: init_account_db, get_best_book_for_stake, update_account_post_bet, mark_account_limited
- Called services/storage signals: get_best_book_for_stake, sqlite3.connect
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\add_passes_data.py`
- Lines: 25
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: app_config, os, soccerdata
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\advanced_training_pipeline.py`
- Lines: 150
- Purpose: Training pipeline/script for one or more predictive models.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: lightgbm, logging, numpy, os, pandas, pickle, sklearn.metrics, sklearn.model_selection
- Classes: AdvancedTrainingPipeline
- Functions: __init__, generate_dummy_data, train_layer_1_players, prepare_layer_2_features, train_layer_2_teams
- Called services/storage signals: logging.getLogger, pickle.dump
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Training pipeline/script for one or more predictive models.

### `src\adversarial_detection\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\adversarial_detection\hidden_markov_throttle_detector.py`
- Lines: 72
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging, numpy, src.telemetry_warehouse.adversarial_pattern_miner
- Classes: HiddenMarkovThrottleDetector
- Functions: __init__, update_belief, get_restriction_probability
- Called services/storage signals: logging.getLogger, pattern_miner.get_state_transition_matrix
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\alerter.py`
- Lines: 54
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: dotenv, os, requests
- Classes: none
- Functions: send_telegram_message, alert_pipeline_failure, alert_bet_placed, alert_daily_limit_hit, alert_drawdown_triggered, alert_role_shift_detected
- Called services/storage signals: os.getenv, requests.post
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\api\__init__.py`
- Lines: 1
- Purpose: API component.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: API component.

### `src\api\main.py`
- Lines: 616
- Purpose: API component.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: contextlib, fastapi, fastapi.responses, logging, pydantic, src.services.session_manager.service, typing
- Classes: HealthResponse, SessionStatusResponse, BrowserStatusResponse, MetricsResponse, OddsTickResponse, WebSocketStatusResponse, AppState
- Functions: get_app_state, async lifespan, async health_check, async readiness_check, async liveness_check, async get_session_status, async list_sessions, async create_session, async authenticate_session, async close_session, async get_browser_status, async restart_browser, async get_websocket_status, async list_websocket_status, async get_live_odds, async get_odds_history, async get_active_markets, async get_metrics, async http_exception_handler, async general_exception_handler, __init__, set_session_manager, set_database_session, add_websocket_ingestor, get_websocket_ingestor, async do_restart
- Called services/storage signals: FastAPI, app.get, app.post, browser_metrics.get, engine.get_metrics, info.get, ingestor.get_metrics, logging.getLogger, metrics.get, self.websocket_ingestors.get, session.get, state.get_websocket_ingestor, state.session_manager._session_metrics.get, state.session_manager.engine.get_metrics, state.session_manager.get_metrics_summary, state.session_manager.get_session, state.session_manager.get_session_health_score, summary.get, ws_metrics.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: API component.

### `src\app_config.py`
- Lines: 25
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: os
- Classes: Config
- Functions: none
- Called services/storage signals: os.getenv
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\audit_data.py`
- Lines: 32
- Purpose: Telemetry, CLV, audit, monitoring, or reporting component.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: app_config, os, pandas
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Telemetry, CLV, audit, monitoring, or reporting component.

### `src\audit_wc_coverage.py`
- Lines: 110
- Purpose: Telemetry, CLV, audit, monitoring, or reporting component.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: io, pandas, re, sys, unicodedata
- Classes: none
- Functions: normalize_name, name_token_overlap
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Telemetry, CLV, audit, monitoring, or reporting component.

### `src\autonomous_portfolio_evolution\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\autonomous_portfolio_evolution\apel_engine.py`
- Lines: 149
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging, src.autonomous_portfolio_evolution.schemas, typing, uuid
- Classes: AutonomousPortfolioEvolutionLayer
- Functions: __init__, _initialize_core_portfolio, evaluate_portfolio_lifecycle, _spawn_new_variant, get_active_strategies
- Called services/storage signals: logging.getLogger, telemetry.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\autonomous_portfolio_evolution\apel_simulation_lab.py`
- Lines: 50
- Purpose: Simulation/backtesting/replay component.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: asyncio, logging, src.autonomous_portfolio_evolution.apel_engine
- Classes: APELSimulationLab
- Functions: async run_apel_cycle
- Called services/storage signals: apel_engine.get_active_strategies
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Simulation/backtesting/replay component.

### `src\autonomous_portfolio_evolution\schemas.py`
- Lines: 27
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: enum, pydantic, typing
- Classes: StrategyStatus, StrategyGenome, StrategyState
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\backtester.py`
- Lines: 340
- Purpose: Simulation/backtesting/replay component.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: app_config, lightgbm, numpy, os, pandas, pricing_engine, scipy.stats, sys, utils
- Classes: none
- Functions: load_models, build_features, simulate_market_odds
- Called services/storage signals: BASELINE_PASSES.get, df.get, pos_map.get, row.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Simulation/backtesting/replay component.

### `src\bankroll_tracker.py`
- Lines: 250
- Purpose: Risk, bankroll, staking, or exposure control logic.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: datetime, os, sqlite3
- Classes: none
- Functions: init_bankroll_db, get_status, register_bet, register_settlement
- Called services/storage signals: get_status, sqlite3.connect
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Risk, bankroll, staking, or exposure control logic.

### `src\bet_logger.py`
- Lines: 106
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: datetime, os, sqlite3, uuid
- Classes: none
- Functions: init_bet_log_db, log_bet
- Called services/storage signals: sqlite3.connect
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\betarabia_scraper.py`
- Lines: 1154
- Purpose: Data acquisition scraper/parser for sports, odds, lineups, or historical stats.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: asyncio, datetime, json, logging, os, playwright.async_api, random, re, sqlite3, traceback, typing
- Classes: none
- Functions: init_db, clear_todays_data, async random_delay, _parse_odds, _safe_inner_text_sync, async _safe_inner_text, is_player_prop, parse_player_prop, parse_kickertech_events, parse_kickertech_odds, _normalize_selection, filter_todays_fixtures, async run_full_probe, async scrape_fixture_list_html, async run_scraper, async handle_response
- Called services/storage signals: AllOddsByEvent_V.get, Data_V.get, Ev_V.get, EventData_V.get, EventsById_P.get, Fix_V.get, Fixture_P.get, Group_V.get, Info_V.get, MainOdds_V.get, Mkt_V.get, ODD_CODE_MAP.get, Odd_V.get, Response_P.headers.get, Response_V.get, Selection_V.get, TargetDates_V.add, Teams_V.get, async_playwright, get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Data acquisition scraper/parser for sports, odds, lineups, or historical stats.

### `src\build_shots_training_dataset.py`
- Lines: 209
- Purpose: Training pipeline/script for one or more predictive models.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: app_config, os, pandas, sqlite3, unidecode
- Classes: none
- Functions: get_opponent, encode_pos
- Called services/storage signals: sqlite3.connect
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Training pipeline/script for one or more predictive models.

### `src\build_training_dataset.py`
- Lines: 228
- Purpose: Training pipeline/script for one or more predictive models.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: numpy, os, pandas, soccerdata, sqlite3, src.app_config
- Classes: none
- Functions: get_position_baseline
- Called services/storage signals: sqlite3.connect
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Training pipeline/script for one or more predictive models.

### `src\build_training_dataset_v2.py`
- Lines: 172
- Purpose: Training pipeline/script for one or more predictive models.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: app_config, datetime, numpy, os, pandas, sqlite3
- Classes: none
- Functions: none
- Called services/storage signals: sqlite3.connect
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Training pipeline/script for one or more predictive models.

### `src\calibration_backtester.py`
- Lines: 262
- Purpose: Simulation/backtesting/replay component.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging, math, model_runner, os, pandas, sys
- Classes: none
- Functions: poisson_prob_ge, run_market_backtest, run_all_markets
- Called services/storage signals: get_player_historical_stats, logging.getLogger, row.get, stats.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Simulation/backtesting/replay component.

### `src\calibration_trainer.py`
- Lines: 141
- Purpose: Training pipeline/script for one or more predictive models.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging, math, model_runner, os, pandas, pickle, sklearn.linear_model, sys
- Classes: none
- Functions: train_platt_scaler
- Called services/storage signals: get_player_historical_stats, logging.getLogger, pickle.dump, row.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Training pipeline/script for one or more predictive models.

### `src\capital_deployment_protocol\__init__.py`
- Lines: 1
- Purpose: API component.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: API component.

### `src\capital_deployment_protocol\capital_ramp_controller.py`
- Lines: 67
- Purpose: API component.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging, math, src.capital_deployment_protocol.schemas
- Classes: CapitalRampController
- Functions: __init__, compute_max_allocation
- Called services/storage signals: logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: API component.

### `src\capital_deployment_protocol\cdp_simulation_lab.py`
- Lines: 85
- Purpose: Simulation/backtesting/replay component.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: asyncio, logging, src.capital_deployment_protocol.deployment_orchestrator, src.capital_deployment_protocol.schemas, sys
- Classes: CDPSimulationLab
- Functions: async run_cdp_flow
- Called services/storage signals: logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Simulation/backtesting/replay component.

### `src\capital_deployment_protocol\deployment_orchestrator.py`
- Lines: 108
- Purpose: API component.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging, src.capital_deployment_protocol.capital_ramp_controller, src.capital_deployment_protocol.live_capital_switch, src.capital_deployment_protocol.regime_sensitive_position_sizing, src.capital_deployment_protocol.rollout_state_machine, src.capital_deployment_protocol.schemas, src.capital_deployment_protocol.state_persistence
- Classes: DeploymentOrchestrator
- Functions: __init__, process_daily_lifecycle, request_capital_execution
- Called services/storage signals: logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: API component.

### `src\capital_deployment_protocol\live_capital_switch.py`
- Lines: 42
- Purpose: API component.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging, src.capital_deployment_protocol.schemas
- Classes: LiveCapitalSwitch
- Functions: __init__, evaluate_safety_lock
- Called services/storage signals: logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: API component.

### `src\capital_deployment_protocol\regime_sensitive_position_sizing.py`
- Lines: 55
- Purpose: API component.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging, src.capital_deployment_protocol.schemas
- Classes: RegimeSensitivePositionSizing
- Functions: __init__, scale_position
- Called services/storage signals: logging.getLogger, self.regime_multipliers.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: API component.

### `src\capital_deployment_protocol\rollout_state_machine.py`
- Lines: 73
- Purpose: API component.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging, src.capital_deployment_protocol.schemas
- Classes: RolloutStateMachine
- Functions: __init__, evaluate_transition, _trigger_rollback
- Called services/storage signals: logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: API component.

### `src\capital_deployment_protocol\schemas.py`
- Lines: 46
- Purpose: API component.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: datetime, enum, pydantic
- Classes: RolloutPhase, HealthStatus, DeploymentState, CapitalAllocationRequest
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: API component.

### `src\capital_deployment_protocol\state_persistence.py`
- Lines: 141
- Purpose: API component.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: datetime, logging, pathlib, sqlite3, src.capital_deployment_protocol.schemas, typing
- Classes: none
- Functions: _get_conn, _ensure_tables, save_deployment_state, load_deployment_state, save_drift_budget, load_drift_budget
- Called services/storage signals: _get_conn, logging.getLogger, sqlite3.connect
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: API component.

### `src\capital_scaling_intelligence\__init__.py`
- Lines: 1
- Purpose: API component.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: API component.

### `src\capital_scaling_intelligence\acsi_engine.py`
- Lines: 95
- Purpose: API component.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging, src.capital_scaling_intelligence.capital_velocity_controller, src.capital_scaling_intelligence.growth_vs_risk_optimizer, src.capital_scaling_intelligence.long_horizon_ev_forecaster, src.capital_scaling_intelligence.regime_compounding_detector, src.capital_scaling_intelligence.schemas, typing
- Classes: ACSIEngine
- Functions: __init__, evaluate_capital_trajectory
- Called services/storage signals: logging.getLogger, system_inputs.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: API component.

### `src\capital_scaling_intelligence\acsi_simulation_lab.py`
- Lines: 55
- Purpose: Simulation/backtesting/replay component.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: asyncio, logging, src.capital_scaling_intelligence.acsi_engine, sys
- Classes: ACSISimulationLab
- Functions: async run_acsi_cycle
- Called services/storage signals: logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Simulation/backtesting/replay component.

### `src\capital_scaling_intelligence\capital_velocity_controller.py`
- Lines: 47
- Purpose: API component.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging
- Classes: CapitalVelocityController
- Functions: __init__, compute_safe_velocity
- Called services/storage signals: logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: API component.

### `src\capital_scaling_intelligence\growth_vs_risk_optimizer.py`
- Lines: 49
- Purpose: Risk, bankroll, staking, or exposure control logic.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging, src.capital_scaling_intelligence.schemas
- Classes: GrowthVsRiskOptimizer
- Functions: __init__, optimize_scaling_decision
- Called services/storage signals: logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Risk, bankroll, staking, or exposure control logic.

### `src\capital_scaling_intelligence\long_horizon_ev_forecaster.py`
- Lines: 44
- Purpose: API component.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging, math
- Classes: LongHorizonEVForecaster
- Functions: __init__, forecast_ev_trajectory
- Called services/storage signals: logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: API component.

### `src\capital_scaling_intelligence\regime_compounding_detector.py`
- Lines: 128
- Purpose: API component.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging, math, src.capital_scaling_intelligence.schemas, typing
- Classes: RegimeCompoundingDetector
- Functions: _sigmoid, detect_regime, _compute_decay_probability
- Called services/storage signals: logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: API component.

### `src\capital_scaling_intelligence\schemas.py`
- Lines: 29
- Purpose: API component.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: enum, pydantic
- Classes: CompoundingRegime, ScalingDecision, ACSIScalingState
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: API component.

### `src\clv_tracker.py`
- Lines: 179
- Purpose: Telemetry, CLV, audit, monitoring, or reporting component.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: csv, datetime, os, pandas, random, sqlite3, uuid
- Classes: none
- Functions: init_csv, record_bet, settle_bet, generate_report, scan_and_settle
- Called services/storage signals: sqlite3.connect
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Telemetry, CLV, audit, monitoring, or reporting component.

### `src\clv_updater.py`
- Lines: 128
- Purpose: Telemetry, CLV, audit, monitoring, or reporting component.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: dotenv, os, pandas, requests, sqlite3
- Classes: none
- Functions: fetch_closing_odds_from_api, update_clv
- Called services/storage signals: data.get, os.getenv, requests.get, sqlite3.connect
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Telemetry, CLV, audit, monitoring, or reporting component.

### `src\config\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\config\settings.py`
- Lines: 73
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: os, pathlib
- Classes: Settings
- Functions: ensure_directories
- Called services/storage signals: os.getenv
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\dashboard.py`
- Lines: 142
- Purpose: User-facing dashboard/server surface.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: datetime, os, pandas, plotly.express, sqlite3, streamlit
- Classes: none
- Functions: get_db_connection
- Called services/storage signals: get_db_connection, sqlite3.connect
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: User-facing dashboard/server surface.

### `src\data\advanced_fbref_scraper.py`
- Lines: 76
- Purpose: Data acquisition scraper/parser for sports, odds, lineups, or historical stats.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: pandas, soccerdata, time
- Classes: none
- Functions: scrape_advanced_tables
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Data acquisition scraper/parser for sports, odds, lineups, or historical stats.

### `src\data_acquisition\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\betarabia_scraper.py`
- Lines: 149
- Purpose: Data acquisition scraper/parser for sports, odds, lineups, or historical stats.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: asyncio, datetime, logging, market_mapper, playwright.async_api, typing, websocket_parser
- Classes: BetarabiaAPIClient
- Functions: __init__, async initialize, async _intercept_xhr_response, async _intercept_websocket, async _handle_ws_frame, _cache_canonical_events, get_latest_odds, async scrape_player_props, async close
- Called services/storage signals: async_playwright, logging.getLogger, self.get_latest_odds, self.playwright.chromium.launch, self.playwright.stop
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Data acquisition scraper/parser for sports, odds, lineups, or historical stats.

### `src\data_acquisition\clv_engine.py`
- Lines: 47
- Purpose: Telemetry, CLV, audit, monitoring, or reporting component.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging
- Classes: CLVEngine
- Functions: __init__, register_execution, record_closing_line
- Called services/storage signals: logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Telemetry, CLV, audit, monitoring, or reporting component.

### `src\data_acquisition\db_writer.py`
- Lines: 231
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: app_config, asyncio, datetime, json, logging, os, sqlite3, typing
- Classes: DBWriter
- Functions: init_db, __init__, _insert_lineups_sync, _insert_odds_sync, async insert_lineups, async insert_odds
- Called services/storage signals: logging.getLogger, odd.get, player.get, sqlite3.connect
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\dynamic_repricer.py`
- Lines: 124
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: event_dispatcher, formation_impact_engine, logging, math, src.model_runner, typing
- Classes: DynamicRepricingEngine
- Functions: __init__, async handle_lineup_event, _calculate_market_probs, get_fair_probability
- Called services/storage signals: adjusted_stats.get, changes.get, formation_impact_engine.get_multipliers, get, get_player_historical_stats, logging.getLogger, multipliers.get, player.get, self.fair_price_cache.get, stats.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\edge_engine.py`
- Lines: 99
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: dynamic_repricer, logging, src.portfolio_optimization.liquidity_impact_model, src.research.real_world_validation.execution_friction_analyzer, typing, websocket_parser
- Classes: MarketEdgeEngine
- Functions: __init__, evaluate_edge
- Called services/storage signals: friction_analyzer.get_expected_slippage, logging.getLogger, repricer.get_fair_probability
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\event_dispatcher.py`
- Lines: 146
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: asyncio, dataclasses, datetime, db_writer, lineup_change_detector, lineup_confidence_engine, logging, normalization_engine, player_position_normalizer, src.model_runner, typing, validation_engine
- Classes: LineupConfirmedEvent, EventDispatcher
- Functions: __init__, async trigger_pricing_pipeline, async handle_lineups_confirmed
- Called services/storage signals: asyncio.get_running_loop, get, lineup_payload.get, logging.getLogger, p.get, player.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\execution_queue.py`
- Lines: 96
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging, typing
- Classes: ExecutionRouteOptimizer
- Functions: __init__, add_to_queue, async flush_to_workers
- Called services/storage signals: edge_data.get, logging.getLogger, self.market_decay_rates.get, self.market_fill_probabilities.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\execution_simulator.py`
- Lines: 103
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging, random, simulation_clock, typing
- Classes: ExecutionSimulator
- Functions: __init__, attempt_execution
- Called services/storage signals: bet_payload.get, logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\expected_lineup_predictor.py`
- Lines: 40
- Purpose: Inference/prediction runner that loads models and produces priced markets or match predictions.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging, typing
- Classes: ExpectedLineupPredictor
- Functions: __init__, predict_starters
- Called services/storage signals: logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Inference/prediction runner that loads models and produces priced markets or match predictions.

### `src\data_acquisition\fixtures_monitor.py`
- Lines: 87
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: asyncio, datetime, event_dispatcher, lineup_scraper, logging
- Classes: FixturesMonitor
- Functions: __init__, add_fixture_to_monitor, _calculate_poll_interval, async monitor_loop
- Called services/storage signals: data.get, lineup_payload.get, logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\formation_impact_engine.py`
- Lines: 67
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging, typing
- Classes: FormationImpactEngine
- Functions: get_multipliers
- Called services/storage signals: FormationImpactEngine.IMPACT_MATRIX.get, formation_impacts.get, logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\historical_batch_simulator.py`
- Lines: 166
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: app_config, asyncio, datetime, gzip, json, logging, os, random, src.data_acquisition.dynamic_repricer, src.data_acquisition.edge_engine, src.data_acquisition.event_dispatcher, src.data_acquisition.execution_queue, src.data_acquisition.execution_simulator, src.data_acquisition.replay_analytics, src.data_acquisition.replay_engine, src.data_acquisition.simulation_clock, src.data_acquisition.websocket_parser, sys
- Classes: none
- Functions: generate_batch_data, async run_batch_simulation
- Called services/storage signals: edge_data.get, logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\latency_stress_test.py`
- Lines: 120
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: asyncio, logging, os, random, src.data_acquisition.execution_simulator, src.data_acquisition.replay_analytics, sys
- Classes: none
- Functions: generate_stress_test_edges, async run_latency_stress_test, get_rate
- Called services/storage signals: get_rate, logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\latency_telemetry.py`
- Lines: 72
- Purpose: Telemetry, CLV, audit, monitoring, or reporting component.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging, time, typing, uuid
- Classes: LatencyTelemetry
- Functions: __init__, start_execution, mark, finalize
- Called services/storage signals: bet_payload.get, logging.getLogger, timestamps.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Telemetry, CLV, audit, monitoring, or reporting component.

### `src\data_acquisition\lineup_change_detector.py`
- Lines: 112
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging, typing
- Classes: LineupChangeDetector
- Functions: __init__, detect_changes, _update_state
- Called services/storage signals: logging.getLogger, p.get, self.last_known_formation.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\lineup_confidence_engine.py`
- Lines: 65
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: lineup_sources, logging, typing
- Classes: LineupConfidenceEngine
- Functions: __init__, compute_confidence
- Called services/storage signals: lineup_registry.get_source_metrics, logging.getLogger, p.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\lineup_scraper.py`
- Lines: 33
- Purpose: Data acquisition scraper/parser for sports, odds, lineups, or historical stats.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging, typing
- Classes: LineupScraper
- Functions: __init__, async fetch_official_lineups
- Called services/storage signals: logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Data acquisition scraper/parser for sports, odds, lineups, or historical stats.

### `src\data_acquisition\lineup_sources.py`
- Lines: 23
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: LineupSourceRegistry
- Functions: get_source_metrics
- Called services/storage signals: LINEUP_SOURCES.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\lineup_telemetry.py`
- Lines: 67
- Purpose: Telemetry, CLV, audit, monitoring, or reporting component.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: datetime, logging
- Classes: LineupTelemetry
- Functions: __init__, record_latency, track_market_reaction
- Called services/storage signals: logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Telemetry, CLV, audit, monitoring, or reporting component.

### `src\data_acquisition\live_execution\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\live_execution\adaptive_layer\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\live_execution\adaptive_layer\adaptive_events.py`
- Lines: 45
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: dataclasses
- Classes: MarketVelocityChangedEvent, MarketRegimeChangedEvent, EdgeDecayUpdatedEvent, ExecutionFailureEvent, ExecutionSurvivabilityUpdatedEvent
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\live_execution\adaptive_layer\adaptive_execution_engine.py`
- Lines: 97
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: autonomous_queue_optimizer, autonomous_stake_allocator, live_execution_feedback_loop, logging, typing
- Classes: AdaptiveExecutionEngine
- Functions: __init__, evaluate_and_route, async flush_and_execute_batch
- Called services/storage signals: logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\live_execution\adaptive_layer\adaptive_latency_controller.py`
- Lines: 30
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging
- Classes: AdaptiveLatencyController
- Functions: __init__, get_latency_profile
- Called services/storage signals: logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\live_execution\adaptive_layer\adaptive_simulation_harness.py`
- Lines: 135
- Purpose: Simulation/backtesting/replay component.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: asyncio, datetime, logging, os, random, src.data_acquisition.live_execution.adaptive_layer.adaptive_events, src.data_acquisition.live_execution.adaptive_layer.adaptive_execution_engine, src.data_acquisition.live_execution.adaptive_layer.edge_decay_predictor, src.data_acquisition.live_execution.adaptive_layer.execution_failure_classifier, src.data_acquisition.live_execution.adaptive_layer.execution_heatmap_engine, src.data_acquisition.live_execution.adaptive_layer.market_regime_classifier, src.data_acquisition.live_execution.adaptive_layer.market_velocity_tracker, sys, uuid
- Classes: MockEvent
- Functions: mock_live_trader, async run_adaptive_simulation, __init__
- Called services/storage signals: logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Simulation/backtesting/replay component.

### `src\data_acquisition\live_execution\adaptive_layer\autonomous_queue_optimizer.py`
- Lines: 81
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: edge_decay_predictor, execution_survivability_model, logging, market_regime_classifier, smart_market_skipper, typing
- Classes: AutonomousQueueOptimizer
- Functions: __init__, evaluate_and_queue
- Called services/storage signals: bet_metadata.get, get, logging.getLogger, regime_classifier.regimes.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\live_execution\adaptive_layer\autonomous_stake_allocator.py`
- Lines: 65
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging
- Classes: AutonomousStakeAllocator
- Functions: __init__, allocate_stake
- Called services/storage signals: logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\live_execution\adaptive_layer\edge_decay_predictor.py`
- Lines: 62
- Purpose: Inference/prediction runner that loads models and produces priced markets or match predictions.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging, math, typing
- Classes: EdgeDecayPredictor
- Functions: __init__, predict_remaining_edge, update_base_half_life
- Called services/storage signals: logging.getLogger, self.base_half_life_sec.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Inference/prediction runner that loads models and produces priced markets or match predictions.

### `src\data_acquisition\live_execution\adaptive_layer\execution_behavior_memory.py`
- Lines: 114
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: app_config, logging, os, sqlite3, typing
- Classes: ExecutionBehaviorMemory
- Functions: __init__, _init_db, record_execution, get_historical_fill_rate
- Called services/storage signals: exec_data.get, logging.getLogger, sqlite3.connect
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\live_execution\adaptive_layer\execution_failure_classifier.py`
- Lines: 46
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging, typing
- Classes: ExecutionFailureClassifier
- Functions: __init__, classify
- Called services/storage signals: execution_result.get, logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\live_execution\adaptive_layer\execution_heatmap_engine.py`
- Lines: 55
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: app_config, logging, os, pandas, sqlite3
- Classes: ExecutionHeatmapEngine
- Functions: __init__, generate_fill_rate_heatmap
- Called services/storage signals: logging.getLogger, sqlite3.connect
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\live_execution\adaptive_layer\execution_survivability_model.py`
- Lines: 46
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: execution_behavior_memory, logging
- Classes: ExecutionSurvivabilityModel
- Functions: __init__, estimate_survivability
- Called services/storage signals: behavior_memory.get_historical_fill_rate, logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\live_execution\adaptive_layer\live_execution_feedback_loop.py`
- Lines: 62
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: adaptive_events, edge_decay_predictor, execution_behavior_memory, logging, typing
- Classes: LiveExecutionFeedbackLoop
- Functions: __init__, process_execution_outcome
- Called services/storage signals: exec_data.get, logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\live_execution\adaptive_layer\market_regime_classifier.py`
- Lines: 60
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: adaptive_events, logging, typing
- Classes: MarketRegimeClassifier
- Functions: __init__, classify
- Called services/storage signals: get, logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\live_execution\adaptive_layer\market_velocity_tracker.py`
- Lines: 71
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: adaptive_events, collections, logging, time, typing
- Classes: MarketVelocityTracker
- Functions: __init__, record_odds_update
- Called services/storage signals: logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\live_execution\adaptive_layer\smart_market_skipper.py`
- Lines: 37
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging
- Classes: SmartMarketSkipper
- Functions: __init__, should_skip
- Called services/storage signals: logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\live_execution\dom_interaction_engine.py`
- Lines: 80
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: asyncio, logging, playwright.async_api
- Classes: DomInteractionEngine
- Functions: __init__, async safe_click, async safe_fill
- Called services/storage signals: logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\live_execution\live_paper_trader.py`
- Lines: 113
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: asyncio, logging, os, playwright.async_api, src.data_acquisition.latency_telemetry, src.data_acquisition.live_execution.selector_registry, sys, typing
- Classes: LivePaperTrader
- Functions: async run_paper_trader_test, __init__, async initialize_warm_session, async execute_paper_trade, async shutdown
- Called services/storage signals: async_playwright, logging.getLogger, registry.get, self.playwright.chromium.launch, self.playwright.stop
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\live_execution\predictive_layer\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\live_execution\predictive_layer\execution_policy_agent.py`
- Lines: 52
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging, suspension_probability_model
- Classes: ExecutionPolicyAgent
- Functions: __init__, decide_policy
- Called services/storage signals: logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\live_execution\predictive_layer\execution_research_lab.py`
- Lines: 76
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: asyncio, logging, os, src.data_acquisition.live_execution.predictive_layer.execution_policy_agent, src.data_acquisition.live_execution.predictive_layer.market_movement_forecaster, src.data_acquisition.live_execution.predictive_layer.real_time_edge_decay_forecaster, src.data_acquisition.live_execution.predictive_layer.suspension_probability_model, sys
- Classes: ExecutionResearchLab
- Functions: __init__, async run_policy_ab_test
- Called services/storage signals: logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\live_execution\predictive_layer\market_microstructure_embeddings.py`
- Lines: 55
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging, numpy
- Classes: MarketMicrostructureEmbeddings
- Functions: __init__, generate_embedding
- Called services/storage signals: logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\live_execution\predictive_layer\market_movement_forecaster.py`
- Lines: 59
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging, typing
- Classes: MarketMovementForecaster
- Functions: __init__, forecast_movement
- Called services/storage signals: logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\live_execution\predictive_layer\real_time_edge_decay_forecaster.py`
- Lines: 43
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging, src.data_acquisition.live_execution.adaptive_layer.edge_decay_predictor
- Classes: RealTimeEdgeDecayForecaster
- Functions: __init__, forecast_edge_at_execution
- Called services/storage signals: logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\live_execution\predictive_layer\suspension_probability_model.py`
- Lines: 62
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging, math
- Classes: SuspensionProbabilityModel
- Functions: __init__, predict_suspension_probability
- Called services/storage signals: logging.getLogger, self.market_fragility.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\live_execution\selector_registry.py`
- Lines: 47
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging
- Classes: SelectorRegistry
- Functions: __init__, get
- Called services/storage signals: logging.getLogger, self.SELECTORS.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\live_execution\shadow_mode\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\live_execution\shadow_mode\account_behavior_profile.py`
- Lines: 71
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: app_config, logging, os, sqlite3, time
- Classes: AccountBehaviorProfile
- Functions: __init__, _init_db, log_session_telemetry
- Called services/storage signals: logging.getLogger, sqlite3.connect
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\live_execution\shadow_mode\browser_rotation_controller.py`
- Lines: 42
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: asyncio, logging
- Classes: BrowserRotationController
- Functions: __init__, async rotate_session
- Called services/storage signals: logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\live_execution\shadow_mode\execution_drift_monitor.py`
- Lines: 40
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: collections, logging
- Classes: ExecutionDriftMonitor
- Functions: __init__, log_execution_latency, check_for_drift
- Called services/storage signals: logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\live_execution\shadow_mode\self_healing_browser_manager.py`
- Lines: 63
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging, src.data_acquisition.live_execution.shadow_mode.browser_rotation_controller, time
- Classes: SelfHealingBrowserManager
- Functions: __init__, async monitor_health, async trigger_rotation, async hard_reset_browser
- Called services/storage signals: logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\live_execution\shadow_mode\shadow_deployment_lab.py`
- Lines: 63
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: asyncio, logging, os, random, src.data_acquisition.live_execution.shadow_mode.account_behavior_profile, src.data_acquisition.live_execution.shadow_mode.execution_drift_monitor, src.data_acquisition.live_execution.shadow_mode.sportsbook_adversarial_model, sys
- Classes: ShadowDeploymentLab
- Functions: async run_longitudinal_test
- Called services/storage signals: logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\live_execution\shadow_mode\shadow_execution_mode.py`
- Lines: 82
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: asyncio, logging, src.data_acquisition.latency_telemetry, src.data_acquisition.live_execution.dom_interaction_engine, src.data_acquisition.live_execution.selector_registry, typing
- Classes: ShadowExecutionMode
- Functions: __init__, async execute_shadow_trade
- Called services/storage signals: logging.getLogger, registry.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\live_execution\shadow_mode\sportsbook_adversarial_model.py`
- Lines: 46
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging
- Classes: SportsbookAdversarialModel
- Functions: __init__, evaluate_adversarial_risk
- Called services/storage signals: logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\live_execution_manager.py`
- Lines: 109
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: asyncio, latency_telemetry, logging, typing
- Classes: LiveExecutionManager
- Functions: __init__, async preload_market_state, async execute_parallel, async _fast_lane_worker, async _batch_lane_worker
- Called services/storage signals: logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\market_mapper.py`
- Lines: 58
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: MarketMapper
- Functions: map_market_name
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\normalization_engine.py`
- Lines: 59
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: rapidfuzz, re, unidecode
- Classes: NormalizationEngine
- Functions: __init__, normalize_name, fuzzy_match
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\odds_monitor.py`
- Lines: 60
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: asyncio, betarabia_scraper, db_writer, logging, typing, validation_engine
- Classes: OddsMonitor
- Functions: __init__, start_monitoring_fixture, stop_monitoring_fixture, async monitor_loop
- Called services/storage signals: betarabia_scraper.get_latest_odds, logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\player_position_normalizer.py`
- Lines: 40
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: PlayerPositionNormalizer
- Functions: normalize
- Called services/storage signals: POSITION_MAP.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\raw_frames\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\raw_frames\BATCH_FIX_0\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\raw_frames\BATCH_FIX_1\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\raw_frames\BATCH_FIX_10\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\raw_frames\BATCH_FIX_11\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\raw_frames\BATCH_FIX_12\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\raw_frames\BATCH_FIX_13\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\raw_frames\BATCH_FIX_14\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\raw_frames\BATCH_FIX_15\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\raw_frames\BATCH_FIX_16\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\raw_frames\BATCH_FIX_17\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\raw_frames\BATCH_FIX_18\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\raw_frames\BATCH_FIX_19\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\raw_frames\BATCH_FIX_2\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\raw_frames\BATCH_FIX_20\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\raw_frames\BATCH_FIX_21\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\raw_frames\BATCH_FIX_22\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\raw_frames\BATCH_FIX_23\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\raw_frames\BATCH_FIX_24\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\raw_frames\BATCH_FIX_25\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\raw_frames\BATCH_FIX_26\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\raw_frames\BATCH_FIX_27\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\raw_frames\BATCH_FIX_28\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\raw_frames\BATCH_FIX_29\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\raw_frames\BATCH_FIX_3\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\raw_frames\BATCH_FIX_30\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\raw_frames\BATCH_FIX_31\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\raw_frames\BATCH_FIX_32\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\raw_frames\BATCH_FIX_33\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\raw_frames\BATCH_FIX_34\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\raw_frames\BATCH_FIX_35\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\raw_frames\BATCH_FIX_36\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\raw_frames\BATCH_FIX_37\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\raw_frames\BATCH_FIX_38\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\raw_frames\BATCH_FIX_39\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\raw_frames\BATCH_FIX_4\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\raw_frames\BATCH_FIX_40\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\raw_frames\BATCH_FIX_41\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\raw_frames\BATCH_FIX_42\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\raw_frames\BATCH_FIX_43\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\raw_frames\BATCH_FIX_44\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\raw_frames\BATCH_FIX_45\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\raw_frames\BATCH_FIX_46\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\raw_frames\BATCH_FIX_47\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\raw_frames\BATCH_FIX_48\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\raw_frames\BATCH_FIX_49\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\raw_frames\BATCH_FIX_5\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\raw_frames\BATCH_FIX_6\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\raw_frames\BATCH_FIX_7\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\raw_frames\BATCH_FIX_8\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\raw_frames\BATCH_FIX_9\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\raw_frames\MOCK_FIX_1\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\replay_analytics.py`
- Lines: 154
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: collections, logging, statistics, typing
- Classes: ReplayAnalyticsDashboard
- Functions: __init__, record_attempt, generate_report
- Called services/storage signals: logging.getLogger, result.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\replay_engine.py`
- Lines: 116
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: app_config, datetime, gzip, logging, os, replay_analytics, simulation_clock, websocket_parser
- Classes: ReplayEngine
- Functions: __init__, _load_historical_frames, async run_simulation
- Called services/storage signals: logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\risk_engine.py`
- Lines: 84
- Purpose: Risk, bankroll, staking, or exposure control logic.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging, typing
- Classes: PortfolioRiskEngine
- Functions: __init__, evaluate_risk, register_executed_bet
- Called services/storage signals: logging.getLogger, self.match_exposure.get, self.player_exposure.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Risk, bankroll, staking, or exposure control logic.

### `src\data_acquisition\run_trial_simulation.py`
- Lines: 162
- Purpose: Simulation/backtesting/replay component.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: app_config, asyncio, datetime, gzip, json, logging, os, src.data_acquisition.dynamic_repricer, src.data_acquisition.edge_engine, src.data_acquisition.event_dispatcher, src.data_acquisition.execution_queue, src.data_acquisition.execution_simulator, src.data_acquisition.replay_analytics, src.data_acquisition.replay_engine, src.data_acquisition.simulation_clock, src.data_acquisition.websocket_parser, sys
- Classes: none
- Functions: generate_mock_data, async run_single_match_validation
- Called services/storage signals: edge_data.get, logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Simulation/backtesting/replay component.

### `src\data_acquisition\settlement_engine.py`
- Lines: 67
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging
- Classes: SettlementEngine
- Functions: __init__, settle_bet, run_calibration_report
- Called services/storage signals: logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\simulation_clock.py`
- Lines: 49
- Purpose: Simulation/backtesting/replay component.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: datetime, logging
- Classes: SimulationClock
- Functions: __init__, enable_simulation_mode, disable_simulation_mode, advance_to, now
- Called services/storage signals: logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Simulation/backtesting/replay component.

### `src\data_acquisition\validation_engine.py`
- Lines: 67
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging, typing
- Classes: ValidationEngine
- Functions: validate_lineup, validate_odds
- Called services/storage signals: lineup_payload.get, logging.getLogger, odd.get, p.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_acquisition\websocket_parser.py`
- Lines: 220
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: app_config, dataclasses, datetime, gzip, hashlib, json, logging, market_mapper, normalization_engine, os, typing
- Classes: CanonicalOddsEvent, BetarabiaFrameParser
- Functions: __init__, _archive_raw_frame, _fingerprint_schema, _validate_integrity, _apply_delta_patch, parse_frame
- Called services/storage signals: data.get, full_state.get, logging.getLogger, self.sequence_tracker.get, update.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_fetcher_all_leagues.py`
- Lines: 272
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: os, pandas, requests, sqlite3, sys, time
- Classes: none
- Functions: init_db, check_api_status, get_all_leagues, fetch_player_page, process_players, save_to_csv, run_sync
- Called services/storage signals: cards.get, data.get, games.get, get, get_all_leagues, goals.get, info.get, p.get, paging.get, passes.get, reqs.get, requests.get, shots.get, sqlite3.connect, st.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\data_pipeline.py`
- Lines: 837
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: datetime, dotenv, json, logging, os, pandas, requests, sqlite3, statsbombpy, time
- Classes: none
- Functions: init_db, upsert_player, upsert_team, safe_p90, now_str, fetch_statsbomb, _map_sb_position, _calc_minutes, _apif_cached_get, fetch_api_football, _map_apif_position, enrich_from_thesportsdb, _map_tsdb_position, fetch_statsbomb_github_fallback, export_to_csv, run_pipeline
- Called services/storage signals: _apif_cached_get, data.get, events_df.get, get, logging.getLogger, m.get, os.environ.get, p_events.get, player.get, player_info.get, player_row.get, requests.get, sqlite3.connect, squad_data.get, squad_entry.get, team.get, team_entry.get, team_info.get, teams_data.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\database\__init__.py`
- Lines: 1
- Purpose: Database model, migration, or persistence utility.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Database model, migration, or persistence utility.

### `src\database\migrate.py`
- Lines: 74
- Purpose: Database model, migration, or persistence utility.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: database.models, os, sqlalchemy, sys
- Classes: none
- Functions: get_database_url, run_migrations
- Called services/storage signals: engine.connect, get_database_url, inspector.get_table_names, os.environ.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Database model, migration, or persistence utility.

### `src\database\models.py`
- Lines: 481
- Purpose: Database model, migration, or persistence utility.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: datetime, sqlalchemy, sqlalchemy.orm
- Classes: Fixture, OddsTick, OddsSnapshot, LineMovement, WebSocketEvent, SessionLog, BrowserHealth, IngestionMetrics, Odds, Prediction, Bet, BankrollSnapshot
- Functions: __repr__, __repr__, __repr__, __repr__, __repr__, __repr__, __repr__, __repr__, __repr__, __repr__, __repr__, __repr__
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Database model, migration, or persistence utility.

### `src\debug_backtest.py`
- Lines: 123
- Purpose: Simulation/backtesting/replay component.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: lightgbm, pandas, pricing_engine, sys, utils
- Classes: none
- Functions: none
- Called services/storage signals: pos_map.get, row.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Simulation/backtesting/replay component.

### `src\downloaded_files\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\engine_bettor.py`
- Lines: 443
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: datetime, engine_predictor, os, pandas, requests, sqlite3
- Classes: none
- Functions: strip_vig, implied_prob, expected_value, edge_pct, fetch_bookmaker_odds, load_local_db_odds, identify_value_bets, run_betting_engine
- Called services/storage signals: MARKET_MAP.get, bet.get, bk.get, bk_data.get, data.get, entry.get, get, requests.get, row.get, sqlite3.connect, val.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\engine_predictor.py`
- Lines: 307
- Purpose: Inference/prediction runner that loads models and produces priced markets or match predictions.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: datetime, lightgbm, numpy, os, pandas, re, requests, unicodedata
- Classes: none
- Functions: normalize, load_dataset, load_models, get_todays_fixtures, simulate_player, run_predictions
- Called services/storage signals: TEAM_TO_NATION.get, get, get_todays_fixtures, requests.get, result.get, row.get, target.replace
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Inference/prediction runner that loads models and produces priced markets or match predictions.

### `src\engine_staker.py`
- Lines: 411
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: datetime, engine_bettor, engine_predictor, io, os, pandas, sqlite3, sys
- Classes: none
- Functions: get_or_init_bankroll, update_exposure, record_settlement, kelly_stake_pct, get_stake, run_stake_sizer
- Called services/storage signals: bet.get, get_or_init_bankroll, get_stake, match_committed.get, sizing.get, sqlite3.connect
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\execution_cluster\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\execution_cluster\actor_orchestrator.py`
- Lines: 93
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: asyncio, logging, typing
- Classes: CircuitBreaker, ActorOrchestrator
- Functions: __init__, record_failure, record_success, can_execute, __init__, _get_circuit_breaker, async execute_task
- Called services/storage signals: asyncio.get_event_loop, logging.getLogger, result.get, self._get_circuit_breaker
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\execution_engine.py`
- Lines: 319
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: account_manager, alerter, bankroll_tracker, bet_logger, clv_updater, datetime, dotenv, kelly_calculator, lineup_parser, odds_feed, os, role_baseline_builder, sqlite3, time, utils, uuid
- Classes: none
- Functions: place_bet, settle_bet, initialize_all
- Called services/storage signals: get_best_book_for_stake, get_recommended_stake, get_status, sqlite3.connect, update_account_post_bet
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\features\availability.py`
- Lines: 87
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: numpy, pandas
- Classes: none
- Functions: calculate_availability_features
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\features\fatigue.py`
- Lines: 133
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: numpy, pandas
- Classes: none
- Functions: calculate_fatigue_features, haversine
- Called services/storage signals: all_coords.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\features\generate_all.py`
- Lines: 146
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: availability, fatigue, market_intelligence, opponent_features, os, pandas, player_rolling_form, referee, sys, team_tactics, venue_effects, weather
- Classes: none
- Functions: main
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\features\market_intelligence.py`
- Lines: 47
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: numpy, pandas
- Classes: none
- Functions: calculate_market_intelligence
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\features\opponent_features.py`
- Lines: 144
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: pandas
- Classes: none
- Functions: calculate_opponent_features, calculate_rolling
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\features\player_rolling_form.py`
- Lines: 64
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: pandas
- Classes: none
- Functions: calculate_player_rolling_form
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\features\referee.py`
- Lines: 69
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: pandas
- Classes: none
- Functions: calculate_referee_features
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\features\team_tactics.py`
- Lines: 99
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: pandas
- Classes: none
- Functions: calculate_team_tactics, calculate_rolling
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\features\venue_effects.py`
- Lines: 103
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: numpy, pandas
- Classes: none
- Functions: calculate_venue_effects
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\features\weather.py`
- Lines: 116
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: pandas, requests
- Classes: none
- Functions: fetch_weather_data, integrate_weather_features
- Called services/storage signals: all_coords.get, requests.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\fix_data_integrity.py`
- Lines: 62
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: io, os, pandas, sys
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\fix_wc_name_mapping.py`
- Lines: 137
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: io, pandas, re, sys, unicodedata
- Classes: none
- Functions: normalize_name, find_match
- Called services/storage signals: last_name_index.get, row.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\free_scraper_module.py`
- Lines: 166
- Purpose: Data acquisition scraper/parser for sports, odds, lineups, or historical stats.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: datetime, json, seleniumbase, time
- Classes: none
- Functions: get_todays_fixtures_free, get_fixture_lineups_free, get_fixture_stats_free, get_fixture_lineups_batch
- Called services/storage signals: data.get, e.get, get, p.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Data acquisition scraper/parser for sports, odds, lineups, or historical stats.

### `src\full_system_audit.py`
- Lines: 303
- Purpose: Telemetry, CLV, audit, monitoring, or reporting component.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: io, json, os, pandas, sys
- Classes: none
- Functions: none
- Called services/storage signals: os.path.getsize, target.replace, target_model_map.items, v.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Telemetry, CLV, audit, monitoring, or reporting component.

### `src\generate_datasets_and_reports.py`
- Lines: 157
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: os, pandas
- Classes: none
- Functions: generate_datasets
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\generate_feature_importance.py`
- Lines: 67
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: lightgbm, os, pandas
- Classes: none
- Functions: generate_report
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\generate_predictions.py`
- Lines: 337
- Purpose: Inference/prediction runner that loads models and produces priced markets or match predictions.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: json, logging, math, model_runner, os, pandas, pickle, sys
- Classes: none
- Functions: generate_predictions
- Called services/storage signals: BestMarket_V.get, game.get, get_player_historical_stats, logging.getLogger, pickle.load, stats.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Inference/prediction runner that loads models and produces priced markets or match predictions.

### `src\get_real_pass_data.py`
- Lines: 148
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: app_config, os, pandas, statsbombpy
- Classes: none
- Functions: none
- Called services/storage signals: events.get, get, match.get, player.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\goal_scraper.py`
- Lines: 141
- Purpose: Data acquisition scraper/parser for sports, odds, lineups, or historical stats.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: io, os, pandas, soccerdata, sys, time, traceback
- Classes: none
- Functions: clean_df, get_existing_leagues, scrape_league, main
- Called services/storage signals: get_existing_leagues
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Data acquisition scraper/parser for sports, odds, lineups, or historical stats.

### `src\heartbeat.py`
- Lines: 52
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: alerter, psutil, requests, time
- Classes: none
- Functions: ping_api, check_process_alive, monitor
- Called services/storage signals: requests.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\hyperparameter_optimization.py`
- Lines: 116
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: lightgbm, numpy, os, pandas, sklearn.metrics, sklearn.model_selection
- Classes: none
- Functions: optimize
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\inject_real_odds.py`
- Lines: 52
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: json, sqlite3
- Classes: none
- Functions: run
- Called services/storage signals: data.get, odd_data.get, r.get, sqlite3.connect
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\inspect_odds.py`
- Lines: 18
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: requests
- Classes: none
- Functions: none
- Called services/storage signals: b.get, data.get, get, requests.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\institutional_deployment_lab.py`
- Lines: 88
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: asyncio, logging, numpy, os, src.adversarial_detection.hidden_markov_throttle_detector, src.execution_cluster.actor_orchestrator, src.meta_research.meta_research_governor, src.ml.online_learning.concept_drift_monitor, src.risk_engine.conditional_var_simulator, sys
- Classes: InstitutionalDeploymentLab
- Functions: async run_institutional_ecosystem, async mock_fail
- Called services/storage signals: hmm_detector.get_restriction_probability, logging.getLogger, meta_governor.get_allocated_weight
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\kelly_calculator.py`
- Lines: 76
- Purpose: Risk, bankroll, staking, or exposure control logic.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: fractional_kelly, get_recommended_stake
- Called services/storage signals: get_recommended_stake
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Risk, bankroll, staking, or exposure control logic.

### `src\lineup_monitor.py`
- Lines: 255
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: aiohttp, argparse, asyncio, csv, datetime, dotenv, lineup_parser, model_runner, os, role_baseline_builder, role_shift_detector
- Classes: none
- Functions: init_log_file, log_latency, async fetch_lineup, process_lineup_pipeline, async monitor_match
- Called services/storage signals: POSITION_TO_ROLE.get, data.get, entry.get, get, os.getenv, p.get, s.get, session.get, t.get, team_data.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\lineup_parser.py`
- Lines: 214
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: os, sqlite3
- Classes: none
- Functions: init_db, parse_and_store_lineup, _insert_players
- Called services/storage signals: POSITION_TO_ROLE.get, api_team_data.get, entry.get, get, p.get, sqlite3.connect
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\live_dashboard_server.py`
- Lines: 821
- Purpose: User-facing dashboard/server surface.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: bankroll_tracker, bet_logger, datetime, flask, json, live_predictions_daemon, os, requests, sqlite3, threading
- Classes: none
- Functions: query_db, index, get_state, get_bankroll, get_stair_balance, get_tracker, get_performance, get_stair_bets, settle_bet, place_bet, manage_settings, trigger_recalibration, get_comparisons_list, get_comparison, init_databases, start_background_prediction_worker, summarize
- Called services/storage signals: Flask, data.get, extra.get, fixture_obj.get, get, m.get, os.getenv, request.args.get, requests.get, sqlite3.connect, wallet.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: User-facing dashboard/server surface.

### `src\live_game_test.py`
- Lines: 155
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: asyncio, logging, os, random, src.data_acquisition.live_execution.predictive_layer.execution_policy_agent, src.portfolio_optimization.capital_allocation_engine, sys
- Classes: TodaysGamesSimulation
- Functions: async run_live_feed
- Called services/storage signals: logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\live_operations\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\live_operations\account_health_engine.py`
- Lines: 117
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: datetime, logging, os, sqlite3, sys
- Classes: none
- Functions: init_db, update_health, get_latest_scores
- Called services/storage signals: get_latest_scores, logging.getLogger, sqlite3.connect
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\live_operations\alerting_system.py`
- Lines: 109
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: datetime, json, logging, os, sys
- Classes: none
- Functions: fire_alert, get_recent_alerts, alert_kill_switch, alert_edge_collapse, alert_drawdown, alert_account_danger
- Called services/storage signals: SEVERITY.get, get_recent_alerts, logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\live_operations\edge_decay_live.py`
- Lines: 101
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: datetime, logging, os, sqlite3, sys
- Classes: none
- Functions: init_db, record_snapshot, get_avg_half_life
- Called services/storage signals: get_avg_half_life, logging.getLogger, sqlite3.connect
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\live_operations\live_clv_tracker.py`
- Lines: 66
- Purpose: Telemetry, CLV, audit, monitoring, or reporting component.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: datetime, os, sqlite3, sys
- Classes: none
- Functions: init_db, record_clv, get_rolling_clv
- Called services/storage signals: get_rolling_clv, sqlite3.connect
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Telemetry, CLV, audit, monitoring, or reporting component.

### `src\live_operations\shadow_deployment_orchestrator.py`
- Lines: 142
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: datetime, json, logging, os, sqlite3, sys
- Classes: none
- Functions: init_db, record_signal, settle_bet, get_summary, run_from_todays_bets
- Called services/storage signals: get_summary, logging.getLogger, sqlite3.connect
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\live_predictions_daemon.py`
- Lines: 2244
- Purpose: Inference/prediction runner that loads models and produces priced markets or match predictions.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: bankroll_tracker, datetime, free_scraper_module, joblib, json, math, models.calibration_engine, numpy, os, pandas, re, requests, risk_engine.no_bet_filter, seleniumbase, sqlite3, subprocess, sys, telemetry_warehouse.clv_tracker, time, unicodedata, uuid
- Classes: none
- Functions: print, initialize_deepfield_modules, clean_name, initialize_caches, load_player_database, get_predicted_lineup, log_prediction_to_db, load_predictions_from_db, get_player_rolling_stats, predict_match, update_markdown_artifact, load_settings, get_match_score, fuzzy_match_teams, find_betarabia_odds, log_ai_bet, settle_open_bets, update_dashboard_json, refresh_completed_comparisons, init_stair_ai_agent, run_daemon, poisson_prob, get_tokens, clean_name
- Called services/storage signals: all_stats.get, batch_lineups.get, comp_match.get, data.get, dp.get, e.get, extra.get, g.get, get, get_fixture_lineups_batch, get_fixture_stats_free, get_match_score, get_player_rolling_stats, get_predicted_lineup, get_todays_fixtures, get_tokens, group.get, item.get, joblib.load, league_elo_map.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Inference/prediction runner that loads models and produces priced markets or match predictions.

### `src\match_odds_evaluator.py`
- Lines: 223
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: engine_bettor, engine_predictor, io, pandas, scipy.stats, sys
- Classes: none
- Functions: aggregate_team_xg, compute_match_probs, find_match_value_bets
- Called services/storage signals: btts.get, dc.get, get, match_xg.get, mw.get, odds_data.get, ou.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\match_simulation_engine.py`
- Lines: 320
- Purpose: Simulation/backtesting/replay component.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: io, lightgbm, numpy, os, pandas, re, sys, unicodedata, warnings
- Classes: none
- Functions: build_features, load_models, get_team_players, simulate_match, run_team_simulation, calculate_ev, generate_report, main, normalize
- Called services/storage signals: get_team_players, row.get, target.replace
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Simulation/backtesting/replay component.

### `src\match_simulator.py`
- Lines: 214
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: json, numpy, pandas, typing
- Classes: MatchSimulator
- Functions: __init__, _poisson, _binomial, simulate_player, simulate_match, _player_output
- Called services/storage signals: player.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\meta_research\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\meta_research\meta_research_governor.py`
- Lines: 65
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging, typing
- Classes: MetaResearchGovernor
- Functions: __init__, evaluate_strategy_health, get_allocated_weight
- Called services/storage signals: logging.getLogger, self.strategy_registry.get, strat.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\migrate_bet_log.py`
- Lines: 30
- Purpose: Database model, migration, or persistence utility.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: sqlite3
- Classes: none
- Functions: none
- Called services/storage signals: sqlite3.connect
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Database model, migration, or persistence utility.

### `src\minor_league_scraper_2025.py`
- Lines: 178
- Purpose: Data acquisition scraper/parser for sports, odds, lineups, or historical stats.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: json, os, pandas, seleniumbase, time
- Classes: none
- Functions: extract_json, get_2025_season_id, get_events_for_season, get_player_statistics_for_event, main
- Called services/storage signals: TARGET_LEAGUES.items, data.get, event.get, get, get_2025_season_id, get_events_for_season, get_player_statistics_for_event, p.get, p_info.get, s.get, stats.get, team_data.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Data acquisition scraper/parser for sports, odds, lineups, or historical stats.

### `src\ml\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\ml\online_learning\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\ml\online_learning\concept_drift_monitor.py`
- Lines: 102
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging, numpy, scipy.stats, typing
- Classes: ConceptDriftMonitor
- Functions: __init__, calculate_psi, calculate_kl_divergence, evaluate_drift, get_bucket_proportions
- Called services/storage signals: get_bucket_proportions, logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\model_comparison.py`
- Lines: 211
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: lightgbm, numpy, os, pandas, sklearn.ensemble, sklearn.linear_model, sklearn.metrics, sklearn.model_selection, time, warnings, xgboost
- Classes: none
- Functions: load_and_engineer_features, train_and_evaluate, generate_report
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\model_runner.py`
- Lines: 538
- Purpose: Inference/prediction runner that loads models and produces priced markets or match predictions.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: app_config, datetime, dotenv, execution_engine, lightgbm, math, os, pandas, pickle, pricing_engine, sqlite3, sys, time, unidecode
- Classes: none
- Functions: load_models, get_player_historical_stats, get_opponent_profile, get_current_odds, safe_float, build_feature_vector, poisson_prob_ge, run_for_match
- Called services/storage signals: get_current_odds, get_opponent_profile, get_player_historical_stats, pickle.load, position_map.get, sqlite3.connect, stats.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Inference/prediction runner that loads models and produces priced markets or match predictions.

### `src\model_runner_v2.py`
- Lines: 494
- Purpose: Inference/prediction runner that loads models and produces priced markets or match predictions.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: datetime, dotenv, execution_engine, math, os, pandas, pickle, sqlite3, time, unidecode
- Classes: none
- Functions: load_models_international, get_player_historical_stats, log_missing_player, detect_competition_type, get_opponent_profile, compute_intl_ppda_norm, compute_intl_minutes_factor, safe_float, build_feature_vector, poisson_prob_ge, compute_pearson_lambda, get_sot_model, run_for_match, get_current_odds
- Called services/storage signals: get_current_odds, get_opponent_profile, get_player_historical_stats, get_sot_model, opp_profile.get, pickle.load, position_map.get, sqlite3.connect, stats.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Inference/prediction runner that loads models and produces priced markets or match predictions.

### `src\models\calibration_engine.py`
- Lines: 228
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: numpy, os, pandas, pickle, sklearn.calibration, sklearn.isotonic, typing
- Classes: ProbabilityCalibrator
- Functions: create_calibration_pipeline, apply_calibration_to_bet, get_calibrated_ev, __init__, fit, calibrate_probability, calibrate_probabilities, save, load
- Called services/storage signals: data.get, pickle.dump, pickle.load
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\models\expected_minutes.py`
- Lines: 180
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: lightgbm, numpy, pandas, sklearn.metrics, sklearn.model_selection
- Classes: none
- Functions: prepare_minutes_features, train_expected_minutes_model, predict_expected_minutes, get_xmin_for_player
- Called services/storage signals: inference_df.get, player_data.get, row.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\models\train_prop_model.py`
- Lines: 125
- Purpose: Training pipeline/script for one or more predictive models.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: lightgbm, numpy, pandas, scipy.stats, sklearn.metrics, sklearn.model_selection
- Classes: none
- Functions: build_unified_feature_store, train_prop_model_lightgbm, backtest_framework
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Training pipeline/script for one or more predictive models.

### `src\module_audit.py`
- Lines: 123
- Purpose: Telemetry, CLV, audit, monitoring, or reporting component.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: importlib, importlib.util, os, sys
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Telemetry, CLV, audit, monitoring, or reporting component.

### `src\odds_feed.py`
- Lines: 250
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: betfairlightweight, dotenv, os, queue, requests, sqlite3, threading, time
- Classes: none
- Functions: init_db, _db_writer_thread, log_odds, start_db_writer, fetch_odds_dev, start_betfair_stream
- Called services/storage signals: _write_queue.get, _write_queue.get_nowait, os.getenv, requests.get, sqlite3.connect
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\odds_scraper_betarabia.py`
- Lines: 232
- Purpose: Data acquisition scraper/parser for sports, odds, lineups, or historical stats.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: bs4, datetime, json, re, requests, sqlite3, time
- Classes: none
- Functions: init_db, get_live_football_matches, scrape_player_props, write_odds_to_db, run
- Called services/storage signals: get_live_football_matches, match.get, obj.get, requests.get, sqlite3.connect
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Data acquisition scraper/parser for sports, odds, lineups, or historical stats.

### `src\opponent_model_integrator.py`
- Lines: 99
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: numpy, pandas
- Classes: none
- Functions: prepare_training_data, train_model
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\opponent_scraper.py`
- Lines: 138
- Purpose: Data acquisition scraper/parser for sports, odds, lineups, or historical stats.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: os, pandas, requests, sqlite3
- Classes: none
- Functions: init_db, scrape_fbref_defense_stats
- Called services/storage signals: requests.get, row.get, sqlite3.connect
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Data acquisition scraper/parser for sports, odds, lineups, or historical stats.

### `src\orchestrator.py`
- Lines: 348
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: asyncio, datetime, logging, os, signal, sqlalchemy.ext.asyncio, sqlalchemy.orm, src.database.models, src.services.odds_acquisition.websocket_ingestor, src.services.session_manager.service, sys, typing
- Classes: DeepFieldOrchestrator
- Functions: async main, __init__, async start, async stop, async _initialize_session_manager, async _initialize_database, async _start_websocket_ingestors, async _persist_tick, async _health_monitor, async _metrics_collector, async run_forever, request_shutdown, signal_handler
- Called services/storage signals: asyncio.get_event_loop, info.get, ingestor.get_metrics, logging.getLogger, metrics.get, s.get, self.session_manager.get_metrics_summary, summary.get, ws_metrics.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\parlay_builder.py`
- Lines: 124
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: itertools, json, logging, os, typing
- Classes: none
- Functions: is_correlated, build_parlays
- Called services/storage signals: data.get, leg.get, logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\portfolio_optimization\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\portfolio_optimization\bayesian_confidence_engine.py`
- Lines: 55
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging, math
- Classes: BayesianConfidenceEngine
- Functions: __init__, update_posterior, get_confidence_interval_width, get_confidence_penalty
- Called services/storage signals: logging.getLogger, self.get_confidence_interval_width, self.market_priors.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\portfolio_optimization\capital_allocation_engine.py`
- Lines: 114
- Purpose: API component.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: app_config, logging, os, pandas, portfolio_optimization.bayesian_confidence_engine, portfolio_optimization.drawdown_governor, portfolio_optimization.dynamic_bankroll_allocator, portfolio_optimization.liquidity_impact_model
- Classes: CapitalAllocationEngine
- Functions: __init__, allocate_capital
- Called services/storage signals: bayesian_engine.get_confidence_penalty, bet_metadata.get, getattr, logging.getLogger, self.slate_exposure.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: API component.

### `src\portfolio_optimization\drawdown_governor.py`
- Lines: 54
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging, typing
- Classes: DrawdownGovernor
- Functions: __init__, record_equity, calculate_governor_multiplier
- Called services/storage signals: logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\portfolio_optimization\dynamic_bankroll_allocator.py`
- Lines: 62
- Purpose: Risk, bankroll, staking, or exposure control logic.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: app_config, logging, portfolio_optimization.portfolio_correlation_engine
- Classes: DynamicBankrollAllocator
- Functions: __init__, allocate
- Called services/storage signals: bet_metadata.get, logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Risk, bankroll, staking, or exposure control logic.

### `src\portfolio_optimization\liquidity_impact_model.py`
- Lines: 48
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging
- Classes: LiquidityImpactModel
- Functions: __init__, constrain_stake
- Called services/storage signals: logging.getLogger, self.market_liquidity_caps.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\portfolio_optimization\portfolio_correlation_engine.py`
- Lines: 85
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging, networkx
- Classes: PortfolioCorrelationEngine
- Functions: __init__, add_exposure, calculate_correlation_penalty
- Called services/storage signals: get, logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\portfolio_optimization\portfolio_research_lab.py`
- Lines: 72
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: asyncio, logging, os, src.portfolio_optimization.capital_allocation_engine, src.portfolio_optimization.drawdown_governor, src.portfolio_optimization.portfolio_correlation_engine, sys
- Classes: PortfolioResearchLab
- Functions: __init__, async run_portfolio_simulation
- Called services/storage signals: logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\predict_todays_games.py`
- Lines: 433
- Purpose: Inference/prediction runner that loads models and produces priced markets or match predictions.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: datetime, io, lightgbm, numpy, os, pandas, re, requests, sys, unicodedata
- Classes: none
- Functions: normalize, get_team_players, run_simulations, ev_analysis
- Called services/storage signals: TEAM_TO_NATION.get, get, get_team_players, requests.get, row.get, target.replace
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Inference/prediction runner that loads models and produces priced markets or match predictions.

### `src\pricing_engine.py`
- Lines: 141
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: numpy, scipy.stats
- Classes: none
- Functions: calculate_over_prob_pearson, calculate_over_prob
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\research\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\research\meta_governor\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\research\meta_governor\global_safety_constraints.py`
- Lines: 55
- Purpose: Training pipeline/script for one or more predictive models.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: datetime, logging
- Classes: GlobalSafetyConstraints
- Functions: __init__, _maybe_reset_daily_budget, validate_apo_update
- Called services/storage signals: logging.getLogger, self._maybe_reset_daily_budget
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Training pipeline/script for one or more predictive models.

### `src\research\meta_governor\learning_rate_controller.py`
- Lines: 47
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging, src.research.meta_governor.system_health_scorer
- Classes: LearningRateController
- Functions: __init__, compute_learning_rate
- Called services/storage signals: logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\research\meta_governor\meta_regret_engine.py`
- Lines: 52
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: dataclasses, logging
- Classes: MetaRegretMetrics, MetaRegretEngine
- Functions: __init__, compute_meta_regret
- Called services/storage signals: decision.get, logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\research\meta_governor\mgl_engine.py`
- Lines: 107
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging, src.research.meta_governor.global_safety_constraints, src.research.meta_governor.learning_rate_controller, src.research.meta_governor.meta_regret_engine, src.research.meta_governor.system_health_scorer, typing
- Classes: MetaGovernorLayer
- Functions: __init__, evaluate_and_control
- Called services/storage signals: apo_proposal.get, logging.getLogger, mgl_inputs.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\research\meta_governor\mgl_simulation_lab.py`
- Lines: 48
- Purpose: Simulation/backtesting/replay component.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: asyncio, logging, os, src.research.meta_governor.mgl_engine, sys
- Classes: MGLSimulationLab
- Functions: async run_mgl_flow
- Called services/storage signals: logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Simulation/backtesting/replay component.

### `src\research\meta_governor\system_health_scorer.py`
- Lines: 63
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: dataclasses, logging
- Classes: SystemHealthState, SystemHealthScorer
- Functions: __init__, evaluate_health
- Called services/storage signals: logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\research\policy_outcome_auditor\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\research\policy_outcome_auditor\autonomous_policy_optimizer.py`
- Lines: 62
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging, typing
- Classes: AutonomousPolicyOptimizer
- Functions: __init__, optimize_from_audit
- Called services/storage signals: breakdown.get, logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\research\policy_outcome_auditor\clv_validation_layer.py`
- Lines: 50
- Purpose: Telemetry, CLV, audit, monitoring, or reporting component.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging, typing
- Classes: CLVValidationLayer
- Functions: __init__, evaluate_clv_contradiction
- Called services/storage signals: logging.getLogger, row.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Telemetry, CLV, audit, monitoring, or reporting component.

### `src\research\policy_outcome_auditor\counterfactual_engine.py`
- Lines: 92
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: dataclasses, logging, typing
- Classes: CounterfactualOutcome, CounterfactualEngine
- Functions: __init__, simulate_skip, simulate_execute, simulate_delayed, compute_counterfactuals
- Called services/storage signals: logging.getLogger, row.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\research\policy_outcome_auditor\decision_store.py`
- Lines: 133
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: app_config, logging, os, pandas, sqlite3, src.research.policy_outcome_auditor.event_schema
- Classes: DecisionStore
- Functions: __init__, _init_db, record_decision, record_outcome, record_market_snapshot, fetch_audit_dataframe
- Called services/storage signals: logging.getLogger, sqlite3.connect
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\research\policy_outcome_auditor\event_schema.py`
- Lines: 55
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: datetime, pydantic, typing, uuid
- Classes: PolicyDecisionEvent, ExecutionOutcomeEvent, MarketSnapshotEvent
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\research\policy_outcome_auditor\poa_simulation_lab.py`
- Lines: 84
- Purpose: Simulation/backtesting/replay component.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: asyncio, datetime, logging, os, pandas, src.research.policy_outcome_auditor.autonomous_policy_optimizer, src.research.policy_outcome_auditor.policy_scoring_system, sys
- Classes: POASimulationLab
- Functions: async run_audit_loop
- Called services/storage signals: logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Simulation/backtesting/replay component.

### `src\research\policy_outcome_auditor\policy_scoring_system.py`
- Lines: 93
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging, pandas, src.research.policy_outcome_auditor.clv_validation_layer, src.research.policy_outcome_auditor.counterfactual_engine, src.research.policy_outcome_auditor.regret_engine, typing
- Classes: PolicyScoringSystem
- Functions: __init__, score_batch
- Called services/storage signals: logging.getLogger, row_dict.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\research\policy_outcome_auditor\regret_engine.py`
- Lines: 51
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging, typing
- Classes: RegretEngine
- Functions: __init__, compute_regret
- Called services/storage signals: logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\research\real_world_validation\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\research\real_world_validation\baseline_comparison_engine.py`
- Lines: 64
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging, typing
- Classes: BaselineComparisonEngine
- Functions: __init__, compare_against_baselines
- Called services/storage signals: ex.get, logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\research\real_world_validation\execution_friction_analyzer.py`
- Lines: 42
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging, typing
- Classes: ExecutionFrictionAnalyzer
- Functions: __init__, analyze_friction
- Called services/storage signals: ex.get, logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\research\real_world_validation\performance_attribution_engine.py`
- Lines: 50
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging, typing
- Classes: PerformanceAttributionEngine
- Functions: __init__, attribute_performance
- Called services/storage signals: ex.get, logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\research\real_world_validation\reality_alignment_check.py`
- Lines: 39
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging
- Classes: RealityAlignmentCheck
- Functions: __init__, check_alignment
- Called services/storage signals: logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\research\real_world_validation\rvl_simulation_lab.py`
- Lines: 63
- Purpose: Simulation/backtesting/replay component.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: asyncio, logging, os, random, src.research.real_world_validation.system_readiness_gate, sys
- Classes: RVLSimulationLab
- Functions: async run_rvl_check
- Called services/storage signals: logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Simulation/backtesting/replay component.

### `src\research\real_world_validation\statistical_significance_tester.py`
- Lines: 89
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging, numpy, typing
- Classes: StatisticalSignificanceTester
- Functions: __init__, run_significance_tests
- Called services/storage signals: logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\research\real_world_validation\system_readiness_gate.py`
- Lines: 86
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging, src.research.real_world_validation.baseline_comparison_engine, src.research.real_world_validation.execution_friction_analyzer, src.research.real_world_validation.performance_attribution_engine, src.research.real_world_validation.reality_alignment_check, src.research.real_world_validation.statistical_significance_tester
- Classes: SystemReadinessGate
- Functions: __init__, evaluate_readiness
- Called services/storage signals: base_metrics.get, ex.get, fric_metrics.get, logging.getLogger, stat_metrics.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\research\validation_framework\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\research\validation_framework\combinatorial_purged_cv.py`
- Lines: 68
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: itertools, logging, numpy, typing
- Classes: CombinatorialPurgedCV
- Functions: __init__, get_splits
- Called services/storage signals: logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\research_os\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\research_os\experiment_registry.py`
- Lines: 112
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: datetime, json, logging, os, sqlite3, sys, uuid
- Classes: none
- Functions: init_db, register, update_results, list_experiments
- Called services/storage signals: logging.getLogger, sqlite3.connect
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\research_os\strategy_graveyard.py`
- Lines: 93
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: datetime, logging, os, sqlite3, sys
- Classes: none
- Functions: init_db, bury, list_buried
- Called services/storage signals: logging.getLogger, sqlite3.connect
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\research_os\strategy_lifecycle.py`
- Lines: 140
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: datetime, logging, os, sqlite3, sys
- Classes: none
- Functions: init_db, register_strategy, evaluate_promotion, get_all_strategies
- Called services/storage signals: PROMOTION_CRITERIA.get, criteria.get, get_all_strategies, logging.getLogger, sqlite3.connect
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\restore_api_rows.py`
- Lines: 51
- Purpose: API component.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: io, os, pandas, sys
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: API component.

### `src\risk_engine\__init__.py`
- Lines: 1
- Purpose: Risk, bankroll, staking, or exposure control logic.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Risk, bankroll, staking, or exposure control logic.

### `src\risk_engine\conditional_var_simulator.py`
- Lines: 75
- Purpose: Risk, bankroll, staking, or exposure control logic.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging, numpy, typing
- Classes: ConditionalVaRSimulator
- Functions: __init__, run_monte_carlo_stress_test
- Called services/storage signals: logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Risk, bankroll, staking, or exposure control logic.

### `src\risk_engine\no_bet_filter.py`
- Lines: 287
- Purpose: Risk, bankroll, staking, or exposure control logic.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: datetime, os, sqlite3, typing
- Classes: NoBetFilter
- Functions: create_no_bet_filter, __init__, _load_active_exposures, reject_if_uncertainty_high, reject_if_stale_odds, reject_if_correlated, evaluate_bet, record_bet, clear_settled_exposures
- Called services/storage signals: bet_proposal.get, sqlite3.connect
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Risk, bankroll, staking, or exposure control logic.

### `src\role_baseline_builder.py`
- Lines: 110
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: datetime, os, pandas, sqlite3
- Classes: none
- Functions: init_history_db, build_baseline
- Called services/storage signals: sqlite3.connect
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\role_shift_detector.py`
- Lines: 158
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: alerter, os, sqlite3
- Classes: none
- Functions: detect_shifts
- Called services/storage signals: ROLE_SHIFT_MULTIPLIERS.get, player.get, sqlite3.connect
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\run_bottom_up_predictions_today.py`
- Lines: 254
- Purpose: Inference/prediction runner that loads models and produces priced markets or match predictions.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: datetime, joblib, numpy, pandas, requests, sys
- Classes: none
- Functions: get_todays_fixtures, get_fixture_lineups, load_player_database, get_player_rolling_stats, predict_match, main
- Called services/storage signals: data.get, f.get, get, get_fixture_lineups, get_player_rolling_stats, get_todays_fixtures, joblib.load, latest.get, league_elo_map.get, requests.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Inference/prediction runner that loads models and produces priced markets or match predictions.

### `src\run_todays_predictions.py`
- Lines: 447
- Purpose: Inference/prediction runner that loads models and produces priced markets or match predictions.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: __future__, argparse, datetime, json, logging, match_simulator, os, pandas, shutil, similarity_engine, sqlite3, subprocess, sys
- Classes: none
- Functions: run_script, print_db_health, generate_output_file, run_simulation, get_players
- Called services/storage signals: data.get, est.get, get_players, logging.getLogger, se.get_estimated_stats, sqlite3.connect
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Inference/prediction runner that loads models and produces priced markets or match predictions.

### `src\scheduler_daemon.py`
- Lines: 197
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: apscheduler.schedulers.asyncio, apscheduler.triggers.cron, asyncio, clv_tracker, clv_updater, datetime, generate_predictions, json, logging, os, sqlite3, sys
- Classes: PipelineDaemon
- Functions: __init__, candidate_scan, final_confirmation, run_daily_settlement, on_lineup_change, recalibrate_platt_scaler, run
- Called services/storage signals: AsyncIOScheduler, asyncio.get_event_loop, logging.getLogger, play.get, proj.get, self.scheduler.add_job, self.scheduler.shutdown, self.scheduler.start, sqlite3.connect
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\scrape_api_football.py`
- Lines: 232
- Purpose: Data acquisition scraper/parser for sports, odds, lineups, or historical stats.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: io, json, os, pandas, re, requests, sys, time, unicodedata
- Classes: none
- Functions: normalize_name
- Called services/storage signals: cards.get, data.get, entry.get, games.get, get, goals.get, p.get, player_info.get, requests.get, res.get, shots.get, stat.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Data acquisition scraper/parser for sports, odds, lineups, or historical stats.

### `src\scrape_league_worker.py`
- Lines: 134
- Purpose: Data acquisition scraper/parser for sports, odds, lineups, or historical stats.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: io, os, pandas, re, soccerdata, sys, time, unicodedata
- Classes: none
- Functions: normalize_name, is_wc_player
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Data acquisition scraper/parser for sports, odds, lineups, or historical stats.

### `src\scrape_missing_wc_players.py`
- Lines: 238
- Purpose: Data acquisition scraper/parser for sports, odds, lineups, or historical stats.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: io, os, pandas, re, soccerdata, sys, time, unicodedata
- Classes: none
- Functions: normalize_name, is_wc_player
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Data acquisition scraper/parser for sports, odds, lineups, or historical stats.

### `src\scratch\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\scratch\check_sofascore.py`
- Lines: 24
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: free_scraper_module, os, sys
- Classes: none
- Functions: none
- Called services/storage signals: get_todays_fixtures_free
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\scratch\decode_state.py`
- Lines: 40
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: base64, json, re, requests, urllib.parse
- Classes: none
- Functions: none
- Called services/storage signals: requests.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\scratch\inspect_bet_db.py`
- Lines: 36
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: os, sqlite3
- Classes: none
- Functions: none
- Called services/storage signals: sqlite3.connect
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\scratch\parse_all_bets.py`
- Lines: 81
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: codecs, re
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\scratch\parse_all_opportunities.py`
- Lines: 75
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: codecs, re
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\scratch\parse_betarabia_bets.py`
- Lines: 95
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: codecs, re
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\scratch\parse_bets.py`
- Lines: 72
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: codecs, re
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\scratch\predict_matches.py`
- Lines: 397
- Purpose: Inference/prediction runner that loads models and produces priced markets or match predictions.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: app_config, lightgbm, numpy, os, pandas, pricing_engine, scipy.stats, sqlite3, unidecode
- Classes: none
- Functions: get_player_stats, get_opponent_profile, safe_float, build_features
- Called services/storage signals: BASELINE_PASSES.get, get_opponent_profile, get_player_stats, position_map.get, sqlite3.connect, stats.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Inference/prediction runner that loads models and produces priced markets or match predictions.

### `src\scratch_inspect.py`
- Lines: 30
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: os, sqlite3
- Classes: none
- Functions: none
- Called services/storage signals: sqlite3.connect
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\scratch_inspect_api.py`
- Lines: 33
- Purpose: API component.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: json
- Classes: none
- Functions: none
- Called services/storage signals: resp.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: API component.

### `src\scratch_inspect_event.py`
- Lines: 26
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: json
- Classes: none
- Functions: none
- Called services/storage signals: event.get, resp.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\seed_comparisons.py`
- Lines: 476
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: datetime, json, os, sqlite3
- Classes: none
- Functions: none
- Called services/storage signals: sqlite3.connect
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\seed_opponent_profiles.py`
- Lines: 138
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: app_config, os, pandas, sqlite3
- Classes: none
- Functions: none
- Called services/storage signals: sqlite3.connect
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\services\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\services\backtesting\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\services\backtesting\execution_simulator.py`
- Lines: 461
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: asyncio, dataclasses, datetime, decimal, enum, logging, random, typing
- Classes: ExecutionStatus, RejectionReason, ExecutionRequest, ExecutionResult, SportsbookProfile, ExecutionSimulator, ExecutionMetrics
- Functions: __init__, _init_default_profiles, register_sportsbook_profile, update_market_state, async execute, estimate_execution_probability, get_statistics, add_result, acceptance_rate, rejection_rate
- Called services/storage signals: current_odds.get, get, logging.getLogger, market_state.get, profile.max_stake_limits.get, self._market_states.get, self._sportsbook_profiles.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\services\backtesting\historical_replay.py`
- Lines: 601
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: asyncio, database.models, dataclasses, datetime, decimal, enum, logging, sqlalchemy, sqlalchemy.ext.asyncio, typing
- Classes: ReplayMode, MarketEventType, MarketEvent, ReplayState, ReplayClock, EventScheduler, HistoricalReplayEngine, MarketSimulator, MarketState
- Functions: __init__, pause, resume, advance, get_current_time, is_finished, progress, __init__, subscribe, unsubscribe, schedule_event, schedule_events, async dispatch_next, async dispatch_until, async _dispatch_event, clear, pending_count, __init__, async initialize, async _load_historical_data, async _load_line_movements, async run, async stop, pause, resume, set_speed, get_market_state, get_all_market_states, async _on_odds_update, async _on_line_movement
- Called services/storage signals: EventScheduler, event.data.get, logging.getLogger, self._market_states.get, self._subscribers.get, self.clock.get_current_time, self.schedule_event, self.scheduler.dispatch_until, self.scheduler.pending_count, self.scheduler.schedule_events, self.scheduler.subscribe
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\services\clv\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\services\clv\engine.py`
- Lines: 504
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: collections, database.models, dataclasses, datetime, decimal, logging, sqlalchemy, sqlalchemy.ext.asyncio, statistics, typing
- Classes: CLVResult, CLVSummary, CLVEngine
- Functions: positive_clv_rate, clv_edge, __init__, async calculate_clv, async _get_closing_odds, async calculate_portfolio_clv, async get_market_adjusted_clv, async generate_clv_report, _calculate_significance, clear_cache
- Called services/storage signals: logging.getLogger, self._get_closing_odds
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\services\feature_store\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\services\market_intelligence\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\services\market_intelligence\engine.py`
- Lines: 689
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: collections, database.models, dataclasses, datetime, decimal, logging, sqlalchemy, sqlalchemy.ext.asyncio, statistics, typing
- Classes: LineMetrics, SteamMove, CrossBookDisagreement, MarketPressure, MarketIntelligenceEngine
- Functions: __init__, async analyze_market, async _get_market_ticks, async _calculate_line_metrics, _find_nearest_odds, _calculate_velocity, async _detect_steam_moves, async _calculate_cross_book_disagreement, async _calculate_market_pressure, _generate_summary_signals, _determine_consensus, _classify_volatility, _metrics_to_dict, _steam_to_dict, _disagreement_to_dict, _pressure_to_dict
- Called services/storage signals: analysis.get, d.get, data.get, logging.getLogger, m.get, o.get, p.get, self._get_market_ticks
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\services\normalizer\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\services\normalizer\engine.py`
- Lines: 201
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: datetime, typing
- Classes: NormalizationEngine
- Functions: __init__, _build_market_mappings, normalize_odds, _find_market, _normalize_market, _fractional_to_decimal, _american_to_decimal, validate_odds, detect_arbitrage, _check_market_arbitrage
- Called services/storage signals: get, odds_data.get, raw_odds.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\services\odds_acquisition\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\services\odds_acquisition\collector.py`
- Lines: 158
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: asyncio, datetime, typing
- Classes: OddsCollector, RateLimitError
- Functions: __init__, async collect_odds, async _fetch_sportsbook_odds, async _parse_odds_page, async stream_odds, get_latest_odds
- Called services/storage signals: self.session_manager.get_session
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\services\odds_acquisition\websocket_ingestor.py`
- Lines: 578
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: asyncio, dataclasses, datetime, enum, hashlib, json, logging, playwright.async_api, typing
- Classes: WebSocketState, WebSocketMetrics, OddsTick, WebSocketIngestor
- Functions: __init__, async start, async stop, async _setup_websocket_interception, async _navigate_to_streaming_page, async _connect_direct, _handle_frame, _handle_close, async _process_message, async _parse_odds_message, async _create_tick_from_odds, async _create_tick_from_market, _get_previous_odds, _get_next_sequence, _generate_tick_id, async _process_tick, async _flush_tick_buffer, _schedule_reconnect, async _reconnect_loop, async _run_health_checks, async _check_stream_health, register_message_handler, get_metrics, is_healthy, async handle_websocket
- Called services/storage signals: context.get, logging.getLogger, message.get, odds_data.get, self._connect_direct, self._get_next_sequence, self._get_previous_odds, self._reconnect_loop, self._reconnect_task.cancel, self._reconnect_task.done, self._schedule_reconnect, self._websocket.disconnect, streaming_pages.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\services\risk_engine\__init__.py`
- Lines: 1
- Purpose: Risk, bankroll, staking, or exposure control logic.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Risk, bankroll, staking, or exposure control logic.

### `src\services\risk_engine\engine.py`
- Lines: 553
- Purpose: Risk, bankroll, staking, or exposure control logic.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: database.models, dataclasses, datetime, decimal, enum, logging, sqlalchemy, sqlalchemy.ext.asyncio, typing
- Classes: RiskLevel, BankrollState, BankrollConfig, BankrollState, BetSizing, RiskEngine
- Functions: __init__, async initialize, async _load_bankroll_state, async _calculate_pl, async _calculate_active_exposure, async _count_active_bets, _determine_bankroll_state, _determine_risk_level, calculate_kelly_stake, calculate_recommended_stake, _get_risk_adjustment, _get_correlated_exposure, register_correlation_group, check_bet_allowed, async update_bankroll, get_statistics, calculate_risk_of_ruin
- Called services/storage signals: logging.getLogger, self._get_correlated_exposure, self._get_risk_adjustment
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Risk, bankroll, staking, or exposure control logic.

### `src\services\session_manager\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\services\session_manager\browser_engine.py`
- Lines: 578
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: datetime, hashlib, json, logging, pathlib, playwright.async_api, typing
- Classes: BrowserEngine
- Functions: __init__, async start, async stop, async _persist_session_state, _get_state_directory, async create_context, async _inject_stealth_scripts, async _setup_network_interception, register_request_interceptor, register_response_interceptor, register_websocket_handler, async get_context, async remove_context, async new_page, async save_cookies, async load_cookies, async execute_in_context, async fetch_via_browser, is_healthy, get_metrics, async handle_route
- Called services/storage signals: async_playwright, logging.getLogger, self._context_metadata.get, self._contexts.get, self._get_state_directory, self._playwright.chromium.launch, self._playwright.stop, self.get_context
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\services\session_manager\service.py`
- Lines: 712
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: asyncio, browser_engine, dataclasses, datetime, enum, logging, os, sys, typing
- Classes: SessionState, SessionMetrics, SessionManager, CircuitBreaker
- Functions: __init__, async start, async stop, async create_session, async close_session, async authenticate, async _perform_sportsbook_auth, async _extract_auth_tokens, _get_login_url, async check_rate_limit, get_session, list_sessions, async refresh_session, _update_metrics, get_session_health_score, async _run_health_checks, async _perform_health_check_cycle, async _attempt_session_recovery, get_metrics_summary, __init__, record_request, allow_request, _open_circuit, _close_circuit, _should_attempt_recovery, is_open
- Called services/storage signals: logging.getLogger, self._circuit_breakers.get, self._get_login_url, self._session_metrics.get, self._sessions.get, self.get_session_health_score, session.get, urls.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\services\shadow_execution\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\services\shadow_execution\engine.py`
- Lines: 429
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: database.models, dataclasses, datetime, decimal, enum, json, logging, sqlalchemy, sqlalchemy.ext.asyncio, typing, uuid
- Classes: BetStatus, BetType, ShadowBet, ShadowExecutionEngine
- Functions: to_dict, __init__, async place_bet, async _persist_bet, async update_bet_status, async _calculate_profit_loss, async settle_bet, async _load_bet, async _update_bet_in_db, get_active_bets, get_bet_history, get_statistics, _decimal_to_american
- Called services/storage signals: logging.getLogger, self._active_bets.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\services\validation\__init__.py`
- Lines: 1
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\show_tonights_bets.py`
- Lines: 63
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: json
- Classes: none
- Functions: none
- Called services/storage signals: p.get, pdata.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\similarity_engine.py`
- Lines: 240
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: logging, numpy, pandas, sklearn.neighbors, sklearn.preprocessing, sqlite3
- Classes: PlayerSimilarityEngine
- Functions: __init__, _load_and_fit, get_estimated_stats
- Called services/storage signals: engine.get_estimated_stats, logging.getLogger, self.POSITIONAL_PRIORS.get, sqlite3.connect, synth.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\simulation.py`
- Lines: 689
- Purpose: Simulation/backtesting/replay component.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: __future__, app_config, argparse, datetime, json, logging, math, os, pandas, pickle, unidecode
- Classes: none
- Functions: load_player_db, find_player, get_position_average, safe_get, poisson_prob_ge, compute_lam_passes, compute_lam_sot, compute_lam_goals, size_bet, compute_ev, run_simulation, write_output
- Called services/storage signals: B_V.get, Stats_P.get, get_position_average, logging.getLogger, pickle.load, safe_get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Simulation/backtesting/replay component.

### `src\single_bet_predictor.py`
- Lines: 420
- Purpose: Inference/prediction runner that loads models and produces priced markets or match predictions.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: datetime, json, logging, math, os, pandas, pickle, sqlite3, src.model_runner_v2, sys
- Classes: none
- Functions: compute_ev, implied_fair_probs, run_single_bet_predictor
- Called services/storage signals: Models_V.get, Stats_V.get, get_opponent_profile, get_player_historical_stats, logging.getLogger, pickle.load, sqlite3.connect
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Inference/prediction runner that loads models and produces priced markets or match predictions.

### `src\survival_window_analyzer.py`
- Lines: 101
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: matplotlib.pyplot, os, pandas, sqlite3
- Classes: none
- Functions: analyze_survival_windows
- Called services/storage signals: sqlite3.connect
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\system_check.py`
- Lines: 109
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: datetime, importlib, json, os, sqlite3, sys
- Classes: none
- Functions: none
- Called services/storage signals: os.path.getmtime, os.path.getsize, sqlite3.connect, x.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\telemetry_warehouse\__init__.py`
- Lines: 1
- Purpose: Telemetry, CLV, audit, monitoring, or reporting component.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Telemetry, CLV, audit, monitoring, or reporting component.

### `src\telemetry_warehouse\adversarial_pattern_miner.py`
- Lines: 67
- Purpose: Telemetry, CLV, audit, monitoring, or reporting component.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: app_config, logging, numpy, os
- Classes: AdversarialPatternMiner
- Functions: __init__, detect_soft_limits, detect_ui_freezing, get_state_transition_matrix
- Called services/storage signals: logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Telemetry, CLV, audit, monitoring, or reporting component.

### `src\telemetry_warehouse\clv_tracker.py`
- Lines: 503
- Purpose: Telemetry, CLV, audit, monitoring, or reporting component.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: datetime, json, os, sqlite3, sys, threading, time, typing
- Classes: CLVTracker
- Functions: create_clv_tracker, __init__, _init_database, schedule_clv_capture, _monitor_and_capture, _capture_closing_odds, _fetch_closing_odds, _update_bet_with_clv, record_bet_for_clv, _save_bet_to_db, get_clv_summary
- Called services/storage signals: bet_data.get, cache.get, market_data.get, self.schedule_clv_capture, sqlite3.connect
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Telemetry, CLV, audit, monitoring, or reporting component.

### `src\telemetry_warehouse\data_quality_monitor.py`
- Lines: 569
- Purpose: Telemetry, CLV, audit, monitoring, or reporting component.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: datetime, os, sqlite3, sys, typing
- Classes: DataQualityMonitor
- Functions: create_data_quality_monitor, __init__, _init_database, record_lineup_latency, record_odds_tick, _get_market_staleness, record_missing_lineup, get_stale_markets, get_api_health_summary, get_dashboard_data
- Called services/storage signals: freshness_stats.get, health_summary.get, monitor.get_dashboard_data, s.get, self._get_market_staleness, self.get_api_health_summary, self.get_stale_markets, sqlite3.connect
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Telemetry, CLV, audit, monitoring, or reporting component.

### `src\telemetry_warehouse\execution_ecology_engine.py`
- Lines: 74
- Purpose: Telemetry, CLV, audit, monitoring, or reporting component.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: asyncio, datetime, logging, os, src.data_acquisition.live_execution.adaptive_layer.execution_behavior_memory, src.data_acquisition.live_execution.shadow_mode.self_healing_browser_manager, src.telemetry_warehouse.telemetry_archiver, sys, uuid
- Classes: ExecutionEcologyEngine
- Functions: __init__, async run_ecology_lifecycle
- Called services/storage signals: logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Telemetry, CLV, audit, monitoring, or reporting component.

### `src\telemetry_warehouse\sportsbook_behavior_fingerprinter.py`
- Lines: 46
- Purpose: Telemetry, CLV, audit, monitoring, or reporting component.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: app_config, logging, os, pandas
- Classes: SportsbookBehaviorFingerprinter
- Functions: __init__, fingerprint_time_of_day_aggressiveness, fingerprint_market_profiling, run_daily_fingerprint
- Called services/storage signals: logging.getLogger
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Telemetry, CLV, audit, monitoring, or reporting component.

### `src\telemetry_warehouse\telemetry_archiver.py`
- Lines: 70
- Purpose: Telemetry, CLV, audit, monitoring, or reporting component.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: datetime, logging, os, pandas, sqlite3, src.app_config
- Classes: TelemetryArchiver
- Functions: __init__, archive_executions
- Called services/storage signals: logging.getLogger, sqlite3.connect
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Telemetry, CLV, audit, monitoring, or reporting component.

### `src\test_model_prediction.py`
- Lines: 59
- Purpose: Inference/prediction runner that loads models and produces priced markets or match predictions.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: io, lightgbm, pandas, sys
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Inference/prediction runner that loads models and produces priced markets or match predictions.

### `src\test_odds_parsing.py`
- Lines: 140
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: json
- Classes: none
- Functions: none
- Called services/storage signals: ev.get, main_odds.get, odd_obj.get, resp.get, teams.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\test_pipeline.py`
- Lines: 214
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: datetime, model_runner, os, sqlite3
- Classes: none
- Functions: none
- Called services/storage signals: sqlite3.connect
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\train_all_betarabia_models.py`
- Lines: 250
- Purpose: Training pipeline/script for one or more predictive models.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: lightgbm, os, pandas, sqlite3, src.app_config, unidecode
- Classes: none
- Functions: get_opponent
- Called services/storage signals: pos_map.get, sqlite3.connect
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Training pipeline/script for one or more predictive models.

### `src\train_bottom_up_model.py`
- Lines: 334
- Purpose: Training pipeline/script for one or more predictive models.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: joblib, os, pandas, sklearn.ensemble, sklearn.metrics, sklearn.model_selection
- Classes: none
- Functions: load_and_preprocess, build_player_profiles, reconstruct_matches, train_bottom_up_pipeline, get_elo
- Called services/storage signals: get_elo, joblib.dump, league_elo_map.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Training pipeline/script for one or more predictive models.

### `src\train_minutes_model.py`
- Lines: 85
- Purpose: Training pipeline/script for one or more predictive models.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: lightgbm, os, pandas, sklearn.model_selection, src.app_config
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Training pipeline/script for one or more predictive models.

### `src\train_models.py`
- Lines: 504
- Purpose: Training pipeline/script for one or more predictive models.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: lightgbm, numpy, os, pandas, pickle, sklearn.metrics, sklearn.model_selection
- Classes: none
- Functions: load_and_prepare_data, clean_features, encode_position, train_sot_club_model, train_sot_international_model, train_passes_model, train_minutes_model, print_calibration_buckets, run_sanity_check, main
- Called services/storage signals: pickle.dump, pickle.load
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Training pipeline/script for one or more predictive models.

### `src\train_passes_model.py`
- Lines: 100
- Purpose: Training pipeline/script for one or more predictive models.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: lightgbm, os, pandas, src.app_config
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Training pipeline/script for one or more predictive models.

### `src\train_shots_models.py`
- Lines: 120
- Purpose: Training pipeline/script for one or more predictive models.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: lightgbm, os, pandas, src.app_config
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Training pipeline/script for one or more predictive models.

### `src\train_wc_prop_models.py`
- Lines: 310
- Purpose: Training pipeline/script for one or more predictive models.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: io, lightgbm, numpy, os, pandas, pickle, re, sklearn.metrics, sklearn.model_selection, sys, unicodedata, warnings
- Classes: none
- Functions: normalize_name
- Called services/storage signals: TARGETS.items, TARGETS.keys, pickle.dump, pos_map.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Training pipeline/script for one or more predictive models.

### `src\utils.py`
- Lines: 81
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: none
- Classes: none
- Functions: remove_vig, implied_prob, decimal_to_american, calculate_edge
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `src\wc_scraper.py`
- Lines: 180
- Purpose: Data acquisition scraper/parser for sports, odds, lineups, or historical stats.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: app_config, os, pandas, soccerdata
- Classes: none
- Functions: scrape_and_filter, extract_nation, get_col_name
- Called services/storage signals: get_col_name
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Data acquisition scraper/parser for sports, odds, lineups, or historical stats.

### `test_fixes.py`
- Lines: 41
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: generate_predictions, json, os, sys
- Classes: none
- Functions: test_issues
- Called services/storage signals: p.get, top_play.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `tests\test_imports.py`
- Lines: 29
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: calibration_trainer, clv_tracker, model_runner_v2, os, sys
- Classes: none
- Functions: none
- Called services/storage signals: none detected
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

### `tests\test_pipeline_e2e.py`
- Lines: 189
- Purpose: Supporting Python module or script used by the platform.
- Responsibilities: implements the module role implied by filename/package and exposes the listed classes/functions.
- Dependencies/imported modules: app_config, clv_tracker, csv, generate_predictions, json, math, model_runner, os, pandas, pickle, portfolio_optimization.capital_allocation_engine, random, sqlite3, sys
- Classes: none
- Functions: print_result, test_1_poisson_variance, test_2_competition_routing, test_3_missing_fallback, test_4_platt_scaler, test_5_odds_pending, test_6_kelly_sizing, test_7_stop_loss, test_8_clv_logging
- Called services/storage signals: get_player_historical_stats, getattr, pickle.load, stats.get
- Data inputs: command arguments, imported modules, configured paths, APIs, DBs, or files referenced by the code.
- Data outputs: stdout/logs plus any DB/API/model/file writes indicated by calls and filename.
- Why this file exists: Supporting Python module or script used by the platform.

## Non-Python/Binary/Archive File Inventory
- `.env` (<none>, 695 bytes): Repository artifact.
- `.env.example` (.example, 1791 bytes): Configuration, migration, container, CI, or launch script.
- `.gitattributes` (<none>, 113 bytes): Repository artifact.
- `.github\workflows\deepfield_pipeline.yml` (.yml, 12177 bytes): Configuration, migration, container, CI, or launch script.
- `.gitignore` (<none>, 131 bytes): Repository artifact.
- `0` (<none>, 0 bytes): Repository artifact.
- `artifacts\complete_feature_database.csv` (.csv, 11750007 bytes): Structured data/config/cache/telemetry artifact.
- `artifacts\complete_player_database.csv` (.csv, 260382 bytes): Structured data/config/cache/telemetry artifact.
- `artifacts\feature_importance_analysis.md` (.md, 3132 bytes): Markdown documentation.
- `artifacts\final_recommendation_report.md` (.md, 656 bytes): Markdown documentation.
- `artifacts\hyperparameter_optimization_report.md` (.md, 884 bytes): Markdown documentation.
- `artifacts\match_simulation_report.md` (.md, 4245 bytes): Markdown documentation.
- `artifacts\model_comparison_report.md` (.md, 2428 bytes): Markdown documentation.
- `artifacts\predictions_2026-06-05.md` (.md, 6627 bytes): Markdown documentation.
- `artifacts\risk_and_uncertainty_analysis.md` (.md, 825 bytes): Markdown documentation.
- `artifacts\team_projection_report.md` (.md, 1067 bytes): Markdown documentation.
- `data\api_stats_progress.json` (.json, 731 bytes): Structured data/config/cache/telemetry artifact.
- `data\api_wc_players_2022.json` (.json, 5238 bytes): Structured data/config/cache/telemetry artifact.
- `data\backtest_results.csv` (.csv, 14614 bytes): Structured data/config/cache/telemetry artifact.
- `data\bankroll.db` (.db, 16384 bytes): SQLite database artifact; schema documented in main documentation.
- `data\bet_log.csv` (.csv, 245 bytes): Structured data/config/cache/telemetry artifact.
- `data\bet_log.db` (.db, 290816 bytes): SQLite database artifact; schema documented in main documentation.
- `data\bet_slip_2026-06-05.csv` (.csv, 566 bytes): Structured data/config/cache/telemetry artifact.
- `data\betarabia_api_responses.json` (.json, 30088629 bytes): Structured data/config/cache/telemetry artifact.
- `data\betarabia_page_probe.html` (.html, 1837295 bytes): Operational artifact, probe output, lock, shortcut, or log.
- `data\betarabia_screenshot.png` (.png, 4718 bytes): Operational artifact, probe output, lock, shortcut, or log.
- `data\betarabia_urls.txt` (.txt, 38818 bytes): Repository artifact.
- `data\genuinely_missing_wc_players.txt` (.txt, 9033 bytes): Repository artifact.
- `data\migrations\001_advanced_markets.sql` (.sql, 2252 bytes): Configuration, migration, container, CI, or launch script.
- `data\minor_leagues_2025.csv` (.csv, 119 bytes): Structured data/config/cache/telemetry artifact.
- `data\missing_players.log` (.log, 844242 bytes): Operational artifact, probe output, lock, shortcut, or log.
- `data\odds_stream.db` (.db, 499712 bytes): SQLite database artifact; schema documented in main documentation.
- `data\scraper_errors.log` (.log, 1039 bytes): Operational artifact, probe output, lock, shortcut, or log.
- `data\settings.json` (.json, 437 bytes): Structured data/config/cache/telemetry artifact.
- `data\shots_training_dataset.csv` (.csv, 13345385 bytes): Structured data/config/cache/telemetry artifact.
- `data\simulation_results_2026-06-04.json` (.json, 317296 bytes): Structured data/config/cache/telemetry artifact.
- `data\statsbomb_real_passes.csv` (.csv, 367696 bytes): Structured data/config/cache/telemetry artifact.
- `data\sync_state.db` (.db, 57344 bytes): SQLite database artifact; schema documented in main documentation.
- `data\test_incidents.json` (.json, 50155 bytes): Structured data/config/cache/telemetry artifact.
- `data\test_stats.json` (.json, 81 bytes): Structured data/config/cache/telemetry artifact.
- `data\TODAYS_BETS_2026-06-03.txt` (.txt, 15343 bytes): Repository artifact.
- `data\TODAYS_BETS_2026-06-04.json` (.json, 4497 bytes): Structured data/config/cache/telemetry artifact.
- `data\TODAYS_BETS_2026-06-04.txt` (.txt, 1607 bytes): Repository artifact.
- `data\todays_dashboard_state.json` (.json, 611398 bytes): Structured data/config/cache/telemetry artifact.
- `data\todays_live_predictions.md` (.md, 23429 bytes): Markdown documentation.
- `data\todays_predictions.md` (.md, 15912 bytes): Markdown documentation.
- `data\tomorrow_predictions_real.json` (.json, 840 bytes): Structured data/config/cache/telemetry artifact.
- `data\training_dataset.csv` (.csv, 918485 bytes): Structured data/config/cache/telemetry artifact.
- `data\wc_player_name_mapping.csv` (.csv, 40462 bytes): Structured data/config/cache/telemetry artifact.
- `data\world_cup_players_match_logs.csv` (.csv, 6897218 bytes): Structured data/config/cache/telemetry artifact.
- `data\world_cup_players_match_logs_global.bak.csv` (.csv, 14035327 bytes): Structured data/config/cache/telemetry artifact.
- `data\world_cup_players_match_logs_global.csv` (.csv, 13956537 bytes): Structured data/config/cache/telemetry artifact.
- `data\worldcup_players.csv` (.csv, 125485 bytes): Structured data/config/cache/telemetry artifact.
- `data\worldcup_players_with_fbref_names.csv` (.csv, 151892 bytes): Structured data/config/cache/telemetry artifact.
- `db\adaptive_memory.sqlite` (.sqlite, 20480 bytes): SQLite database artifact; schema documented in main documentation.
- `db\adversarial_telemetry.sqlite` (.sqlite, 12288 bytes): SQLite database artifact; schema documented in main documentation.
- `DEEPFIELD_AUDIT_REPORT.md` (.md, 5943 bytes): Markdown documentation.
- `DEEPFIELD_AUDIT_REPORT_HISTORICAL.md` (.md, 11054 bytes): Markdown documentation.
- `deploy_deepfieldpro.sh` (.sh, 1466 bytes): Configuration, migration, container, CI, or launch script.
- `docker-compose.yml` (.yml, 652 bytes): Configuration, migration, container, CI, or launch script.
- `Dockerfile` (<none>, 1206 bytes): Repository artifact.
- `Dockerfile.browser` (.browser, 807 bytes): Configuration, migration, container, CI, or launch script.
- `downloaded_files\driver_fixing.lock` (.lock, 0 bytes): Operational artifact, probe output, lock, shortcut, or log.
- `FILE_INVENTORY_DEEPFIELDPRO.md` (.md, 517572 bytes): Markdown documentation.
- `file_list.txt` (.txt, 365604 bytes): Repository artifact.
- `IMPLEMENTATION_PLAN.md` (.md, 4730 bytes): Markdown documentation.
- `IMPLEMENTATION_PLAN_HISTORICAL.md` (.md, 8196 bytes): Markdown documentation.
- `LAUNCH_DEEPFIELD.bat` (.bat, 1037 bytes): Configuration, migration, container, CI, or launch script.
- `logs\test.log` (.log, 0 bytes): Operational artifact, probe output, lock, shortcut, or log.
- `MASTER_SYSTEM_DOCUMENTATION.md` (.md, 16850 bytes): Markdown documentation.
- `models\bottom_up_match_model.pkl` (.pkl, 499665 bytes): Serialized model/calibrator artifact loaded by prediction/training code.
- `models\cards_mean.txt` (.txt, 872007 bytes): LightGBM text booster artifact.
- `models\goals_mean.txt` (.txt, 878668 bytes): LightGBM text booster artifact.
- `models\lgb_min__final.txt` (.txt, 431166 bytes): LightGBM text booster artifact.
- `models\lgb_Performance_Ast_final.txt` (.txt, 421563 bytes): LightGBM text booster artifact.
- `models\lgb_Performance_CrdY_final.txt` (.txt, 438338 bytes): LightGBM text booster artifact.
- `models\lgb_Performance_Gls_final.txt` (.txt, 411898 bytes): LightGBM text booster artifact.
- `models\lgb_Performance_Sh_final.txt` (.txt, 415197 bytes): LightGBM text booster artifact.
- `models\lgb_Performance_SoT_final.txt` (.txt, 425756 bytes): LightGBM text booster artifact.
- `models\lgbm_assists.pkl` (.pkl, 2841813 bytes): Serialized model/calibrator artifact loaded by prediction/training code.
- `models\lgbm_goals.pkl` (.pkl, 2536072 bytes): Serialized model/calibrator artifact loaded by prediction/training code.
- `models\lgbm_minutes.pkl` (.pkl, 2828113 bytes): Serialized model/calibrator artifact loaded by prediction/training code.
- `models\lgbm_minutes_v1.pkl` (.pkl, 297391 bytes): Serialized model/calibrator artifact loaded by prediction/training code.
- `models\lgbm_passes_v1.pkl` (.pkl, 1011738 bytes): Serialized model/calibrator artifact loaded by prediction/training code.
- `models\lgbm_shots.pkl` (.pkl, 3523073 bytes): Serialized model/calibrator artifact loaded by prediction/training code.
- `models\lgbm_shots_on_target.pkl` (.pkl, 3351321 bytes): Serialized model/calibrator artifact loaded by prediction/training code.
- `models\lgbm_sot_club_v1.pkl` (.pkl, 795860 bytes): Serialized model/calibrator artifact loaded by prediction/training code.
- `models\lgbm_sot_international_v2.pkl` (.pkl, 799853 bytes): Serialized model/calibrator artifact loaded by prediction/training code.
- `models\lgbm_yellow_cards.pkl` (.pkl, 2760129 bytes): Serialized model/calibrator artifact loaded by prediction/training code.
- `models\minutes_p10_regressor.txt` (.txt, 179275 bytes): LightGBM text booster artifact.
- `models\minutes_p50_regressor.txt` (.txt, 152709 bytes): LightGBM text booster artifact.
- `models\minutes_p90_regressor.txt` (.txt, 179985 bytes): LightGBM text booster artifact.
- `models\minutes_start_classifier.txt` (.txt, 3248 bytes): LightGBM text booster artifact.
- `models\offsides_mean.txt` (.txt, 875693 bytes): LightGBM text booster artifact.
- `models\passes_p10.txt` (.txt, 283942 bytes): LightGBM text booster artifact.
- `models\passes_p50.txt` (.txt, 292214 bytes): LightGBM text booster artifact.
- `models\passes_p90.txt` (.txt, 291844 bytes): LightGBM text booster artifact.
- `models\platt_scaler_sot.pkl` (.pkl, 712 bytes): Serialized model/calibrator artifact loaded by prediction/training code.
- `models\player_goal_lgbm.pkl` (.pkl, 11341 bytes): Serialized model/calibrator artifact loaded by prediction/training code.
- `models\player_impact_model.pkl` (.pkl, 1295841 bytes): Serialized model/calibrator artifact loaded by prediction/training code.
- `models\shots_p10.txt` (.txt, 2269448 bytes): LightGBM text booster artifact.
- `models\shots_p50.txt` (.txt, 2842746 bytes): LightGBM text booster artifact.
- `models\shots_p90.txt` (.txt, 2936867 bytes): LightGBM text booster artifact.
- `models\sot_p10.txt` (.txt, 2253448 bytes): LightGBM text booster artifact.
- `models\sot_p50.txt` (.txt, 2363606 bytes): LightGBM text booster artifact.
- `models\sot_p90.txt` (.txt, 2942589 bytes): LightGBM text booster artifact.
- `models\team_goals_lgbm.pkl` (.pkl, 60647 bytes): Serialized model/calibrator artifact loaded by prediction/training code.
- `models\training_meta.pkl` (.pkl, 903 bytes): Serialized model/calibrator artifact loaded by prediction/training code.
- `mypy.ini` (.ini, 28 bytes): Configuration, migration, container, CI, or launch script.
- `pyproject.toml` (.toml, 218 bytes): Configuration, migration, container, CI, or launch script.
- `README.md` (.md, 6795 bytes): Markdown documentation.
- `README_V1.md` (.md, 45570 bytes): Markdown documentation.
- `README_V2.md` (.md, 45052 bytes): Markdown documentation.
- `requirements.txt` (.txt, 402 bytes): Repository artifact.
- `RUN_SYSTEM.bat` (.bat, 1252 bytes): Configuration, migration, container, CI, or launch script.
- `src\data\bet_log.db` (.db, 20480 bytes): SQLite database artifact; schema documented in main documentation.
- `src\data\deepfield.db` (.db, 266240 bytes): SQLite database artifact; schema documented in main documentation.
- `src\data_acquisition\raw_frames\BATCH_FIX_0\20260522T154636707755.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_0\20260602T154636756830.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_0\20260602T154636772447.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_0\20260602T154636781143.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_0\20260602T154636796037.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_0\20260602T154636811988.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_0\20260602T154636828516.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_0\20260602T154636844388.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_0\20260602T154636862787.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_0\20260602T154636879874.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_0\20260602T154636899053.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_0\20260602T154636919014.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_0\20260602T154636940134.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_0\20260602T154636964066.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_0\20260602T154636985237.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_0\20260602T154637010040.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_0\20260602T154637036638.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_0\20260602T154637065787.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_0\20260602T154637084884.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_0\20260602T154637113050.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_0\20260602T154637140541.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_0\20260602T154637163450.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_0\20260602T154637192867.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_0\20260602T154637219607.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_0\20260602T154637257554.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_0\20260602T154637296230.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_0\20260602T154637353944.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_0\20260602T154637400546.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_0\20260602T154637446202.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_0\20260602T154637494634.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_0\20260602T154637538189.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_0\20260602T154637575669.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_0\20260602T154637611934.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_0\20260602T154637665847.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_0\20260602T154637711637.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_0\20260602T154637762487.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_0\20260602T154637808740.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_0\20260602T154637866176.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_0\20260602T154637919431.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_0\20260602T154637971436.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_0\20260602T154638016726.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_0\20260602T154638066305.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_0\20260602T154638127241.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_0\20260602T154638169239.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_0\20260602T154638221299.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_0\20260602T154638281606.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_0\20260602T154638368786.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_0\20260602T154638419898.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_0\20260602T154638481587.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_0\20260602T154638530728.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_0\20260602T154638603988.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_1\20260517T154636708697.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_1\20260602T154636771697.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_1\20260602T154636779757.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_1\20260602T154636794086.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_1\20260602T154636810175.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_1\20260602T154636826955.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_1\20260602T154636842759.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_1\20260602T154636861272.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_1\20260602T154636878436.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_1\20260602T154636897700.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_1\20260602T154636917597.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_1\20260602T154636937657.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_1\20260602T154636961763.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_1\20260602T154636983291.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_1\20260602T154637007918.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_1\20260602T154637034286.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_1\20260602T154637060588.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_1\20260602T154637082836.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_1\20260602T154637110856.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_1\20260602T154637137644.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_1\20260602T154637160584.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_1\20260602T154637188858.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_1\20260602T154637216186.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_1\20260602T154637252993.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_1\20260602T154637288098.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_1\20260602T154637344331.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_1\20260602T154637394097.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_1\20260602T154637438436.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_1\20260602T154637488144.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_1\20260602T154637530771.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_1\20260602T154637570334.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_1\20260602T154637607998.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_1\20260602T154637661275.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_1\20260602T154637707429.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_1\20260602T154637757793.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_1\20260602T154637804494.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_1\20260602T154637859162.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_1\20260602T154637914385.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_1\20260602T154637967023.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_1\20260602T154638012155.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_1\20260602T154638062499.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_1\20260602T154638120626.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_1\20260602T154638165699.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_1\20260602T154638216290.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_1\20260602T154638276556.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_1\20260602T154638362672.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_1\20260602T154638413282.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_1\20260602T154638475737.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_1\20260602T154638525961.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_1\20260602T154638590691.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_10\20260508T154636714399.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_10\20260602T154636913107.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_10\20260602T154636933730.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_10\20260602T154636956999.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_10\20260602T154636979445.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_10\20260602T154637004454.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_10\20260602T154637029565.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_10\20260602T154637056278.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_10\20260602T154637078210.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_10\20260602T154637106289.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_10\20260602T154637132215.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_10\20260602T154637156058.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_10\20260602T154637182692.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_10\20260602T154637212059.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_10\20260602T154637241732.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_10\20260602T154637279279.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_10\20260602T154637331566.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_10\20260602T154637380481.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_10\20260602T154637426953.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_10\20260602T154637479935.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_10\20260602T154637522079.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_10\20260602T154637559694.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_10\20260602T154637598034.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_10\20260602T154637641880.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_10\20260602T154637698292.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_10\20260602T154637745823.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_10\20260602T154637793290.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_10\20260602T154637844175.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_10\20260602T154637904058.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_10\20260602T154637955752.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_10\20260602T154638002846.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_10\20260602T154638050426.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_10\20260602T154638106478.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_10\20260602T154638155664.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_10\20260602T154638202910.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_10\20260602T154638265211.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_10\20260602T154638337188.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_10\20260602T154638402924.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_10\20260602T154638462971.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_10\20260602T154638513013.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_10\20260602T154638576308.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_11\20260509T154636714939.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_11\20260602T154636935172.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_11\20260602T154636958310.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_11\20260602T154636981087.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_11\20260602T154637005790.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_11\20260602T154637031307.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_11\20260602T154637057724.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_11\20260602T154637079443.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_11\20260602T154637107514.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_11\20260602T154637133814.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_11\20260602T154637157173.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_11\20260602T154637183703.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_11\20260602T154637213250.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_11\20260602T154637243976.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_11\20260602T154637280683.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_11\20260602T154637334218.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_11\20260602T154637382542.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_11\20260602T154637428601.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_11\20260602T154637481359.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_11\20260602T154637523633.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_11\20260602T154637562478.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_11\20260602T154637599859.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_11\20260602T154637646128.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_11\20260602T154637700129.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_11\20260602T154637748444.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_11\20260602T154637795801.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_11\20260602T154637846770.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_11\20260602T154637906030.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_11\20260602T154637957426.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_11\20260602T154638004457.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_11\20260602T154638053044.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_11\20260602T154638109049.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_11\20260602T154638157489.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_11\20260602T154638204217.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_11\20260602T154638267113.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_11\20260602T154638341072.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_11\20260602T154638404210.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_11\20260602T154638465294.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_11\20260602T154638514490.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_11\20260602T154638577817.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_12\20260526T154636715464.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_12\20260602T154636965791.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_12\20260602T154636987965.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_12\20260602T154637012061.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_12\20260602T154637039220.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_12\20260602T154637068236.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_12\20260602T154637087627.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_12\20260602T154637114945.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_12\20260602T154637143811.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_12\20260602T154637166410.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_12\20260602T154637196495.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_12\20260602T154637223149.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_12\20260602T154637265187.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_12\20260602T154637306306.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_12\20260602T154637361523.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_12\20260602T154637405760.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_12\20260602T154637455271.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_12\20260602T154637500000.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_12\20260602T154637545994.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_12\20260602T154637582222.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_12\20260602T154637618165.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_12\20260602T154637671630.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_12\20260602T154637717780.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_12\20260602T154637768651.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_12\20260602T154637815095.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_12\20260602T154637878993.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_12\20260602T154637928929.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_12\20260602T154637978227.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_12\20260602T154638024643.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_12\20260602T154638073538.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_12\20260602T154638133897.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_12\20260602T154638177188.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_12\20260602T154638234099.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_12\20260602T154638296918.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_12\20260602T154638377131.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_12\20260602T154638429261.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_12\20260602T154638488779.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_12\20260602T154638540197.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_12\20260602T154638611244.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_13\20260601T154636715972.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_13\20260602T154636988887.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_13\20260602T154637012736.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_13\20260602T154637039709.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_13\20260602T154637068727.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_13\20260602T154637088589.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_13\20260602T154637115542.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_13\20260602T154637144565.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_13\20260602T154637166904.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_13\20260602T154637196972.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_13\20260602T154637223603.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_13\20260602T154637265969.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_13\20260602T154637307948.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_13\20260602T154637362616.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_13\20260602T154637406857.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_13\20260602T154637457091.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_13\20260602T154637500605.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_13\20260602T154637547483.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_13\20260602T154637584012.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_13\20260602T154637620667.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_13\20260602T154637672793.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_13\20260602T154637719265.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_13\20260602T154637769948.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_13\20260602T154637816386.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_13\20260602T154637880786.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_13\20260602T154637930261.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_13\20260602T154637979499.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_13\20260602T154638026956.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_13\20260602T154638075554.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_13\20260602T154638136233.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_13\20260602T154638179411.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_13\20260602T154638236689.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_13\20260602T154638300806.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_13\20260602T154638379572.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_13\20260602T154638432873.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_13\20260602T154638491721.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_13\20260602T154638547643.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_13\20260602T154638615471.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_14\20260517T154636716524.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_14\20260602T154637009099.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_14\20260602T154637035235.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_14\20260602T154637064578.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_14\20260602T154637083775.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_14\20260602T154637112098.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_14\20260602T154637139283.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_14\20260602T154637162144.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_14\20260602T154637190455.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_14\20260602T154637217311.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_14\20260602T154637254959.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_14\20260602T154637290481.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_14\20260602T154637348567.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_14\20260602T154637397022.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_14\20260602T154637441861.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_14\20260602T154637490489.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_14\20260602T154637533226.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_14\20260602T154637572112.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_14\20260602T154637609336.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_14\20260602T154637663108.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_14\20260602T154637708949.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_14\20260602T154637759572.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_14\20260602T154637806118.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_14\20260602T154637861674.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_14\20260602T154637916293.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_14\20260602T154637968461.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_14\20260602T154638013738.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_14\20260602T154638063745.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_14\20260602T154638122555.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_14\20260602T154638166877.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_14\20260602T154638218144.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_14\20260602T154638278462.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_14\20260602T154638364780.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_14\20260602T154638414850.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_14\20260602T154638477659.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_14\20260602T154638527531.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_14\20260602T154638593494.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_15\20260524T154636717089.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_15\20260602T154637037280.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_15\20260602T154637066287.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_15\20260602T154637085364.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_15\20260602T154637113595.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_15\20260602T154637141446.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_15\20260602T154637164263.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_15\20260602T154637193519.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_15\20260602T154637220999.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_15\20260602T154637260191.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_15\20260602T154637299488.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_15\20260602T154637356540.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_15\20260602T154637402121.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_15\20260602T154637448493.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_15\20260602T154637496594.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_15\20260602T154637540812.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_15\20260602T154637577959.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_15\20260602T154637614549.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_15\20260602T154637668475.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_15\20260602T154637714721.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_15\20260602T154637765648.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_15\20260602T154637811218.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_15\20260602T154637871774.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_15\20260602T154637925388.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_15\20260602T154637973844.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_15\20260602T154638019657.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_15\20260602T154638069343.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_15\20260602T154638129756.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_15\20260602T154638172188.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_15\20260602T154638227031.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_15\20260602T154638286018.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_15\20260602T154638372136.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_15\20260602T154638423751.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_15\20260602T154638484370.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_15\20260602T154638533385.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_15\20260602T154638607014.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_16\20260512T154636717660.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_16\20260602T154637058751.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_16\20260602T154637081234.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_16\20260602T154637109396.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_16\20260602T154637135825.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_16\20260602T154637159061.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_16\20260602T154637185615.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_16\20260602T154637214626.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_16\20260602T154637249544.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_16\20260602T154637284614.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_16\20260602T154637337829.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_16\20260602T154637387664.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_16\20260602T154637432484.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_16\20260602T154637484047.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_16\20260602T154637526796.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_16\20260602T154637566384.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_16\20260602T154637602750.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_16\20260602T154637655189.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_16\20260602T154637703341.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_16\20260602T154637753494.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_16\20260602T154637801134.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_16\20260602T154637852552.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_16\20260602T154637910701.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_16\20260602T154637963816.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_16\20260602T154638008374.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_16\20260602T154638058557.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_16\20260602T154638117075.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_16\20260602T154638162331.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_16\20260602T154638210377.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_16\20260602T154638272493.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_16\20260602T154638353174.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_16\20260602T154638409078.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_16\20260602T154638469685.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_16\20260602T154638519186.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_16\20260602T154638583195.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_17\20260511T154636718223.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_17\20260602T154637080097.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_17\20260602T154637108059.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_17\20260602T154637134469.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_17\20260602T154637157669.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_17\20260602T154637184346.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_17\20260602T154637213737.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_17\20260602T154637247626.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_17\20260602T154637282804.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_17\20260602T154637335744.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_17\20260602T154637385232.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_17\20260602T154637429975.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_17\20260602T154637482737.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_17\20260602T154637525401.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_17\20260602T154637564648.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_17\20260602T154637601421.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_17\20260602T154637650622.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_17\20260602T154637701881.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_17\20260602T154637751199.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_17\20260602T154637799389.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_17\20260602T154637850271.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_17\20260602T154637909116.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_17\20260602T154637961728.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_17\20260602T154638007191.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_17\20260602T154638057166.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_17\20260602T154638115454.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_17\20260602T154638160875.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_17\20260602T154638208300.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_17\20260602T154638271288.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_17\20260602T154638349571.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_17\20260602T154638407944.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_17\20260602T154638468468.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_17\20260602T154638517461.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_17\20260602T154638581485.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_18\20260507T154636718953.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_18\20260602T154637105501.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_18\20260602T154637130402.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_18\20260602T154637154409.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_18\20260602T154637181222.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_18\20260602T154637210794.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_18\20260602T154637238310.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_18\20260602T154637277747.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_18\20260602T154637329360.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_18\20260602T154637378419.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_18\20260602T154637425419.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_18\20260602T154637478171.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_18\20260602T154637519797.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_18\20260602T154637558091.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_18\20260602T154637596500.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_18\20260602T154637639161.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_18\20260602T154637695541.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_18\20260602T154637742528.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_18\20260602T154637791228.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_18\20260602T154637840156.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_18\20260602T154637901119.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_18\20260602T154637953892.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_18\20260602T154638001316.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_18\20260602T154638049019.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_18\20260602T154638102675.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_18\20260602T154638153032.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_18\20260602T154638201550.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_18\20260602T154638263488.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_18\20260602T154638334576.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_18\20260602T154638401291.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_18\20260602T154638460006.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_18\20260602T154638511890.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_18\20260602T154638574658.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_19\20260507T154636719649.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_19\20260602T154637131542.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_19\20260602T154637155252.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_19\20260602T154637181930.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_19\20260602T154637211507.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_19\20260602T154637240478.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_19\20260602T154637278728.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_19\20260602T154637330374.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_19\20260602T154637379236.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_19\20260602T154637426286.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_19\20260602T154637478995.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_19\20260602T154637521057.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_19\20260602T154637558926.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_19\20260602T154637597338.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_19\20260602T154637640353.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_19\20260602T154637697391.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_19\20260602T154637743600.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_19\20260602T154637792175.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_19\20260602T154637842103.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_19\20260602T154637902274.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_19\20260602T154637954893.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_19\20260602T154638002129.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_19\20260602T154638049684.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_19\20260602T154638104567.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_19\20260602T154638154406.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_19\20260602T154638202121.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_19\20260602T154638264482.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_19\20260602T154638335766.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_19\20260602T154638402252.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_19\20260602T154638461130.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_19\20260602T154638512487.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_19\20260602T154638575446.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_2\20260518T154636709364.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_2\20260602T154636780603.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_2\20260602T154636795339.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_2\20260602T154636811528.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_2\20260602T154636827936.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_2\20260602T154636843875.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_2\20260602T154636862272.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_2\20260602T154636879376.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_2\20260602T154636898609.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_2\20260602T154636918577.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_2\20260602T154636939562.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_2\20260602T154636963546.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_2\20260602T154636984661.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_2\20260602T154637009555.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_2\20260602T154637036018.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_2\20260602T154637065273.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_2\20260602T154637084230.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_2\20260602T154637112593.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_2\20260602T154637139840.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_2\20260602T154637162873.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_2\20260602T154637192165.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_2\20260602T154637218856.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_2\20260602T154637256789.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_2\20260602T154637292968.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_2\20260602T154637351441.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_2\20260602T154637398623.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_2\20260602T154637443641.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_2\20260602T154637492306.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_2\20260602T154637535566.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_2\20260602T154637573772.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_2\20260602T154637610928.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_2\20260602T154637664346.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_2\20260602T154637710399.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_2\20260602T154637761069.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_2\20260602T154637807429.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_2\20260602T154637864539.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_2\20260602T154637918047.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_2\20260602T154637970132.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_2\20260602T154638014977.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_2\20260602T154638065081.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_2\20260602T154638125849.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_2\20260602T154638168143.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_2\20260602T154638219692.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_2\20260602T154638279825.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_2\20260602T154638367601.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_2\20260602T154638417945.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_2\20260602T154638480055.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_2\20260602T154638529435.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_2\20260602T154638599938.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_20\20260524T154636720225.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_20\20260602T154637164863.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_20\20260602T154637194167.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_20\20260602T154637221492.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_20\20260602T154637261319.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_20\20260602T154637301382.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_20\20260602T154637357782.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_20\20260602T154637403227.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_20\20260602T154637449674.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_20\20260602T154637497445.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_20\20260602T154637541913.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_20\20260602T154637578919.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_20\20260602T154637615453.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_20\20260602T154637669060.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_20\20260602T154637715266.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_20\20260602T154637766213.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_20\20260602T154637811733.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_20\20260602T154637873952.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_20\20260602T154637926269.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_20\20260602T154637974663.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_20\20260602T154638020253.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_20\20260602T154638070234.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_20\20260602T154638130318.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_20\20260602T154638173101.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_20\20260602T154638228058.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_20\20260602T154638287240.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_20\20260602T154638372804.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_20\20260602T154638424759.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_20\20260602T154638485161.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_20\20260602T154638533897.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_20\20260602T154638607583.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_21\20260517T154636720824.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_21\20260602T154637191260.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_21\20260602T154637218012.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_21\20260602T154637255895.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_21\20260602T154637291779.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_21\20260602T154637349724.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_21\20260602T154637397854.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_21\20260602T154637442811.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_21\20260602T154637491344.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_21\20260602T154637534473.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_21\20260602T154637572925.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_21\20260602T154637610366.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_21\20260602T154637663763.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_21\20260602T154637709540.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_21\20260602T154637760348.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_21\20260602T154637806749.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_21\20260602T154637863211.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_21\20260602T154637917350.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_21\20260602T154637969325.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_21\20260602T154638014341.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_21\20260602T154638064494.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_21\20260602T154638124819.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_21\20260602T154638167597.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_21\20260602T154638218980.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_21\20260602T154638279082.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_21\20260602T154638365650.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_21\20260602T154638415585.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_21\20260602T154638478406.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_21\20260602T154638528037.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_21\20260602T154638595449.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_22\20260523T154636721383.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_22\20260602T154637220483.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_22\20260602T154637259100.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_22\20260602T154637297805.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_22\20260602T154637354903.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_22\20260602T154637401396.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_22\20260602T154637447371.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_22\20260602T154637495734.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_22\20260602T154637539370.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_22\20260602T154637576504.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_22\20260602T154637612777.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_22\20260602T154637666462.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_22\20260602T154637712441.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_22\20260602T154637763295.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_22\20260602T154637809340.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_22\20260602T154637866805.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_22\20260602T154637921532.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_22\20260602T154637971994.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_22\20260602T154638017458.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_22\20260602T154638067073.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_22\20260602T154638127843.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_22\20260602T154638170048.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_22\20260602T154638222423.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_22\20260602T154638282833.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_22\20260602T154638369689.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_22\20260602T154638421087.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_22\20260602T154638482401.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_22\20260602T154638531267.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_22\20260602T154638604862.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_23\20260509T154636722040.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_23\20260602T154637246433.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_23\20260602T154637281687.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_23\20260602T154637335029.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_23\20260602T154637384078.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_23\20260602T154637429306.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_23\20260602T154637482011.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_23\20260602T154637524633.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_23\20260602T154637563726.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_23\20260602T154637600745.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_23\20260602T154637648376.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_23\20260602T154637701151.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_23\20260602T154637749207.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_23\20260602T154637797403.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_23\20260602T154637848048.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_23\20260602T154637906788.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_23\20260602T154637958320.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_23\20260602T154638005141.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_23\20260602T154638054158.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_23\20260602T154638110223.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_23\20260602T154638158068.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_23\20260602T154638204863.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_23\20260602T154638268199.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_23\20260602T154638343484.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_23\20260602T154638405238.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_23\20260602T154638466185.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_23\20260602T154638515016.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_23\20260602T154638578694.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_24\20260519T154636722596.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_24\20260602T154637294483.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_24\20260602T154637352865.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_24\20260602T154637399711.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_24\20260602T154637444820.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_24\20260602T154637493465.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_24\20260602T154637536963.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_24\20260602T154637574679.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_24\20260602T154637611414.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_24\20260602T154637664958.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_24\20260602T154637711032.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_24\20260602T154637761844.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_24\20260602T154637808013.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_24\20260602T154637865447.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_24\20260602T154637918727.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_24\20260602T154637970834.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_24\20260602T154638015898.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_24\20260602T154638065662.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_24\20260602T154638126499.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_24\20260602T154638168662.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_24\20260602T154638220365.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_24\20260602T154638280899.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_24\20260602T154638368220.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_24\20260602T154638419011.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_24\20260602T154638480949.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_24\20260602T154638529985.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_24\20260602T154638602680.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_25\20260513T154636723663.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_25\20260602T154637340011.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_25\20260602T154637390672.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_25\20260602T154637434702.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_25\20260602T154637485474.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_25\20260602T154637528372.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_25\20260602T154637568039.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_25\20260602T154637604144.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_25\20260602T154637658401.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_25\20260602T154637705173.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_25\20260602T154637755392.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_25\20260602T154637802425.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_25\20260602T154637855526.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_25\20260602T154637912075.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_25\20260602T154637965238.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_25\20260602T154638009964.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_25\20260602T154638060332.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_25\20260602T154638118367.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_25\20260602T154638163619.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_25\20260602T154638212311.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_25\20260602T154638274369.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_25\20260602T154638357586.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_25\20260602T154638410567.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_25\20260602T154638471155.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_25\20260602T154638522629.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_25\20260602T154638586428.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_26\20260513T154636724267.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_26\20260602T154637392030.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_26\20260602T154637436088.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_26\20260602T154637486471.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_26\20260602T154637529035.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_26\20260602T154637568871.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_26\20260602T154637604795.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_26\20260602T154637659663.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_26\20260602T154637705869.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_26\20260602T154637756136.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_26\20260602T154637803211.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_26\20260602T154637857027.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_26\20260602T154637912707.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_26\20260602T154637965791.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_26\20260602T154638010697.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_26\20260602T154638061158.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_26\20260602T154638119119.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_26\20260602T154638164298.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_26\20260602T154638213984.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_26\20260602T154638275142.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_26\20260602T154638359518.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_26\20260602T154638411174.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_26\20260602T154638472799.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_26\20260602T154638523756.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_26\20260602T154638587513.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_27\20260525T154636724819.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_27\20260602T154637452515.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_27\20260602T154637498600.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_27\20260602T154637543713.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_27\20260602T154637580476.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_27\20260602T154637616701.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_27\20260602T154637670161.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_27\20260602T154637716729.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_27\20260602T154637767569.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_27\20260602T154637813894.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_27\20260602T154637877334.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_27\20260602T154637927845.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_27\20260602T154637976930.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_27\20260602T154638022377.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_27\20260602T154638072252.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_27\20260602T154638132093.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_27\20260602T154638174954.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_27\20260602T154638231848.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_27\20260602T154638291777.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_27\20260602T154638374849.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_27\20260602T154638427253.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_27\20260602T154638486845.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_27\20260602T154638536026.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_27\20260602T154638609240.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_28\20260506T154636725345.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_28\20260602T154637477192.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_28\20260602T154637518151.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_28\20260602T154637557132.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_28\20260602T154637595220.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_28\20260602T154637638003.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_28\20260602T154637693007.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_28\20260602T154637739098.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_28\20260602T154637788071.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_28\20260602T154637835551.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_28\20260602T154637897647.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_28\20260602T154637950726.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_28\20260602T154637999650.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_28\20260602T154638047154.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_28\20260602T154638098485.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_28\20260602T154638148537.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_28\20260602T154638198954.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_28\20260602T154638261206.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_28\20260602T154638330183.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_28\20260602T154638399123.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_28\20260602T154638457915.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_28\20260602T154638509784.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_28\20260602T154638572156.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_29\20260526T154636725843.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_29\20260602T154637546875.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_29\20260602T154637583044.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_29\20260602T154637619273.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_29\20260602T154637672206.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_29\20260602T154637718473.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_29\20260602T154637769182.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_29\20260602T154637815619.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_29\20260602T154637880085.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_29\20260602T154637929504.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_29\20260602T154637978848.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_29\20260602T154638025620.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_29\20260602T154638074128.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_29\20260602T154638134763.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_29\20260602T154638177958.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_29\20260602T154638235129.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_29\20260602T154638298087.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_29\20260602T154638377958.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_29\20260602T154638429900.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_29\20260602T154638489461.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_29\20260602T154638542291.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_29\20260602T154638612652.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_3\20260517T154636710014.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_3\20260602T154636794790.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_3\20260602T154636810860.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_3\20260602T154636827443.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_3\20260602T154636843325.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_3\20260602T154636861819.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_3\20260602T154636878906.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_3\20260602T154636898135.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_3\20260602T154636918117.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_3\20260602T154636938885.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_3\20260602T154636962925.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_3\20260602T154636983797.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_3\20260602T154637008446.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_3\20260602T154637034757.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_3\20260602T154637062286.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_3\20260602T154637083319.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_3\20260602T154637111451.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_3\20260602T154637138660.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_3\20260602T154637161580.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_3\20260602T154637189473.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_3\20260602T154637216674.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_3\20260602T154637253864.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_3\20260602T154637289098.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_3\20260602T154637346445.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_3\20260602T154637396046.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_3\20260602T154637439826.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_3\20260602T154637489537.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_3\20260602T154637531805.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_3\20260602T154637571108.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_3\20260602T154637608755.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_3\20260602T154637662024.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_3\20260602T154637708283.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_3\20260602T154637758845.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_3\20260602T154637805200.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_3\20260602T154637860348.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_3\20260602T154637915236.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_3\20260602T154637967786.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_3\20260602T154638013074.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_3\20260602T154638063103.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_3\20260602T154638121262.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_3\20260602T154638166276.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_3\20260602T154638217091.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_3\20260602T154638277727.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_3\20260602T154638363790.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_3\20260602T154638414138.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_3\20260602T154638476822.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_3\20260602T154638526926.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_3\20260602T154638591638.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_30\20260523T154636726425.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_30\20260602T154637577254.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_30\20260602T154637613372.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_30\20260602T154637667039.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_30\20260602T154637713464.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_30\20260602T154637764083.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_30\20260602T154637809911.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_30\20260602T154637867383.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_30\20260602T154637924005.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_30\20260602T154637972700.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_30\20260602T154638018134.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_30\20260602T154638067852.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_30\20260602T154638128369.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_30\20260602T154638170699.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_30\20260602T154638223877.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_30\20260602T154638283903.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_30\20260602T154638370475.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_30\20260602T154638422002.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_30\20260602T154638483155.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_30\20260602T154638532047.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_30\20260602T154638605569.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_31\20260523T154636726980.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_31\20260602T154637614056.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_31\20260602T154637667614.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_31\20260602T154637714141.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_31\20260602T154637764979.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_31\20260602T154637810495.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_31\20260602T154637870262.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_31\20260602T154637924742.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_31\20260602T154637973253.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_31\20260602T154638018982.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_31\20260602T154638068676.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_31\20260602T154638128987.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_31\20260602T154638171465.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_31\20260602T154638225503.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_31\20260602T154638284981.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_31\20260602T154638371317.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_31\20260602T154638422839.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_31\20260602T154638483761.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_31\20260602T154638532817.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_31\20260602T154638606318.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_32\20260504T154636727496.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_32\20260602T154637636702.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_32\20260602T154637691238.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_32\20260602T154637737850.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_32\20260602T154637786433.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_32\20260602T154637833734.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_32\20260602T154637893758.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_32\20260602T154637949260.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_32\20260602T154637998199.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_32\20260602T154638045082.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_32\20260602T154638093767.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_32\20260602T154638146932.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_32\20260602T154638196287.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_32\20260602T154638257530.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_32\20260602T154638326580.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_32\20260602T154638395534.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_32\20260602T154638454543.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_32\20260602T154638506658.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_32\20260602T154638568776.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_33\20260506T154636728128.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_33\20260602T154637694261.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_33\20260602T154637740926.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_33\20260602T154637789318.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_33\20260602T154637837230.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_33\20260602T154637899691.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_33\20260602T154637952237.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_33\20260602T154638000340.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_33\20260602T154638048309.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_33\20260602T154638100431.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_33\20260602T154638149489.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_33\20260602T154638199978.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_33\20260602T154638261975.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_33\20260602T154638331175.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_33\20260602T154638399882.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_33\20260602T154638458634.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_33\20260602T154638510355.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_33\20260602T154638573017.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_34\20260510T154636728719.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_34\20260602T154637750057.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_34\20260602T154637798298.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_34\20260602T154637849090.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_34\20260602T154637907816.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_34\20260602T154637959398.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_34\20260602T154638005779.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_34\20260602T154638055815.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_34\20260602T154638113521.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_34\20260602T154638159428.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_34\20260602T154638206810.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_34\20260602T154638269582.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_34\20260602T154638346103.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_34\20260602T154638406644.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_34\20260602T154638467458.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_34\20260602T154638516004.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_34\20260602T154638580014.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_35\20260524T154636729436.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_35\20260602T154637812439.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_35\20260602T154637875133.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_35\20260602T154637926863.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_35\20260602T154637975503.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_35\20260602T154638020846.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_35\20260602T154638070871.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_35\20260602T154638130880.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_35\20260602T154638173761.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_35\20260602T154638228941.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_35\20260602T154638288546.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_35\20260602T154638373405.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_35\20260602T154638425578.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_35\20260602T154638485743.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_35\20260602T154638534726.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_35\20260602T154638608161.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_36\20260504T154636730048.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_36\20260602T154637834734.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_36\20260602T154637894988.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_36\20260602T154637949941.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_36\20260602T154637998991.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_36\20260602T154638046255.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_36\20260602T154638096169.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_36\20260602T154638147739.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_36\20260602T154638197436.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_36\20260602T154638258480.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_36\20260602T154638327520.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_36\20260602T154638396488.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_36\20260602T154638455506.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_36\20260602T154638507571.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_36\20260602T154638569819.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_37\20260510T154636730735.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_37\20260602T154637908498.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_37\20260602T154637960413.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_37\20260602T154638006431.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_37\20260602T154638056535.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_37\20260602T154638114609.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_37\20260602T154638160108.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_37\20260602T154638207545.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_37\20260602T154638270287.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_37\20260602T154638348135.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_37\20260602T154638407167.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_37\20260602T154638467974.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_37\20260602T154638516891.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_37\20260602T154638580739.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_38\20260503T154636731668.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_38\20260602T154637948455.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_38\20260602T154637996888.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_38\20260602T154638043704.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_38\20260602T154638091516.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_38\20260602T154638145885.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_38\20260602T154638195114.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_38\20260602T154638256103.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_38\20260602T154638325339.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_38\20260602T154638394041.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_38\20260602T154638453674.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_38\20260602T154638505830.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_38\20260602T154638567802.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_39\20260528T154636732675.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_39\20260602T154638026388.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_39\20260602T154638074696.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_39\20260602T154638135501.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_39\20260602T154638178601.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_39\20260602T154638235909.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_39\20260602T154638299581.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_39\20260602T154638378778.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_39\20260602T154638431104.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_39\20260602T154638490213.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_39\20260602T154638544448.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_39\20260602T154638613536.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_4\20260526T154636710582.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_4\20260602T154636812418.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_4\20260602T154636829068.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_4\20260602T154636844899.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_4\20260602T154636863251.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_4\20260602T154636880787.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_4\20260602T154636900183.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_4\20260602T154636920312.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_4\20260602T154636941840.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_4\20260602T154636965307.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_4\20260602T154636987144.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_4\20260602T154637011368.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_4\20260602T154637038667.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_4\20260602T154637067760.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_4\20260602T154637086506.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_4\20260602T154637114482.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_4\20260602T154637142714.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_4\20260602T154637165790.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_4\20260602T154637195966.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_4\20260602T154637222654.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_4\20260602T154637264166.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_4\20260602T154637304820.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_4\20260602T154637360052.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_4\20260602T154637404903.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_4\20260602T154637453683.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_4\20260602T154637499301.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_4\20260602T154637545018.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_4\20260602T154637581313.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_4\20260602T154637617208.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_4\20260602T154637671027.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_4\20260602T154637717245.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_4\20260602T154637768134.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_4\20260602T154637814525.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_4\20260602T154637878143.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_4\20260602T154637928450.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_4\20260602T154637977513.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_4\20260602T154638023443.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_4\20260602T154638072951.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_4\20260602T154638133269.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_4\20260602T154638176491.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_4\20260602T154638233408.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_4\20260602T154638294778.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_4\20260602T154638376438.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_4\20260602T154638428649.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_4\20260602T154638488057.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_4\20260602T154638538820.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_4\20260602T154638610315.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_40\20260509T154636733572.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_40\20260602T154638054972.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_40\20260602T154638111873.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_40\20260602T154638158645.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_40\20260602T154638205949.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_40\20260602T154638268904.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_40\20260602T154638344846.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_40\20260602T154638406069.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_40\20260602T154638466889.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_40\20260602T154638515502.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_40\20260602T154638579424.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_41\20260525T154636734272.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_41\20260602T154638132630.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_41\20260602T154638175784.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_41\20260602T154638232625.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_41\20260602T154638293472.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_41\20260602T154638375587.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_41\20260602T154638428022.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_41\20260602T154638487564.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_41\20260602T154638537039.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_41\20260602T154638609710.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_42\20260506T154636734870.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_42\20260602T154638151087.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_42\20260602T154638200724.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_42\20260602T154638262788.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_42\20260602T154638332981.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_42\20260602T154638400624.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_42\20260602T154638459242.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_42\20260602T154638511070.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_42\20260602T154638573815.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_43\20260504T154636735489.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_43\20260602T154638198283.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_43\20260602T154638259318.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_43\20260602T154638328211.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_43\20260602T154638397191.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_43\20260602T154638456278.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_43\20260602T154638508279.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_43\20260602T154638570772.json.gz` (.gz, 230 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_44\20260505T154636736261.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_44\20260602T154638260221.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_44\20260602T154638329170.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_44\20260602T154638397975.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_44\20260602T154638457208.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_44\20260602T154638509178.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_44\20260602T154638571522.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_45\20260517T154636737050.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_45\20260602T154638366879.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_45\20260602T154638416650.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_45\20260602T154638479156.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_45\20260602T154638528614.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_45\20260602T154638597875.json.gz` (.gz, 228 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_46\20260513T154636737645.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_46\20260602T154638411704.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_46\20260602T154638473589.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_46\20260602T154638524742.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_46\20260602T154638588432.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_47\20260531T154636738448.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_47\20260602T154638490997.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_47\20260602T154638546489.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_47\20260602T154638614858.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_48\20260512T154636739222.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_48\20260602T154638520869.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_48\20260602T154638583873.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_49\20260530T154636739889.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_49\20260602T154638614213.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_5\20260512T154636711196.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_5\20260602T154636826227.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_5\20260602T154636840817.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_5\20260602T154636859001.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_5\20260602T154636876553.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_5\20260602T154636896195.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_5\20260602T154636914736.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_5\20260602T154636935846.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_5\20260602T154636959272.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_5\20260602T154636981613.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_5\20260602T154637006308.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_5\20260602T154637032005.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_5\20260602T154637058231.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_5\20260602T154637080757.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_5\20260602T154637108819.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_5\20260602T154637135023.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_5\20260602T154637158256.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_5\20260602T154637185097.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_5\20260602T154637214190.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_5\20260602T154637248608.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_5\20260602T154637283634.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_5\20260602T154637336505.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_5\20260602T154637386475.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_5\20260602T154637431170.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_5\20260602T154637483308.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_5\20260602T154637526079.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_5\20260602T154637565609.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_5\20260602T154637602026.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_5\20260602T154637652923.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_5\20260602T154637702613.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_5\20260602T154637752208.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_5\20260602T154637800364.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_5\20260602T154637851485.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_5\20260602T154637909691.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_5\20260602T154637963134.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_5\20260602T154638007830.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_5\20260602T154638057807.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_5\20260602T154638116436.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_5\20260602T154638161534.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_5\20260602T154638209338.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_5\20260602T154638271922.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_5\20260602T154638351179.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_5\20260602T154638408524.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_5\20260602T154638469136.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_5\20260602T154638518166.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_5\20260602T154638582475.json.gz` (.gz, 225 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_6\20260513T154636711740.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_6\20260602T154636842104.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_6\20260602T154636859784.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_6\20260602T154636877277.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_6\20260602T154636896749.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_6\20260602T154636915661.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_6\20260602T154636936443.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_6\20260602T154636959920.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_6\20260602T154636982105.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_6\20260602T154637006917.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_6\20260602T154637032938.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_6\20260602T154637059491.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_6\20260602T154637081803.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_6\20260602T154637109903.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_6\20260602T154637136397.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_6\20260602T154637159524.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_6\20260602T154637186709.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_6\20260602T154637215160.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_6\20260602T154637251088.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_6\20260602T154637285893.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_6\20260602T154637338791.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_6\20260602T154637388812.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_6\20260602T154637433837.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_6\20260602T154637484682.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_6\20260602T154637527622.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_6\20260602T154637567129.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_6\20260602T154637603482.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_6\20260602T154637656956.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_6\20260602T154637704403.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_6\20260602T154637754421.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_6\20260602T154637801821.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_6\20260602T154637854103.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_6\20260602T154637911423.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_6\20260602T154637964573.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_6\20260602T154638009076.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_6\20260602T154638059432.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_6\20260602T154638117692.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_6\20260602T154638162953.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_6\20260602T154638211342.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_6\20260602T154638273139.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_6\20260602T154638355622.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_6\20260602T154638409616.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_6\20260602T154638470338.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_6\20260602T154638521823.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_6\20260602T154638584826.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_7\20260515T154636712453.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_7\20260602T154636860692.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_7\20260602T154636877790.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_7\20260602T154636897244.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_7\20260602T154636916659.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_7\20260602T154636937051.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_7\20260602T154636960908.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_7\20260602T154636982558.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_7\20260602T154637007420.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_7\20260602T154637033743.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_7\20260602T154637060084.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_7\20260602T154637082278.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_7\20260602T154637110408.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_7\20260602T154637136967.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_7\20260602T154637160017.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_7\20260602T154637187839.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_7\20260602T154637215614.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_7\20260602T154637252078.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_7\20260602T154637286991.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_7\20260602T154637341526.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_7\20260602T154637393078.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_7\20260602T154637437468.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_7\20260602T154637487218.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_7\20260602T154637529752.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_7\20260602T154637569582.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_7\20260602T154637605642.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_7\20260602T154637660548.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_7\20260602T154637706487.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_7\20260602T154637756986.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_7\20260602T154637803789.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_7\20260602T154637858259.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_7\20260602T154637913711.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_7\20260602T154637966276.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_7\20260602T154638011408.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_7\20260602T154638061917.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_7\20260602T154638119904.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_7\20260602T154638165100.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_7\20260602T154638215123.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_7\20260602T154638275853.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_7\20260602T154638361028.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_7\20260602T154638412206.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_7\20260602T154638474699.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_7\20260602T154638525420.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_7\20260602T154638589729.json.gz` (.gz, 224 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_8\20260525T154636713156.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_8\20260602T154636880370.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_8\20260602T154636899532.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_8\20260602T154636919477.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_8\20260602T154636940818.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_8\20260602T154636964532.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_8\20260602T154636986216.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_8\20260602T154637010550.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_8\20260602T154637037851.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_8\20260602T154637067211.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_8\20260602T154637085878.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_8\20260602T154637114040.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_8\20260602T154637142022.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_8\20260602T154637165322.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_8\20260602T154637195322.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_8\20260602T154637221981.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_8\20260602T154637262269.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_8\20260602T154637303107.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_8\20260602T154637358899.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_8\20260602T154637404006.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_8\20260602T154637451350.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_8\20260602T154637498052.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_8\20260602T154637542912.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_8\20260602T154637579622.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_8\20260602T154637616028.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_8\20260602T154637669594.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_8\20260602T154637716179.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_8\20260602T154637766772.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_8\20260602T154637813059.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_8\20260602T154637876537.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_8\20260602T154637927367.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_8\20260602T154637976220.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_8\20260602T154638021487.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_8\20260602T154638071446.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_8\20260602T154638131408.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_8\20260602T154638174351.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_8\20260602T154638230542.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_8\20260602T154638290178.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_8\20260602T154638374038.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_8\20260602T154638426490.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_8\20260602T154638486268.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_8\20260602T154638535333.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_8\20260602T154638608722.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_9\20260509T154636713769.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_9\20260602T154636895350.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_9\20260602T154636913859.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_9\20260602T154636934662.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_9\20260602T154636957791.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_9\20260602T154636980236.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_9\20260602T154637005211.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_9\20260602T154637030540.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_9\20260602T154637057202.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_9\20260602T154637078912.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_9\20260602T154637107004.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_9\20260602T154637133232.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_9\20260602T154637156695.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_9\20260602T154637183193.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_9\20260602T154637212605.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_9\20260602T154637242819.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_9\20260602T154637279785.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_9\20260602T154637332852.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_9\20260602T154637381625.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_9\20260602T154637427873.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_9\20260602T154637480685.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_9\20260602T154637522886.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_9\20260602T154637560933.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_9\20260602T154637598745.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_9\20260602T154637643891.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_9\20260602T154637699279.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_9\20260602T154637747630.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_9\20260602T154637794294.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_9\20260602T154637845716.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_9\20260602T154637905155.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_9\20260602T154637956633.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_9\20260602T154638003525.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_9\20260602T154638051430.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_9\20260602T154638108034.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_9\20260602T154638156754.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_9\20260602T154638203548.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_9\20260602T154638266175.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_9\20260602T154638338713.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_9\20260602T154638403608.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_9\20260602T154638464327.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_9\20260602T154638513635.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\BATCH_FIX_9\20260602T154638577100.json.gz` (.gz, 229 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\MOCK_FIX_1\20260602T134445006719.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\MOCK_FIX_1\20260602T134500006719.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\MOCK_FIX_1\20260602T154445038578.json.gz` (.gz, 227 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\data_acquisition\raw_frames\MOCK_FIX_1\20260602T154445039443.json.gz` (.gz, 226 bytes): Compressed raw frame archive used for replay/historical simulation.
- `src\decoded_blob_0.json` (.json, 44880 bytes): Structured data/config/cache/telemetry artifact.
- `src\decoded_blob_1.json` (.json, 120708 bytes): Structured data/config/cache/telemetry artifact.
- `src\decoded_blob_2.json` (.json, 2929 bytes): Structured data/config/cache/telemetry artifact.
- `src\downloaded_files\driver_fixing.lock` (.lock, 0 bytes): Operational artifact, probe output, lock, shortcut, or log.
- `src\live_data.db` (.db, 32768 bytes): SQLite database artifact; schema documented in main documentation.
- `src\preloaded_state.json` (.json, 120708 bytes): Structured data/config/cache/telemetry artifact.
- `src\templates\index.html` (.html, 123850 bytes): Operational artifact, probe output, lock, shortcut, or log.
- `src\test_output.txt` (.txt, 398730 bytes): Repository artifact.
- `START_AUTO_PREDICTOR.bat` (.bat, 490 bytes): Configuration, migration, container, CI, or launch script.
- `START_AUTO_PREDICTOR.bat - Shortcut.lnk` (.lnk, 1403 bytes): Operational artifact, probe output, lock, shortcut, or log.
- `SYSTEM_AUDIT_DOCUMENTATION.md` (.md, 27569 bytes): Markdown documentation.
- `telemetry_warehouse\parquet\executions_2026-06-02.parquet` (.parquet, 9916 bytes): Structured data/config/cache/telemetry artifact.
- `tsdb_teams.json` (.json, 46111 bytes): Structured data/config/cache/telemetry artifact.
- `USER_GUIDE.md` (.md, 4406 bytes): Markdown documentation.
- `USER_GUIDE_HISTORICAL.md` (.md, 7530 bytes): Markdown documentation.