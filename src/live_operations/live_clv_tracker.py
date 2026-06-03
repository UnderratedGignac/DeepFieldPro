"""Live CLV Tracker — rolling weighted CLV by sportsbook/market/latency."""

import os
import sys
import sqlite3
import datetime

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE)
DB_PATH = os.path.join(BASE, "data", "live_clv.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS clv_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sportsbook TEXT, market TEXT, fixture TEXT,
            bet_odds REAL, closing_odds REAL,
            clv_pct REAL, latency_ms INTEGER,
            recorded_at TEXT
        )
    """
    )
    conn.commit()
    conn.close()


def record_clv(sportsbook, market, fixture, bet_odds, closing_odds, latency_ms=0):
    init_db()
    clv_pct = round((bet_odds / max(closing_odds, 0.01) - 1) * 100, 4)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO clv_records (sportsbook,market,fixture,bet_odds,closing_odds,clv_pct,latency_ms,recorded_at) VALUES (?,?,?,?,?,?,?,?)",
        (
            sportsbook,
            market,
            fixture,
            bet_odds,
            closing_odds,
            clv_pct,
            latency_ms,
            datetime.datetime.now(datetime.UTC).isoformat(),
        ),
    )
    conn.commit()
    conn.close()
    return clv_pct


def get_rolling_clv(days=7):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT AVG(clv_pct), COUNT(*) FROM clv_records WHERE recorded_at >= date('now', ?)",
        (f"-{days} days",),
    ).fetchone()
    conn.close()
    return {"avg_clv_pct": round(row[0] or 0, 3), "count": row[1]}


if __name__ == "__main__":
    print("Live CLV Tracker ready.")
    print(get_rolling_clv())
