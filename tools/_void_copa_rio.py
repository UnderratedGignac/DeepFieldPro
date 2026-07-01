"""One-shot: void the stuck Copa Rio open bet (AI, CAbofriense vs Bonsucesso FC).
This league has no ESPN/TheSportsDB/Flashscore coverage and now falls outside the
whitelisted leagues so it can never be placed again. Safe to void: paper money only."""
import sqlite3, os

db = os.path.join(os.path.dirname(__file__), "..", "data", "bet_log.db")
conn = sqlite3.connect(db)
cur = conn.cursor()

cur.execute("SELECT bet_id, match_id, stake, result FROM bet_log WHERE result='OPEN'")
rows = cur.fetchall()
print("Open bets:")
for r in rows:
    print(" ", r)

voided = []
for bet_id, match_id, stake, result in rows:
    if "Copa" in (match_id or "") or "Bonsucesso" in (match_id or "") or "Cabofriense" in (match_id or "") or "CAbofriense" in (match_id or ""):
        cur.execute("UPDATE bet_log SET result='VOID', pnl=0 WHERE bet_id=?", (bet_id,))
        voided.append(bet_id)
        print(f"  VOIDED: {bet_id} ({match_id}, stake={stake})")

if not voided:
    print("\nNo Copa Rio bets found to void. Checking match_id patterns...")
    for bet_id, match_id, stake, result in rows:
        print(f"  bet_id={bet_id} match_id={match_id!r}")

conn.commit()
conn.close()
print(f"\nDone — voided {len(voided)} bet(s).")
