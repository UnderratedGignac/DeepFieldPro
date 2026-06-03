"""
W1 FIX: State Persistence Layer
Persists DeploymentState to SQLite so process restarts don't reset to Day 0.
Also persists the daily drift budget for GlobalSafetyConstraints.
"""

import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.capital_deployment_protocol.schemas import (
    DeploymentState,
    RolloutPhase,
    HealthStatus,
)

logger = logging.getLogger(__name__)

_DB_PATH = Path(__file__).parent.parent.parent / "data" / "dfp_state.db"


def _get_conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_tables(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS deployment_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            current_phase TEXT NOT NULL,
            max_capital_allocation REAL NOT NULL,
            current_health TEXT NOT NULL,
            days_in_phase INTEGER NOT NULL,
            phase_drawdown_pct REAL NOT NULL,
            last_updated TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS drift_budget (
            drift_date TEXT PRIMARY KEY,
            min_ev_drift REAL NOT NULL DEFAULT 0.0,
            p_fill_drift REAL NOT NULL DEFAULT 0.0
        )
    """)
    conn.commit()


def save_deployment_state(state: DeploymentState):
    """Upserts the single DeploymentState row (id=1) into SQLite."""
    conn = _get_conn()
    _ensure_tables(conn)
    conn.execute(
        """
        INSERT INTO deployment_state (id, current_phase, max_capital_allocation,
            current_health, days_in_phase, phase_drawdown_pct, last_updated)
        VALUES (1, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            current_phase=excluded.current_phase,
            max_capital_allocation=excluded.max_capital_allocation,
            current_health=excluded.current_health,
            days_in_phase=excluded.days_in_phase,
            phase_drawdown_pct=excluded.phase_drawdown_pct,
            last_updated=excluded.last_updated
    """,
        (
            state.current_phase.value,
            state.max_capital_allocation,
            state.current_health.value,
            state.days_in_phase,
            state.phase_drawdown_pct,
            state.last_updated.isoformat(),
        ),
    )
    conn.commit()
    conn.close()
    logger.debug("[PERSISTENCE] DeploymentState saved to SQLite.")


def load_deployment_state() -> Optional[DeploymentState]:
    """Loads the persisted DeploymentState, returns None if first run."""
    conn = _get_conn()
    _ensure_tables(conn)
    row = conn.execute("SELECT * FROM deployment_state WHERE id = 1").fetchone()
    conn.close()
    if row is None:
        logger.info(
            "[PERSISTENCE] No persisted state found. Starting fresh from PHASE_0_SHADOW."
        )
        return None
    logger.info(
        f"[PERSISTENCE] Restored DeploymentState: phase={row['current_phase']}, day={row['days_in_phase']}"
    )
    return DeploymentState(
        current_phase=RolloutPhase(row["current_phase"]),
        max_capital_allocation=row["max_capital_allocation"],
        current_health=HealthStatus(row["current_health"]),
        days_in_phase=row["days_in_phase"],
        phase_drawdown_pct=row["phase_drawdown_pct"],
        last_updated=datetime.fromisoformat(row["last_updated"]),
    )


def save_drift_budget(date_str: str, min_ev_drift: float, p_fill_drift: float):
    """Persists today's drift budget so restarts don't reset it."""
    conn = _get_conn()
    _ensure_tables(conn)
    conn.execute(
        """
        INSERT INTO drift_budget (drift_date, min_ev_drift, p_fill_drift)
        VALUES (?, ?, ?)
        ON CONFLICT(drift_date) DO UPDATE SET
            min_ev_drift=excluded.min_ev_drift,
            p_fill_drift=excluded.p_fill_drift
    """,
        (date_str, min_ev_drift, p_fill_drift),
    )
    conn.commit()
    conn.close()


def load_drift_budget(date_str: str) -> dict:
    """Loads today's drift budget. Returns zeroes if first time today."""
    conn = _get_conn()
    _ensure_tables(conn)
    row = conn.execute(
        "SELECT * FROM drift_budget WHERE drift_date = ?", (date_str,)
    ).fetchone()
    conn.close()
    if row is None:
        return {"min_ev": 0.0, "p_fill": 0.0}
    return {"min_ev": row["min_ev_drift"], "p_fill": row["p_fill_drift"]}
