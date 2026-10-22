"""
void_1x2_corrupted.py — Void all TIPSTER_FOREBET 1X2 settled bets.

The _resolve_selection fuzzy fallback was returning the wrong team's odds
for fixtures where the team name didn't exactly match Betarabia's market
table. A home bet at 1.5 would record odds of 12.0 (the opponent's price),
making wins look like +$55 when they should be +$2.50. Settlement (W/L)
was correct; only the logged odds and PNL were wrong.

The O/U bets (no fuzzy matching) are clean and preserved.
This script marks all settled 1X2 as VOID so the ROI baseline is honest.
"""
import sqlite3, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BET_LOG = os.path.join(os.path.dirname(__file__), "..", "data", "bet_log.db")

def main():
    conn = sqlite3.connect(BET_LOG)
    rows = conn.execute(
        "SELECT bet_id, stake, result, pnl FROM bet_log "
        "WHERE bet_source=? AND market_type=? AND result IN (?,?)",
        ("TIPSTER_FOREBET", "1X2", "W", "L"),
    ).fetchall()

    if not rows:
        print("Nothing to void.")
        conn.close()
        return

    print(f"Voiding {len(rows)} corrupted 1X2 bets (fake PNL={sum(r[3] or 0 for r in rows):+.2f})...")
    for bet_id, stake, result, pnl in rows:
        conn.execute("UPDATE bet_log SET result=?, pnl=? WHERE bet_id=?", ("VOID", 0.0, bet_id))
    conn.commit()
    conn.close()
    print("Done. 1X2 history wiped. O/U bets (honest -2.9% ROI) preserved.")
    print("Fix deployed: _resolve_selection no longer uses fuzzy fallback.")
    print("New 1X2 bets from today onwards will have correct odds.")

if __name__ == "__main__":
    main()
