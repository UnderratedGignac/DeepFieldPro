"""
Delete all historical data from losing strategies: SHARP, SHARPV, and prop markets
(Corners, Total Cards, Goalscorer, Player Shots, Over/Under 2.5, BTTS).
Run once. Irreversible.
"""

import sqlite3, os

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
db = sqlite3.connect(os.path.join(DATA, "bet_log.db"))

# Count before
total_before = db.execute("SELECT COUNT(*) FROM bet_log").fetchone()[0]

# SHARP / SHARPV bets
sharp_count = db.execute(
    "SELECT COUNT(*) FROM bet_log WHERE bet_source IN ('SHARP','SHARPV')"
).fetchone()[0]

# Prop market bets (losing markets now blocked)
prop_count = db.execute(
    """SELECT COUNT(*) FROM bet_log
       WHERE market_type IN ('Corners','Total Cards','Goalscorer','Player Shots',
                             'Over/Under 2.5','Over/Under 3.0','Over/Under 2.0','BTTS',
                             'Double Chance','Draw No Bet','Asian Handicap')"""
).fetchone()[0]

print(f"Records before deletion: {total_before}")
print(f"  SHARP/SHARPV bets to delete: {sharp_count}")
print(f"  Prop market bets to delete:  {prop_count}")

# Delete
db.execute("DELETE FROM bet_log WHERE bet_source IN ('SHARP','SHARPV')")
db.execute(
    """DELETE FROM bet_log
       WHERE market_type IN ('Corners','Total Cards','Goalscorer','Player Shots',
                             'Over/Under 2.5','Over/Under 3.0','Over/Under 2.0','BTTS',
                             'Double Chance','Draw No Bet','Asian Handicap')"""
)
db.commit()

total_after = db.execute("SELECT COUNT(*) FROM bet_log").fetchone()[0]
deleted = total_before - total_after
print(f"\nDeleted {deleted} records. Remaining: {total_after}")

# Verify no losers remain
remaining_sources = db.execute("SELECT DISTINCT bet_source FROM bet_log").fetchall()
remaining_markets = db.execute("SELECT DISTINCT market_type FROM bet_log").fetchall()
print(f"Remaining bet_sources: {[r[0] for r in remaining_sources]}")
print(f"Remaining market_types: {[r[0] for r in remaining_markets]}")

db.close()
