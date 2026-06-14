"""
settlement_audit.py — verify that win/loss settlement is trustworthy.
====================================================================
A betting model only learns if its results are scored correctly. The daemon
settles 1X2 from REAL final scores (home_score vs away_score), but Goalscorer and
Player Shots fall back to a HASH of the bet_id when real per-player stats are
missing (live_predictions_daemon.py ~L1747, L1767):

    won = (hash(bet_id) % 100) / 100 < (1/entry_odds)

That is pseudo-random, not real — so any ROI on those markets is partly fictional.
This audit flags how much of the record is real vs hash-settled, so you trust the
1X2 numbers and discount the rest.

Run:  .venv\\Scripts\\python.exe tools\\settlement_audit.py
"""
import os
import sqlite3

DB = os.path.join(os.path.dirname(__file__), "..", "data", "bet_log.db")

# Markets whose settlement uses the hash fallback when stats are missing.
HASH_RISK = {"Goalscorer", "Player Shots"}
# Markets settled from real final scores / scrapers.
REAL = {"1X2", "Over/Under 2.5", "BTTS", "Corners", "Total Cards"}


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT * FROM bet_log")]
    con.close()
    settled = [r for r in rows if str(r.get("result", "")).upper() in
               ("W", "L", "WIN", "LOSS", "WON", "LOST")]

    by_market = {}
    for r in settled:
        by_market.setdefault(r["market_type"], []).append(r)

    real_n = hash_n = 0
    print(f"{'market':16s} {'n':>4s} {'hit':>6s} {'roi':>8s}  settlement")
    print("-" * 60)
    for m, g in sorted(by_market.items(), key=lambda kv: -len(kv[1])):
        n = len(g)
        wins = sum(1 for r in g if str(r["result"]).upper().startswith("W"))
        staked = sum(float(r["stake"] or 0) for r in g)
        pnl = sum(float(r["pnl"] or 0) for r in g)
        roi = pnl / staked if staked else 0
        kind = "HASH-RISK (discount!)" if m in HASH_RISK else (
            "real scores" if m in REAL else "unknown")
        if m in HASH_RISK:
            hash_n += n
        else:
            real_n += n
        print(f"{str(m)[:16]:16s} {n:4d} {wins/n:6.1%} {roi:+7.1%}  {kind}")

    tot = real_n + hash_n
    print("-" * 60)
    print(f"Real-settled bets : {real_n}/{tot} ({real_n/tot:.0%})" if tot else "no settled bets")
    print(f"Hash-settled bets : {hash_n}/{tot} ({hash_n/tot:.0%}) — treat their ROI as NOISE")
    print("\nConclusion: trust 1X2 (real scores). The hash-settled prop markets are")
    print("already excluded from betting via settings['allowed_markets'] = ['1X2'].")
    print("To make props trustworthy later, wire real per-player stats into settlement.")


if __name__ == "__main__":
    main()
