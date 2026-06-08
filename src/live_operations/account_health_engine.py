"""
Account Health Engine
Tracks sportsbook account trust score (0-100) based on bet acceptance rate,
limits applied, and restriction signals. Triggers alerts when score drops.
"""

import os
import sys
import sqlite3
import datetime
import logging

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE)

logger = logging.getLogger(__name__)
DB_PATH = os.path.join(BASE, "data", "account_health.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS account_health (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sportsbook TEXT,
            trust_score REAL,
            acceptance_rate REAL,
            limits_applied INTEGER DEFAULT 0,
            restriction_flag INTEGER DEFAULT 0,
            recorded_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def update_health(
    sportsbook, accepted_bets, total_bets, limits_applied=False, restriction_flag=False
):
    """Update trust score based on recent bet acceptance metrics."""
    init_db()
    acceptance_rate = accepted_bets / max(total_bets, 1)
    # Trust score: 100 = perfect, degrades with limits and rejections
    trust_score = min(
        100.0,
        max(
            0.0,
            acceptance_rate * 80
            - (20 if limits_applied else 0)
            - (40 if restriction_flag else 0),
        ),
    )
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        INSERT INTO account_health
        (sportsbook, trust_score, acceptance_rate, limits_applied, restriction_flag, recorded_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """,
        (
            sportsbook,
            trust_score,
            acceptance_rate,
            int(limits_applied),
            int(restriction_flag),
            datetime.datetime.now(datetime.timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    conn.close()

    if trust_score < 40:
        logger.warning(
            f"ALERT: {sportsbook} trust score critically low: {trust_score:.0f}/100"
        )
    elif trust_score < 70:
        logger.warning(
            f"WARNING: {sportsbook} trust score degraded: {trust_score:.0f}/100"
        )
    else:
        logger.info(f"{sportsbook} trust score: {trust_score:.0f}/100")

    return trust_score


def get_latest_scores():
    """Return the most recent trust score per sportsbook."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT sportsbook, trust_score, acceptance_rate, recorded_at
        FROM account_health
        WHERE id IN (SELECT MAX(id) FROM account_health GROUP BY sportsbook)
    """).fetchall()
    conn.close()
    return [
        {
            "sportsbook": r[0],
            "trust_score": r[1],
            "acceptance_rate": round(r[2] * 100, 1),
            "recorded_at": r[3],
        }
        for r in rows
    ]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Self-test with Betarabia at full acceptance
    score = update_health("betarabia", accepted_bets=10, total_bets=10)
    print(f"Betarabia trust score: {score}/100")
    print("All scores:", get_latest_scores())
