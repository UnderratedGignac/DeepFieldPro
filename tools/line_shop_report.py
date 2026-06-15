"""
line_shop_report.py — how much is line-shopping (Betarabia vs Kambi) actually worth?
===================================================================================
Reads bet_log's best_odds/best_book (recorded at bet time) and reports the price uplift
line-shopping would have captured — the realized value of the +1.9% CLV line-shopping edge.
"""
import os
import sqlite3

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
c = sqlite3.connect(os.path.join(BASE, "data", "bet_log.db"))
rows = c.execute(
    "SELECT bet_source, entry_odds, best_odds, best_book FROM bet_log "
    "WHERE best_odds IS NOT NULL AND entry_odds IS NOT NULL"
).fetchall()
c.close()

if not rows:
    print("No line-shop data yet. Steam bets record it going forward.")
    raise SystemExit

n = len(rows)
better = [(eo, bo) for _, eo, bo, bk in rows if bk == "Kambi" and bo > eo]
uplifts = [(bo / eo - 1.0) for eo, bo in better]
avg_uplift_when_better = (sum(uplifts) / len(uplifts)) if uplifts else 0.0
avg_uplift_all = sum(max(0.0, bo / eo - 1.0) for _, eo, bo, _ in rows) / n

print("=" * 60)
print(" LINE-SHOP VALUE  (Betarabia vs Kambi/Unibet)")
print("=" * 60)
print(f" bets with cross-book price ... {n}")
print(f" Kambi beat Betarabia ......... {len(better)}  ({len(better)/n:.0%})")
print(f" avg uplift when Kambi better . {avg_uplift_when_better:+.2%}")
print(f" avg uplift across ALL bets ... {avg_uplift_all:+.2%}  (the bankable line-shop edge)")
print("-" * 60)
print(" Take the BEST price on every pick to capture this. >~+1.5% avg")
print(" across all bets means line-shopping is a real, free edge to wire in.")
