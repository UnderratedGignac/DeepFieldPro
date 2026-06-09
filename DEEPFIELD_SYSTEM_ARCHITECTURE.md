# DeepFieldPro: Quantitative Sports Intelligence & Execution Platform

## 1. Executive Summary
**DeepFieldPro** is an institutional-grade quantitative platform designed for football research, predictive modeling, and autonomous trade execution. It bridges the gap between raw data acquisition and financial execution by combining machine learning inference with rigorous risk management and real-time telemetry.

---

## 2. Technology Stack: The "Why"

### **Core Infrastructure**
| Technology | Rationale |
| :--- | :--- |
| **Python** | The industry standard for ML and data science, offering a vast ecosystem of libraries for sports modeling. |
| **FastAPI** | Used for the high-performance institutional API layer. Its asynchronous nature allows for high-concurrency data ingestion without blocking. |
| **Flask** | Employed for the Live Dashboard. Its simplicity is ideal for rendering Jinja2 templates and managing Server-Sent Events (SSE) for real-time UI updates. |
| **Docker & Compose** | Ensures environment parity between research (local) and production (cloud). Simplifies the management of the multi-service stack (API, Workers, Databases). |
| **Redis** | Acts as a high-speed memory bridge and message broker, facilitating instant communication between scrapers and the prediction engine. |

### **Data Science & ML**
| Library | Rationale |
| :--- | :--- |
| **LightGBM** | Chosen for its speed and ability to handle tabular data with high efficiency. It supports **Quantile Regression**, allowing the system to predict not just a mean (e.g., expected goals) but uncertainty bands (p10, p90). |
| **Scikit-Learn** | Used for the **Probability Calibrator**. Since ML models are often "overconfident," we use Platt Scaling and Isotonic Regression to ensure predicted probabilities match real-world frequencies. |
| **Pandas & NumPy** | The engine for feature engineering. All fixture data is vectorized into matrices for rapid model scoring. |
| **Joblib** | Used for serializing model artifacts. It is more efficient than standard pickle for large NumPy arrays contained within LightGBM models. |

### **Automation & Acquisition**
| Tool | Rationale |
| :--- | :--- |
| **Playwright** | Provides reliable, headless browser automation. It is used to bypass modern bot-detection and capture dynamic market data that isn't available via standard REST APIs. |
| **WebSockets** | Integrated to handle high-frequency data streams, allowing the system to react to "Line Movements" within milliseconds of a price change. |

---

## 3. System Architecture
The architecture is designed as a **Unidirectional Data Pipeline** to ensure that data corruption in one layer cannot crash the execution layer.

1.  **Acquisition Layer:** Headless browsers and WebSocket listeners capture raw market data and lineups.
2.  **Intelligence Layer:** Raw data is cleaned and fed into LightGBM models. This layer calculates **Fair Odds** and **Expected Value (EV)**.
3.  **Risk Engine:** Before execution, a candidate trade must pass through "Gated Logic" (Kelly Criterion for sizing, stop-loss filters, and institutional odds minimums).
4.  **Execution Engine:** Registered trades are sent to the sportsbook/exchange via automated sessions.
5.  **Telemetry Layer:** Tracks **CLV (Closing Line Value)** to measure if our entry odds were better than the final market price—the ultimate metric of "Alpha."

---

## 4. Database Design
DeepFieldPro uses a hybrid storage strategy: **PostgreSQL** for institutional scalability and **SQLite** for low-latency local logging.

### **Core Tables Overview**

#### **Financial & Performance State**
*   **`bankroll`**: Tracks total capital, daily exposure, and system-wide drawdown limits.
*   **`bet_log`**: The master audit trail. Stores every execution with fields for `entry_odds`, `closing_odds`, `edge_pct`, and `pnl`.
*   **`parlay_log`**: Tracks multi-leg executions. Uses `legs_json` to store the win/loss status of individual legs within a parlay.

#### **Market Intelligence**
*   **`fixtures`**: Central registry of all matches, including status (Live/Finished) and scores.
*   **`odds_ticks`**: A time-series table recording every price movement. This is used by the **Sniper Logic** to identify if current odds are at a daily peak.
*   **`predictions`**: Stores the output of the ML models, including home/draw/away probabilities and prop-level forecasts (shots, goals, etc.).

#### **System Health**
*   **`browser_health`**: Monitors Playwright instances for memory leaks or crashes.
*   **`session_logs`**: Tracks authentication states and recovery attempts for automated accounts.

---

## 5. Agent Design (Autonomous Logic)

The system operates via specialized agents that handle discrete parts of the lifecycle:

1.  **Live Prediction Daemon**: The system's "Heart." It runs a continuous loop (every 180s) to refresh lineups and re-score matches as kickoff approaches.
2.  **Odds Sniper**: An opportunistic agent that monitors price volatility. It prevents "buying early" if the market is trending upward, waiting for the optimal entry point.
3.  **Capital Deployment Protocol (CDP)**: A safety agent that manages the "Drift Budget." It ensures that no single strategy or market consumes too much of the total bankroll.
4.  **Shadow Execution Agent**: Allows the system to run "paper trades" in a sandbox environment to validate new models before they are promoted to live capital.
5.  **Settlement Engine**: An automated agent that scrapes final results and updates the P&L Ledger, ensuring the bankroll is always accurate.

---

## 6. Infrastructure & Reliability
*   **GitHub Actions**: Automates a CI/CD pipeline that runs a battery of tests (using `fakeredis` and `pytest-postgresql`) to ensure code changes don't break the mathematical logic.
*   **Prometheus**: Exposes a `/metrics` endpoint to monitor "Edge Decay" and system latency in real-time.
*   **Alerter System**: A multi-channel notification engine (Discord/Telegram) that pings the operator for critical events: "Big Bet Placed," "Lineup Detected," or "Drawdown Warning."
