"""
worldcup_model.py — World Cup 2026 specialist prediction model.
Combines FIFA Elo ratings + squad quality + international-calibrated Poisson.
"""

import json
import math
import os
import time

MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "models")
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
MODEL_FILE = os.path.join(MODEL_DIR, "worldcup_model.json")

ELO_RATINGS = {
    "Argentina": 2144,
    "Spain": 2134,
    "France": 2090,
    "England": 2028,
    "Brazil": 2009,
    "Colombia": 1979,
    "Netherlands": 1968,
    "Portugal": 1960,
    "Germany": 1952,
    "Belgium": 1940,
    "Italy": 1930,
    "Croatia": 1910,
    "Uruguay": 1900,
    "Mexico": 1870,
    "Denmark": 1860,
    "Switzerland": 1848,
    "USA": 1838,
    "Japan": 1828,
    "Morocco": 1820,
    "Austria": 1810,
    "Senegal": 1805,
    "South Korea": 1800,
    "Turkey": 1792,
    "Serbia": 1778,
    "Ecuador": 1770,
    "Poland": 1760,
    "Scotland": 1755,
    "Ukraine": 1748,
    "Nigeria": 1740,
    "Paraguay": 1720,
    "Australia": 1710,
    "Ghana": 1705,
    "Sweden": 1700,
    "Tunisia": 1695,
    "Cameroon": 1685,
    "Ivory Coast": 1678,
    "Egypt": 1670,
    "Canada": 1660,
    "Iran": 1650,
    "Algeria": 1640,
    "Costa Rica": 1630,
    "Saudi Arabia": 1620,
    "South Africa": 1610,
    "Wales": 1598,
    "Norway": 1560,
    "Jamaica": 1580,
    "Honduras": 1570,
    "Panama": 1558,
    "Qatar": 1548,
    "United Arab Emirates": 1540,
    "Mali": 1530,
    "Uzbekistan": 1530,
    "Congo DR": 1520,
    "Jordan": 1520,
    "Curacao": 1510,
    "Bolivia": 1500,
    "New Zealand": 1490,
    "Cabo Verde": 1480,
    "Burkina Faso": 1470,
    "Czech Republic": 1750,
}

_ALIASES = {
    "usa": "USA",
    "united states": "USA",
    "america": "USA",
    "south korea": "South Korea",
    "korea republic": "South Korea",
    "korea": "South Korea",
    "republic of korea": "South Korea",
    "ivory coast": "Ivory Coast",
    "cote d'ivoire": "Ivory Coast",
    "south africa": "South Africa",
    "saudi arabia": "Saudi Arabia",
    "costa rica": "Costa Rica",
    "united arab emirates": "United Arab Emirates",
    "uae": "United Arab Emirates",
    "new zealand": "New Zealand",
    "cabo verde": "Cabo Verde",
    "cape verde": "Cabo Verde",
    "burkina faso": "Burkina Faso",
    "congo dr": "Congo DR",
    "dr congo": "Congo DR",
    "czech republic": "Czech Republic",
    "czechia": "Czech Republic",
}

AVG_GOALS_PER_TEAM = 1.275
ELO_TO_XG_SCALE = 0.0045
MAX_GOALS = 8

_squad_cache = {"ts": 0, "data": {}}
_SQUAD_TTL = 3600


def _norm(s):
    if not s:
        return ""
    return s.strip().lower().replace(".", "").replace("-", " ")


def _resolve(name):
    if not name:
        return None
    n = _norm(name)
    for canonical in ELO_RATINGS:
        if _norm(canonical) == n:
            return canonical
    if n in _ALIASES:
        return _ALIASES[n]
    for canonical in ELO_RATINGS:
        cn = _norm(canonical)
        if n in cn or cn in n:
            return canonical
        if len(n) >= 5 and len(cn) >= 5 and n[:5] == cn[:5]:
            return canonical
    return None


