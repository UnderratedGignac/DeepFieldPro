"""
backtest_market_signals.py — do MARKET-STRUCTURE signals beat the model? (1X2)
=============================================================================
The model (Dixon-Coles) does not beat the market (see backtest_1x2_lines.py). This asks
whether information the MARKET itself carries — that the model ignores — is exploitable.
No model is used here; these are pure market signals on the held-out season.

Signals tested:
  1) STEAM (early->close line move). Bet the side the market moved TOWARD (its de-vigged
     prob rose early->close), at the EARLY price, settle by result. Measures whether line
     movement predicts outcomes. NOTE: diagnostic/ceiling — it peeks at the close, so it is
     NOT directly tradable; a live version needs two pre-kickoff snapshots to detect the move.
  2) SOFT-OUTLIER (tradable now). Compare the best early price across books (odds_max*) to the
     SHARP early consensus (de-vigged Pinnacle early). Bet the selection whose soft price pays
     more than the sharp fair prob implies (EV = sharp_prob * best_price - 1 >= margin), at the
     best price. This is line-shopping refined with a value margin — both prices known at bet time.

Lineup/team-news signals are NOT testable here (football-data history has no lineups); they'd
need a live feed. This tool covers what the free historical data can actually validate.

Run:  .venv\\Scripts\\python.exe tools\\backtest_market_signals.py
"""

import os
import sqlite3

DB = os.path.join(os.path.dirname(__file__), "..", "data", "history.db")


def devig(a, b, c):
    ia, ib, ic = 1 / a, 1 / b, 1 / c
    s = ia + ib + ic
    return ia / s, ib / s, ic / s


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT * FROM matches")]
    con.close()
    seasons = sorted({r["season"] for r in rows})
    test_season = seasons[-1]
    test = [r for r in rows if r["season"] == test_season]
    print(f"Test season: {test_season}  ({len(test)} matches)\n")

    def usable(r):
        cols = (
            "odds_h",
            "odds_d",
            "odds_a",
            "odds_ch",
            "odds_cd",
            "odds_ca",
            "odds_maxh",
            "odds_maxd",
            "odds_maxa",
        )
        return all(r[c] for c in cols) and r["result"] in ("H", "D", "A")

    # ---- Signal 1: STEAM (early->close move), settled at the EARLY price ----
    print(
        "=== SIGNAL 1: STEAM (bet the side the line moved toward, at the early price) ==="
    )
    print("    diagnostic ceiling — peeks at the close, not directly tradable")
    print(
        f"{'min move':>8s} {'bets':>5s} {'hit':>6s} {'roi(early)':>11s} {'roi(close)':>11s}"
    )
    for min_move in (0.0, 0.005, 0.01, 0.02, 0.03, 0.05):
        n = w = 0
        pnl_e = pnl_c = 0.0
        for r in test:
            if not usable(r):
                continue
            oi = {"H": 0, "D": 1, "A": 2}[r["result"]]
            early = devig(r["odds_h"], r["odds_d"], r["odds_a"])
            close = devig(r["odds_ch"], r["odds_cd"], r["odds_ca"])
            move = [close[k] - early[k] for k in range(3)]
            best = max(range(3), key=lambda k: move[k])
            if move[best] < min_move:
                continue
            eo = (r["odds_h"], r["odds_d"], r["odds_a"])[best]
            co = (r["odds_ch"], r["odds_cd"], r["odds_ca"])[best]
            n += 1
            won = best == oi
            if won:
                w += 1
            pnl_e += (eo - 1.0) if won else -1.0
            pnl_c += (co - 1.0) if won else -1.0
        if n:
            print(
                f"{min_move:8.1%} {n:5d} {w/n:6.1%} {pnl_e/n:+11.1%} {pnl_c/n:+11.1%}"
            )
    print(
        "    (early >> close ROI confirms the move is informative; profit needs early ROI > 0)"
    )

    # ---- Signal 2: SOFT-OUTLIER vs sharp consensus, settled at the BEST price ----
    print(
        "\n=== SIGNAL 2: SOFT-OUTLIER (best soft price vs sharp early consensus) — TRADABLE ==="
    )
    print(f"{'EV margin':>9s} {'bets':>5s} {'hit':>6s} {'roi':>8s}")
    for margin in (0.0, 0.02, 0.04, 0.06, 0.08, 0.10):
        n = w = 0
        pnl = 0.0
        for r in test:
            if not usable(r):
                continue
            oi = {"H": 0, "D": 1, "A": 2}[r["result"]]
            sharp = devig(r["odds_h"], r["odds_d"], r["odds_a"])  # sharp fair probs
            best_px = (r["odds_maxh"], r["odds_maxd"], r["odds_maxa"])
            evs = [
                sharp[k] * best_px[k] - 1.0 for k in range(3)
            ]  # EV at best price by sharp prob
            best = max(range(3), key=lambda k: evs[k])
            if evs[best] < margin:
                continue
            n += 1
            won = best == oi
            if won:
                w += 1
            pnl += (best_px[best] - 1.0) if won else -1.0
        if n:
            print(f"{margin:9.1%} {n:5d} {w/n:6.1%} {pnl/n:+8.1%}")
    print(
        "    (this is line-shopping vs the sharp line; positive ROI here is directly bettable)"
    )


if __name__ == "__main__":
    main()
