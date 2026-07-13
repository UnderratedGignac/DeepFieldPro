"""Probe the bet_log DB to understand what bets exist."""

import sqlite3, os, sys

BASE = os.path.join(os.path.dirname(__file__), "..")

for db_path, label in [
    (os.path.join(BASE, "data", "bet_log.db"), "bet_log"),
]:
    if not os.path.exists(db_path):
        print(f"[{label}] NOT FOUND")
        continue
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in c.fetchall()]
    print(f"\n=== {label} — tables: {tables} ===")
    for tbl in tables:
        c.execute(f"SELECT COUNT(*) FROM {tbl}")
        cnt = c.fetchone()[0]
        print(f"  {tbl}: {cnt} rows")
        if cnt > 0 and cnt <= 20:
            c.execute(f"SELECT * FROM {tbl} LIMIT 5")
            rows = c.fetchall()
            for r in rows:
                print("   ", dict(r))
    conn.close()
