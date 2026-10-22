"""
backfill_fair_clv.py - fill pinnacle_fair_clv for bets settled before it existed.
================================================================================
pinnacle_fair_clv (entry * Pinnacle's de-vigged closing probability - 1) is
recorded at settlement from 2026-10-22. Bets settled earlier only have the
raw-close pinnacle_clv, which flatters them by Pinnacle's margin. This computes
the fair value from sharp_odds_history for settled W/L bets that lack it,
using each bet's own kickoff. Only bets whose Pinnacle close is still inside
the history retention window (pinnacle_feed.SHARP_ODDS_RETENTION_DAYS) can be
filled; the rest stay NULL rather than guessed. Touches no other column.

Run:  .venv\\Scripts\\python.exe tools\\backfill_fair_clv.py            (dry run)
      .venv\\Scripts\\python.exe tools\\backfill_fair_clv.py --apply
"""

import os
import sqlite3
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

from src.pinnacle_feed import SHARP_ODDS_RETENTION_DAYS  # noqa: E402
from tools.pinnacle_value import _to_ts, pinnacle_clvs  # noqa: E402

DB = os.path.join(BASE, "data", "bet_log.db")


def backfill(db_path=DB, apply=False):
    """Returns how many bets got (or, on a dry run, would get) a fair CLV.

    Only bets kicking off inside the Pinnacle history window are looked up:
    older ones cannot be filled, and looking up all ~5000 settled bets hung
    the run. A dry run reads only.
    """
    cutoff = time.time() - (SHARP_ODDS_RETENTION_DAYS + 1) * 86400
    con = sqlite3.connect(db_path, timeout=30)
    has_col = "pinnacle_fair_clv" in {r[1] for r in con.execute("PRAGMA table_info(bet_log)")}
    rows = con.execute(
        "SELECT bet_id, match_id, market_type, side, entry_odds, kickoff_time FROM bet_log "
        "WHERE result IN ('W','L') AND kickoff_time IS NOT NULL"
        + (" AND pinnacle_fair_clv IS NULL" if has_col else "")
    ).fetchall()
    filled = []
    for bet_id, match_id, market, side, odds, kickoff in rows:
        ko = _to_ts(kickoff)
        if ko is None or ko < cutoff:
            continue
        home, _, away = (match_id or "").partition(" vs ")
        _, fair = pinnacle_clvs(market, home, away, side, odds, kickoff_ts=kickoff)
        if fair is not None:
            filled.append((fair, bet_id))
    if apply and filled:
        if not has_col:
            con.execute("ALTER TABLE bet_log ADD COLUMN pinnacle_fair_clv REAL")
        with con:
            con.executemany(
                "UPDATE bet_log SET pinnacle_fair_clv=? WHERE bet_id=? AND pinnacle_fair_clv IS NULL",
                filled,
            )
    con.close()
    return len(filled)


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    n = backfill(apply=apply)
    print(f"{'Filled' if apply else 'Would fill'} pinnacle_fair_clv for {n} settled bets"
          + ("" if apply else " (dry run; --apply to write)"))
