"""
role_baseline_builder.py
-------------------------
Builds and maintains each player's typical role profile from historical lineup data.

Minimum sample requirement: 3 starts per player before a baseline is set.
This prevents false role-shift alerts from players with very few data points.
"""

import os
import sqlite3
import pandas as pd
from datetime import datetime, timezone

DB_PATH_LINEUPS = os.path.join(
    os.path.dirname(__file__), "..", "data", "parsed_lineups.db"
)
DB_PATH_HISTORY = os.path.join(
    os.path.dirname(__file__), "..", "data", "player_role_history.db"
)

MIN_STARTS_FOR_BASELINE = 3  # Do not build a baseline with fewer starts than this


def init_history_db():
    conn = sqlite3.connect(DB_PATH_HISTORY)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS role_baseline (
        player_id        TEXT PRIMARY KEY,
        player_name      TEXT,
        usual_role       TEXT,
        role_frequency   DECIMAL(5,2),
        total_appearances INTEGER,
        last_updated     TIMESTAMP
    )
    """)
    conn.commit()
    conn.close()


def build_baseline():
    """
    Reads the last 10 starts per player from parsed_lineups and builds
    a role baseline. Only players with >= MIN_STARTS_FOR_BASELINE appearances
    are written to the baseline table.
    """
    if not os.path.exists(DB_PATH_LINEUPS):
        print("No parsed lineups found. Run lineup_parser.py first to collect data.")
        return

    conn_lineups = sqlite3.connect(DB_PATH_LINEUPS)
    df = pd.read_sql_query(
        "SELECT player_id, player_name, expected_role, timestamp "
        "FROM parsed_lineups WHERE is_starter = 1 "
        "ORDER BY timestamp DESC",
        conn_lineups,
    )
    conn_lineups.close()

    if df.empty:
        print("No starting lineup data found to build baseline from.")
        return

    conn_hist = sqlite3.connect(DB_PATH_HISTORY)
    cursor = conn_hist.cursor()
    now = datetime.now(timezone.utc).isoformat()

    updated = 0
    skipped = 0

    for player_id, group in df.groupby("player_id"):
        # Use only the last 10 starts
        group = group.head(10)
        total_apps = len(group)

        # ENFORCE minimum sample size
        if total_apps < MIN_STARTS_FOR_BASELINE:
            skipped += 1
            continue

        player_name = group["player_name"].iloc[0]
        role_counts = group["expected_role"].value_counts()
        usual_role = role_counts.index[0]
        frequency = float(role_counts.iloc[0]) / total_apps

        cursor.execute(
            """
            INSERT OR REPLACE INTO role_baseline
            (player_id, player_name, usual_role, role_frequency, total_appearances, last_updated)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (str(player_id), player_name, usual_role, frequency, total_apps, now),
        )
        updated += 1

    conn_hist.commit()
    conn_hist.close()
    print(
        f"Role baseline updated: {updated} players | "
        f"{skipped} skipped (fewer than {MIN_STARTS_FOR_BASELINE} starts)."
    )


if __name__ == "__main__":
    init_history_db()
    build_baseline()
