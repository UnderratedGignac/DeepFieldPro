"""
Strategy Lifecycle Manager
Manages state transitions: RESEARCH → VALIDATION → SHADOW → LIMITED_CAPITAL → PRODUCTION → DEGRADED → RETIRED
Promotion/demotion decisions are based on CLV thresholds and statistical significance.
"""

import os
import sys
import sqlite3
import datetime
import logging

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE)

DB_PATH = os.path.join(BASE, "data", "strategy_lifecycle.db")
logger = logging.getLogger(__name__)

STATES = [
    "RESEARCH",
    "VALIDATION",
    "SHADOW",
    "LIMITED_CAPITAL",
    "PRODUCTION",
    "DEGRADED",
    "RETIRED",
]

PROMOTION_CRITERIA = {
    "SHADOW": {"min_clv": 0.015, "min_bets": 30},
    "LIMITED_CAPITAL": {"min_clv": 0.025, "min_bets": 100, "min_roi": 0.03},
    "PRODUCTION": {
        "min_clv": 0.035,
        "min_bets": 200,
        "min_roi": 0.05,
        "min_sharpe": 1.5,
    },
}

DEMOTION_CRITERIA = {
    "clv_below_zero_7d": -0.01,
    "daily_drawdown": 0.05,
}


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS strategies (
            strategy_id TEXT PRIMARY KEY,
            name TEXT, current_state TEXT DEFAULT 'RESEARCH',
            clv_avg REAL DEFAULT 0, roi REAL DEFAULT 0,
            sharpe REAL DEFAULT 0, total_bets INTEGER DEFAULT 0,
            created_at TEXT, last_transition TEXT
        )
    """
    )
    conn.commit()
    conn.close()


def register_strategy(strategy_id, name):
    init_db()
    now = datetime.datetime.now(datetime.UTC).isoformat()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT OR IGNORE INTO strategies (strategy_id, name, created_at, last_transition) VALUES (?,?,?,?)",
        (strategy_id, name, now, now),
    )
    conn.commit()
    conn.close()
    logger.info(f"Strategy registered: {strategy_id} — {name}")


def evaluate_promotion(strategy_id, clv_avg, roi=0, sharpe=0, total_bets=0):
    """Evaluate whether this strategy should be promoted to the next state."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT current_state FROM strategies WHERE strategy_id=?", (strategy_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None, "Strategy not found"

    current = row[0]
    criteria = PROMOTION_CRITERIA.get(current, {})

    if not criteria:
        return current, "No promotion criteria for this state"

    if clv_avg < criteria.get("min_clv", 0):
        return current, f"CLV {clv_avg:.3f} below minimum {criteria['min_clv']}"
    if total_bets < criteria.get("min_bets", 0):
        return current, f"Only {total_bets} bets, need {criteria['min_bets']}"
    if roi < criteria.get("min_roi", -999):
        return current, f"ROI {roi:.3f} below minimum {criteria['min_roi']}"
    if sharpe < criteria.get("min_sharpe", -999):
        return current, f"Sharpe {sharpe:.2f} below minimum {criteria['min_sharpe']}"

    # Promote!
    next_state = (
        STATES[STATES.index(current) + 1] if current in STATES[:-1] else current
    )
    now = datetime.datetime.now(datetime.UTC).isoformat()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        UPDATE strategies SET current_state=?, clv_avg=?, roi=?, sharpe=?, total_bets=?, last_transition=?
        WHERE strategy_id=?
    """,
        (next_state, clv_avg, roi, sharpe, total_bets, now, strategy_id),
    )
    conn.commit()
    conn.close()
    logger.info(f"Strategy {strategy_id} promoted: {current} → {next_state}")
    return next_state, f"Promoted from {current} to {next_state}"


def get_all_strategies():
    init_db()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT strategy_id, name, current_state, clv_avg, roi FROM strategies"
    ).fetchall()
    conn.close()
    return [
        {"id": r[0], "name": r[1], "state": r[2], "clv": r[3], "roi": r[4]}
        for r in rows
    ]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    register_strategy("MKT_IMPLIED_EV_V1", "Market-Implied EV Strategy")
    state, msg = evaluate_promotion("MKT_IMPLIED_EV_V1", clv_avg=0.031, total_bets=45)
    print(f"State: {state} | {msg}")
    print(get_all_strategies())
