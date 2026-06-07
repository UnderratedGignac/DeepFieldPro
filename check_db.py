import sqlite3
c = sqlite3.connect('data/bet_log.db')
print("AI bets:", c.execute("SELECT COUNT(*) FROM bet_log WHERE bet_source='AI'").fetchone()[0])
print("Predictions table count:", c.execute("SELECT COUNT(*) FROM predictions").fetchone()[0])
c.close()
