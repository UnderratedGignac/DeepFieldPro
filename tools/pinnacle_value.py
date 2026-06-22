"""
pinnacle_value.py — Live Pinnacle vs soft-book value detector.

Strategy (documented ROI 3-7%):
  Compare current Betarabia odds to de-vigged Pinnacle fair price.
  When Betarabia is >= pinnacle_fair * (1 + min_edge), place a PINNACLE_VALUE bet.

This is the most evidence-backed profitable strategy in sports betting:
  - Individual books are NOT efficient relative to Pinnacle (Forrest & Simmons 2000)
  - Soft book value vs Pinnacle: 3-7% ROI (professional bettor documented results)
  - CLV from this approach is provably positive when it fires
"""

import math
import os
import sqlite3

_COMPLETED_DB = os.path.join(
    os.path.dirname(__file__), "..", "data", "deepfield_browser_data", "completed_fixtures.db"
)

# Map daemon selection labels → Pinnacle selection strings
_SEL_MAP = {
    "Home (1)": "home",
    "Draw (X)": "draw",
    "Away (2)": "away",
    "home": "home",
    "draw": "draw",
    "away": "away",
    "1": "home",
    "X": "draw",
    "2": "away",
}


def _normalize_team(name: str) -> str:
    return (name or "").lower().strip().replace(".", "").replace("-", " ")


def get_pinnacle_latest(home: str, away: str, selection: str, kickoff_ts=None):
    """
    Return latest Pinnacle snapshot for a match/selection.

    Returns dict with keys: devig_prob, decimal_odds, fair_odds, ts
    or None if no match found.
    """
    pin_sel = _SEL_MAP.get(selection, selection.lower())
    if not os.path.exists(_COMPLETED_DB):
        return None

    try:
        con = sqlite3.connect(_COMPLETED_DB, timeout=5)
        con.row_factory = sqlite3.Row

        h_norm = _normalize_team(home)
        a_norm = _normalize_team(away)

        # Try exact match first, then partial
        queries = [
            (
                "SELECT devig_prob, decimal_odds, ts FROM sharp_odds_history "
                "WHERE LOWER(REPLACE(REPLACE(home_team,'.',''),'-',' '))=? "
                "AND LOWER(REPLACE(REPLACE(away_team,'.',''),'-',' '))=? "
                "AND selection=? ORDER BY ts DESC LIMIT 1"
            ),
        ]
        # Add kickoff filter if provided
        if kickoff_ts:
            queries.append(
                "SELECT devig_prob, decimal_odds, ts FROM sharp_odds_history "
                "WHERE LOWER(REPLACE(REPLACE(home_team,'.',''),'-',' '))=? "
                "AND LOWER(REPLACE(REPLACE(away_team,'.',''),'-',' '))=? "
                "AND selection=? "
                "AND starts_ts BETWEEN ? AND ? ORDER BY ts DESC LIMIT 1"
            )

        row = None
        row = con.execute(queries[0], (h_norm, a_norm, pin_sel)).fetchone()
        if not row and kickoff_ts:
            row = con.execute(
                queries[1] if len(queries) > 1 else queries[0],
                (h_norm, a_norm, pin_sel, kickoff_ts - 7200, kickoff_ts + 3600),
            ).fetchone()

        con.close()
        if not row:
            return None

        devig_prob = row["devig_prob"]
        if not devig_prob or devig_prob <= 0:
            return None

        return {
            "devig_prob": devig_prob,
            "decimal_odds": row["decimal_odds"],
            "fair_odds": 1.0 / devig_prob,
            "ts": row["ts"],
        }
    except Exception:
        return None


def check_value(
    home: str,
    away: str,
    selection: str,
    betarabia_odds: float,
    kickoff_ts=None,
    min_edge: float = 0.03,
):
    """
    Returns (edge_pct, pinnacle_data) if Betarabia >= Pinnacle fair by min_edge.
    Returns (0.0, None) if no edge or no Pinnacle data.

    edge_pct > 0 means Betarabia is more generous than Pinnacle fair price.
    """
    if not betarabia_odds or betarabia_odds <= 1.0:
        return 0.0, None

    pin = get_pinnacle_latest(home, away, selection, kickoff_ts)
    if pin is None:
        return 0.0, None

    edge = betarabia_odds / pin["fair_odds"] - 1.0
    if edge >= min_edge:
        return round(edge, 4), pin
    return 0.0, None


def kelly_stake(edge: float, odds: float, kelly_frac: float = 0.2) -> float:
    """
    Fractional Kelly stake as a fraction of bankroll.
    edge = betarabia_odds / fair_odds - 1
    p = fair probability (1/fair_odds)
    Kelly = (p * odds - 1) / (odds - 1) * frac
    """
    if odds <= 1.0 or edge <= 0:
        return 0.0
    # Work backwards: devig_prob = 1 / fair_odds = 1 / (betarabia_odds / (1+edge))
    fair_odds = odds / (1.0 + edge) if edge > 0 else odds
    p = 1.0 / fair_odds
    b = odds - 1.0  # net odds
    k = (p * odds - 1.0) / b
    return max(0.0, min(k * kelly_frac, 0.10))  # cap at 10% bankroll


def clv_from_pinnacle(home: str, away: str, selection: str, entry_odds: float):
    """
    Compute CLV = entry_odds / pinnacle_current_odds - 1.
    Called at settlement time to record how much we beat the closing line.
    Returns float or None.
    """
    pin = get_pinnacle_latest(home, away, selection)
    if pin is None:
        return None
    if not pin["decimal_odds"] or pin["decimal_odds"] <= 1.0:
        return None
    return round(entry_odds / pin["decimal_odds"] - 1.0, 4)
