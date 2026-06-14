"""
reset_paper_bankroll.py — restore the SHADOW (paper) bankroll's liquid balance.
==============================================================================
The shadow bankroll tracks liquid cash: register_bet() deducts a stake, and
settlement adds the payout back. When many bets sit OPEN, liquid balance can hit
$0 and the daemon can place no new (paper) bets. This restores liquid balance and
clears the daily exposure/pnl counters so the upgraded, disciplined logic can
build a clean forward track record.

PAPER ONLY — does not touch the real-money Arena wallet. Safe to run.

Run:  .venv\\Scripts\\python.exe tools\\reset_paper_bankroll.py [--balance 1000]
"""
import argparse
import os
import sqlite3
import datetime

DB = os.path.join(os.path.dirname(__file__), "..", "data", "bankroll.db")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--balance", type=float, default=None,
                    help="liquid balance to restore (default: current starting_balance)")
    args = ap.parse_args()

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT * FROM bankroll ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        print("No bankroll row found; nothing to reset.")
        return
    row = dict(row)
    target = args.balance if args.balance is not None else row["starting_balance"]
    today = datetime.date.today().isoformat()

    con.execute(
        "UPDATE bankroll SET current_balance = ?, daily_exposure = 0, daily_pnl = 0, "
        "peak_balance = MAX(peak_balance, ?), system_status = 'ACTIVE' WHERE id = ?",
        (target, target, row["id"]),
    )
    # ensure today's date row reflects the reset (register_bet keys on date)
    con.execute("UPDATE bankroll SET date = ? WHERE id = ?", (today, row["id"]))
    con.commit()
    after = dict(con.execute("SELECT * FROM bankroll ORDER BY id DESC LIMIT 1").fetchone())
    con.close()
    print(f"Paper bankroll reset: liquid balance ${row['current_balance']:.2f} -> "
          f"${after['current_balance']:.2f} (date {after['date']}, status {after['system_status']})")
    print("The running daemon will resume placing disciplined (1X2-only) paper bets on its next sweep.")


if __name__ == "__main__":
    main()
