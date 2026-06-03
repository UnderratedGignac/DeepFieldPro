import sqlite3
import logging
import pandas as pd
from src.research.policy_outcome_auditor.event_schema import (
    PolicyDecisionEvent,
    ExecutionOutcomeEvent,
    MarketSnapshotEvent,
)

logger = logging.getLogger(__name__)


class DecisionStore:
    """
    Phase 1: Build Decision Store & Outcome Store.
    Links decision -> execution -> market evolution using trace_id.
    """

    def __init__(self, db_path: str = "C:/Users/Elie/DeepFieldPro/db/poa_audit.sqlite"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        import os

        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS decisions (
                    trace_id TEXT PRIMARY KEY,
                    timestamp TEXT,
                    fixture_id TEXT,
                    market_type TEXT,
                    player_name TEXT,
                    decision_action TEXT,
                    odds_at_decision REAL,
                    regime_state TEXT,
                    predicted_ev REAL,
                    predicted_p_fill REAL,
                    allocated_stake REAL
                );
                
                CREATE TABLE IF NOT EXISTS outcomes (
                    trace_id TEXT PRIMARY KEY,
                    timestamp TEXT,
                    fill_status TEXT,
                    actual_latency_ms REAL,
                    actual_fill_odds REAL,
                    slippage_ticks INTEGER,
                    FOREIGN KEY(trace_id) REFERENCES decisions(trace_id)
                );
                
                CREATE TABLE IF NOT EXISTS market_snapshots (
                    trace_id TEXT PRIMARY KEY,
                    timestamp TEXT,
                    closing_odds REAL,
                    market_status TEXT,
                    FOREIGN KEY(trace_id) REFERENCES decisions(trace_id)
                );
            """)

    def record_decision(self, event: PolicyDecisionEvent):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO decisions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    event.trace_id,
                    str(event.timestamp),
                    event.fixture_id,
                    event.market_type,
                    event.player_name,
                    event.decision_action,
                    event.odds_at_decision,
                    event.regime_state,
                    event.predicted_ev,
                    event.predicted_p_fill,
                    event.allocated_stake,
                ),
            )

    def record_outcome(self, event: ExecutionOutcomeEvent):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO outcomes VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    event.trace_id,
                    str(event.timestamp),
                    event.fill_status,
                    event.actual_latency_ms,
                    event.actual_fill_odds,
                    event.slippage_ticks,
                ),
            )

    def record_market_snapshot(self, event: MarketSnapshotEvent):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO market_snapshots VALUES (?, ?, ?, ?)
            """,
                (
                    event.trace_id,
                    str(event.timestamp),
                    event.closing_odds,
                    event.market_status,
                ),
            )

    def fetch_audit_dataframe(self) -> pd.DataFrame:
        """
        Joins all three tables to reconstruct the full counterfactual timeline.
        """
        query = """
            SELECT d.*, o.fill_status, o.actual_latency_ms, o.actual_fill_odds, o.slippage_ticks, 
                   m.closing_odds, m.market_status
            FROM decisions d
            LEFT JOIN outcomes o ON d.trace_id = o.trace_id
            LEFT JOIN market_snapshots m ON d.trace_id = m.trace_id
        """
        with sqlite3.connect(self.db_path) as conn:
            return pd.read_sql_query(query, conn)


decision_store = DecisionStore()
