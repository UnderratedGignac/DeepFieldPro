"""
backtest_1x2_model.py — out-of-sample validation of the Dixon-Coles 1X2 model.
============================================================================
Trains per-league Dixon-Coles on the EARLIER seasons, then evaluates on the most
recent held-out season (no leakage). Compares three predictors on the same matches:

  * dixon-coles : the new continuous team-strength model
  * heuristic   : the OLD 3-bucket model (fixed expected goals 2.1/0.8, 0.8/2.1, 1.2/1.2),
                  bucket chosen by the market favourite (its best case)
  * market      : the de-vigged closing odds (the gold standard — hardest to beat)

Metrics: log-loss & Brier (lower=better), and a betting sim at the EARLY Pinnacle line
(odds_h/d/a; football-data's `PSH` is the early, not closing, price). For the closing-line
benchmark and CLV (the real edge test — does the edge live in softer/earlier prices?),
see tools/backtest_1x2_lines.py.

Run:  .venv\\Scripts\\python.exe tools\\backtest_1x2_model.py
"""
import datetime
import math
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.models.dixon_coles import fit_league, predict_1x2_from_params

DB = os.path.join(os.path.dirname(__file__), "..", "data", "history.db")


def parse_ordinal(s):
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.datetime.strptime(s, fmt).toordinal()
        except (ValueError, TypeError):
            continue
    return None


def pois(k, lam):
    return math.exp(-lam) * lam ** k / math.factorial(k)


def poisson_1x2(lam, mu, n=10):
    ph = pd = pa = 0.0
    for i in range(n + 1):
        for j in range(n + 1):
            p = pois(i, lam) * pois(j, mu)
            if i > j: ph += p
            elif i == j: pd += p
            else: pa += p
    t = ph + pd + pa
    return ph / t, pd / t, pa / t


# Old heuristic's three fixed outputs (plain Poisson, no DC correction).
HEUR = {"H": poisson_1x2(2.1, 0.8), "A": poisson_1x2(0.8, 2.1), "D": poisson_1x2(1.2, 1.2)}


def devig(oh, od, oa):
    ih, idr, ia = 1 / oh, 1 / od, 1 / oa
    s = ih + idr + ia
    return ih / s, idr / s, ia / s


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT * FROM matches")]
    con.close()
    seasons = sorted({r["season"] for r in rows})
    test_season = seasons[-1]
    train_seasons = seasons[:-1]
    print(f"Train seasons: {train_seasons}  |  Test season: {test_season}\n")

    # fit per league on train seasons
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

    # evaluate on test season
    agg = {k: {"ll": 0.0, "brier": 0.0, "n": 0} for k in ("dixon-coles", "heuristic", "market")}
    bets = {k: {"staked": 0.0, "pnl": 0.0, "n": 0, "w": 0} for k in ("dixon-coles", "heuristic")}
    THRESH = 0.03   # require 3% model edge over the market price to bet

    for r in rows:
        if r["season"] != test_season:
            continue
        lg = models.get(r["league"])
        if not lg:
            continue
        h, a = r["home"], r["away"]
        if h not in lg["teams"] or a not in lg["teams"]:
            continue
        oh, od, oa = r["odds_h"], r["odds_d"], r["odds_a"]
        if not (oh and od and oa):
            continue
        outcome = r["result"]  # 'H','D','A'
        if outcome not in ("H", "D", "A"):
            continue
        oi = {"H": 0, "D": 1, "A": 2}[outcome]

        dc = predict_1x2_from_params(lg["teams"][h]["att"], lg["teams"][h]["def"],
                                     lg["teams"][a]["att"], lg["teams"][a]["def"],
                                     lg["home_adv"], lg["rho"])
        mkt = devig(oh, od, oa)
        fav = "H" if mkt[0] >= max(mkt[1], mkt[2]) else ("A" if mkt[2] >= mkt[1] else "D")
        heur = HEUR[fav]

        preds = {"dixon-coles": dc, "heuristic": heur, "market": mkt}
        for name, p in preds.items():
            p = [max(1e-9, min(1 - 1e-9, x)) for x in p]
            agg[name]["ll"] += -math.log(p[oi])
            agg[name]["brier"] += sum((p[k] - (1 if k == oi else 0)) ** 2 for k in range(3))
            agg[name]["n"] += 1

        # betting at the EARLY Pinnacle line (PSH/PSD/PSA = early, not closing)
        odds = (oh, od, oa)
        for name, p in (("dixon-coles", dc), ("heuristic", heur)):
            evs = [p[k] * odds[k] - 1 for k in range(3)]
            best = max(range(3), key=lambda k: evs[k])
            if p[best] - mkt[best] >= THRESH and evs[best] > 0:
                bets[name]["staked"] += 1.0
                bets[name]["n"] += 1
                if best == oi:
                    bets[name]["pnl"] += odds[best] - 1.0
                    bets[name]["w"] += 1
                else:
                    bets[name]["pnl"] -= 1.0

    print("=== OUT-OF-SAMPLE ACCURACY (lower is better) ===")
    print(f"{'model':14s} {'n':>5s} {'log-loss':>9s} {'brier':>7s}")
    for name in ("market", "dixon-coles", "heuristic"):
        s = agg[name]
        if s["n"]:
            print(f"{name:14s} {s['n']:5d} {s['ll']/s['n']:9.4f} {s['brier']/s['n']:7.4f}")
    print("(market is the benchmark; DC should beat heuristic and approach market)")

    print("\n=== BETTING AT THE EARLY PINNACLE LINE (see backtest_1x2_lines.py for close+CLV) ===")
    print(f"{'model':14s} {'bets':>5s} {'hit':>6s} {'staked':>8s} {'pnl':>8s} {'roi':>8s}")
    for name in ("dixon-coles", "heuristic"):
        b = bets[name]
        roi = b["pnl"] / b["staked"] if b["staked"] else 0
        hit = b["w"] / b["n"] if b["n"] else 0
        print(f"{name:14s} {b['n']:5d} {hit:6.1%} {b['staked']:8.0f} {b['pnl']:+8.1f} {roi:+8.1%}")
    print("\nNote: this is the EARLY Pinnacle line (the price you can actually take). The")
    print("closing-line benchmark and CLV — the real edge test — are in backtest_1x2_lines.py.")


if __name__ == "__main__":
    main()
