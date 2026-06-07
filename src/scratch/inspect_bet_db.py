import sqlite3
import os

db_path = "data/bet_log.db"
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
    print("Tables:", cur.fetchall())
    
    cur.execute("SELECT COUNT(*), bet_source, result FROM bet_log GROUP BY bet_source, result")
    print("Bets stats:", cur.fetchall())
    
    cur.execute("SELECT * FROM bet_log ORDER BY placed_at DESC LIMIT 5")
    rows = cur.fetchall()
    print("Latest 5 bets:")
    for r in rows:
        print(r)
    conn.close()
else:
    print("bet_log.db does not exist.")

br_path = "data/bankroll.db"
if os.path.exists(br_path):
    conn = sqlite3.connect(br_path)
    cur = conn.cursor()
    cur.execute("SELECT * FROM bankroll ORDER BY date DESC LIMIT 5")
    print("Bankroll rows:")
    for r in cur.fetchall():
        print(r)
    conn.close()
else:
    print("bankroll.db does not exist.")
