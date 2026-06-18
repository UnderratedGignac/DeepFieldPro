"""
market_models.py — Probability engine for all betting markets.

Derives probabilities from Dixon-Coles expected goals (exp_h, exp_a).
Pure Python + math stdlib; no scipy dependency.

Markets covered:
  - Over/Under (any line: 0.5, 1.5, 2.0, 2.5, 3.0, 3.5, ...)
  - Asian Goal Lines (quarter lines: 2.25, 2.75, 3.25, ...)
  - Both Teams To Score (BTTS)
  - Double Chance (1X, X2, 12)
  - Draw No Bet (Home/Away)
  - Asian Handicap (any .0 or .5 line; quarter lines split)
  - Team Totals (per-team O/U)
  - 1X2 (re-derives from joint distribution for consistency)

All probability functions return fractions (0.0–1.0).
"""

import math

_MAX_GOALS = 10  # P(goals > 10) ≈ 0 for any realistic xG


def _pmf(lam: float, k: int) -> float:
    """Poisson PMF — P(X = k) for X ~ Poisson(lam)."""
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def _joint(exp_h: float, exp_a: float):
    """
    Dixon-Coles joint probability table P[h][a].
    Uses the DC low-score correction (rho = -0.1, a typical league average).
    Returns a (MAX+1) x (MAX+1) list-of-lists.
    """
    rho = -0.1
    table = []
    for h in range(_MAX_GOALS + 1):
        row = []
        for a in range(_MAX_GOALS + 1):
            p = _pmf(exp_h, h) * _pmf(exp_a, a)
            # DC correction on {0,1} x {0,1} joint cells
            if h == 0 and a == 0:
                p *= max(0.0, 1 - exp_h * exp_a * rho)
            elif h == 0 and a == 1:
                p *= max(0.0, 1 + exp_h * rho)
            elif h == 1 and a == 0:
                p *= max(0.0, 1 + exp_a * rho)
            elif h == 1 and a == 1:
                p *= max(0.0, 1 - rho)
            row.append(max(0.0, p))
        table.append(row)
    return table


def match_1x2(exp_h: float, exp_a: float) -> tuple:
    """Returns (p_home, p_draw, p_away) from DC joint distribution."""
    t = _joint(exp_h, exp_a)
    ph = sum(t[h][a] for h in range(_MAX_GOALS + 1) for a in range(_MAX_GOALS + 1) if h > a)
    px = sum(t[h][a] for h in range(_MAX_GOALS + 1) for a in range(_MAX_GOALS + 1) if h == a)
    pa = sum(t[h][a] for h in range(_MAX_GOALS + 1) for a in range(_MAX_GOALS + 1) if a > h)
    total = ph + px + pa or 1.0
    return ph / total, px / total, pa / total


def over_under(exp_h: float, exp_a: float, line: float) -> tuple:
    """
    Returns (p_over, p_under, p_push) for total goals vs a line.
    p_push is non-zero only for integer lines (e.g. 3.0).
    For .5 lines (2.5, 3.5): p_push = 0.
    """
    t = _joint(exp_h, exp_a)
    p_over = p_push = p_under = 0.0
    for h in range(_MAX_GOALS + 1):
        for a in range(_MAX_GOALS + 1):
            total = h + a
            p = t[h][a]
            if total > line:
                p_over += p
            elif total < line:
                p_under += p
            else:
                p_push += p
    return p_over, p_under, p_push


