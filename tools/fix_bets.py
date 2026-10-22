import sqlite3

con = sqlite3.connect("data/bet_log.db")

# Void the bogus Portugal Away bet (from Bookings/Corners data mixing before fix)
con.execute(
    "UPDATE bet_log SET result='VOID', pnl=0 WHERE bet_id='PINNACLEST_fc07114c71'"
)
con.commit()
print("Portugal Away (2) bogus bet -> VOID")

# Add UNIQUE INDEX so concurrent daemon processes can't race-condition a duplicate
# INSERT OR IGNORE in log_steam_bet will now be atomic
try:
    con.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_bet_dedup "
        "ON bet_log (match_id, market_type, side, bet_source)"
    )
    con.commit()
    print("Unique dedup index created on (match_id, market_type, side, bet_source)")
except Exception as e:
    print("Index error:", e)

# Confirm state
rows = con.execute(
    "SELECT bet_id, match_id, bet_source, side, result FROM bet_log ORDER BY placed_at DESC"
).fetchall()
con.close()
print(f"\nBet log ({len(rows)} total):")
for r in rows:
    print(" ", r)