def _load_squad_quality():
    now = time.time()
    if _squad_cache["data"] and (now - _squad_cache["ts"]) < _SQUAD_TTL:
        return _squad_cache["data"]
    if os.path.exists(MODEL_FILE):
        try:
            with open(MODEL_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            _squad_cache["data"] = data.get("squad_quality", {})
            _squad_cache["ts"] = now
        except (OSError, ValueError):
            pass
    return _squad_cache["data"]


def _get_squad_quality(team_canonical):
    sq = _load_squad_quality()
    if team_canonical and team_canonical in sq:
        return sq[team_canonical]
    return {"g_p90": 0.0, "xg_p90": 0.0, "avg_fifa_rating": 0, "top_league_pct": 0.0}


def _poisson_pmf(lam, k):
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    try:
        return math.exp(-lam) * (lam**k) / math.factorial(k)
    except (OverflowError, ValueError):
        return 0.0


def _dixon_coles_tau(h, a, lam, mu, rho):
    if h == 0 and a == 0:
        return max(0.0, 1.0 - lam * mu * rho)
    if h == 0 and a == 1:
        return max(0.0, 1.0 + lam * rho)
    if h == 1 and a == 0:
        return max(0.0, 1.0 + mu * rho)
    if h == 1 and a == 1:
        return max(0.0, 1.0 - rho)
    return 1.0


def _poisson_1x2(lam_h, lam_a, rho=-0.08):
    p_h = p_d = p_a = 0.0
    for i in range(MAX_GOALS + 1):
        for j in range(MAX_GOALS + 1):
            p = _poisson_pmf(lam_h, i) * _poisson_pmf(lam_a, j)
            tau = _dixon_coles_tau(i, j, lam_h, lam_a, rho)
            p *= max(0.0, tau)
            if i > j:
                p_h += p
            elif i == j:
                p_d += p
            else:
                p_a += p
    total = p_h + p_d + p_a
    if total <= 0:
        return 0.4, 0.3, 0.3
    return p_h / total, p_d / total, p_a / total


def _expected_goals(elo_h, elo_a, sq_h, sq_a, is_host=False):
    elo_diff = elo_h - elo_a
    base_h = AVG_GOALS_PER_TEAM + ELO_TO_XG_SCALE * elo_diff
    base_a = AVG_GOALS_PER_TEAM - ELO_TO_XG_SCALE * elo_diff
    sq_diff = (sq_h.get("g_p90", 1.0) - sq_a.get("g_p90", 1.0)) * 0.08
    base_h += sq_diff
    base_a -= sq_diff
    fr_h = sq_h.get("avg_fifa_rating", 75)
    fr_a = sq_a.get("avg_fifa_rating", 75)
    if fr_h > 0 and fr_a > 0:
        fr_diff = (fr_h - fr_a) * 0.005
        base_h += fr_diff
        base_a -= fr_diff
    if is_host:
        base_h += 0.12
    base_h = max(0.30, min(3.50, base_h))
    base_a = max(0.30, min(3.50, base_a))
    return round(base_h, 3), round(base_a, 3)


def predict(home_name, away_name, verbose=False):
    h_team = _resolve(home_name)
    a_team = _resolve(away_name)
    if not h_team and not a_team:
        return None
    elo_h = ELO_RATINGS.get(h_team, 1600) if h_team else 1600
    elo_a = ELO_RATINGS.get(a_team, 1600) if a_team else 1600
    sq_h = _get_squad_quality(h_team)
    sq_a = _get_squad_quality(a_team)
    exp_h, exp_a = _expected_goals(elo_h, elo_a, sq_h, sq_a)
    p_h, p_d, p_a = _poisson_1x2(exp_h, exp_a)
    if verbose:
        print(
            f"[WC] {home_name} ({h_team}, Elo {elo_h}) vs "
            f"{away_name} ({a_team}, Elo {elo_a})"
        )
        print(f"[WC] xG: {exp_h:.2f} vs {exp_a:.2f}")
        print(f"[WC] Probs: H={p_h:.3f} D={p_d:.3f} A={p_a:.3f}")
    return {"home": round(p_h, 4), "draw": round(p_d, 4), "away": round(p_a, 4)}


def blend_with_sportmonks(wc_probs, sportmonks_probs, wc_weight=0.65):
    if not wc_probs or not sportmonks_probs:
        return wc_probs or sportmonks_probs
    sw = 1.0 - wc_weight
    blended = {}
    for key in ("home", "draw", "away"):
        wp = wc_probs.get(key, 1 / 3)
        sp = sportmonks_probs.get(key, 1 / 3)
        blended[key] = round(wc_weight * wp + sw * sp, 4)
    total = sum(blended.values()) or 1.0
    return {k: round(v / total, 4) for k, v in blended.items()}


def get_all_ratings():
    return dict(sorted(ELO_RATINGS.items(), key=lambda x: -x[1]))


def get_team_info(team_name):
    canonical = _resolve(team_name)
    if not canonical:
        return None
    return {
        "name": canonical,
        "elo": ELO_RATINGS.get(canonical, 0),
        "squad_quality": _get_squad_quality(canonical),
    }
