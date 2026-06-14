import sqlite3, os

dbs = ['data/bankroll.db', 'data/bet_log.db', 'data/odds_stream.db', 'data/sync_state.db']
for db in dbs:
    if os.path.exists(db):
        conn = sqlite3.connect(db)
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [t[0] for t in c.fetchall()]
        if 'predictions' in tables:
            print(f'Found predictions in {db}')
        conn.close()
