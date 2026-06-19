import sqlite3
db = sqlite3.connect("data/bet_log.db")
rows = db.execute(
    "SELECT bet_id, player_id, bet_source, market_type, entry_odds, stake, result "
    "FROM bet_log WHERE placed_at >= date('now') ORDER BY placed_at"
).fetchall()
print(f"Bets today: {len(rows)}")
for r in rows:
    print(f"  {r[2]:8s} | {r[3]:15s} | {r[1][:50]} | odds={r[4]} | stake={r[5]:.1f} | {r[6]}")
