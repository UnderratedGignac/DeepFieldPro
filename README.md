# DeepFieldPro - Institutional-Grade Quantitative Sports Betting Platform

![CI/CD Pipeline](https://github.com/deepfieldpro/deepfieldpro/actions/workflows/deepfield_pipeline.yml/badge.svg)
![License](https://img.shields.io/badge/license-proprietary-red.svg)
![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![Status](https://img.shields.io/badge/status-production--ready-green.svg)

## 🏗 Executive Summary

DeepFieldPro is a **fully integrated, institutional-grade quantitative sports betting platform** that transforms theoretical research into live market validation. The system combines stealth data acquisition, scientific backtesting, continuous shadow deployment, and rigorous risk management to answer one critical question:

> **"Does our edge survive real-world market conditions, latency, and sportsbook adaptation?"**

### Core Capabilities

✅ **24/7 Live Data Acquisition** - Playwright-based browser orchestration with anti-detection  
✅ **Immutable Odds Storage** - TimescaleDB time-series storage for every market movement  
✅ **Scientific Validation** - Walk-forward testing, Monte Carlo simulation, leakage detection  
✅ **Shadow Deployment** - Continuous paper trading with real-time CLV tracking  
✅ **Risk Management** - Fractional Kelly, exposure caps, automatic kill-switches  
✅ **Research Governance** - Experiment registry, strategy lifecycle, promotion/rejection engine  
✅ **Live Operations** - Execution telemetry, account health monitoring, edge decay detection  

✅ **Live Operations** - Execution telemetry, account health monitoring, edge decay detection  

---

## 🚀 How to Start the Project (For Users)

You have two easy ways to launch the system:

**Option 1: One-Click Local Launcher (Windows)**
Simply double-click the `LAUNCH_DEEPFIELD.bat` file in the root directory. It will automatically start the background AI daemon, launch the web server, and open your browser to `http://127.0.0.1:5000`.

**Option 2: Docker Setup (Any OS / VPS)**
Ensure Docker and Docker Compose are installed. Run:
```bash
docker-compose up -d --build
```
Then visit `http://localhost:5000` in your browser.

---

## 🤖 Extending the Project (For AI Agents)

**IMPORTANT:** If you are an AI assistant tasked with modifying this codebase, please read the [AI_SYSTEM_GUIDE.md](AI_SYSTEM_GUIDE.md) first! It contains the exact current architecture, database schemas, and routing logic you need to know before writing any code.

---

## 📂 System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         DeepFieldPro Platform                        │
├─────────────────────────────────────────────────────────────────────┤
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  │
│  │   ACQUISITION    │  │     RESEARCH     │  │  LIVE OPERATIONS │  │
│  │     LAYER        │  │       OS         │  │      CORE        │  │
│  ├──────────────────┤  ├──────────────────┤  ├──────────────────┤  │
│  │ • Browser Engine │  │ • Experiment     │  │ • Shadow         │  │
│  │ • Session Mgr    │  │   Registry       │  │   Orchestrator   │  │
│  │ • WebSocket      │  │ • Walk-Forward   │  │ • Edge Decay     │  │
│  │   Ingestor       │  │ • Monte Carlo    │  │   Monitor        │  │
│  │ • Normalizer     │  │ • Strategy       │  │ • Sportsbook     │  │
│  │                  │  │   Lifecycle      │  │   Behavior       │  │
│  └────────┬─────────┘  └────────┬─────────┘  │   Model          │  │
│           │                     │            └────────┬─────────┘  │
│           └─────────────────────┼─────────────────────┘            │
│                                 │                                  │
│                    ┌────────────▼────────────┐                     │
│                    │    DATA PERSISTENCE     │                     │
│                    ├─────────────────────────┤                     │
│                    │ • PostgreSQL/TimescaleDB│                     │
│                    │ • Redis (Pub/Sub)       │                     │
│                    │ • Feature Store         │                     │
│                    └─────────────────────────┘                     │
│                                                                     │
│                    ┌─────────────────────────┐                     │
│                    │   GOVERNANCE & RISK     │                     │
│                    ├─────────────────────────┤                     │
│                    │ • Meta-Portfolio Alloc  │                     │
│                    │ • Capital Gatekeeper    │                     │
│                    │ • Alerting System       │                     │
│                    └─────────────────────────┘                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Core Functional Modules

### 1. Acquisition & Infrastructure Layer

| Module | File | Description |
|--------|------|-------------|
| **Browser Engine** | `src/services/session_manager/browser_engine.py` | Persistent Chromium profiles with advanced fingerprint spoofing, navigator masking, canvas/WebGL protection, automatic crash recovery |
| **Session Manager** | `src/services/session_manager/service.py` | Circuit breakers, health scoring (0-100), automatic re-authentication, rate limiting, exponential backoff retry |
| **WebSocket Ingestor** | `src/services/odds_acquisition/websocket_ingestor.py` | Live frame interception, auto-reconnect (1s-60s backoff), stream staleness detection, sequence tracking |
| **Odds Normalizer** | `src/services/normalizer/engine.py` | Cross-book market mapping, arbitrage detection, implied probability calculation |

**Key Features:**
- Stealth browsing with 3 realistic fingerprints (Windows/Mac/Linux)
- localStorage/sessionStorage persistence across sessions
- Automatic cookie restoration
- Fetch via browser context (`page.evaluate(fetch...)`)
- 406/401/403 error recovery

---

### 2. Data Persistence & Storage

| Table | Retention | Purpose |
|-------|-----------|---------|
| `odds_ticks` | Infinite | Every single odds change (timestamped) |
| `odds_snapshots` | 2 years | Periodic full market state |
| `line_movements` | Infinite | Aggregated delta events |
| `websocket_events` | 90 days | Connection logs, disconnect reasons |
| `session_logs` | 1 year | Browser lifecycle, authentication events |
| `browser_health` | 30 days | Memory usage, CPU, FPS metrics |

**Technology Stack:**
- **Primary DB:** PostgreSQL 15 + TimescaleDB (hypertables)
- **Cache:** Redis 7 (Pub/Sub for real-time streams)
- **Feature Store:** Redis-backed with TTL management

---

### 3. Research Operating System (Research OS)

#### Experiment Management
| Module | File | Purpose |
|--------|------|---------|
| **Experiment Registry** | `src/research_os/experiment_registry.py` | Immutable tracking of hypotheses, parameters, results |
| **Dataset Versioning** | `src/research_os/dataset_versioning.py` | Checksummed snapshots for reproducibility |
| **Feature Snapshot** | `src/research_os/feature_snapshot_manager.py` | Feature schema versioning, drift tracking |
| **Hypothesis Tracker** | `src/research_os/hypothesis_tracker.py` | Formal scientific hypothesis lifecycle |

#### Validation Engines
| Module | File | Purpose |
|--------|------|---------|
| **Walk-Forward Validator** | `src/research/walk_forward_validator.py` | Rolling train/validate/test windows, temporal isolation |
| **Monte Carlo Engine** | `src/research/monte_carlo_engine.py` | 10,000+ bankroll simulations, ruin probability |
| **Regime Detector** | `src/research/regime_detector.py` | Unsupervised clustering for market states |
| **Edge Decay Analyzer** | `src/research/edge_decay_analyzer.py` | EV half-life measurement, latency sensitivity |
| **Overfitting Detector** | `src/research/overfitting_detector.py` | Leakage scanning, multiple hypothesis correction |

#### Strategy Lifecycle
```
RESEARCH → VALIDATION → SHADOW → LIMITED_CAPITAL → PRODUCTION → DEGRADED → RETIRED
```

| Module | File | Purpose |
|--------|------|---------|
| **Strategy Lifecycle** | `src/research_os/strategy_lifecycle.py` | Automated state transitions based on CLV, drawdowns |
| **Promotion Engine** | `src/research_os/promotion_engine.py` | Strict criteria: CLV > threshold, statistical significance |
| **Strategy Graveyard** | `src/research_os/strategy_graveyard.py` | Permanent record of failed strategies |
| **Reproducibility Engine** | `src/research_os/reproducibility_engine.py` | Deterministic replay, seed tracking |

---

### 4. Live Operations & Telemetry

| Module | File | Purpose |
|--------|------|---------|
| **Shadow Orchestrator** | `src/live_operations/shadow_deployment_orchestrator.py` | Continuous paper trading, signal → simulated fill → CLV tracking |
| **Execution Telemetry** | `src/live_operations/execution_telemetry.py` | Nanosecond latency tracking, Execution Quality Score (EQS) |
| **Edge Decay Live** | `src/live_operations/edge_decay_live.py` | Real-time EV snapshots at T₀, T+1s, T+5s, T_exec, T_close |
| **Sportsbook Monitor** | `src/live_operations/sportsbook_behavior_monitor.py` | Rejection patterns, line shading, dynamic profiles |
| **Account Health** | `src/live_operations/account_health_engine.py` | Trust Score (0-100), restriction probability prediction |
| **Market Adaptation** | `src/live_operations/market_adaptation_detector.py` | Alpha decay detection, structural break analysis |
| **Live Regime Monitor** | `src/live_operations/live_regime_monitor.py` | Real-time classification (High Vol, Low Liq, Sharp Money) |
| **Operational Risk** | `src/live_operations/operational_risk_monitor.py` | Infrastructure health, circuit breakers, kill-switches |
| **Live CLV Tracker** | `src/live_operations/live_clv_tracker.py` | Rolling weighted CLV by book/market/latency |
| **Alerting System** | `src/live_operations/alerting_system.py` | Multi-channel alerts, incident timelines |

**Shadow Bet Lifecycle:**
```
SIGNAL_GENERATED → EXECUTION_SIMULATED → CLV_TRACKED → SETTLED
```

---

### 5. Risk & Portfolio Management

| Module | File | Purpose |
|--------|------|---------|
| **Risk Engine** | `src/services/risk_engine/engine.py` | Fractional Kelly (25% default), exposure caps, drawdown protection |
| **Meta-Portfolio** | `src/research_os/meta_portfolio_allocator.py` | Dynamic capital allocation across strategies/sports |
| **Capital Gatekeeper** | `src/research_os/capital_deployment_gatekeeper.py` | Final approval layer, automatic halt triggers |

**Kelly Formula:**
```
f* = (bp - q) / b
where: b = decimal odds - 1, p = win probability, q = 1 - p
```

**Risk Limits:**
- Single bet max: 2% bankroll
- Total exposure cap: 20% bankroll
- Daily loss limit: 5% bankroll
- Correlated exposure: 10% bankroll

---

## 📊 Key Performance Indicators (KPIs)

### Edge Validation Metrics
| Metric | Formula | Target |
|--------|---------|--------|
| **CLV** | `(ClosingOdds - BetOdds) / BetOdds × 100` | > 3% |
| **Edge Half-Life** | Time for 50% EV evaporation | > 30 seconds |
| **Realized ROI** | `(P/L) / Total Staked × 100` | > 5% |
| **Slippage Cost** | `Signal Price - Execution Price` | < 2% |

### Operational Health Metrics
| Metric | Measurement | Threshold |
|--------|-------------|-----------|
| **Account Trust Score** | 0-100 composite score | > 70 |
| **Execution Quality Score** | Latency + Fill Rate + Slippage | > 0.8 |
| **Uptime** | Acquisition success % | > 99% |
| **Stale Data %** | Outdated odds frequency | < 1% |

### Statistical Significance
| Metric | Interpretation |
|--------|---------------|
| **Sharpe Ratio** | Risk-adjusted returns (>1.5 target) |
| **Sortino Ratio** | Downside deviation adjusted (>2.0 target) |
| **T-Statistic** | Statistical significance of ROI (>2.0 for 95% confidence) |
| **Risk of Ruin** | Bankroll depletion probability (<5% target) |

---

## 🛡 Safety & Governance Mechanisms

### Automatic Kill-Switches

The system **immediately halts** if ANY of these conditions are met:

| Trigger | Condition | Action |
|---------|-----------|--------|
| **Edge Collapse** | Rolling 7-day CLV < 0% | Halt all strategies |
| **Drawdown Breach** | Daily loss > 5% | Cool-off period (24h) |
| **Account Danger** | Trust Score < 40 | Reduce exposure 50% |
| **Infrastructure Failure** | Browser crash rate > 5/min | Graceful restart |
| **Data Staleness** | No odds update > 60s | Pause ingestion |
| **Regime Shift** | Unproven market state detected | Switch to conservative mode |

### Anti-Fragility Features

- **Circuit Breakers:** Per-sportsbook and per-strategy throttling
- **Graceful Degradation:** Automatic fallback to backup browsers/proxies
- **Self-Healing:** Automatic session restoration, websocket reconnection
- **Redundancy:** Multiple browser contexts, database replication ready

---

## 🔧 Technology Stack

| Component | Technology | Version |
|-----------|------------|---------|
| **Language** | Python | 3.10+ |
| **Async Runtime** | asyncio / uvloop | Latest |
| **Browser Automation** | Playwright | 1.40+ |
| **Stealth** | playwright-stealth | Latest |
| **Database** | PostgreSQL + TimescaleDB | 15 / 2.13 |
| **Cache/Queue** | Redis | 7.x |
| **API Framework** | FastAPI | 0.104+ |
| **ML/AI** | LightGBM, Scikit-Learn, SHAP | Latest |
| **Visualization** | Grafana, Plotly, Prometheus | Latest |
| **Containerization** | Docker, Docker Compose | Latest |
| **CI/CD** | GitHub Actions | Latest |

---

## 📈 Operational Workflow

### Phase 1: Discovery (Research)
```mermaid
graph LR
    A[Hypothesis] --> B[Dataset Snapshot]
    B --> C[Walk-Forward Test]
    C --> D[Monte Carlo Sim]
    D --> E{Leakage Check}
    E -->|Pass| F[Promote to Shadow]
    E -->|Fail| G[Strategy Graveyard]
```

### Phase 2: Shadow Deployment (Live Validation)
```mermaid
graph LR
    A[Live Signal] --> B[Theoretical Fill]
    B --> C[Track CLV]
    C --> D{N Bets Reached?}
    D -->|No| A
    D -->|Yes| E{CLV > Threshold?}
    E -->|Yes| F[Promote to Production]
    E -->|No| G[Retire Strategy]
```

### Phase 3: Production (Capital Deployment)
```mermaid
graph LR
    A[Capital Approval] --> B[Risk Sizing]
    B --> C[Exposure Assignment]
    C --> D[Live Monitoring]
    D --> E{Kill-Switch Triggered?}
    E -->|No| D
    E -->|Yes| F[Halt & Analyze]
```

---

## 🚦 Getting Started

### Prerequisites

```bash
# Required
- Python 3.10+
- Docker & Docker Compose
- PostgreSQL 15 + TimescaleDB
- Redis 7
- Node.js 18+ (for Playwright)
```

### Quick Start

```bash
# 1. Clone repository
git clone https://github.com/deepfieldpro/deepfieldpro.git
cd deepfieldpro

# 2. Set up environment
cp .env.example .env
# Edit .env with your credentials

# 3. Start infrastructure
docker-compose up -d postgres redis grafana

# 4. Install dependencies
pip install -r requirements.txt

# 5. Install Playwright browsers
playwright install chromium
playwright install-deps chromium

# 6. Run migrations
python src/database/migrate.py

# 7. Start acquisition service
python src/orchestrator.py

# 8. Access API
open http://localhost:8000/docs
```

### Configuration (.env)

```ini
# Database
DATABASE_URL=postgresql://postgres:password@localhost:5432/deepfield
REDIS_URL=redis://localhost:6379/0

# Browser
BROWSER_HEADLESS=true
BROWSER_PROFILE_PATH=/tmp/browser_profiles
MAX_CONCURRENT_BROWSERS=3

# Sportsbooks
SPORTSBOOK_LIST=draftkings,fanduel,betmgm,caesars
PROXY_ENABLED=false

# Risk
DEFAULT_KELLY_FRACTION=0.25
MAX_EXPOSURE_PERCENT=0.20
DAILY_LOSS_LIMIT=0.05

# Monitoring
LOG_LEVEL=INFO
METRICS_ENABLED=true
GRAFANA_URL=http://localhost:3000
```

---

## 🧪 Testing & Validation

### Run Test Suite

```bash
# Unit tests
pytest tests/unit/ -v

# Integration tests (requires Docker)
pytest tests/integration/ -v --timeout=300

# Research validation
pytest tests/research/ -v --timeout=600

# Full CI/CD simulation
act push  # Requires 'act' tool for local GitHub Actions
```

### Shadow Simulation

```bash
# Run 45-minute shadow simulation
python src/live_operations/shadow_deployment_orchestrator.py \
  --simulate \
  --duration 45 \
  --output report.json

# Analyze results
python src/scripts/analyze_shadow_results.py --input report.json
```

---

## 📊 Monitoring & Dashboards

### Grafana Dashboards

| Dashboard ID | Purpose |
|--------------|---------|
| `acquisition_overview` | Browser health, session status, ingestion rates |
| `clv_tracking` | Real-time CLV by sportsbook/market |
| `edge_decay` | EV half-life visualization |
| `account_health` | Trust scores, restriction warnings |
| `strategy_performance` | ROI, Sharpe, drawdowns by strategy |
| `operational_alerts` | Active incidents, kill-switch status |

Access: `http://localhost:3000`

### Prometheus Metrics

```promql
# Acquisition
deepfield_browser_sessions_active
deepfield_odds_ticks_per_second
deepfield_websocket_connections

# Performance
deepfield_clv_average{sportsbook="draftkings"}
deepfield_edge_half_life_seconds
deepfield_execution_quality_score

# Risk
deepfield_bankroll_current
deepfield_exposure_percent
deepfield_drawdown_current

# Operations
deepfield_account_trust_score{sportsbook="fanduel"}
deepfield_kill_switch_active
```

---

## 📁 Project Structure

```
deepfieldpro/
├── src/
│   ├── api/                    # FastAPI endpoints
│   │   ├── main.py
│   │   ├── routes/
│   │   └── middleware/
│   ├── config/                 # Configuration management
│   │   └── settings.py
│   ├── database/               # SQLAlchemy models & migrations
│   │   ├── models.py
│   │   └── migrate.py
│   ├── services/
│   │   ├── session_manager/    # Browser & session logic
│   │   ├── odds_acquisition/   # Collector & WebSocket
│   │   ├── normalizer/         # Market normalization
│   │   ├── risk_engine/        # Position sizing & limits
│   │   ├── feature_store/      # Real-time features
│   │   └── backtesting/        # Historical replay
│   ├── research/               # Validation engines
│   │   ├── walk_forward_validator.py
│   │   ├── monte_carlo_engine.py
│   │   ├── regime_detector.py
│   │   └── edge_decay_analyzer.py
│   ├── research_os/            # Research governance
│   │   ├── experiment_registry.py
│   │   ├── strategy_lifecycle.py
│   │   └── capital_gatekeeper.py
│   ├── live_operations/        # Live telemetry
│   │   ├── shadow_deployment_orchestrator.py
│   │   ├── execution_telemetry.py
│   │   └── account_health_engine.py
│   └── orchestrator.py         # Main entry point
├── tests/
│   ├── unit/
│   ├── integration/
│   └── research/
├── docker/
│   ├── Dockerfile
│   └── Dockerfile.browser
├── .github/workflows/
│   └── deepfield_pipeline.yml
├── docker-compose.yml
├── requirements.txt
└── README.md
```

---

## 🔐 Security & Compliance

- **No Real Money by Default:** System operates in shadow mode until explicitly promoted
- **Credential Encryption:** All sensitive data encrypted at rest (AES-256)
- **Rate Limiting:** Built-in protection against sportsbook bans
- **Audit Logging:** Immutable logs for all decisions and executions
- **Access Control:** Role-based API access (researcher, operator, admin)

---

## 📄 License

**Proprietary - All Rights Reserved**

This software is confidential and intended for internal use only. Unauthorized distribution is prohibited.

---

## 🤝 Contributing

1. Create feature branch: `git checkout -b feature/my-feature`
2. Commit changes with conventional commits
3. Run full test suite: `pytest tests/ -v`
4. Submit pull request to `develop` branch
5. Await code review and CI/CD validation

---

## 📞 Support

- **Documentation:** `/docs` directory
- **API Reference:** `http://localhost:8000/docs` (Swagger UI)
- **Issues:** GitHub Issues tracker
- **Emergency Contact:** ops-team@deepfieldpro.internal

---

## 🎯 Current Status

**Production Ready** ✅

- [x] Acquisition Layer: Fully operational
- [x] Research OS: All modules deployed
- [x] Live Operations: Shadow deployment active
- [x] Risk Management: Circuit breakers enabled
- [x] Monitoring: Grafana dashboards live
- [x] CI/CD: Automated testing & deployment

**Next Milestone:** Extended shadow deployment (30 days) for statistical significance validation.

---

*Built with precision for institutional-grade quantitative sports betting research.*
