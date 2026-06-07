import sqlite3

db_path = "data/bet_log.db"
conn = sqlite3.connect(db_path)
cur = conn.cursor()

# Check current columns in bet_log
cur.execute("PRAGMA table_info(bet_log)")
cols = [c[1] for c in cur.fetchall()]

# Add bet_source if not exists
if 'bet_source' not in cols:
    try:
        cur.execute("ALTER TABLE bet_log ADD COLUMN bet_source TEXT DEFAULT 'AI'")
        print("Added bet_source column.")
    except Exception as e:
        print("Error adding bet_source:", e)

# Add is_recommended if not exists
if 'is_recommended' not in cols:
    try:
        cur.execute("ALTER TABLE bet_log ADD COLUMN is_recommended INTEGER DEFAULT 0")
        print("Added is_recommended column.")
    except Exception as e:
        print("Error adding is_recommended:", e)

conn.commit()
conn.close()
print("bet_log.db migration completed.")
