"""
train_ou_calibrator.py — fit the Over/Under 2.5 probability calibrator.
=======================================================================
The DC-derived O/U 2.5 has genuine discriminative signal but a systematic downward
bias (it under-estimates total goals by ~0.2, so it under-calls "over"). This fits a
Platt calibrator on walk-forward (model P(over), actual over) pairs over ~13k real
matches — the same protocol as train_1x2_calibrator.py — to remove that bias.

Output: models/calibrator_ou25.json  {type:platt, market:"OU25", a, b}.
The daemon's O/U path applies it the same way _calibrate_1x2 does for 1X2.

Run:  .venv\\Scripts\\python.exe tools\\train_ou_calibrator.py
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
OUT = os.path.join(os.path.dirname(__file__), "..", "models", "calibrator_ou25.json")
MAX_GOALS = 10


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


def _pois(k, lam):
    return math.exp(-lam) * lam**k / math.factorial(k)


def p_over25(lam, mu):
    """P(total goals > 2.5), plain Poisson — matches the daemon's O/U derivation."""
    over = tot = 0.0
    for i in range(MAX_GOALS + 1):
        for j in range(MAX_GOALS + 1):
            p = _pois(i, lam) * _pois(j, mu)
            tot += p
            if i + j > 2.5:
                over += p
    return over / tot if tot > 0 else None


def collect_from_history():
    """Walk-forward DC O/U predictions -> (model P(over), over) pairs."""
    from src.models.dixon_coles import fit_league

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
            lam = math.exp(
                m["teams"][r["home"]]["att"]
                + m["teams"][r["away"]]["def"]
                + m["home_adv"]
            )
            mu = math.exp(m["teams"][r["away"]]["att"] + m["teams"][r["home"]]["def"])
            po = p_over25(lam, mu)
            X.append(po)
            Y.append(1 if (r["home_goals"] + r["away_goals"]) > 2.5 else 0)
    return X, Y


def reliability(X, Y, fn, label):
    print(f"  {label}")
    for lo, hi in [(0, 0.35), (0.35, 0.45), (0.45, 0.55), (0.55, 0.65), (0.65, 1.01)]:
        idx = [i for i in range(len(X)) if lo <= X[i] < hi]
        if idx:
            pred = sum(fn(X[i]) for i in idx) / len(idx)
            act = sum(Y[i] for i in idx) / len(idx)
            print(
                f"    {lo:4.0%}-{hi:4.0%} n={len(idx):5d} pred={pred:5.1%} actual={act:5.1%}"
            )


def main():
    X, Y = collect_from_history()
    n = len(X)
    if n < 200:
        print("Too few samples (need history.db + dixon_coles.json); aborting.")
        return
    print(
        f"Calibration source: history (Dixon-Coles, walk-forward) | samples: {n} | "
        f"base over-rate: {np.mean(Y):.1%} | mean raw P(over): {np.mean(X):.1%}\n"
    )

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
        + " ".join(f"{p:.0%}->{cal(p):.0%}" for p in (0.3, 0.4, 0.5, 0.6, 0.7))
    )

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(
            {
                "type": "platt",
                "market": "OU25",
                "a": a,
                "b": b,
                "n_train": n,
                "source": "history (Dixon-Coles, walk-forward)",
            },
            f,
            indent=2,
        )
    print(f"\nSaved -> {os.path.relpath(OUT)}")


if __name__ == "__main__":
    main()
