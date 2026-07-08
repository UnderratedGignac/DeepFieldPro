"""
void_non_tipster_bets.py — One-shot: void all OPEN non-TIPSTER_FOREBET bets
and return their stakes to the bankroll. Safe to run repeatedly (idempotent).
"""
import sqlite3, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BET_LOG = os.path.join(os.path.dirname(__file__), "..", "data", "bet_log.db")

def main():
    from src.bankroll_tracker import register_settlement
    conn = sqlite3.connect(BET_LOG)

    # Fetch all OPEN non-TIPSTER bets
    rows = conn.execute(
        "SELECT bet_id, stake, match_id, bet_source FROM bet_log "
        "WHERE result=? AND bet_source!=? ORDER BY placed_at",
        ("OPEN", "TIPSTER_FOREBET"),
    ).fetchall()

    if not rows:
        print("Nothing to void.")
        conn.close()
        return

    print(f"Voiding {len(rows)} bets...")
    total_returned = 0.0

    for bet_id, stake, match_id, source in rows:
        stake = float(stake or 0)
        # Mark void in bet_log
        conn.execute(
            "UPDATE bet_log SET result=?, pnl=? WHERE bet_id=?",
            ("VOID", 0.0, bet_id),
        )
        conn.commit()
        # Return stake to bankroll (VOID = payout=stake, pnl=0)
        register_settlement(payout=stake, pnl=0.0)
        total_returned += stake
        name = (match_id or "")[:40]
        print(f"  VOID [{source}] {name} stake=${stake:.2f}")

    conn.close()
    print(f"\nDone. Returned ${total_returned:.2f} to bankroll.")

    # Reconcile exposure to be sure
    from src.bankroll_tracker import reconcile_exposure
    reconcile_exposure()
    print("Exposure reconciled.")

if __name__ == "__main__":
    main()
