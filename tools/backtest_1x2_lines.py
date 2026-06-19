"""
backtest_1x2_lines.py — does the 1X2 edge live in softer/earlier lines? (CLV test)
==================================================================================
The project's core hypothesis is "nobody beats the Pinnacle CLOSE, but the edge is in
softer/earlier books." backtest_1x2_model.py couldn't test that — it bet `PSH`, which is
the EARLY Pinnacle line, while *labelling* it the close. This tool uses the real columns:

  early  Pinnacle  = odds_h/odds_d/odds_a     (when you actually place the bet)
  best   early      = odds_maxh/.../odds_maxa  (softest price across books — line shopping)
  CLOSE  Pinnacle  = odds_ch/odds_cd/odds_ca   (the sharp benchmark)

Same walk-forward protocol: fit DC on earlier seasons, evaluate on the held-out season.
For every match the model flags an edge on, we settle the bet by the real result AT three
prices, and we measure **CLV** (closing line value): clv = price_taken / closing_price − 1.
Positive average CLV (and >50% of bets beating the close) is the gold-standard signal that
an edge is real, even when betting INTO the close is break-even.

Run:  .venv\\Scripts\\python.exe tools\\backtest_1x2_lines.py
"""

import datetime
import math
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.models.dixon_coles import fit_league, predict_1x2_from_params

DB = os.path.join(os.path.dirname(__file__), "..", "data", "history.db")
THRESH = 0.03  # require 3% model edge over the de-vigged early market to bet


def parse_ordinal(s):
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.datetime.strptime(s, fmt).toordinal()
        except (ValueError, TypeError):
            continue
    return None


def devig(oh, od, oa):
    ih, idr, ia = 1 / oh, 1 / od, 1 / oa
    s = ih + idr + ia
    return ih / s, idr / s, ia / s


def evaluate(rows, models, test_season, thresh):
    """Run one threshold; return per-strategy {n,w,pnl,clv,clv_pos}."""
    strat = {
        k: {"pnl": 0.0, "n": 0, "w": 0, "clv": 0.0, "clv_pos": 0}
        for k in ("pinnacle-early", "best-soft-early", "pinnacle-close")
    }
    for r in rows:
        if r["season"] != test_season:
            continue
        m = models.get(r["league"])
        if not m:
            continue
        h, a = r["home"], r["away"]
        if h not in m["teams"] or a not in m["teams"]:
            continue
        eh, ed, ea = r["odds_h"], r["odds_d"], r["odds_a"]  # early Pinnacle
        ch, cd, ca = r["odds_ch"], r["odds_cd"], r["odds_ca"]  # closing Pinnacle
        mh, md, ma = r["odds_maxh"], r["odds_maxd"], r["odds_maxa"]  # best early
        if not all((eh, ed, ea, ch, cd, ca, mh, md, ma)):
            continue
        if r["result"] not in ("H", "D", "A"):
            continue
        oi = {"H": 0, "D": 1, "A": 2}[r["result"]]

        dc = predict_1x2_from_params(
            m["teams"][h]["att"],
            m["teams"][h]["def"],
            m["teams"][a]["att"],
            m["teams"][a]["def"],
            m["home_adv"],
            m["rho"],
        )
        early_odds = (eh, ed, ea)
        early_mkt = devig(eh, ed, ea)
        evs = [dc[k] * early_odds[k] - 1 for k in range(3)]
        best = max(range(3), key=lambda k: evs[k])
        if not (dc[best] - early_mkt[best] >= thresh and evs[best] > 0):
            continue

        close_odds = (ch, cd, ca)
        prices = {
            "pinnacle-early": early_odds[best],
            "best-soft-early": (mh, md, ma)[best],
            "pinnacle-close": close_odds[best],
        }
        won = best == oi
        for name, price in prices.items():
            s = strat[name]
            s["n"] += 1
            s["pnl"] += (price - 1.0) if won else -1.0
            if won:
                s["w"] += 1
            clv = price / close_odds[best] - 1.0
            s["clv"] += clv
            if clv > 0:
                s["clv_pos"] += 1
    return strat


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT * FROM matches")]
    con.close()
    seasons = sorted({r["season"] for r in rows})
    test_season, train_seasons = seasons[-1], seasons[:-1]
    print(f"Train seasons: {train_seasons}  |  Test season: {test_season}\n")

    by_league_train = {}
    for r in rows:
        if r["season"] in train_seasons:
            o = parse_ordinal(r["date"])
            if o:
                by_league_train.setdefault(r["league"], []).append(
                    {
                        "home": r["home"],
                        "away": r["away"],
                        "hg": r["home_goals"],
                        "ag": r["away_goals"],
                        "ordinal": o,
                    }
                )
    models = {}
    for lg, ms in by_league_train.items():
        p = fit_league(ms)
        if p:
            models[lg] = p

    # Baseline: same model picks at THREE prices, at the default threshold.
    strat = evaluate(rows, models, test_season, THRESH)
    print(f"=== SAME MODEL PICKS, SETTLED AT THREE PRICES (edge>={THRESH:.0%}) ===")
    print(
        f"{'strategy':16s} {'bets':>5s} {'hit':>6s} {'pnl':>8s} {'roi':>8s} {'avgCLV':>8s} {'beat-close':>10s}"
    )
    for name in ("pinnacle-close", "pinnacle-early", "best-soft-early"):
        s = strat[name]
        if not s["n"]:
            continue
        print(
            f"{name:16s} {s['n']:5d} {s['w']/s['n']:6.1%} {s['pnl']:+8.1f} "
            f"{s['pnl']/s['n']:+8.1%} {s['clv']/s['n']:+8.2%} {s['clv_pos']/s['n']:10.1%}"
        )

    # Selectivity sweep: does a higher edge bar find a profitable subset at the best price?
    print(
        "\n=== SELECTIVITY SWEEP (best-soft-early price — the actionable strategy) ==="
    )
    print(
        f"{'edge>=':>7s} {'bets':>5s} {'hit':>6s} {'roi':>8s} {'avgCLV':>8s} {'beat-close':>10s}"
    )
    for th in (0.02, 0.04, 0.06, 0.08, 0.10, 0.15, 0.20):
        s = evaluate(rows, models, test_season, th)["best-soft-early"]
        if s["n"]:
            print(
                f"{th:7.0%} {s['n']:5d} {s['w']/s['n']:6.1%} {s['pnl']/s['n']:+8.1%} "
                f"{s['clv']/s['n']:+8.2%} {s['clv_pos']/s['n']:10.1%}"
            )

    print("\nReading it:")
    print(
        " - pinnacle-close ROI ~ the unbeatable benchmark (~ -vig). The model does NOT beat it."
    )
    print(
        " - The actionable edge: take the BEST soft price. Positive avgCLV + >50% beat-close"
    )
    print(
        "   = a real (if small) edge. Look in the sweep for a threshold where ROI turns positive"
    )
    print("   with enough bets to trust — that's the selective rule worth running.")


if __name__ == "__main__":
    main()
