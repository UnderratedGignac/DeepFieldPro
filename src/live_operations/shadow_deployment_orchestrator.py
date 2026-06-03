"""
Shadow Deployment Orchestrator
Continuously generates paper bets from live signals, simulates fills,
and tracks CLV on every position for statistical validation.
"""
import os
import sys
import json
import sqlite3
import logging
import datetime

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE)

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(BASE, "data", "shadow_bets.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS shadow_bets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            generated_at TEXT,
            fixture TEXT,
            selection TEXT,
            market TEXT,
            signal_odds REAL,
            fair_prob REAL,
            ev REAL,
            stake REAL,
            status TEXT DEFAULT 'OPEN',
            closing_odds REAL,
            clv REAL,
            settled_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def record_signal(fixture, selection, market, signal_odds, fair_prob, ev, stake):
    """Record a new paper bet from a live signal."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO shadow_bets (generated_at, fixture, selection, market, signal_odds, fair_prob, ev, stake)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.datetime.now(datetime.UTC).isoformat(),
        fixture, selection, market, signal_odds, fair_prob, ev, stake
    ))
    conn.commit()
    conn.close()
    logger.info(f"Shadow bet recorded: {fixture} | {selection} @ {signal_odds} | EV={ev:.1%}")


def settle_bet(bet_id, closing_odds):
    """Settle a shadow bet with the closing line."""
    clv = (closing_odds - 1) / closing_odds if closing_odds > 1 else 0
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        UPDATE shadow_bets SET status='SETTLED', closing_odds=?, clv=?, settled_at=?
        WHERE id=?
    """, (closing_odds, clv, datetime.datetime.now(datetime.UTC).isoformat(), bet_id))
    conn.commit()
    conn.close()
    return clv


def get_summary():
    """Return aggregate CLV stats across all settled bets."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT COUNT(*), AVG(clv), MIN(clv), MAX(clv), AVG(ev)
        FROM shadow_bets WHERE status='SETTLED'
    """).fetchone()
    conn.close()
    return {
        "settled_count": rows[0] or 0,
        "avg_clv": round(rows[1] or 0, 4),
        "min_clv": round(rows[2] or 0, 4),
        "max_clv": round(rows[3] or 0, 4),
        "avg_ev": round(rows[4] or 0, 4),
    }


def run_from_todays_bets():
    """Ingest today's BATCH bets into the shadow ledger automatically."""
    bets_path = os.path.join(BASE, "data", "todays_single_bets.json")
    if not os.path.exists(bets_path):
        logger.error("No todays_single_bets.json found. Run predictor first.")
        return
    data = json.load(open(bets_path, encoding="utf-8"))
    batch = [b for b in data["bets"] if b["status"] == "BATCH"]
    for b in batch:
        record_signal(
            fixture=b["fixture"],
            selection=b["selection"],
            market=b["market"],
            signal_odds=b["raw_odds"],
            fair_prob=b["fair_prob"],
            ev=b["ev"],
            stake=b["kelly_stake"],
        )
    logger.info(f"Ingested {len(batch)} BATCH bets into shadow ledger.")
    print(f"Shadow Ledger: {len(batch)} bets ingested.")
    summary = get_summary()
    print(f"Historical CLV Summary: {summary}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_from_todays_bets()
