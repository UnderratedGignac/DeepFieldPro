"""force_correct_bet.py — re-grade a SINGLE already-settled bet that was graded
WRONG, following the tools/force_settle.py operator pattern.

Motivating case (2026-07-10): bet TIP_FORE_KAMBI_b3fc66fc4c40_e759e303
("River Plate Reserves vs Racing Club Reserves", Home @1.78, $2, Uruguay Tercera
Reserves) was settled L/-$2 by the pre-provenance settlement code via a fuzzy
name-collision. The real result was a 4-0 HOME win, so it should be W/+$1.56.

Two separable steps (real-money safety):
  1. correct_bet()  — fix the bet_log row (recompute pnl from the bet's own
     odds/stake, stamp verified provenance). Unambiguous and safe.
  2. apply_ledger_correction() — move the correction into the bankroll ledger
     that staked the bet (TIPSTER_FOREBET -> real_bankroll.db). A SEPARATE step
     so the operator can review the ledger before mutating real money.

Both are idempotent-friendly: correct_bet() no-ops when the bet already holds the
target result; ledger_delta() is derived purely from the before/after results.
"""

import argparse
import datetime
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")


def _payout(result, stake, odds):
    """Money returned to the balance for a settled result."""
    if result == "W":
        return stake * odds
    if result == "VOID":
        return stake
    return 0.0  # L (or OPEN)


def _pnl(result, stake, odds):
    """Net profit/loss for a settled result."""
    if result == "W":
        return stake * (odds - 1)
    if result == "VOID":
        return 0.0
    return -stake  # L


def ledger_delta(old_result, new_result, stake, odds):
    """(delta_payout, delta_pnl) to move a bet's ledger contribution from
    old_result to new_result — feed straight into register_settlement(payout, pnl)."""
    stake = float(stake)
    odds = float(odds)
    dp = _payout(new_result, stake, odds) - _payout(old_result, stake, odds)
    dpnl = _pnl(new_result, stake, odds) - _pnl(old_result, stake, odds)
    return round(dp, 4), round(dpnl, 4)


def correct_bet(bet_db, bet_id, *, to_result, settle_source, settle_reason, when=None):
    """Re-grade one bet in bet_db. Recomputes pnl from the bet's entry_odds/stake,
    stamps verified provenance (settle_source/result_verified=1/settle_reason).

    Returns a dict describing the change; ``applied`` is False (no-op) when the bet
    already holds ``to_result``. Raises ValueError if the bet_id does not exist.
    Does NOT touch any bankroll ledger.
    """
    if to_result not in ("W", "L", "VOID"):
        raise ValueError(f"to_result must be W/L/VOID, got {to_result!r}")
    conn = sqlite3.connect(bet_db)
    try:
        row = conn.execute(
            "SELECT result, pnl, entry_odds, stake, bet_source FROM bet_log WHERE bet_id=?",
            (bet_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"bet_id not found: {bet_id}")
        old_result, old_pnl, odds, stake, bet_source = row
        odds = float(odds or 0)
        stake = float(stake or 0)
        new_pnl = round(_pnl(to_result, stake, odds), 4)
        result = {
            "bet_id": bet_id,
            "old_result": old_result,
            "old_pnl": old_pnl,
            "new_result": to_result,
            "new_pnl": new_pnl,
            "stake": stake,
            "odds": odds,
            "bet_source": bet_source,
            "applied": False,
        }
        if old_result == to_result:
            return result  # already correct -> no-op (idempotent)
        now = when or datetime.datetime.now(datetime.timezone.utc).isoformat()
        conn.execute(
            "UPDATE bet_log SET result=?, pnl=?, settle_source=?, result_verified=1, "
            "settle_reason=?, settle_checked_at=? WHERE bet_id=?",
            (to_result, new_pnl, settle_source, settle_reason, now, bet_id),
        )
        conn.commit()
        result["applied"] = True
        return result
    finally:
        conn.close()


def apply_ledger_correction(
    delta_payout,
    delta_pnl,
    *,
    bet_source,
    real_bankroll_db,
    research_bankroll_db=None,
):
    """Register the delta into the ledger that staked the bet: TIPSTER_FOREBET
    bets stake the real $200 ledger (real_bankroll.db); every other source stakes
    the research ledger. Mirrors live_predictions_daemon._register_settlement_routed."""
    from src.bankroll_tracker import register_settlement

    if bet_source == "TIPSTER_FOREBET":
        register_settlement(delta_payout, delta_pnl, db_path=real_bankroll_db)
    elif research_bankroll_db:
        register_settlement(delta_payout, delta_pnl, db_path=research_bankroll_db)
    else:
        register_settlement(delta_payout, delta_pnl)


def _main(argv=None):
    ap = argparse.ArgumentParser(description="Re-grade one mis-settled bet.")
    ap.add_argument("bet_id")
    ap.add_argument("--to", dest="to_result", required=True, choices=["W", "L", "VOID"])
    ap.add_argument("--source", default="operator-manual", help="settle_source stamp")
    ap.add_argument("--reason", required=True, help="settle_reason (why this is correct)")
    ap.add_argument("--bet-db", default=os.path.join(DATA_DIR, "bet_log.db"))
    ap.add_argument(
        "--apply-ledger",
        action="store_true",
        help="ALSO register the delta into the routed bankroll ledger (real money).",
    )
    ap.add_argument("--real-bankroll-db", default=os.path.join(DATA_DIR, "real_bankroll.db"))
    ap.add_argument(
        "--research-bankroll-db", default=os.path.join(DATA_DIR, "research_bankroll.db")
    )
    args = ap.parse_args(argv)

    res = correct_bet(
        args.bet_db,
        args.bet_id,
        to_result=args.to_result,
        settle_source=args.source,
        settle_reason=args.reason,
    )
    if not res["applied"]:
        print(f"[force_correct_bet] {args.bet_id}: already {res['old_result']} — no change.")
        return 0
    print(
        f"[force_correct_bet] {args.bet_id}: {res['old_result']} (pnl {res['old_pnl']:+.2f}) "
        f"-> {res['new_result']} (pnl {res['new_pnl']:+.2f})"
    )
    if args.apply_ledger:
        dp, dpnl = ledger_delta(
            res["old_result"], res["new_result"], res["stake"], res["odds"]
        )
        apply_ledger_correction(
            dp, dpnl,
            bet_source=res["bet_source"],
            real_bankroll_db=args.real_bankroll_db,
            research_bankroll_db=args.research_bankroll_db,
        )
        _ledger = (
            args.real_bankroll_db
            if res["bet_source"] == "TIPSTER_FOREBET"
            else args.research_bankroll_db
        )
        print(
            f"[force_correct_bet] ledger correction registered: payout {dp:+.2f}, "
            f"pnl {dpnl:+.2f} -> {os.path.basename(_ledger)}"
        )
    else:
        print("[force_correct_bet] ledger NOT touched (pass --apply-ledger to register it).")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
