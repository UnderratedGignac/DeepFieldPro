"""
backtest_pinnacle_value.py — Backtest soft-book value betting vs Pinnacle.

Uses history.db which contains:
  odds_h/d/a   = Pinnacle early price
  odds_ch/cd/ca = Pinnacle closing price
  odds_maxh/d/a = Best available price across soft books (B365, Unibet, etc.)

Strategy: bet when best soft price >= de-vigged Pinnacle early * (1 + edge_threshold)
This simulates the PINNACLE_VALUE signal on 17k historical matches.

Run: .venv\\Scripts\\python.exe tools\\backtest_pinnacle_value.py
"""
import math
import os
import sqlite3
import sys

DB = os.path.join(os.path.dirname(__file__), "..", "data", "history.db")


def devig_prob(h, d, a):
    """Power de-vig (more accurate than simple margin removal)."""
    try:
        margin = 1 / h + 1 / d + 1 / a
        # Simple proportional de-vig
        return 1 / h / margin, 1 / d / margin, 1 / a / margin
    except (TypeError, ZeroDivisionError):
        return None, None, None


def fair_odds(prob):
    return 1.0 / prob if prob and prob > 0 else None


def run_backtest(min_edge: float = 0.03, test_season: str = "2526"):
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    rows = con.execute(
        "SELECT * FROM matches WHERE season=? AND odds_h IS NOT NULL "
        "AND odds_maxh IS NOT NULL AND home_goals IS NOT NULL",
        (test_season,),
    ).fetchall()
    con.close()

    print(f"\n=== PINNACLE VALUE BACKTEST — {test_season} season ({len(rows)} matches) ===")
    print(f"Strategy: bet soft (odds_max) vs Pinnacle early (odds_h/d/a), min_edge={min_edge*100:.0f}%")
    print()

    thresholds = [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10]
    print(f"{'edge':>6}  {'bets':>6}  {'hit':>6}  {'roi_entry':>10}  {'avg_clv':>9}  {'beat_close':>10}")
    print("-" * 60)

    for thresh in thresholds:
        bets, wins, staked, pnl, clv_sum, clv_count, beat_close = 0, 0, 0.0, 0.0, 0.0, 0, 0

        for row in rows:
            ph, pd, pa = devig_prob(row["odds_h"], row["odds_d"], row["odds_a"])
            if not ph:
                continue

            result = row["result"]  # H, D, A
            home_g, away_g = row["home_goals"], row["away_goals"]

            # Check each outcome
            checks = [
                ("H", row["odds_maxh"], ph, row["odds_ch"]),
                ("D", row["odds_maxd"], pd, row["odds_cd"]),
                ("A", row["odds_maxa"], pa, row["odds_ca"]),
            ]

            for outcome, soft_odds, pin_prob, close_odds in checks:
                if not soft_odds or not pin_prob or soft_odds <= 1.0:
                    continue
                pin_fair = fair_odds(pin_prob)
                if not pin_fair:
                    continue
                edge = soft_odds / pin_fair - 1.0
                if edge < thresh:
                    continue

                bets += 1
                staked += 1.0
                won = result == outcome
                if won:
                    wins += 1
                    pnl += soft_odds - 1.0
                else:
                    pnl -= 1.0

                # CLV vs Pinnacle closing
                if close_odds and close_odds > 1.0:
                    clv = soft_odds / close_odds - 1.0
                    clv_sum += clv
                    clv_count += 1
                    if clv > 0:
                        beat_close += 1

        if bets == 0:
            print(f"{thresh*100:>5.0f}%  {'0':>6}  {'—':>6}")
            continue

        roi = pnl / staked
        hit = wins / bets
        avg_clv = clv_sum / clv_count if clv_count else 0
        pct_beat = beat_close / clv_count if clv_count else 0

        print(
            f"{thresh*100:>5.0f}%  {bets:>6}  {hit*100:>5.1f}%  "
            f"{roi*100:>+9.1f}%  {avg_clv*100:>+8.2f}%  {pct_beat*100:>9.1f}%"
        )

    print()
    print("CLV > 0 on a bet = you got better than the closing Pinnacle price = provably +EV.")
    print("ROI > 0 = profitable at flat stakes against the market.")
    print()

    # Compare all seasons
    print("=== ALL SEASONS (min_edge=3%) ===")
    con2 = sqlite3.connect(DB)
    con2.row_factory = sqlite3.Row
    seasons = [r[0] for r in con2.execute("SELECT DISTINCT season FROM matches ORDER BY season").fetchall()]

    print(f"{'season':>8}  {'bets':>6}  {'hit':>6}  {'roi':>8}  {'avg_clv':>9}")
    print("-" * 50)
    for season in seasons:
        rows_s = con2.execute(
            "SELECT * FROM matches WHERE season=? AND odds_h IS NOT NULL "
            "AND odds_maxh IS NOT NULL AND home_goals IS NOT NULL",
            (season,),
        ).fetchall()
        bets, wins, staked, pnl, clv_sum, clv_count = 0, 0, 0.0, 0.0, 0.0, 0
        for row in rows_s:
            ph, pd, pa = devig_prob(row["odds_h"], row["odds_d"], row["odds_a"])
            if not ph:
                continue
            for outcome, soft_odds, pin_prob, close_odds in [
                ("H", row["odds_maxh"], ph, row["odds_ch"]),
                ("D", row["odds_maxd"], pd, row["odds_cd"]),
                ("A", row["odds_maxa"], pa, row["odds_ca"]),
            ]:
                if not soft_odds or not pin_prob or soft_odds <= 1.0:
                    continue
                edge = soft_odds / fair_odds(pin_prob) - 1.0
                if edge < 0.03:
                    continue
                bets += 1
                staked += 1.0
                if row["result"] == outcome:
                    wins += 1
                    pnl += soft_odds - 1.0
                else:
                    pnl -= 1.0
                if close_odds and close_odds > 1.0:
                    clv_sum += soft_odds / close_odds - 1.0
                    clv_count += 1
        if bets:
            print(
                f"{season:>8}  {bets:>6}  {wins/bets*100:>5.1f}%  "
                f"{pnl/staked*100:>+7.1f}%  {clv_sum/clv_count*100:>+8.2f}%"
            )
    con2.close()


if __name__ == "__main__":
    edge = float(sys.argv[1]) / 100 if len(sys.argv) > 1 else 0.03
    run_backtest(min_edge=edge)