def asian_goal_line(exp_h: float, exp_a: float, line: float) -> dict:
    """
    Asian goal line — handles quarter lines (.25, .75) by splitting the stake.
    Returns {"over": p_eff_over, "under": p_eff_under}.
    On push (integer line exact): stake returned, treated as 0 net.

    Quarter-line interpretation (e.g. Over 2.75):
      Half stake at Over 2.5, half stake at Over 3.0.
      Net over payout = avg of both; push only on integer half.
    """
    frac = round((line % 1) * 4) % 4  # 0=.00, 1=.25, 2=.50, 3=.75

    if frac in (0, 2):  # standard integer or .5 line
        p_o, p_u, p_push = over_under(exp_h, exp_a, line)
        # Push: stake returned → treat as 0 net on that half
        eff_over = p_o  # push refunded, so effective win prob = p_over
        eff_under = p_u
        return {"over": eff_over, "under": eff_under, "push": p_push}

    # Quarter lines: split between floor .5-line and ceil .5-line
    lo = math.floor(line * 2) / 2   # nearest .0 or .5 below
    hi = lo + 0.5
    lo_r = asian_goal_line(exp_h, exp_a, lo)
    hi_r = asian_goal_line(exp_h, exp_a, hi)
    return {
        "over": (lo_r["over"] + hi_r["over"]) / 2,
        "under": (lo_r["under"] + hi_r["under"]) / 2,
        "push": 0.0,
    }


def btts(exp_h: float, exp_a: float) -> tuple:
    """Returns (p_yes, p_no) for Both Teams To Score."""
    t = _joint(exp_h, exp_a)
    p_yes = sum(t[h][a] for h in range(_MAX_GOALS + 1)
                for a in range(_MAX_GOALS + 1) if h >= 1 and a >= 1)
    return p_yes, 1.0 - p_yes


def double_chance(p_home: float, p_draw: float, p_away: float) -> dict:
    """
    Returns probabilities for Double Chance selections.
    1X = home or draw, X2 = draw or away, 12 = home or away.
    """
    return {
        "1X": p_home + p_draw,
        "X2": p_draw + p_away,
        "12": p_home + p_away,
    }


def draw_no_bet(p_home: float, p_away: float) -> dict:
    """
    DNB: draw is a push (stake returned). Effective win probability:
    P(home wins | not draw) = p_home / (p_home + p_away).
    """
    denom = p_home + p_away
    if denom <= 0:
        return {"Home": 0.5, "Away": 0.5}
    return {"Home": p_home / denom, "Away": p_away / denom}


def asian_handicap(exp_h: float, exp_a: float, line: float) -> dict:
    """
    Asian Handicap applied to the HOME team.
    Positive line = home receives goals (underdog), negative = home gives goals.
    E.g. line=-1 means home must win by 2+ to cover.

    Quarter lines (.25/.75): stake split between adjacent integer/.5 lines.
    Returns {"home": p_home_covers, "away": p_away_covers, "push": p_push}.
    """
    frac = round((abs(line) % 1) * 4) % 4

    if frac in (1, 3):  # quarter line
        lo = math.floor(line * 2) / 2
        hi = lo + (1 if line >= 0 else -1) * 0.5
        # Correct sign for negative quarter lines
        if line < 0:
            lo = math.ceil(line * 2) / 2
            hi = lo - 0.5
        lo_r = asian_handicap(exp_h, exp_a, lo)
        hi_r = asian_handicap(exp_h, exp_a, hi)
        return {
            "home": (lo_r["home"] + hi_r["home"]) / 2,
            "away": (lo_r["away"] + hi_r["away"]) / 2,
            "push": 0.0,
        }

    t = _joint(exp_h, exp_a)
    p_home = p_push = p_away = 0.0
    for h in range(_MAX_GOALS + 1):
        for a in range(_MAX_GOALS + 1):
            p = t[h][a]
            margin = (h - a) + line  # positive = home covers
            if margin > 0:
                p_home += p
            elif margin < 0:
                p_away += p
            else:
                p_push += p
    return {"home": p_home, "away": p_away, "push": p_push}


def team_total(exp: float, line: float) -> tuple:
    """
    Returns (p_over, p_under, p_push) for a single team's goals vs a line.
    E.g. team_total(exp_h=1.8, line=1.5) → P(home scores 2+).
    """
    p_over = p_push = p_under = 0.0
    for k in range(_MAX_GOALS + 1):
        p = _pmf(exp, k)
        if k > line:
            p_over += p
        elif k < line:
            p_under += p
        else:
            p_push += p
    return p_over, p_under, p_push
