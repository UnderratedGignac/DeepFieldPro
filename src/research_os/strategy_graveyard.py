"""
Strategy Graveyard — permanent immutable record of all retired/rejected strategies.
Every strategy that dies gets an autopsy entry explaining why.
"""
import os
import sys
import sqlite3
import datetime
import logging

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE)
DB_PATH = os.path.join(BASE, "data", "strategy_graveyard.db")
logger = logging.getLogger(__name__)


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS graveyard (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy_id TEXT, name TEXT,
            death_reason TEXT, cause_of_death TEXT,
            final_clv REAL, final_roi REAL, final_sharpe REAL,
            total_bets INTEGER, capital_at_risk REAL,
            promoted_to TEXT, buried_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def bury(strategy_id, name, death_reason, cause_of_death="N/A",
         final_clv=0, final_roi=0, final_sharpe=0, total_bets=0,
         capital_at_risk=0, highest_state_reached="RESEARCH"):
    """Add a strategy to the permanent graveyard."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO graveyard
        (strategy_id, name, death_reason, cause_of_death, final_clv, final_roi,
         final_sharpe, total_bets, capital_at_risk, promoted_to, buried_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, (strategy_id, name, death_reason, cause_of_death, final_clv, final_roi,
          final_sharpe, total_bets, capital_at_risk, highest_state_reached,
          datetime.datetime.now(datetime.UTC).isoformat()))
    conn.commit()
    conn.close()
    logger.warning(f"Strategy RETIRED: {strategy_id} ({name}) — {death_reason}")


def list_buried():
    init_db()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT strategy_id, name, death_reason, final_clv, buried_at FROM graveyard ORDER BY buried_at DESC").fetchall()
    conn.close()
    return [{"id": r[0], "name": r[1], "reason": r[2], "final_clv": r[3], "buried_at": r[4]} for r in rows]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Graveyard entries:", list_buried())
