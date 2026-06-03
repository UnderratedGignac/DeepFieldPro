"""
Edge Decay Live Monitor
Snapshots EV at T0, T+1s, T+5s, T_exec, T_close and computes EV half-life.
"""
import os
import sys
import sqlite3
import datetime 
import logging

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE)

logger = logging.getLogger(__name__)
DB_PATH = os.path.join(BASE, "data", "edge_decay.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS edge_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bet_id TEXT,
            fixture TEXT,
            selection TEXT,
            t0_ev REAL,
            t1_ev REAL,
            t5_ev REAL,
            t_exec_ev REAL,
            t_close_ev REAL,
            half_life_seconds REAL,
            recorded_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def record_snapshot(bet_id, fixture, selection, t0_ev, t1_ev=None, t5_ev=None, t_exec_ev=None, t_close_ev=None):
    """Record an EV decay snapshot for a live bet."""
    init_db()
    # Simple half-life estimate: when does EV drop to 50% of T0?
    half_life = None
    if t0_ev and t1_ev and t0_ev > 0:
        decay_rate = (t0_ev - (t1_ev or t0_ev)) / max(t0_ev, 0.001)
        if decay_rate > 0:
            half_life = round(1.0 / decay_rate, 1)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO edge_snapshots
        (bet_id, fixture, selection, t0_ev, t1_ev, t5_ev, t_exec_ev, t_close_ev, half_life_seconds, recorded_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (bet_id, fixture, selection, t0_ev, t1_ev, t5_ev, t_exec_ev, t_close_ev,
          half_life, datetime.datetime.now(datetime.UTC).isoformat()))
    conn.commit()
    conn.close()
    return half_life


def get_avg_half_life():
    """Return the average measured EV half-life across all snapshots."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT AVG(half_life_seconds) FROM edge_snapshots WHERE half_life_seconds IS NOT NULL").fetchone()
    conn.close()
    return round(row[0] or 0, 1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Edge Decay Live Monitor initialized.")
    print(f"Average EV half-life: {get_avg_half_life()}s")
