# DeepFieldPro: Operator's Manual & Quick Start Guide

**Version:** 3.0 (Distributed Adaptive Architecture)  
**Audience:** Quantitative Researchers, System Operators, DevOps Engineers  

---

## 🚀 1. Quick Start (5 Minutes to Shadow Mode)

### Prerequisites
- Docker & Docker Compose v2.0+
- Python 3.10+ (for local tooling)
- 16GB+ RAM recommended for browser orchestration
- PostgreSQL 14+ with TimescaleDB extension

### Step 1: Environment Configuration
```bash
# Clone the repository
git clone <your-repo-url> deepfield-pro
cd deepfield-pro

# Copy environment template
cp .env.example .env

# Edit .env with your credentials
# CRITICAL: Set KAFKA_BROKERS, REDIS_URL, DATABASE_URL
nano .env
```

### Step 2: Infrastructure Launch
```bash
# Start core infrastructure (Kafka, Redis, Postgres, Grafana)
docker-compose up -d kafka redis postgres grafana

# Wait for services to be healthy (approx 30s)
docker-compose ps

# Run database migrations
docker-compose exec api python -m src.database.migrations upgrade head
```

### Step 3: Start Acquisition & Shadow Engine
```bash
# Start the browser acquisition engine (Headless)
docker-compose up -d browser-engine

# Start the Live Operations Shadow Orchestrator
docker-compose up -d shadow-orchestrator

# View live logs
docker-compose logs -f shadow-orchestrator
```

### Step 4: Verify Operation
Open your browser to `http://localhost:3000` (Grafana).
- **Username:** `admin`
- **Password:** `admin` (change immediately)
- **Dashboard:** "DeepField Live Operations"

You should see:
- ✅ Event Bus Lag: < 10ms
- ✅ Active Strategies: 0 (Waiting for promotion)
- ✅ Account Health: 100%
- ✅ Market State: "Normal"

---

## 🏗 2. System Architecture Overview

DeepFieldPro is built on **four pillars**:

| Pillar | Responsibility | Key Components |
|--------|----------------|----------------|
| **Acquisition** | Data Ingestion | Playwright Engine, WebSocket Ingestor, Session Manager |
| **Event Bus** | Nervous System | Kafka Streams, Schema Registry, Dead Letter Queues |
| **Intelligence** | Decision Making | Market State Engine, Signal Quality, Drift Detection |
| **Governance** | Safety & Control | Capital Kernel, Operator Console, Strategy Sandboxes |

**Data Flow:**
1. **Browser Engine** scrapes odds → publishes `OddsTick` event to Kafka.
2. **Normalizer** consumes ticks → maps markets → publishes `NormalizedMarket`.
3. **Strategies** (in Sandboxes) consume markets → generate `Signal`.
4. **Signal Quality Engine** scores signals → attaches confidence.
5. **Capital Kernel** validates risk → approves/rejects bet.
6. **Shadow Executor** simulates fill → tracks CLV → publishes `ShadowBet`.

---

## 🎮 3. Daily Operator Workflows

### A. Monitoring Health (Morning Routine)
1. **Check Grafana Dashboards**:
   - *System Health*: CPU, Memory, Kafka Lag.
   - *Account Health*: Trust scores per sportsbook.
   - *Drift Detection*: Is live CLV matching backtests?
2. **Review Alerts**: Check PagerDuty/Slack for overnight incidents.
3. **Verify Data Freshness**: Ensure `OddsTick` volume is normal for the time of day.

### B. Promoting a Strategy (Research → Live)
*Prerequisite: Strategy has passed Walk-Forward and Monte Carlo validation.*

1. **Submit Promotion Request**:
   ```bash
   curl -X POST http://localhost:8000/api/v1/strategies/{id}/promote \
     -H "Authorization: Bearer <TOKEN>" \
     -d '{"target_state": "SHADOW", "capital_limit": 1000}'
   ```
2. **Operator Review**:
   - Log into Operator Console (`http://localhost:8000/console`).
   - Review "Pending Promotions" queue.
   - Verify: Sharpe > 1.5, Max Drawdown < 15%, No Leakage flags.
3. **Approve**: Click "Approve". The strategy moves to `SHADOW` state.
4. **Monitor**: Watch "Shadow P/L" dashboard for 48 hours.
5. **Graduate**: If Shadow CLV is positive, repeat process for `LIVE CAPITAL` state.

### C. Handling an Incident (e.g., Edge Collapse)
1. **Alert Received**: "Drift Detected: Strategy Alpha CLV -15%".
2. **Automatic Action**: Capital Kernel has already reduced stake size by 50%.
3. **Investigate**:
   - Check *Drift Detection Dashboard*.
   - Compare live slippage vs. backtest assumptions.
   - Check *Market State*: Did regime change to "Low Liquidity"?
