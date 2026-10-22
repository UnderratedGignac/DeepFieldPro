"""
Phase 11 CLI: full backtest report (ROI/Sharpe/Sortino/Calmar/MaxDD/Profit
Factor/Kelly Growth/bootstrap CI/Monte Carlo) using the SAME production
model code (src/models/dixon_coles.py's fit_league/predict_1x2_from_params
-- literally what src/arena_betting.py and src/live_predictions_daemon.py
import) via the existing walk-forward setup in tools/backtest_1x2_lines.py.

Scope note (see src/backtest_framework.py's module docstring): this replays
the production MODEL against held-out history -- it does not replay Arena's
full live decision pipeline (gates/sizing/liquidity) against historical
Polymarket data, because no historical WC2026 Polymarket archive exists yet
to replay against (the tournament is current). Not fabricated here.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import sqlite3
import json

from tools.backtest_1x2_lines import DB, parse_ordinal, evaluate
from src.models.dixon_coles import fit_league
from src.backtest_framework import full_backtest_report

STRATEGY = "best-soft-early"  # Phase 5's identified actionable strategy
EDGE_THRESHOLD = 0.03


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT * FROM matches")]
    con.close()

    seasons = sorted({r["season"] for r in rows})
    test_season, train_seasons = seasons[-1], seasons[:-1]

    by_league_train = {}
    for r in rows:
        if r["season"] in train_seasons:
            o = parse_ordinal(r["date"])
            if o:
                by_league_train.setdefault(r["league"], []).append(
                    {"home": r["home"], "away": r["away"], "hg": r["home_goals"],
                     "ag": r["away_goals"], "ordinal": o}
                )
    models = {lg: p for lg, ms in by_league_train.items() if (p := fit_league(ms))}

    strat = evaluate(rows, models, test_season, EDGE_THRESHOLD)
    bets = strat[STRATEGY]["bets"]

    print(f"Test season: {test_season} | strategy: {STRATEGY} | edge>={EDGE_THRESHOLD:.0%} | n_bets={len(bets)}\n")
    report = full_backtest_report(bets, kelly_fraction=0.25, n_sims=5000)
    print(json.dumps(report, indent=2))

    print(
        "\nModel code path: src/models/dixon_coles.py (same module imported by "
        "src/arena_betting.py and src/live_predictions_daemon.py in production).\n"
        "Scope: does not replay Arena's live gates/sizing against historical "
        "Polymarket data -- no such archive exists for a live, current tournament."
    )


if __name__ == "__main__":
    main()
