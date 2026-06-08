# DeepFieldPro: Comprehensive Master Technical Documentation

---

## 1. Executive Summary
**System Name:** DeepFieldPro
**Purpose:** Automated, high-frequency sportsbook data acquisition and betting intelligence system.
**Business Goals:** Identify +EV (Expected Value) opportunities in football player prop markets using proprietary ML models.
**Architecture Pattern:** Modular, decoupled, production-grade micro-services architecture.

## 2. Complete Feature Inventory
| Feature Name | Purpose | Files Involved |
| :--- | :--- | :--- |
| **Data Acquisition** | Scrape match/player data. | `src/data_pipeline.py`, `src/betarabia_scraper.py` |
| **Prediction Engine** | Probability distributions via LightGBM. | `src/engine_predictor.py` |
| **Betting Engine** | EV identification and staking. | `src/engine_bettor.py`, `src/engine_staker.py` |
| **Live Execution** | Automated browser-based betting. | `src/services/session_manager/`, `src/execution_engine.py` |
| **Risk Governance** | Bankroll/Drawdown control. | `src/services/risk_engine/`, `src/portfolio_optimization/` |

## 3. System Architecture
[Mermaid Diagram Placeholder]
*Design Decision: SQLite3 chosen for local performance; Flat-file JSON state for fast UI decoupled from AI loop.*

## 4. Database Documentation
- **Databases:** `bankroll.db`, `bet_log.db`, `odds_stream.db`
- **Critical Tables:** `fixtures`, `odds_ticks`, `bets`, `predictions`
- **Schema:** Managed via SQLAlchemy ORM (`src/database/models.py`).

## 5. AI / ML Documentation
- **Framework:** LightGBM
- **Key Models:** `lgbm_goals.pkl`, `lgbm_shots.pkl`, `player_impact_model.pkl`

## 6. Deployment & Configuration
- **Environment:** Python 3.10
- **Configuration:** Managed via `.env` (API keys, bankroll thresholds).
- **CI/CD:** GitHub Actions enforcing Black 25.11.0.

## 7. Historical Context & Technical Debt
- **Note:** Previous architecture relied on PostgreSQL/TimescaleDB. System was refactored for local performance and simplicity using SQLite.
- **Reference:** For details on the original complex stack, refer to historical `ARCHITECTURE.md` (archived June 2026).

---

*(This master file provides a comprehensive overview of the system architecture, feature set, data persistence models, and AI/ML model registry.)*
