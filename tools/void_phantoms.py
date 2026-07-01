"""
void_phantoms.py — find and void OPEN bets that can never settle (phantom fixtures).
====================================================================================
A "phantom" is a bet logged against a garbled/stale fixture that never corresponded to a
real match (e.g. "Tindastoll vs Augnablik Under 2.5 @ 4.10"). No results source can settle
it, so it sits OPEN as "awaiting result" forever. This sweeps them out.

Detection (conservative — only flags clear cases):
  A bet is a phantom candidate if it is OPEN, older than --min-age-hours (default 36, so a
  match has had ample time to finish and be published), AND either
    (a) its price is IMPLAUSIBLE for the market (stale/garbled), or
    (b) Flashscore verification says the fixture is PHANTOM (a team doesn't exist, or the
        opponent is absent from the team's results/fixtures).
  Bets that merely lack coverage (verifier says UNKNOWN / REAL) are LEFT OPEN.

Voiding refunds the paper stake (pnl 0) — it does not count as a loss.

Usage:
    python tools/void_phantoms.py                 # report only (dry run)
    python tools/void_phantoms.py --apply         # actually void (asks per bet)
    python tools/void_phantoms.py --apply --yes    # void all detected, no prompt
    python tools/void_phantoms.py --no-verify      # use only the implausible-odds signal
                                                   #   (fast; skips Playwright/Flashscore)
"""

import os
import sys
import sqlite3
import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
DATA = os.path.join(BASE, "data")

from src.live_predictions_daemon import _implausible_odds


def _age_hours(iso):
    try:
        t = datetime.datetime.fromisoformat(str(iso))
        return (datetime.datetime.now() - t).total_seconds() / 3600.0
    except Exception:
        return 1e9  # unknown age -> treat as old


def main():
    apply = "--apply" in sys.argv
    assume_yes = "--yes" in sys.argv
    do_verify = "--no-verify" not in sys.argv
    min_age = 36.0
    if "--min-age-hours" in sys.argv:
        min_age = float(sys.argv[sys.argv.index("--min-age-hours") + 1])

    conn = sqlite3.connect(os.path.join(DATA, "bet_log.db"))
    rows = conn.execute(
        "SELECT bet_id, match_id, market_type, side, entry_odds, stake, placed_at, fixture_id "
        "FROM bet_log WHERE result='OPEN' ORDER BY placed_at"
    ).fetchall()
    print(
        f"Scanning {len(rows)} OPEN bets (min age {min_age:.0f}h, "
        f"verify={'on' if do_verify else 'off'})...\n"
    )

    phantoms = []
    for bid, match_id, market, side, odds, stake, placed_at, fid in rows:
        age = _age_hours(placed_at)
        if age < min_age:
            continue
        reason = None
        if _implausible_odds(market, odds):
            reason = f"implausible {market} odds {odds}"
        elif do_verify:
            parts = (match_id or "").split(" vs ")
            if len(parts) == 2:
                try:
                    from src.fixture_verifier import verify

                    v = verify(parts[0].strip(), parts[1].strip())
                    if v["verdict"] == "PHANTOM":
                        reason = v["detail"]
                except Exception as e:
                    print(f"  [verify error for {match_id}: {e}]")
        if reason:
            phantoms.append((bid, match_id, market, side, odds, stake, age, reason))

    if not phantoms:
        print("No phantom bets detected. Ledger is clean.")
        conn.close()
        return

    print(f"Detected {len(phantoms)} phantom bet(s):\n")
    for bid, match_id, market, side, odds, stake, age, reason in phantoms:
        print(f"  {match_id} | {market} {side} @ {odds} | {age:.0f}h old")
        print(f"      -> {reason}")

    if not apply:
        print(
            "\n(dry run) Re-run with --apply to void these (refunds paper stake). "
            "Add --yes to skip prompts."
        )
        conn.close()
        return

    from src.bankroll_tracker import register_settlement

    voided = 0
    for bid, match_id, market, side, odds, stake, age, reason in phantoms:
        if not assume_yes:
            if (
                input(f"\nVoid {match_id} ({market} {side})? [y/N] ").strip().lower()
                != "y"
            ):
                continue
        conn.execute("UPDATE bet_log SET result='VOID', pnl=0 WHERE bet_id=?", (bid,))
        conn.commit()
        register_settlement(stake or 0.0, 0.0)  # refund paper stake
        voided += 1
        print(f"  VOIDED {match_id} (refunded ${(stake or 0):.2f})")
    conn.close()
    print(f"\nDone. Voided {voided} phantom bet(s).")


if __name__ == "__main__":
    main()
