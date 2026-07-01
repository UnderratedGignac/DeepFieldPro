"""Quick P&L audit — run with .venv/Scripts/python.exe tools/_audit_pnl.py"""
import sqlite3, json

print("=== BANKROLL ===")
conn = sqlite3.connect("data/bankroll.db")
cur = conn.cursor()
cur.execute("SELECT * FROM bankroll ORDER BY rowid DESC LIMIT 7")
rows = cur.fetchall()
cur.execute("PRAGMA table_info(bankroll)")
cols = [c[1] for c in cur.fetchall()]
print(f"Cols: {cols}")
for r in rows:
    print(" ", r)
conn.close()

print("\n=== BET LOG (bet_log table) ===")
conn = sqlite3.connect("data/bet_log.db")
cur = conn.cursor()

print("\n--- Bets by source+outcome ---")
cur.execute("""
    SELECT bet_source, result, COUNT(*),
           ROUND(SUM(stake),2), ROUND(SUM(pnl),2)
    FROM bet_log
    GROUP BY bet_source, result
    ORDER BY bet_source, result
""")
for r in cur.fetchall():
    print(" ", r)

print("\n--- Settled total ---")
cur.execute("""
    SELECT COUNT(*), ROUND(SUM(stake),2), ROUND(SUM(pnl),2)
    FROM bet_log
    WHERE result NOT IN ('OPEN','PENDING') AND result IS NOT NULL
""")
r = cur.fetchone()
print(f"  n={r[0]}, staked={r[1]}, profit={r[2]}")

print("\n--- Open/Pending ---")
cur.execute("SELECT result, COUNT(*), ROUND(SUM(stake),2) FROM bet_log WHERE result IN ('OPEN','PENDING') OR result IS NULL GROUP BY result")
for r in cur.fetchall():
    print(" ", r)

print("\n--- Signal breakdown (settled only) ---")
cur.execute("""
    SELECT signal_name, result, COUNT(*), ROUND(SUM(stake),2), ROUND(SUM(pnl),2)
    FROM bet_log
    WHERE result NOT IN ('OPEN','PENDING') AND result IS NOT NULL
    GROUP BY signal_name, result
    ORDER BY signal_name, result
""")
for r in cur.fetchall():
    print(" ", r)

print("\n--- Last 15 settled bets ---")
cur.execute("""
    SELECT bet_id, placed_at, match_id, market_type, side, entry_odds, stake, result, pnl, bet_source, signal_name
    FROM bet_log
    WHERE result NOT IN ('OPEN','PENDING') AND result IS NOT NULL
    ORDER BY placed_at DESC LIMIT 15
""")
for r in cur.fetchall():
    print(" ", r)

print("\n--- ROI by market type (settled) ---")
cur.execute("""
    SELECT market_type, COUNT(*), ROUND(SUM(stake),2), ROUND(SUM(pnl),2),
           ROUND(100.0*SUM(pnl)/NULLIF(SUM(stake),0),1) as roi_pct
    FROM bet_log
    WHERE result NOT IN ('OPEN','PENDING') AND result IS NOT NULL
    GROUP BY market_type
    ORDER BY roi_pct
""")
for r in cur.fetchall():
    print(" ", r)

print("\n--- Daily P&L ---")
cur.execute("""
    SELECT DATE(placed_at), COUNT(*), ROUND(SUM(stake),2), ROUND(SUM(pnl),2)
    FROM bet_log
    WHERE result NOT IN ('OPEN','PENDING') AND result IS NOT NULL
    GROUP BY DATE(placed_at)
    ORDER BY DATE(placed_at)
""")
for r in cur.fetchall():
    print(" ", r)

conn.close()
print("\n=== MODELS ===")
try:
    with open("models/model_registry.json") as f:
        reg = json.load(f)
    for k, v in reg.items():
        print(f"  {k}: {v}")
except Exception as e:
    print(f"  (no model_registry: {e})")
