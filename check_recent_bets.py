import sqlite3
import pandas as pd
import os
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

db_paths = ["data/deepfield.db", "data/bet_log.db", "db/deepfield.db", "db/bet_log.db"]
conn = None
for path in db_paths:
    if os.path.exists(path):
        try:
            conn = sqlite3.connect(path)
            c = conn.cursor()
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bet_log'")
            if c.fetchone():
                break
        except:
            pass

if conn:
    try:
        with open("recent_bets_output.txt", "w", encoding="utf-8") as f:
            df = pd.read_sql_query("SELECT market_type, COUNT(*) as count, SUM(pnl) as total_pnl, SUM(stake) as total_stake FROM bet_log GROUP BY market_type", conn)
            df['roi'] = (df['total_pnl'] / df['total_stake']) * 100
            f.write("--- ROI ---\n")
            f.write(df.to_string() + "\n")
            
            f.write("\n--- Recent Losing Bets ---\n")
            losing_df = pd.read_sql_query("SELECT * FROM bet_log WHERE pnl < 0 ORDER BY placed_at DESC LIMIT 10", conn)
            f.write(losing_df.to_string() + "\n")
            
            f.write("\n--- Recent Winning Bets ---\n")
            winning_df = pd.read_sql_query("SELECT * FROM bet_log WHERE pnl > 0 ORDER BY placed_at DESC LIMIT 5", conn)
            f.write(winning_df.to_string() + "\n")
    finally:
        conn.close()
