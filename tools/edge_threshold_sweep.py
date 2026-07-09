"""
Phase 5 CLI: edge-threshold sweep (2%-10%) with full metrics — ROI, Sharpe,
Sortino, max drawdown, Calmar, profit factor, Kelly growth, bootstrap ROI CI.

Reuses the existing walk-forward Dixon-Coles backtest in
tools/backtest_1x2_lines.py (same model fit, same held-out test season, same
"best-soft-early" actionable strategy that file's own analysis identified —
see its module docstring) rather than re-implementing model fitting. This
tool only adds the metrics layer (src/edge_threshold_analysis.py) on top of
that existing evaluate() function, which now also returns the per-bet
sequence needed for path-dependent metrics like max drawdown.

Per the master prompt: this RECOMMENDS thresholds, it does not change
edge_min in data/settings.json or any other production config automatically.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import sqlite3

from tools.backtest_1x2_lines import DB, parse_ordinal, evaluate
from src.models.dixon_coles import fit_league
from src.edge_threshold_analysis import edge_threshold_metrics

THRESHOLDS = (0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10)
STRATEGY = "best-soft-early"  # the actionable, line-shopped price per backtest_1x2_lines.py


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT * FROM matches")]
    con.close()

    seasons = sorted({r["season"] for r in rows})
    test_season, train_seasons = seasons[-1], seasons[:-1]
    print(f"Train seasons: {train_seasons}  |  Test season: {test_season}")
    print(f"Strategy priced at: {STRATEGY}\n")

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

    header = (
        f"{'edge>=':>7s} {'n':>5s} {'roi':>8s} {'hit':>7s} {'sharpe':>7s} "
        f"{'sortino':>7s} {'maxDD':>7s} {'calmar':>7s} {'PF':>6s} {'kellyG':>8s} {'roiCI95':>18s}"
    )
    print(header)
    print("-" * len(header))
    results = []
    for th in THRESHOLDS:
        strat = evaluate(rows, models, test_season, th)
        bets = strat[STRATEGY]["bets"]
        m = edge_threshold_metrics(bets)
        results.append({"threshold": th, **m})
        if m["n"] == 0:
            print(f"{th:6.0%}  {'(no qualifying bets)':>60s}")
            continue
        print(
            f"{th:6.0%}  {m['n']:5d} {m['roi']:+8.1%} {m['hit_rate']:7.1%} "
            f"{_fmt(m['sharpe'])} {_fmt(m['sortino'])} {_fmt(m['max_drawdown'], pct=False)} "
            f"{_fmt(m['calmar'])} {_fmt(m['profit_factor'], pct=False)} "
            f"{_fmt(m['kelly_growth'], digits=5, pct=False)} {m['roi_ci_95']}"
        )

    print(
        "\nRecommendation only - this does NOT change data/settings.json's edge_min. "
        "A human decides whether/when to adopt a different threshold."
    )
    return results


def _fmt(v, digits=2, pct=True):
    if v is None:
        return f"{'n/a':>7s}"
    if pct:
        return f"{v:7.{digits}f}"
    return f"{v:7.{digits}f}"


if __name__ == "__main__":
    main()
