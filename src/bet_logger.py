import os
import sqlite3
import uuid
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "bet_log.db")


def init_bet_log_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bet_log (
        bet_id TEXT PRIMARY KEY,
        match_id TEXT,
        player_id TEXT,
        market_type TEXT,
        line DECIMAL(5,1),
        side TEXT,
        entry_odds DECIMAL(6,3),
        fair_odds DECIMAL(6,3),
        edge_pct DECIMAL(5,3),
        stake DECIMAL(10,2),
        book TEXT,
        placed_at TIMESTAMP,
        lineup_drop_at TIMESTAMP,
        latency_ms INTEGER,
        closing_odds DECIMAL(6,3),
        clv DECIMAL(5,3),
        result TEXT,
        pnl DECIMAL(10,2),
        regime TEXT,
        role_shift_flag BOOLEAN
    )
    """)
    conn.commit()
    conn.close()


def log_bet(
    match_id,
    player_id,
    market_type,
    line,
    side,
    entry_odds,
    fair_odds,
    edge_pct,
    stake,
    book,
    lineup_drop_at,
    latency_ms,
    regime,
    role_shift_flag,
):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    bet_id = str(uuid.uuid4())
    placed_at = datetime.now(timezone.utc).isoformat()

    cursor.execute(
        """
        INSERT INTO bet_log (
            bet_id, match_id, player_id, market_type, line, side, entry_odds, fair_odds, edge_pct, 
            stake, book, placed_at, lineup_drop_at, latency_ms, regime, role_shift_flag
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            bet_id,
            match_id,
            player_id,
            market_type,
            line,
            side,
            entry_odds,
            fair_odds,
            edge_pct,
            stake,
            book,
            placed_at,
            lineup_drop_at,
            latency_ms,
            regime,
            role_shift_flag,
        ),
    )

    conn.commit()
    conn.close()
    print(f"Bet {bet_id} logged successfully.")
    return bet_id


if __name__ == "__main__":
    init_bet_log_db()
    print("Bet Log Database Initialized.")
