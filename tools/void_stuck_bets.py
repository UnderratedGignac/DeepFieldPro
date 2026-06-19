"""
void_stuck_bets.py — manually void the 3 paper bets that no free source covers.
These are real paper bets from June 17 in leagues too obscure for any free API:
  - Utsiktens BK vs Atvidabergs FF (Swedish Div 1 South - 4th tier)
  - St Mochtas vs Lucan United (Leinster Senior League - Irish amateur)
  - Goytacaz FC vs America RJ (Copa Rio - Brazilian state cup)

Zero real-money impact (all SHADOW mode paper bets).
"""

import sqlite3, os, sys

DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"
)
DB = os.path.join(DATA_DIR, "bet_log.db")


def main():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    # Get current OPEN bets
    cur.execute(
        "SELECT bet_id, match_id, player_id, market_type, stake FROM bet_log WHERE result = 'OPEN'"
    )
    open_bets = cur.fetchall()
    print(f"Total OPEN bets: {len(open_bets)}\n")

    # Identify the stuck ones
    VOID_KEYWORDS = [
        "utsiktens",
        "atvidaberg",
        "mochtas",
        "lucan",
        "goytacaz",
        "america rj",
    ]

    to_void = []
    for bet_id, match_id, player_id, mtype, stake in open_bets:
        pid_lower = (player_id or "").lower()
        mid_lower = (match_id or "").lower()
        if any(kw in pid_lower or kw in mid_lower for kw in VOID_KEYWORDS):
            to_void.append((bet_id, match_id, player_id, mtype, stake))

    if not to_void:
        print("No matching stuck bets found.")
        conn.close()
        return

    print(f"Bets to VOID ({len(to_void)}):")
    for bet_id, match_id, player_id, mtype, stake in to_void:
        print(f"  ID={bet_id} | {player_id} | {mtype} | stake={stake}")

    print()
    if "--yes" in sys.argv:
        ans = "y"
    else:
        ans = input("Void these? (y/n): ").strip().lower()
    if ans != "y":
        print("Aborted.")
        conn.close()
        return

    for bet_id, match_id, player_id, mtype, stake in to_void:
        cur.execute(
            "UPDATE bet_log SET result='VOID', pnl=0 WHERE bet_id=?",
            (bet_id,),
        )
        print(f"  Voided bet_id={bet_id}")

    conn.commit()
    conn.close()
    print("\nDone. Remaining OPEN bets:")

    conn2 = sqlite3.connect(DB)
    cur2 = conn2.cursor()
    cur2.execute(
        "SELECT bet_id, player_id, market_type FROM bet_log WHERE result='OPEN'"
    )
    for row in cur2.fetchall():
        print(f"  {row}")
    conn2.close()


if __name__ == "__main__":
    main()
