"""
backtest_xg_regression.py — does the xG-regression signal predict results? (v1, no odds)
========================================================================================
Hypothesis (roadmap #7): a team whose recent RESULTS outran its xG (lucky/over-performing)
regresses — future results drop toward its xG. The mirror: teams whose results UNDER-ran
their xG (unlucky) are undervalued and should over-perform going forward. Soft books are
slow to price this, so backing the under-performer is an early-price edge.

This is the SIGNAL-VALIDITY gate (read-only on data/xg_history.db, no odds, no live system):
for each team-match, compute trailing (goals_for - xg_for) over prior K matches (walk-forward,
prior matches only), bucket by that 'luck', and measure the team's NEXT-match outcome
(points 3/1/0 and the next (goals_for - xg_for)). If unlucky teams DON'T out-point lucky
teams next match, the signal is dead -> discard #7 before building the odds backtest.
A real signal is MONOTONE across luck buckets.
"""
import os
import sqlite3
from collections import defaultdict

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "data", "xg_history.db")
K = 5  # trailing window


def main():
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT date, home_team, away_team, home_goals, away_goals, home_xg, away_xg "
        "FROM xg_match WHERE home_xg IS NOT NULL ORDER BY date").fetchall()
    con.close()
    if len(rows) < 100:
        print(f"Only {len(rows)} matches — ingest more (tools/ingest_xg_understat.py).")
        return

    # Build per-team chronological perspective rows.
    team_games = defaultdict(list)  # team -> [(date, gf, ga, xgf, xga, points)]
    for date, h, a, hg, ag, hxg, axg in rows:
        if None in (hg, ag, hxg, axg):
            continue
        hp = 3 if hg > ag else (1 if hg == ag else 0)
        ap = 3 if ag > hg else (1 if ag == hg else 0)
        team_games[h].append((date, hg, ag, hxg, axg, hp))
        team_games[a].append((date, ag, hg, axg, hxg, ap))

    # For each team-match with >=K priors, record (trailing luck, next points, next luck).
    samples = []  # (luck, next_points, next_luck)
    for team, games in team_games.items():
        games.sort(key=lambda g: g[0])
        for i in range(K, len(games)):
            prior = games[i - K:i]
            luck = sum(g[1] - g[3] for g in prior) / K   # avg (goals_for - xg_for)
            nxt = games[i]
            next_points = nxt[5]
            next_luck = nxt[1] - nxt[3]
            samples.append((luck, next_points, next_luck))

    if len(samples) < 100:
        print(f"Only {len(samples)} team-match samples — need more data.")
        return

    samples.sort(key=lambda s: s[0])
    n = len(samples)
    terciles = [("UNLUCKY (low goals-xG)", samples[:n // 3]),
                ("NEUTRAL", samples[n // 3:2 * n // 3]),
                ("LUCKY (high goals-xG)", samples[2 * n // 3:])]

    print("=" * 70)
    print(f" xG-REGRESSION SIGNAL VALIDITY  (n={n} team-matches, K={K} trailing)")
    print("=" * 70)
    print(f"{'bucket':28} {'avg trail luck':>14} {'next PPG':>10} {'next luck':>10}")
    print("-" * 70)
    ppgs = []
    for label, grp in terciles:
        avg_luck = sum(s[0] for s in grp) / len(grp)
        ppg = sum(s[1] for s in grp) / len(grp)
        nxt_luck = sum(s[2] for s in grp) / len(grp)
        ppgs.append(ppg)
        print(f"{label:28} {avg_luck:>+14.3f} {ppg:>10.3f} {nxt_luck:>+10.3f}")
    print("-" * 70)
    # The regression edge would show UNLUCKY teams out-pointing LUCKY teams next match.
    diff = ppgs[0] - ppgs[2]
    print(f" UNLUCKY next-PPG minus LUCKY next-PPG = {diff:+.3f}")
    if diff > 0.10:
        print(" -> SIGNAL PRESENT: unlucky teams out-point lucky teams next match.")
        print("    Justifies the odds-join backtest (settle at soft-early & close; need a")
        print("    monotone-positive selectivity sweep before betting).")
    elif diff > 0.0:
        print(" -> WEAK/INCONCLUSIVE: small positive; more data + odds test needed.")
    else:
        print(" -> NO SIGNAL: unlucky teams do NOT out-point lucky teams. Likely a dead")
        print("    end for betting — the market already prices xG. Lean toward discarding #7.")
    print("\n NOTE: predictive validity is necessary but NOT sufficient for +EV — the market")
    print(" may already price it. Only the odds-join selectivity sweep proves a betting edge.")


if __name__ == "__main__":
    main()
