"""
dixon_coles.py — Dixon-Coles team-strength model for 1X2 probabilities.
=======================================================================
Replaces the daemon's 3-bucket hardcoded expected-goals heuristic with continuous
team attack/defense ratings. Each team i has attack a_i and defense d_i; with home
advantage h:

    lambda_home = exp(a_home + d_away + h)      (home expected goals)
    mu_away     = exp(a_away + d_home)          (away expected goals)

Goals are bivariate-Poisson with the Dixon-Coles low-score correction tau(rho),
which fixes naive Poisson's under-counting of 0-0/1-0/0-1/1-1 and draw inflation.
Recent matches are up-weighted by exponential time decay. Fit by penalised MLE
(scipy L-BFGS-B); fit PER LEAGUE because teams only link within their own league.

Pure-python apply path (predict_1x2) needs only `math`, so the daemon can score
fixtures with no scipy/numpy dependency at runtime.
"""
import json
import math
import os

MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "models", "dixon_coles.json")
MAX_GOALS = 10


# ─────────────────────────── apply (pure python) ───────────────────────────
def _pois(k, lam):
    return math.exp(-lam) * lam ** k / math.factorial(k)


def _tau(hg, ag, lam, mu, rho):
    if hg == 0 and ag == 0:
        return 1.0 - lam * mu * rho
    if hg == 0 and ag == 1:
        return 1.0 + lam * rho
    if hg == 1 and ag == 0:
        return 1.0 + mu * rho
    if hg == 1 and ag == 1:
        return 1.0 - rho
    return 1.0


def predict_1x2_from_params(att_h, def_h, att_a, def_a, home_adv, rho):
    """Return (p_home, p_draw, p_away) from raw team params."""
    lam = math.exp(att_h + def_a + home_adv)
    mu = math.exp(att_a + def_h)
    ph = pd = pa = 0.0
    for i in range(MAX_GOALS + 1):
        for j in range(MAX_GOALS + 1):
            p = _pois(i, lam) * _pois(j, mu) * max(1e-9, _tau(i, j, lam, mu, rho))
            if i > j:
                ph += p
            elif i == j:
                pd += p
            else:
                pa += p
    tot = ph + pd + pa
    return (ph / tot, pd / tot, pa / tot) if tot > 0 else (None, None, None)


class DixonColes:
    """Loaded model: per-league team ratings + home_adv + rho."""

    def __init__(self, data=None):
        self.leagues = (data or {}).get("leagues", {})

    @classmethod
    def load(cls, path=MODEL_PATH):
        with open(path, encoding="utf-8") as f:
            return cls(json.load(f))

    def expected_goals(self, league, home, away):
        lg = self.leagues.get(league)
        if not lg:
            return None
        t = lg["teams"]
        if home not in t or away not in t:
            return None
        lam = math.exp(t[home]["att"] + t[away]["def"] + lg["home_adv"])
        mu = math.exp(t[away]["att"] + t[home]["def"])
        return lam, mu

    def predict_1x2(self, league, home, away):
        lg = self.leagues.get(league)
        if not lg:
            return None
        t = lg["teams"]
        if home not in t or away not in t:
            return None
        return predict_1x2_from_params(
            t[home]["att"], t[home]["def"], t[away]["att"], t[away]["def"],
            lg["home_adv"], lg["rho"])

    def all_team_names(self):
        names = set()
        for lg in self.leagues.values():
            names.update(lg["teams"].keys())
        return names


# ─────────────────────────── fit (needs numpy/scipy) ───────────────────────
def fit_league(matches, time_decay_xi=0.0045, reg=0.5, ref_ordinal=None):
    """matches: list of dicts {home, away, hg, ag, ordinal}. Returns league params dict."""
    import numpy as np
    from scipy.optimize import minimize

    teams = sorted({m["home"] for m in matches} | {m["away"] for m in matches})
    idx = {tm: i for i, tm in enumerate(teams)}
    n = len(teams)
    if n < 4 or len(matches) < n * 4:
        return None

    ref = ref_ordinal if ref_ordinal is not None else max(m["ordinal"] for m in matches)
    H = np.array([idx[m["home"]] for m in matches])
    A = np.array([idx[m["away"]] for m in matches])
    HG = np.array([m["hg"] for m in matches])
    AG = np.array([m["ag"] for m in matches])
    W = np.exp(-time_decay_xi * (ref - np.array([m["ordinal"] for m in matches])))

    def unpack(p):
        return p[:n], p[n:2 * n], p[2 * n], p[2 * n + 1]

    def nll(p):
        att, dfn, home_adv, rho = unpack(p)
        rho = max(-0.4, min(0.4, rho))
        lam = np.exp(att[H] + dfn[A] + home_adv)
        mu = np.exp(att[A] + dfn[H])
        # poisson log-pmf
        ll = (HG * np.log(lam) - lam - _gammaln(HG + 1)
              + AG * np.log(mu) - mu - _gammaln(AG + 1))
        # Dixon-Coles low-score correction
        tau = np.ones(len(matches))
        m00 = (HG == 0) & (AG == 0); tau[m00] = 1 - lam[m00] * mu[m00] * rho
        m01 = (HG == 0) & (AG == 1); tau[m01] = 1 + lam[m01] * rho
        m10 = (HG == 1) & (AG == 0); tau[m10] = 1 + mu[m10] * rho
        m11 = (HG == 1) & (AG == 1); tau[m11] = 1 - rho
        tau = np.clip(tau, 1e-9, None)
        ll = ll + np.log(tau)
        penalty = reg * (np.sum(att ** 2) + np.sum(dfn ** 2))
        return -np.sum(W * ll) + penalty

    p0 = np.zeros(2 * n + 2)
    p0[2 * n] = 0.25  # home advantage prior
    res = minimize(nll, p0, method="L-BFGS-B",
                   options={"maxiter": 500, "ftol": 1e-7})
    att, dfn, home_adv, rho = unpack(res.x)
    att = att - att.mean()  # centre for identifiability/readability
    rho = float(max(-0.4, min(0.4, rho)))
    return {
        "teams": {tm: {"att": float(att[idx[tm]]), "def": float(dfn[idx[tm]])} for tm in teams},
        "home_adv": float(home_adv),
        "rho": rho,
        "n_matches": len(matches),
        "n_teams": n,
    }


def _gammaln(x):
    import numpy as np
    from scipy.special import gammaln
    return gammaln(x)
