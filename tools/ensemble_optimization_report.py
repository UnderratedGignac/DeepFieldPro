"""
Phase 8 CLI: model-vs-market ensemble weight sweep + logistic stacking,
walk-forward on data/history.db. READ-ONLY.

Reuses the same train/test season split, Dixon-Coles fitting, and de-vig
helper as tools/backtest_1x2_lines.py (Phase 5's data source) rather than
re-implementing them. Adds: a blend-weight sweep (src/ensemble_optimizer.py)
scored on log-loss/Brier (prediction quality) AND betting ROI (Phase 5's
edge_threshold_analysis, at a fixed 3% edge bar for comparability across
weights), plus a logistic-stacking model (sklearn) fit on the train seasons
and evaluated out-of-sample on the held-out test season.

This directly checks the two hardcoded blend weights already in production:
- data/settings.json's `market_blend_weight` (paper daemon, default 0.5)
- src/arena_betting.py's `WC_MODEL_WEIGHT` (Arena, default 0.65 -- though
  that one blends WC-Elo with DFP/Sportmonks, not model-vs-market; see
  module docstring in src/ensemble_optimizer.py for why THIS report targets
  model-vs-market specifically, and why an Elo-vs-DC comparison isn't
  fabricated here).

Per the master prompt: recommends, does not auto-change either setting.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import math
import sqlite3

from tools.backtest_1x2_lines import DB, parse_ordinal, devig
from src.models.dixon_coles import fit_league, predict_1x2_from_params
from src.ensemble_optimizer import blend_probs, multiclass_log_loss, multiclass_brier, best_ev_pick
from src.edge_threshold_analysis import edge_threshold_metrics

WEIGHTS = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)
BET_EDGE_THRESHOLD = 0.03  # fixed across weights so ROI differences reflect blend quality, not threshold choice


def _fit_models(rows, train_seasons):
    by_league_train = {}
    for r in rows:
        if r["season"] in train_seasons:
            o = parse_ordinal(r["date"])
            if o:
                by_league_train.setdefault(r["league"], []).append(
                    {"home": r["home"], "away": r["away"], "hg": r["home_goals"],
                     "ag": r["away_goals"], "ordinal": o}
                )
    return {lg: p for lg, ms in by_league_train.items() if (p := fit_league(ms))}


def _usable_rows(rows, models, seasons):
    """
    Rows (from any of `seasons`) with a fitted league model, complete early
    odds, and a real result -- each returned as {dc, mkt, odds, result},
    the shared shape both the blend sweep and the logistic-stacking fit
    consume (no duplicated extraction logic between the two).
    """
    out = []
    for r in rows:
        if r["season"] not in seasons:
            continue
        m = models.get(r["league"])
        if not m:
            continue
        h, a = r["home"], r["away"]
        if h not in m["teams"] or a not in m["teams"]:
            continue
        eh, ed, ea = r["odds_h"], r["odds_d"], r["odds_a"]
        if not all((eh, ed, ea)) or r["result"] not in ("H", "D", "A"):
            continue
        dc_h, dc_d, dc_a = predict_1x2_from_params(
            m["teams"][h]["att"], m["teams"][h]["def"],
            m["teams"][a]["att"], m["teams"][a]["def"], m["home_adv"], m["rho"],
        )
        mkt_h, mkt_d, mkt_a = devig(eh, ed, ea)
        out.append(
            {
                "dc": {"home": dc_h, "draw": dc_d, "away": dc_a},
                "mkt": {"home": mkt_h, "draw": mkt_d, "away": mkt_a},
                "odds": {"home": eh, "draw": ed, "away": ea},
                "result": {"H": "home", "D": "draw", "A": "away"}[r["result"]],
            }
        )
    return out


def _report_blend_sweep(test_rows):
    header = f"{'weight':>7s} {'logloss':>8s} {'brier':>7s} {'n_bets':>7s} {'roi':>8s} {'hit':>7s} {'sharpe':>7s}"
    print(header)
    print("-" * len(header))
    for w in WEIGHTS:
        blended = [blend_probs(r["dc"], r["mkt"], w) for r in test_rows]
        actuals = [r["result"] for r in test_rows]
        ll = multiclass_log_loss(blended, actuals)
        br = multiclass_brier(blended, actuals)

        bets = []
        for r, probs in zip(test_rows, blended):
            outcome, _ev = best_ev_pick(probs, r["odds"], ev_threshold=BET_EDGE_THRESHOLD)
            if outcome:
                bets.append((outcome == r["result"], r["odds"][outcome]))
        m = edge_threshold_metrics(bets)
        label = "model" if w == 1.0 else ("market" if w == 0.0 else f"{w:.1f}")
        roi_s = "n/a" if m["roi"] is None else f"{m['roi']:+7.1%}"
        hit_s = "n/a" if m["hit_rate"] is None else f"{m['hit_rate']:6.1%}"
        sharpe_s = "n/a" if m["sharpe"] is None else f"{m['sharpe']:6.2f}"
        print(f"{label:>7s} {ll:8.4f} {br:7.4f} {m['n']:7d} {roi_s:>8s} {hit_s:>7s} {sharpe_s:>7s}")


def _logit_features(row):
    eps = 1e-6
    dc, mkt = row["dc"], row["mkt"]

    def _logit(p):
        p = max(eps, min(1 - eps, p))
        return math.log(p / (1 - p))

    return [_logit(dc["home"]), _logit(dc["draw"]), _logit(mkt["home"]), _logit(mkt["draw"])]


def _report_logistic_stacking(rows, models, train_seasons, test_season):
    import numpy as np
    from sklearn.linear_model import LogisticRegression

    train = _usable_rows(rows, models, set(train_seasons))
    test = _usable_rows(rows, models, {test_season})
    if len(train) < 50 or not test:
        print(f"  Insufficient data to fit stacking model (train n={len(train)}, test n={len(test)}).")
        return

    X_train = np.array([_logit_features(r) for r in train])
    y_train = np.array([r["result"] for r in train])
    clf = LogisticRegression(max_iter=1000)
    clf.fit(X_train, y_train)

    X_test = np.array([_logit_features(r) for r in test])
    y_test = [r["result"] for r in test]
    proba = clf.predict_proba(X_test)
    class_order = list(clf.classes_)
    blended = [{cls: p for cls, p in zip(class_order, row)} for row in proba]
    ll = multiclass_log_loss(blended, y_test)
    br = multiclass_brier(blended, y_test)
    print(f"  n={len(test)}  logloss={ll:.4f}  brier={br:.4f}  classes={class_order}")


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT * FROM matches")]
    con.close()

    seasons = sorted({r["season"] for r in rows})
    test_season, train_seasons = seasons[-1], seasons[:-1]
    models = _fit_models(rows, train_seasons)
    test_rows = _usable_rows(rows, models, {test_season})
    print(f"Test season: {test_season} | usable rows: {len(test_rows)}\n")

    _report_blend_sweep(test_rows)

    print("\n--- Logistic stacking (multinomial, fit on train seasons) ---")
    _report_logistic_stacking(rows, models, train_seasons, test_season)

    print(
        "\nRecommendation only - does NOT change data/settings.json's "
        "market_blend_weight or src/arena_betting.py's WC_MODEL_WEIGHT."
    )


if __name__ == "__main__":
    main()
