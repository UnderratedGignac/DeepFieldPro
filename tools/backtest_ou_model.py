"""
backtest_ou_model.py — out-of-sample validation of the DC-derived Over/Under 2.5 market.
=======================================================================================
Same walk-forward protocol as backtest_1x2_model.py: fit per-league Dixon-Coles on the
EARLIER seasons, evaluate on the most recent held-out season (no leakage). The daemon
derives O/U 2.5 from the DC expected goals via PLAIN Poisson (no low-score tau), so the
`dc` predictor here replicates that exactly. We also report `dc-tau` (the same expected
goals WITH the Dixon-Coles correction) to see whether the correction helps the goals line.

Predictors compared on the same matches:
  * dc      : plain Poisson on DC expected goals  (== production formula, raw)
  * dc-cal  : dc passed through a Platt calibrator fit on TRAIN seasons only (no leak)
  * market  : the de-vigged O/U 2.5 closing odds  (the gold standard — hardest to beat)

Metrics: log-loss & Brier (lower=better) for P(over 2.5), plus a betting sim INTO the
closing line (positive ROI there = genuinely beating the market — the real edge test).

Run:  .venv\\Scripts\\python.exe tools\\backtest_ou_model.py
"""
import datetime
import math
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.models.dixon_coles import fit_league

DB = os.path.join(os.path.dirname(__file__), "..", "data", "history.db")
MAX_GOALS = 10
THRESH = 0.03   # require 3% model edge over the market price to bet


def parse_ordinal(s):
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.datetime.strptime(s, fmt).toordinal()
        except (ValueError, TypeError):
            continue
    return None


def pois(k, lam):
    return math.exp(-lam) * lam ** k / math.factorial(k)


def _tau(i, j, lam, mu, rho):
    if i == 0 and j == 0:
        return 1.0 - lam * mu * rho
    if i == 0 and j == 1:
        return 1.0 + lam * rho
    if i == 1 and j == 0:
        return 1.0 + mu * rho
    if i == 1 and j == 1:
        return 1.0 - rho
    return 1.0


def p_over25(lam, mu, rho=None):
    """P(total goals > 2.5). rho=None -> plain Poisson (production); else DC tau."""
    over = tot = 0.0
    for i in range(MAX_GOALS + 1):
        for j in range(MAX_GOALS + 1):
            p = pois(i, lam) * pois(j, mu)
            if rho is not None:
                p *= max(1e-9, _tau(i, j, lam, mu, rho))
            tot += p
            if i + j > 2.5:
                over += p
    return over / tot if tot > 0 else None


def logit(p):
    p = min(1 - 1e-6, max(1e-6, p))
    return math.log(p / (1 - p))


def sigmoid(z):
    return 1.0 / (1.0 + math.exp(-z))


def devig(oo, ou):
    io, iu = 1 / oo, 1 / ou
    s = io + iu
    return io / s, iu / s


