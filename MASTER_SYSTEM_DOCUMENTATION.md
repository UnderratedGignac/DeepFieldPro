# DeepFieldPro: Definitive Technical Blueprint

*This document is the authoritative, comprehensive technical specification for the DeepFieldPro platform.*

---

## 1. Executive Summary
DeepFieldPro is an institutional-grade quantitative sports betting platform engineered for high-frequency data acquisition, predictive modeling, and autonomous capital deployment.

**Core Capabilities:**
*   **Stealth Scraping:** Browser-based acquisition using automated Playwright sessions.
*   **Probabilistic Modeling:** Hierarchical LightGBM models for player prop and team-level forecasts.
*   **Dynamic Staking:** Capital allocation using fractional Kelly criteria, adjusted by market regime.
*   **Shadow Deployment:** Real-time paper trading validation against live market outcomes.
*   **Institutional Risk Governance:** Automated drawdown protection, exposure capping, and safety halts.

---

## 2. Project Structure & Repository Map
(See repository root for full list)

---

## 3. File-by-File Documentation: `src/` Root

### `account_manager.py`
*   **Purpose:** Orchestrates authentication and bookmaker account state management.
*   **Responsibilities:** Loads credentials, initializes local SQLite store, manages session-state consistency.
*   **Security:** Handles credentials; ensure access is gated.

### `advanced_training_pipeline.py`
*   **Purpose:** Orchestrates hierarchical ML training.
*   **Logic:** Executes player-level training, generates out-of-fold predictions, then performs team-level training.

### `alerter.py`
*   **Purpose:** Multi-channel alerting dispatcher (e.g., Telegram).

### `app_config.py`
*   **Purpose:** Centralized configuration provider.

### `audit_data.py`
*   **Purpose:** Data integrity audit tool for the `FULL_PLAYER_DATABASE`.

### `backtester.py`
*   **Purpose:** Historical replay and backtesting engine.

### `bankroll_tracker.py`
*   **Purpose:** Core bankroll management and drawdown governance.
*   **Critical Logic:** Differentiates between `current_balance` (liquid cash) and "at-risk" stake.

### `betarabia_scraper.py`
*   **Purpose:** Live odds scraping for Betarabia.

### `bet_logger.py`
*   **Purpose:** Records all formally placed bets.

---

## 4. Subdirectory Documentation

### 📁 Directory: `src/adversarial_detection`
*   **`hidden_markov_throttle_detector.py`**: Adversarial Sportsbook Detection Engine. Uses Hidden Markov modeling to estimate $P(account\_restricted | behavior)$ based on latency and rejection signals.

### 📁 Directory: `src/autonomous_portfolio_evolution`
*   **`apel_engine.py`**: Autonomous Portfolio Evolution Layer (APEL). Manages the lifecycle of multiple betting strategies. Automatically retires strategies exhibiting structural decay.
*   **`apel_simulation_lab.py`**: Simulation harness for testing strategy evolution paths.
*   **`schemas.py`**: Data structures (`StrategyGenome`, `StrategyState`) for the APEL evolution engine.

### 📁 Directory: `src/capital_deployment_protocol`
*   **`deployment_orchestrator.py`**: Master entrypoint for the Capital Deployment Protocol (CDP).
*   **`capital_ramp_controller.py`**: Computes the maximum capital allocation cap.
*   **`live_capital_switch.py`**: Safety lock (kill-switch) implementation.
*   **`regime_sensitive_position_sizing.py`**: Scales positions dynamically based on market regimes.
*   **`rollout_state_machine.py`**: Deterministic state machine for rollout phases.
*   **`state_persistence.py`**: SQLite serialization/deserialization for CDP state.
*   **`schemas.py`**: Data structures for phases (`RolloutPhase`), health (`HealthStatus`), and state.

### 📁 Directory: `src/capital_scaling_intelligence`
*   **`acsi_engine.py`**: Autonomous Capital Scaling Intelligence (ACSI) orchestrator.
*   **`capital_velocity_controller.py`**: Tracks and regulates the rate at which capital is deployed.
*   **`growth_vs_risk_optimizer.py`**: Optimizes trade-off between aggressive compounding and risk tolerance.
*   **`regime_compounding_detector.py`**: Detects market regimes to determine if compounding is safe.
*   **`long_horizon_ev_forecaster.py`**: Long-term EV forecasting to guide structural scaling decisions.
*   **`acsi_simulation_lab.py`**: Simulation harness for ACSI strategies.

### 📁 Directory: `src/config`
*   **`settings.py`**: Centralized runtime settings management.

