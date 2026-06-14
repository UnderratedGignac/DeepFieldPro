"""
steam_report.py — settle & score the live STEAM signal ledger.
==============================================================
The daemon captures fired steam picks (line moved >= settings.steam_min_move_pct toward a
1X2 selection) into the `steam_signals` table in data/deepfield_browser_data/completed_fixtures.db.
This tool settles them against real finished scores (free_results_scraper) at a FLAT 1u stake
and reports hit-rate / ROI — the live, out-of-sample check that the backtested steam edge
(tools/backtest_market_signals.py: +8.8% ROI at >=3% moves) actually shows up in production.

This is a SHADOW research ledger — separate from the model bet path; it stakes nothing real.

Run:  .venv\\Scripts\\python.exe tools\\steam_report.py
"""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

DB = os.path.join(os.path.dirname(__file__), "..", "data",
                  "deepfield_browser_data", "completed_fixtures.db")
BETLOG = os.path.join(os.path.dirname(__file__), "..", "data", "bet_log.db")


def report_staked_steam():
    """Settled P&L of the flat-stake STEAM bets the daemon actually placed (bet_log)."""
    if not os.path.exists(BETLOG):
        return
    con = sqlite3.connect(BETLOG)
    con.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in con.execute(
            "SELECT result, stake, pnl, edge_pct FROM bet_log WHERE bet_source='STEAM'")]
    except sqlite3.OperationalError:
        con.close()
        return
    con.close()
    if not rows:
        return
    settled = [r for r in rows if str(r["result"]).upper() not in ("OPEN", "")]
    openn = len(rows) - len(settled)
    print("\n=== STAKED STEAM BETS (bet_log, flat stake, daemon-settled) ===")
    print(f"  total: {len(rows)}  | open: {openn}  | settled: {len(settled)}")
    if settled:
        staked = sum(r["stake"] or 0 for r in settled)
        pnl = sum(r["pnl"] or 0 for r in settled)
        wins = sum(1 for r in settled if str(r["result"]).upper() in ("W", "WIN", "WON"))
        roi = pnl / staked if staked else 0
        print(f"  hit: {wins/len(settled):.1%}  | staked: {staked:.2f}  | pnl: {pnl:+.2f}  | ROI: {roi:+.1%}")


def _outcome_of(selection, hs, as_):
    """Did this 1X2 selection win, given the final score?"""
    s = selection.lower()
    if "home" in s or "(1)" in s:
        return hs > as_
    if "draw" in s or "(x)" in s:
        return hs == as_
    if "away" in s or "(2)" in s:
        return as_ > hs
    return None


def main():
    if not os.path.exists(DB):
        print("No odds-history DB yet — run the daemon first.")
        return
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    try:
        sigs = [dict(r) for r in con.execute(
            "SELECT * FROM steam_signals ORDER BY detected_at")]
    except sqlite3.OperationalError:
        print("No steam_signals table yet — the daemon hasn't captured any steam picks.")
        con.close()
        report_staked_steam()
        return
    con.close()

    if not sigs:
        print("steam_signals is empty. Run the daemon so it can capture line moves "
              "(needs >=2 odds snapshots per fixture before a move is visible).")
        report_staked_steam()
        return

    print(f"Captured steam signals: {len(sigs)}")
    avg_move = sum(s["steam_move"] for s in sigs) / len(sigs)
    avg_odds = sum(s["entry_odds"] for s in sigs) / len(sigs)
    print(f"  avg move: {avg_move:+.1%}  |  avg entry odds: {avg_odds:.2f}")
    by_lg = {}
    for s in sigs:
        by_lg[s["league"]] = by_lg.get(s["league"], 0) + 1
    print("  by league: " + ", ".join(f"{k}:{v}" for k, v in sorted(by_lg.items(),
                                                                     key=lambda x: -x[1])[:8]))

    # Settle against finished scores.
    try:
        from src.free_results_scraper import get_finished_results
    except Exception as e:
        print(f"\n(results scraper unavailable: {e}) — showing capture stats only.")
        return
    dates = sorted({(s["kickoff"] or "")[:10] for s in sigs if s["kickoff"]})
    results = get_finished_results(dates or None)

    n = w = 0
    pnl = 0.0
    pending = 0
    for s in sigs:
        score = results.get(s["match"])
        if not score:
            pending += 1
            continue
        hs, as_ = score
        won = _outcome_of(s["selection"], hs, as_)
        if won is None:
            continue
        n += 1
        if won:
            w += 1
            pnl += s["entry_odds"] - 1.0
        else:
            pnl -= 1.0

    print(f"\n=== SETTLED (flat 1u, entry price) ===")
    if n:
        print(f"  settled: {n}  | hit: {w/n:.1%}  | pnl: {pnl:+.2f}u  | ROI: {pnl/n:+.1%}")
    else:
        print("  none settled yet.")
    print(f"  pending (no result yet): {pending}")
    report_staked_steam()
    print("\nThis is the live confirmation of the backtested steam edge. Accumulate a few")
    print("hundred settled signals before trusting the ROI; the backtest said +8.8% @ >=3%.")


if __name__ == "__main__":
    main()
