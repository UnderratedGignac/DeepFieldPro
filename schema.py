import sqlite3
conn = sqlite3.connect('data/odds_stream.db')
for row in conn.execute("SELECT sql FROM sqlite_master WHERE type='table'"):
    print(row[0])