def fit_platt(X, Y):
    """Platt scaling on (prob, outcome) pairs -> (a, b) for sigmoid(a + b*logit(p))."""
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    Z = np.array([[logit(p)] for p in X])
    clf = LogisticRegression(C=1.0).fit(Z, np.array(Y))
    return float(clf.intercept_[0]), float(clf.coef_[0][0])


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT * FROM matches")]
    con.close()
    seasons = sorted({r["season"] for r in rows})
    test_season = seasons[-1]
    train_seasons = seasons[:-1]
    print(f"Train seasons: {train_seasons}  |  Test season: {test_season}\n")

    by_league_train = {}
    for r in rows:
        if r["season"] in train_seasons:
            o = parse_ordinal(r["date"])
            if o:
                by_league_train.setdefault(r["league"], []).append(
                    {"home": r["home"], "away": r["away"],
                     "hg": r["home_goals"], "ag": r["away_goals"], "ordinal": o})
    models = {}
    for lg, ms in by_league_train.items():
        p = fit_league(ms)
        if p:
            models[lg] = p

    # Fit the O/U calibrator on TRAIN seasons only (walk-forward within train,
    # predict season k from seasons < k) so the test season stays fully held out.
    calX, calY = [], []
    for si in range(1, len(train_seasons)):
        ts = train_seasons[si]
        prev = set(train_seasons[:si])
        sub = {}
        for r in rows:
            if r["season"] in prev:
                o = parse_ordinal(r["date"])
                if o:
                    sub.setdefault(r["league"], []).append(
                        {"home": r["home"], "away": r["away"],
                         "hg": r["home_goals"], "ag": r["away_goals"], "ordinal": o})
        subm = {lg: fit_league(ms) for lg, ms in sub.items()}
        for r in rows:
            if r["season"] != ts:
                continue
            m = subm.get(r["league"])
            if not m or r["home"] not in m["teams"] or r["away"] not in m["teams"]:
                continue
            lam = math.exp(m["teams"][r["home"]]["att"] + m["teams"][r["away"]]["def"] + m["home_adv"])
            mu = math.exp(m["teams"][r["away"]]["att"] + m["teams"][r["home"]]["def"])
            calX.append(p_over25(lam, mu))
            calY.append(1 if (r["home_goals"] + r["away_goals"]) > 2.5 else 0)
    ca, cb = fit_platt(calX, calY)
    calibrate = lambda po: sigmoid(ca + cb * logit(po))
    print(f"Calibrator fit on {len(calX)} train-only matches: a={ca:.3f} b={cb:.3f}\n")

    agg = {k: {"ll": 0.0, "brier": 0.0, "n": 0} for k in ("dc", "dc-cal", "market")}
    bets = {k: {"staked": 0.0, "pnl": 0.0, "n": 0, "w": 0} for k in ("dc", "dc-cal")}

    for r in rows:
        if r["season"] != test_season:
            continue
        lg = models.get(r["league"])
        if not lg:
            continue
        h, a = r["home"], r["away"]
        if h not in lg["teams"] or a not in lg["teams"]:
            continue
        oo, ou = r["odds_o25"], r["odds_u25"]
        if not (oo and ou):
            continue
        total = r["home_goals"] + r["away_goals"]
        over = 1 if total > 2.5 else 0

        lam = math.exp(lg["teams"][h]["att"] + lg["teams"][a]["def"] + lg["home_adv"])
        mu = math.exp(lg["teams"][a]["att"] + lg["teams"][h]["def"])
        dc = p_over25(lam, mu)                  # production: plain Poisson
        dc_cal = calibrate(dc)                  # bias-corrected (train-only fit)
        mo, mu_ = devig(oo, ou)                 # market P(over), P(under)

        # (P(over), P(under)) pairs for scoring
        preds = {"dc": (dc, 1 - dc), "dc-cal": (dc_cal, 1 - dc_cal), "market": (mo, mu_)}
        for name, (po, pu) in preds.items():
            po = max(1e-9, min(1 - 1e-9, po))
            pu = max(1e-9, min(1 - 1e-9, pu))
            agg[name]["ll"] += -math.log(po if over else pu)
            agg[name]["brier"] += (po - over) ** 2 + (pu - (1 - over)) ** 2
            agg[name]["n"] += 1

        # betting INTO the closing line
        odds = (oo, ou)
        mkt = (mo, mu_)
        for name, (po, pu) in (("dc", (dc, 1 - dc)), ("dc-cal", (dc_cal, 1 - dc_cal))):
            p = (po, pu)
            evs = [p[k] * odds[k] - 1 for k in range(2)]
            best = max(range(2), key=lambda k: evs[k])
            if p[best] - mkt[best] >= THRESH and evs[best] > 0:
                bets[name]["staked"] += 1.0
                bets[name]["n"] += 1
                won = (best == 0 and over) or (best == 1 and not over)
                if won:
                    bets[name]["pnl"] += odds[best] - 1.0
                    bets[name]["w"] += 1
                else:
                    bets[name]["pnl"] -= 1.0

    print("=== OUT-OF-SAMPLE ACCURACY (Over/Under 2.5, lower is better) ===")
    print(f"{'model':10s} {'n':>5s} {'log-loss':>9s} {'brier':>7s}")
    for name in ("market", "dc", "dc-cal"):
        s = agg[name]
        if s["n"]:
            print(f"{name:10s} {s['n']:5d} {s['ll']/s['n']:9.4f} {s['brier']/s['n']:7.4f}")
    print("(market is the benchmark; the DC O/U should at least approach it)")

    print("\n=== BETTING INTO THE CLOSING LINE (positive ROI = beats the market) ===")
    print(f"{'model':10s} {'bets':>5s} {'hit':>6s} {'staked':>8s} {'pnl':>8s} {'roi':>8s}")
    for name in ("dc", "dc-cal"):
        b = bets[name]
        roi = b["pnl"] / b["staked"] if b["staked"] else 0
        hit = b["w"] / b["n"] if b["n"] else 0
        print(f"{name:10s} {b['n']:5d} {hit:6.1%} {b['staked']:8.0f} {b['pnl']:+8.1f} {roi:+8.1%}")
    print("\nNote: betting into CLOSING odds is the hardest possible test. The daemon bets")
    print("earlier/softer lines, which is easier — but a market it can't beat at the close")
    print("and can't even match on log-loss should stay OFF the whitelist.")


if __name__ == "__main__":
    main()
