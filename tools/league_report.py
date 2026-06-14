"""
league_report.py — ROI / CLV broken down by competition.
========================================================
The edge lives in SOFT lines (lazy books in minor leagues), not SHARP markets.
This shows realized ROI, hit-rate and CLV per league so you can see where you
actually win — then feed the losers into settings["league_blocklist"] to stop
betting them.

`league` is captured on bets placed after the upgrade. For older bets it is
backfilled here by matching the team-name match_id against the predictions table
when available.

Run:  .venv\\Scripts\\python.exe tools\\league_report.py
"""
import os
import sqlite3

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
DB = os.path.join(DATA, "bet_log.db")


def build_match_league_map():
    """Best-effort: map 'Home vs Away' -> league from any predictions table found."""
    m = {}
    for fname in ("predictions.db", "bet_log.db", "deepfield.db"):
        p = os.path.join(DATA, fname)
        if not os.path.exists(p):
            continue
        try:
            con = sqlite3.connect(p)
            tabs = [r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")]
            if "predictions" in tabs:
                cols = {r[1] for r in con.execute("PRAGMA table_info(predictions)")}
                if "match" in cols and "league" in cols:
                    for mt, lg in con.execute("SELECT match, league FROM predictions"):
                        if mt and lg:
                            m[mt] = lg
            con.close()
        except Exception:
            pass
    return m


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT * FROM bet_log")]
    con.close()

    lg_map = build_match_league_map()
    settled = [r for r in rows if str(r.get("result", "")).upper() in
               ("W", "L", "WIN", "LOSS", "WON", "LOST")]

    def league_of(r):
        return r.get("league") or lg_map.get(r.get("match_id")) or "(not captured)"

    groups = {}
    for r in settled:
        groups.setdefault(league_of(r), []).append(r)

    print(f"Settled bets: {len(settled)} across {len(groups)} league buckets\n")
    print(f"{'league':32s} {'n':>4s} {'hit':>6s} {'staked':>9s} {'pnl':>9s} {'roi':>8s} {'CLV':>7s}")
    print("-" * 82)
    rowsout = []
    for lg, g in groups.items():
        n = len(g)
        wins = sum(1 for r in g if str(r["result"]).upper().startswith("W"))
        staked = sum(float(r["stake"] or 0) for r in g)
        pnl = sum(float(r["pnl"] or 0) for r in g)
        clvs = [r["clv"] for r in g if r.get("clv") is not None]
        avgclv = (sum(clvs) / len(clvs)) if clvs else None
        rowsout.append((lg, n, wins / n, staked, pnl, pnl / staked if staked else 0, avgclv))
    # biggest staked first
    for lg, n, hit, staked, pnl, roi, avgclv in sorted(rowsout, key=lambda x: -x[3]):
        clv = f"{avgclv:+.1%}" if avgclv is not None else "  --"
        print(f"{str(lg)[:32]:32s} {n:4d} {hit:6.1%} ${staked:8.2f} ${pnl:8.2f} {roi:+7.1%} {clv:>7s}")

    print("\nTip: leagues with many bets and clearly negative ROI/CLV are blocklist")
    print('candidates — add them to settings.json "league_blocklist".')


if __name__ == "__main__":
    main()
