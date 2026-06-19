"""
train_1x2_calibrator.py — fit the 1X2 probability calibrator.
=============================================================
Preferred path: calibrate the **Dixon-Coles** model against ~13k REAL historical
outcomes, walk-forward (fit DC on earlier seasons, predict the next, collect
(model_prob, win) pairs). This matches the model actually used live and uses
thousands of points instead of a few dozen paper bets.

Fallback: if history.db / the DC model is missing, calibrate from bet_log.db.

Output (unchanged format): models/calibrator_1x2.json  {type:platt, a, b}.
The daemon's _calibrate_1x2() maps raw->calibrated win prob with it.

Run:  .venv\\Scripts\\python.exe tools\\train_1x2_calibrator.py
"""

import datetime
import json
import math
import os
import sqlite3
import sys

import numpy as np
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

HIST = os.path.join(os.path.dirname(__file__), "..", "data", "history.db")
BETLOG = os.path.join(os.path.dirname(__file__), "..", "data", "bet_log.db")
OUT = os.path.join(os.path.dirname(__file__), "..", "models", "calibrator_1x2.json")


def logit(p):
    p = min(1 - 1e-6, max(1e-6, p))
    return math.log(p / (1 - p))


def sigmoid(z):
    return 1.0 / (1.0 + math.exp(-z))


def _parse_ord(s):
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.datetime.strptime(s, fmt).toordinal()
        except (ValueError, TypeError):
            continue
    return None


def collect_from_history():
    """Walk-forward DC predictions -> (model_prob, win) pairs over real matches."""
    from src.models.dixon_coles import fit_league, predict_1x2_from_params

    con = sqlite3.connect(HIST)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT * FROM matches")]
    con.close()
    seasons = sorted({r["season"] for r in rows})
    if len(seasons) < 2:
        return [], []
    X, Y = [], []
    for si in range(1, len(seasons)):
        test_s = seasons[si]
        train_s = set(seasons[:si])
        by_lg = {}
        for r in rows:
            if r["season"] in train_s:
                o = _parse_ord(r["date"])
                if o:
                    by_lg.setdefault(r["league"], []).append(
                        {
                            "home": r["home"],
                            "away": r["away"],
                            "hg": r["home_goals"],
                            "ag": r["away_goals"],
                            "ordinal": o,
                        }
                    )
        models = {lg: fit_league(ms) for lg, ms in by_lg.items()}
        for r in rows:
            if r["season"] != test_s:
                continue
            m = models.get(r["league"])
            if not m or r["home"] not in m["teams"] or r["away"] not in m["teams"]:
                continue
            if r["result"] not in ("H", "D", "A"):
                continue
            ph, pd, pa = predict_1x2_from_params(
                m["teams"][r["home"]]["att"],
                m["teams"][r["home"]]["def"],
                m["teams"][r["away"]]["att"],
                m["teams"][r["away"]]["def"],
                m["home_adv"],
                m["rho"],
            )
            for prob, outc in ((ph, "H"), (pd, "D"), (pa, "A")):
                X.append(prob)
                Y.append(1 if r["result"] == outc else 0)
    return X, Y


def collect_from_betlog():
    con = sqlite3.connect(BETLOG)
    con.row_factory = sqlite3.Row
    rows = [
        dict(r) for r in con.execute("SELECT * FROM bet_log WHERE market_type='1X2'")
    ]
    con.close()
    X, Y = [], []
    for r in rows:
        res = str(r.get("result", "")).upper()
        if res not in ("W", "L", "WIN", "LOSS", "WON", "LOST"):
            continue
        try:
            fo = float(r["fair_odds"])
        except (TypeError, ValueError):
            continue
        if fo > 0:
            X.append(1.0 / fo)
            Y.append(1 if res.startswith("W") else 0)
    return X, Y


def reliability(X, Y, fn, label):
    print(f"  {label}")
    for lo, hi in [(0, 0.2), (0.2, 0.35), (0.35, 0.5), (0.5, 0.65), (0.65, 1.01)]:
        idx = [i for i in range(len(X)) if lo <= X[i] < hi]
        if idx:
            pred = sum(fn(X[i]) for i in idx) / len(idx)
            act = sum(Y[i] for i in idx) / len(idx)
            print(
                f"    {lo:4.0%}-{hi:4.0%} n={len(idx):5d} pred={pred:5.1%} actual={act:5.1%}"
            )


def main():
    source = "history (Dixon-Coles, walk-forward)"
    X, Y = ([], [])
    if os.path.exists(HIST) and os.path.exists(
        os.path.join(os.path.dirname(__file__), "..", "models", "dixon_coles.json")
    ):
        try:
            X, Y = collect_from_history()
        except Exception as e:
            print(f"history calibration failed ({e}); falling back to bet_log.")
    if len(X) < 200:
        source = "bet_log paper bets"
        X, Y = collect_from_betlog()
    n = len(X)
    print(
        f"Calibration source: {source} | samples: {n} | base win-rate: {np.mean(Y):.1%}\n"
    )
    if n < 20:
        print("Too few samples; aborting.")
        return

    Z = np.array([[logit(p)] for p in X])
    clf = LogisticRegression(C=1.0)
    clf.fit(Z, np.array(Y))
    a, b = float(clf.intercept_[0]), float(clf.coef_[0][0])
    cal = lambda p: sigmoid(a + b * logit(p))

    print("BEFORE (raw):")
    reliability(X, Y, lambda p: p, "identity")
    print("AFTER  (calibrated):")
    reliability(X, Y, cal, "platt")
    print(
        "\n  mapping: "
        + " ".join(f"{p:.0%}->{cal(p):.0%}" for p in (0.2, 0.35, 0.5, 0.65, 0.8))
    )

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(
            {
                "type": "platt",
                "market": "1X2",
                "a": a,
                "b": b,
                "n_train": n,
                "source": source,
            },
            f,
            indent=2,
        )
    print(f"\nSaved -> {os.path.relpath(OUT)}")


if __name__ == "__main__":
    main()
