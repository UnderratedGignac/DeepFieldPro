import sqlite3
import os

db_path = "data/odds_stream.db"
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM fixture WHERE kickoff_time LIKE '2026-06-11%'")
    count = cur.fetchone()[0]
    print(f"Fixtures in DB for 2026-06-11: {count}")
    
    cur.execute("SELECT home_team, away_team, kickoff_time FROM fixture WHERE kickoff_time LIKE '2026-06-11%' LIMIT 5")
    rows = cur.fetchall()
    for r in rows:
        print(f"- {r[0]} vs {r[1]} @ {r[2]}")
    conn.close()
else:
    print("Database not found.")