### 📁 Directory: `src/data`
*   **`advanced_fbref_scraper.py`**: Advanced scraper for FBref match/player data.
*   **`deepfield.db` / `bet_log.db`**: Local operational SQLite databases.

### 📁 Directory: `src/database`
*   **`models.py`**: Definitive SQLAlchemy ORM models for all system entities.
*   **`migrate.py`**: Database initialization and migration script.

### 📁 Directory: `src/data_acquisition`
*   **`db_writer.py`**: High-performance database writer. Implements buffering to prevent DB locking.
*   **`websocket_parser.py`**: Raw WebSocket frame handler. Decodes raw frames into standardized `OddsTick` representations.
*   **`replay_engine.py`**: Historical replay engine. Enables deterministic simulation.
*   **Scrapers/Engines/Listeners:** (`betarabia_scraper.py`, `clv_engine.py`, `edge_engine.py`...) Standardizing inputs via the `normalization_engine`.

### 📁 Directory: `src/execution_cluster`
*   **`actor_orchestrator.py`**: Orchestrates concurrent execution actors (e.g., individual browser sessions).

### 📁 Directory: `src/features`
*   **`generate_all.py`**: Orchestrator for all feature engineering scripts.
*   **Feature Modules (`availability.py`, `fatigue.py`, etc.):** Independent feature engineering modules.

### 📁 Directory: `src/live_operations`
*   **`account_health_engine.py`**: Tracks sportsbook account trust scores.
*   **`alerting_system.py`**: Multi-channel alert dispatcher for system failures.
*   **`edge_decay_live.py`**: Monitors real-time EV evaporation.
*   **`live_clv_tracker.py`**: Tracks CLV in real-time.
*   **`shadow_deployment_orchestrator.py`**: Continuous shadow execution layer.

### 📁 Directory: `src/meta_research`
*   **`meta_research_governor.py`**: Meta-level governance for research automation.

### 📁 Directory: `src/ml`
*   **`online_learning/concept_drift_monitor.py`**: Detects concept drift in live telemetry.

### 📁 Directory: `src/models`
*   **`calibration_engine.py`**: Calibrates LightGBM probabilities.
*   **`expected_minutes.py`**: Probabilistic xMin engine.
*   **`train_prop_model.py`**: Training pipeline for prop models.

### 📁 Directory: `src/portfolio_optimization`
*   **`bayesian_confidence_engine.py`**: Posterior uncertainty tracking.
*   **`capital_allocation_engine.py`**: Jointly optimizes EV, volatility, correlation, and liquidity.
*   **`drawdown_governor.py`**: Dynamic reduction of aggressiveness during poor regimes.
*   **`dynamic_bankroll_allocator.py`**: Kelly + Regime-Aware Exposure Control.
*   **`liquidity_impact_model.py`**: Market impact and suspension risk estimation.
*   **`portfolio_correlation_engine.py`**: Dynamic exposure overlap detection.
*   **`portfolio_research_lab.py`**: Research simulation harness.

### 📁 Directory: `src/research`
*   **`meta_governor/`**: Governance for learning rate, regret, health.
*   **`policy_outcome_auditor/`**: Regret engine, counterfactual outcomes, validation.
*   **`real_world_validation/`**: Performance attribution, friction analysis, alignment checks.
*   **`validation_framework/`**: Combinatorial Purged CV.

### 📁 Directory: `src/research_os`
*   **`experiment_registry.py`**: Research hypothese tracking.
*   **`strategy_graveyard.py`**: Retired/rejected strategies record.
*   **`strategy_lifecycle.py`**: State machine (RESEARCH → PRODUCTION → RETIRED).

### 📁 Directory: `src/risk_engine`
*   **`conditional_var_simulator.py`**: VaR risk simulation.
*   **`no_bet_filter.py`**: Bet gatekeeper.

### 📁 Directory: `src/services`
*   **Microservices (`backtesting`, `clv`, `market_intelligence`, `normalizer`, `odds_acquisition`, `risk_engine`, `session_manager`, `shadow_execution`, `validation`):** Decoupled, modular services for core betting operations.

### 📁 Directory: `src/telemetry_warehouse`
*   **`adversarial_pattern_miner.py`**: Anomaly detection for bookmaker countermeasures.
*   **`clv_tracker.py`**: CLV computation and warehousing.
*   **`data_quality_monitor.py`**: Telemetry quality metrics.
*   **`execution_ecology_engine.py`**: Health metrics for execution.
*   **`sportsbook_behavior_fingerprinter.py`**: Behavior signature discovery.
*   **`telemetry_archiver.py`**: Dumps fast-memory SQLite into long-term Parquet lake.
