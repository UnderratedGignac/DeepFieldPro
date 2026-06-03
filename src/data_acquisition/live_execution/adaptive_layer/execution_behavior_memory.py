import sqlite3
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class ExecutionBehaviorMemory:
    """
    Persists execution outcomes, suspension patterns, failed clicks, and bookmaker processing latency.
    Serves as the foundational dataset for all adaptive models and machine learning pipelines.
    """
    def __init__(self, db_path: str = "C:/Users/Elie/DeepFieldPro/db/adaptive_memory.sqlite"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        import os
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS execution_outcomes (
                    exec_id TEXT PRIMARY KEY,
                    fixture_id TEXT,
                    market_type TEXT,
                    player_name TEXT,
                    lineup_confidence REAL,
                    theoretical_ev REAL,
                    realized_ev REAL,
                    execution_status TEXT,
                    failure_classification TEXT,
                    bot_latency_ms REAL,
                    bookmaker_latency_ms REAL,
                    slippage_ticks REAL,
                    market_volatility_at_execution REAL,
                    timestamp TEXT
                );
                
                CREATE TABLE IF NOT EXISTS market_regime_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fixture_id TEXT,
                    market_type TEXT,
                    regime_classification TEXT,
                    velocity_score REAL,
                    timestamp TEXT
                );
            """)

    def record_execution(self, exec_data: Dict[str, Any]):
        """
        Logs every attempted execution.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO execution_outcomes (
                    exec_id, fixture_id, market_type, player_name, lineup_confidence,
                    theoretical_ev, realized_ev, execution_status, failure_classification,
                    bot_latency_ms, bookmaker_latency_ms, slippage_ticks, 
                    market_volatility_at_execution, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                exec_data.get("exec_id"),
                exec_data.get("fixture_id"),
                exec_data.get("market_type"),
                exec_data.get("player_name"),
                exec_data.get("lineup_confidence", 1.0),
                exec_data.get("theoretical_ev", 0.0),
                exec_data.get("realized_ev", 0.0),
                exec_data.get("status"),
                exec_data.get("failure_classification", "none"),
                exec_data.get("bot_latency_ms", 0.0),
                exec_data.get("bookmaker_latency_ms", 0.0),
                exec_data.get("slippage_ticks", 0.0),
                exec_data.get("market_volatility", 0.0),
                exec_data.get("timestamp")
            ))

    def get_historical_fill_rate(self, market_type: str, min_volatility: float = 0.0) -> float:
        """
        Retrieves historical survivability for a specific market under current volatility regimes.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT execution_status FROM execution_outcomes
                WHERE market_type = ? AND market_volatility_at_execution >= ?
                ORDER BY timestamp DESC LIMIT 1000
            """, (market_type, min_volatility))
            
            rows = cursor.fetchall()
            if not rows:
                return 0.5 # Default prior
                
            fills = sum(1 for r in rows if r[0] == "filled")
            return fills / len(rows)

behavior_memory = ExecutionBehaviorMemory()
