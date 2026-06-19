"""
clv_report.py — Closing Line Value report.
==========================================
CLV (did we beat the market's closing price?) is the #1 leading indicator of a
real edge: a bettor who consistently beats the close is +EV long before win/loss
confirms it. Settlement now records `clv` per bet (entry_odds/closing_odds - 1).

This reports CLV coverage + stats overall and by market/side. Historical bets
placed before the upgrade have no fixture_id link, so CLV is null for them — the
report fills in as new bets settle.

Run:  .venv\\Scripts\\python.exe tools\\clv_report.py
"""

import os
import sqlite3

DB = os.path.join(os.path.dirname(__file__), "..", "data", "bet_log.db")


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT * FROM bet_log")]
    con.close()

    settled = [
        r
        for r in rows
        if str(r.get("result", "")).upper() in ("W", "L", "WIN", "LOSS", "WON", "LOST")
    ]
    with_clv = [r for r in settled if r.get("clv") is not None]

    print(
        f"Total bets: {len(rows)} | settled: {len(settled)} | with CLV: {len(with_clv)}"
    )
    if not with_clv:
        print(
            "\nNo CLV captured yet. CLV is recorded at settlement for bets that carry a"
        )
        print(
            "fixture_id (i.e. placed after this upgrade) and have odds_history snapshots."
        )
        print("Let the daemon run a day, then re-check — this is the metric to watch.")
        return

    def stats(g):
        n = len(g)
        beat = sum(1 for r in g if r["clv"] > 0)
        avg = sum(r["clv"] for r in g) / n
        return n, beat / n, avg

    n, beat_rate, avg = stats(with_clv)
    print(
        f"\n=== OVERALL CLV === n={n}  beat-close={beat_rate:.1%}  avg CLV={avg:+.2%}"
    )
    print("(positive avg CLV is the signal you are genuinely beating the market)")

    print("\n=== CLV by market ===")
    mkts = {}
    for r in with_clv:
        mkts.setdefault(r["market_type"], []).append(r)
    for m, g in sorted(mkts.items(), key=lambda kv: -len(kv[1])):
        n, br, avg = stats(g)
        print(f"  {str(m):16s} n={n:4d} beat={br:5.1%} avgCLV={avg:+.2%}")

    print("\n=== CLV vs realized (does beating the close predict winning?) ===")
    pos = [r for r in with_clv if r["clv"] > 0]
    neg = [r for r in with_clv if r["clv"] <= 0]
    for label, g in (("CLV > 0 (beat close)", pos), ("CLV <= 0", neg)):
        if g:
            wr = sum(1 for r in g if str(r["result"]).upper().startswith("W")) / len(g)
            print(f"  {label:22s} n={len(g):4d} win-rate={wr:.1%}")


if __name__ == "__main__":
    main()
