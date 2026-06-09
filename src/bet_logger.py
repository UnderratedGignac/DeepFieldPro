import os
import sqlite3
import uuid
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "bet_log.db")


def init_bet_log_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Ensure bet_log table exists
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS bet_log (
        bet_id TEXT PRIMARY KEY,
        match_id TEXT,
        player_id TEXT,
        market_type TEXT,
        line REAL,
        side TEXT,
        entry_odds REAL,
        closing_odds REAL,
        fair_odds REAL,
        edge_pct REAL,
        stake REAL,
        book TEXT,
        result TEXT DEFAULT 'OPEN',
        pnl REAL DEFAULT 0.0,
        placed_at TIMESTAMP,
        lineup_drop_at TIMESTAMP,
        latency_ms INTEGER,
        regime TEXT,
        role_shift_flag INTEGER,
        bet_source TEXT DEFAULT 'AI',
        is_recommended INTEGER DEFAULT 0,
        model_version TEXT
    )
    """
    )
    # Ensure parlay_log table exists
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS parlay_log (
        parlay_id TEXT PRIMARY KEY,
        total_odds DECIMAL(10,2),
        fair_prob DECIMAL(10,4),
        combined_ev DECIMAL(10,2),
        trust_score DECIMAL(10,2),
        stake DECIMAL(10,2),
        legs_json TEXT,
        result TEXT DEFAULT 'OPEN',
        pnl DECIMAL(10,2),
        placed_at TIMESTAMP
    )
    """
    )
    conn.commit()
    conn.close()


def log_parlay(total_odds, fair_prob, combined_ev, trust_score, stake, legs):
    import json
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    parlay_id = str(uuid.uuid4())
    placed_at = datetime.now(timezone.utc).isoformat()
    legs_json = json.dumps(legs)

    cursor.execute(
        """
        INSERT INTO parlay_log (
            parlay_id, total_odds, fair_prob, combined_ev, trust_score, stake, legs_json, placed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            parlay_id,
            total_odds,
            fair_prob,
            combined_ev,
            trust_score,
            stake,
            legs_json,
            placed_at,
        ),
    )

    conn.commit()
    conn.close()
    return parlay_id


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
    bet_source="AI",
    is_recommended=0,
):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    bet_id = str(uuid.uuid4())
    placed_at = datetime.now(timezone.utc).isoformat()

    cursor.execute(
        """
        INSERT INTO bet_log (
            bet_id, match_id, player_id, market_type, line, side, entry_odds, fair_odds, edge_pct, 
            stake, book, placed_at, lineup_drop_at, latency_ms, regime, role_shift_flag, bet_source, is_recommended
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            bet_source,
            is_recommended,
        ),
    )

    conn.commit()
    conn.close()
    print(f"Bet {bet_id} logged successfully.")
    return bet_id


if __name__ == "__main__":
    init_bet_log_db()
    print("Bet Log Database Initialized.")
