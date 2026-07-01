"""Detailed strategy audit — understand what's real vs noise."""

import sqlite3, os, sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
db = sqlite3.connect(os.path.join(DATA, "bet_log.db"))

print("=== AI 1X2 WIN bets: real or hash-noise? ===")
# Hash-settled bets have a clv_sharp that is NULL and pnl that looks like stake*(odds-1)
rows = db.execute(
    """
    SELECT COUNT(*), AVG(pnl), AVG(stake), MIN(placed_at), MAX(placed_at),
           SUM(CASE WHEN clv_sharp IS NULL THEN 1 ELSE 0 END) as no_clv,
           SUM(CASE WHEN fixture_id IS NULL THEN 1 ELSE 0 END) as no_fid
    FROM bet_log WHERE bet_source='AI' AND market_type='1X2' AND result IN ('W','WIN')
"""
).fetchone()
n, avg_pnl, avg_stake, min_dt, max_dt, no_clv, no_fid = rows
print(f"  Count: {n}, avg_pnl={avg_pnl:.2f}, avg_stake={avg_stake:.2f}")
print(f"  Date range: {min_dt[:10]} to {max_dt[:10]}")
print(f"  No CLV data: {no_clv}/{n}, No fixture_id: {no_fid}/{n}")

# Sample a few
sample = db.execute(
    """
    SELECT player_id, stake, pnl, entry_odds, fixture_id, clv_sharp, placed_at
    FROM bet_log WHERE bet_source='AI' AND market_type='1X2' AND result IN ('W','WIN')
    LIMIT 8
"""
).fetchall()
print("\n  Sample wins:")
for r in sample:
    fid = r[4] or "NO_FID"
    print(f"    {r[0][:45]} | stake={r[1]:.1f} pnl={r[2]:.2f} odds={r[3]} fid={fid}")

print()
print("=== Settled bets by strategy (real view) ===")
rows2 = db.execute(
    """
    SELECT bet_source, result,
           COUNT(*) as n,
           SUM(stake) as staked,
           SUM(pnl) as net_pnl,
           ROUND(100.0*SUM(pnl)/SUM(stake),1) as roi
    FROM bet_log
    WHERE result IN ('WIN','LOSS','W','L')
    GROUP BY bet_source, result
    ORDER BY bet_source, result
"""
).fetchall()
print(
    f"  {'Strategy':<10} {'Result':<6} {'N':>4} {'Staked':>8} {'Net PnL':>9} {'ROI%':>7}"
)
print("  " + "-" * 50)
for r in rows2:
    print(f"  {r[0]:<10} {r[1]:<6} {r[2]:>4} {r[3]:>8.1f} {r[4]:>9.2f} {r[5]:>7.1f}%")

print()
print("=== SHARPV / SHARP bets detail ===")
rows3 = db.execute(
    """
    SELECT player_id, stake, pnl, result, entry_odds, placed_at
    FROM bet_log WHERE bet_source IN ('SHARP','SHARPV')
    AND result IN ('WIN','LOSS','W','L')
    ORDER BY placed_at
"""
).fetchall()
for r in rows3:
    print(
        f"  {r[5][:10]} {r[3]:4s} odds={r[4]:5.2f} stake={r[1]:5.1f} pnl={r[2]:7.2f} | {r[0][:50]}"
    )
