"""Idempotent migration for bet_log.db — safe to run repeatedly.

Adds all columns the daemon expects that were not in the original CREATE TABLE,
creates performance indexes on hot WHERE clauses, and enables WAL mode so
readers and writers don't block each other under concurrent access.
"""

import os
import sqlite3

DB = os.path.join(os.path.dirname(__file__), "..", "data", "bet_log.db")

# All columns the daemon writes that may be absent on existing databases.
# Each tuple: (column_name, SQL_type_declaration)
MISSING_COLUMNS = [
    ("fixture_id", "TEXT"),
    ("league", "TEXT"),
    ("best_odds", "REAL"),
    ("best_book", "TEXT"),
    ("signal_name", "TEXT"),
    ("move_size", "REAL"),
    ("monotonicity", "REAL"),
]

# Indexes to create (name, table, columns_sql)
INDEXES = [
    ("idx_bet_log_placed_at", "bet_log", "placed_at"),
    ("idx_bet_log_result", "bet_log", "result"),
    ("idx_bet_log_bet_source", "bet_log", "bet_source"),
    ("idx_bet_log_regime", "bet_log", "regime"),
    ("idx_bet_log_fixture_id", "bet_log", "fixture_id"),
]


def main():
    con = sqlite3.connect(DB)
    cur = con.cursor()

    # Enable WAL mode — allows concurrent readers while writing
    cur.execute("PRAGMA journal_mode=WAL")
    print("journal_mode:", cur.fetchone()[0])

    # Add any missing columns
    have = {r[1] for r in cur.execute("PRAGMA table_info(bet_log)")}
    for col, decl in MISSING_COLUMNS:
        if col not in have:
            cur.execute(f"ALTER TABLE bet_log ADD COLUMN {col} {decl}")
            print(f"added column: {col}")
        else:
            print(f"already present: {col}")

    # Create missing indexes (IF NOT EXISTS keeps it idempotent)
    existing_indexes = {r[1] for r in cur.execute("SELECT type, name FROM sqlite_master WHERE type='index'")}
    for idx_name, table, cols in INDEXES:
        if idx_name not in existing_indexes:
            cur.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table} ({cols})")
            print(f"created index: {idx_name}")
        else:
            print(f"index exists: {idx_name}")

    con.commit()
    con.close()
    print("migration complete.")


if __name__ == "__main__":
    main()