4. **Manual Intervention**:
   - If structural break confirmed: **Quarantine Strategy**.
   - Command: `POST /api/v1/strategies/{id}/quarantine`
5. **Post-Mortem**: Log incident in Operator Console → Generate Report.

---

## 🧪 4. Researcher Workflows

### Running a Backtest
```bash
# Define experiment in YAML
cat > experiments/my_strategy.yaml <<EOF
name: "Momentum_NBA_v1"
hypothesis: "Line momentum predicts closing line"
dataset_version: "v2024.01"
walk_forward_windows: 5
monte_carlo_runs: 10000
EOF

# Submit to Replay Cluster
python -m src.research_os.submit_experiment experiments/my_strategy.yaml

# Monitor Progress
docker-compose logs -f replay-cluster
```

### Analyzing Results
Once complete, results are stored in the **Experiment Registry**.
```python
from src.research_os import ExperimentRegistry

registry = ExperimentRegistry()
exp = registry.get("Momentum_NBA_v1")

print(f"Out-of-Sample ROI: {exp.oos_roi:.2f}%")
print(f"Probability of Ruin: {exp.monte_carlo_ruin:.2f}%")
print(f"Leakage Score: {exp.leakage_score}") # Must be 0

if exp.promotion_ready():
    print("✅ Ready for Shadow Deployment")
```

---

## ⚙️ 5. Configuration Reference

### Critical Environment Variables (`.env`)

| Variable | Description | Default |
|----------|-------------|---------|
| `KAFKA_BROKERS` | Kafka connection string | `kafka:9092` |
| `REDIS_URL` | Redis connection for cache | `redis://redis:6379` |
| `DATABASE_URL` | Postgres/Timescale connection | `postgresql://user:pass@postgres/db` |
| `BROWSER_HEADLESS` | Run browsers without UI | `true` |
| `MAX_CONCURRENT_BROWSERS` | Limit resource usage | `5` |
| `CAPITAL_KERNEL_MODE` | `STRICT`, `LENIENT`, `OFF` | `STRICT` |
| `SHADOW_MODE_ENABLED` | Enable paper trading | `true` |
| `LOG_LEVEL` | Debug, Info, Warn, Error | `INFO` |

### Strategy Sandbox Config
Each strategy runs with isolated config:
```yaml
strategy_id: "arb_finder_01"
capital_bucket: 5000  # USD
max_exposure_per_bet: 0.02  # 2% of bucket
allowed_sportsbooks: ["BookA", "BookB"]
kill_switch_drawdown: 0.15  # 15%
```

---

## 🛡 6. Safety & Governance Protocols

### The Capital Kernel (Automatic)
The Kernel overrides all strategies if:
- **Global Drawdown** > 20% in 24h.
- **Event Bus Lag** > 5 seconds (data stale).
- **Account Trust Score** < 30 (restriction imminent).
- **Drift Score** indicates negative edge for > 100 bets.

### Human-in-the-Loop (Manual)
Operators must manually approve:
- Increasing total capital allocation > 10%.
- Deploying a strategy to `LIVE` state.
- Changing `CAPITAL_KERNEL_MODE` from STRICT.
- Resuming a quarantined strategy.

---

## 🔍 7. Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| **No Odds Data** | Browser banned or crashed | Check `browser-engine` logs. Rotate proxies. Restart session. |
| **High Kafka Lag** | Consumer slow or DB locked | Scale up consumers. Check DB locks. |
| **Strategy Stuck in "PENDING"** | Missing approval | Check Operator Console queue. |
| **CLV Negative but Backtest Positive** | Slippage/Latency drift | Re-run backtest with realistic latency params. |
| **Account Restricted** | Aggressive betting pattern | Enable `Stealth Execution` mode. Reduce frequency. |

---

## 📞 8. Support & Maintenance

### Daily Maintenance
- **Rotate Logs**: `logrotate` configured automatically.
- **Archive Data**: Cold storage pipeline runs at 03:00 UTC.
- **Health Check**: `curl http://localhost:8000/health`

### Weekly Maintenance
- **Update Fingerprints**: Pull latest browser stealth plugins.
- **Review Quarantined Strategies**: Decide to fix or retire.
- **Calibration Check**: Verify model probabilities vs actual outcomes.

### Emergency Contacts
- **System Admin**: [Insert Contact]
- **Quant Lead**: [Insert Contact]
- **On-Call Operator**: [Insert Contact]

---

## 📜 9. Compliance & Audit
All actions are immutably logged in the `audit_logs` table.
- **Who**: User ID or System Service.
- **What**: Action taken (e.g., "Approved Strategy X").
- **When**: UTC Timestamp.
- **Why**: Linked Ticket or Alert ID.

To export audit logs:
```bash
docker-compose exec postgres pg_dump -t audit_logs -U user db_name > audit_$(date +%F).csv
```

---

**Welcome to DeepFieldPro.**  
*Trade carefully. Preserve capital. Trust the data.*
