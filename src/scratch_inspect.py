import sqlite3
import os

data_dir = "data"

for db_name in ["odds_stream.db", "bet_log.db", "bankroll.db"]:
    db_path = os.path.join(data_dir, db_name)
    if not os.path.exists(db_path):
        print(f"{db_name} does not exist.")
        continue

    print(f"\n=== {db_name} ===")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [t[0] for t in cur.fetchall()]
    print("Tables:", tables)

    for table in tables:
        cur.execute(f"PRAGMA table_info({table})")
        cols = [c[1] for c in cur.fetchall()]
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        count = cur.fetchone()[0]
        print(f"  Table '{table}': {count} rows, Columns: {cols}")
        if count > 0:
            cur.execute(f"SELECT * FROM {table} LIMIT 2")
            print("    Sample:", cur.fetchall())

    conn.close()
