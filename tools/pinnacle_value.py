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
from difflib import SequenceMatcher

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

# Common club name aliases that differ between Pinnacle and Betarabia/Sofascore
_TEAM_ALIASES = {
    "manchester city": "man city",
    "manchester united": "man utd",
    "nottingham forest": "nottm forest",
    "wolverhampton": "wolves",
    "tottenham hotspur": "tottenham",
    "atletico madrid": "atletico",
    "atlético madrid": "atletico",
    "paris saint-germain": "psg",
    "paris saint germain": "psg",
    "borussia dortmund": "dortmund",
    "bayer leverkusen": "leverkusen",
    "rb leipzig": "leipzig",
    "red bull leipzig": "leipzig",
    "internazionale": "inter",
    "inter milan": "inter",
    "ac milan": "milan",
    "as roma": "roma",
    "ss lazio": "lazio",
    "real madrid": "real madrid",
    "deportivo alaves": "alaves",
    "deportivo alavés": "alaves",
    "rcd espanyol": "espanyol",
    "cd leganes": "leganes",
    "united states": "usa",
    "new zealand": "new zealand",
}


def _normalize_team(name: str) -> str:
    """Normalize a team name for fuzzy matching.

    Strips punctuation, lowercases, removes common suffixes (FC, CF, SC, AFC, etc.),
    then applies known aliases so 'Manchester City' and 'Man City' collapse to the same key.
    """
    if not name:
        return ""
    n = name.lower().strip()
    # Remove punctuation except spaces
    for ch in ".,'-":
        n = n.replace(ch, " ")
    # Collapse multiple spaces
    n = " ".join(n.split())
    # Strip common club suffixes that differ between sources
    for suffix in (" fc", " cf", " sc", " afc", " fk", " sk", " bk", " if",
                   " united", " city", " town", " athletic", " wanderers",
                   " rovers", " hotspur", " albion"):
        if n.endswith(suffix):
            n = n[: -len(suffix)].rstrip()
            break
    # Apply alias table
    n = _TEAM_ALIASES.get(n, n)
    return n


def _fuzzy_match_ou25(home: str, away: str, candidates: dict, threshold: float = 0.72):
    """Find the best OU25 Pinnacle entry matching the given home/away names.

    candidates: dict keyed by "PinHome vs PinAway" → ou25_data
    Returns the matching ou25_data dict or None when no match is confident enough.
    Uses SequenceMatcher similarity on the normalised team pair string.
    """
    h_n = _normalize_team(home)
    a_n = _normalize_team(away)
    query = f"{h_n} vs {a_n}"

    best_score = 0.0
    best_val = None
    for key, val in candidates.items():
        parts = key.split(" vs ", 1)
        if len(parts) != 2:
            continue
        candidate = f"{_normalize_team(parts[0])} vs {_normalize_team(parts[1])}"
        score = SequenceMatcher(None, query, candidate).ratio()
        if score > best_score:
            best_score = score
            best_val = val

    return best_val if best_score >= threshold else None


def get_pinnacle_latest(home: str, away: str, selection: str, kickoff_ts=None):
    """
    Return latest Pinnacle snapshot for a match/selection.

    Returns dict with keys: devig_prob, decimal_odds, fair_odds, ts, snapshot_count
    or None if no match found or insufficient snapshots.
    """
    pin_sel = _SEL_MAP.get(selection, selection.lower())
    if not os.path.exists(_COMPLETED_DB):
        return None

    try:
        con = sqlite3.connect(_COMPLETED_DB, timeout=5)
        con.row_factory = sqlite3.Row

        h_norm = _normalize_team(home)
        a_norm = _normalize_team(away)

        # P4 FIX: Check snapshot count for data freshness.
        # Stale Pinnacle data on minor leagues produces phantom edges.
        # Need at least MIN_SNAPSHOTS for a reliable price.
        count_row = con.execute(
            "SELECT COUNT(*) as cnt FROM sharp_odds_history "
            "WHERE LOWER(REPLACE(REPLACE(home_team,'.',''),'-',' '))=? "
            "AND LOWER(REPLACE(REPLACE(away_team,'.',''),'-',' '))=?",
            (h_norm, a_norm),
        ).fetchone()
        snapshot_count = count_row["cnt"] if count_row else 0

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
            "snapshot_count": snapshot_count,
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
    min_snapshots: int = 10,
):
    """
    Returns (edge_pct, pinnacle_data) if Betarabia >= Pinnacle fair by min_edge.
    Returns (0.0, None) if no edge, no Pinnacle data, or insufficient snapshots.

    edge_pct > 0 means Betarabia is more generous than Pinnacle fair price.
    min_snapshots: minimum Pinnacle snapshots required for reliable price (P4 FIX).
    """
    if not betarabia_odds or betarabia_odds <= 1.0:
        return 0.0, None

    pin = get_pinnacle_latest(home, away, selection, kickoff_ts)
    if pin is None:
        return 0.0, None

    # P4 FIX: Reject if Pinnacle data is too stale (few snapshots).
    snap_count = pin.get("snapshot_count", 0)
    if snap_count < min_snapshots:
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


def check_ou25_value(
    home: str,
    away: str,
    selection: str,
    betarabia_odds: float,
    pinnacle_ou25_data: dict,
    min_edge: float = 0.03,
):
    """
    Returns (edge_pct, pin_data) if Betarabia O/U 2.5 odds beat Pinnacle fair by min_edge.

    pinnacle_ou25_data: dict from fetch_pinnacle_totals() for this match —
      {"over": float, "under": float, "p_over": float, "p_under": float}
    selection: "Over 2.5" or "Under 2.5"
    Returns (0.0, None) if no edge or missing data.
    """
    if not betarabia_odds or betarabia_odds <= 1.0:
        return 0.0, None
    if not pinnacle_ou25_data:
        return 0.0, None

    sel_lower = (selection or "").lower()
    if "over" in sel_lower:
        sel_key = "over"
    elif "under" in sel_lower:
        sel_key = "under"
    else:
        return 0.0, None

    pin_odds = pinnacle_ou25_data.get(sel_key)
    pin_prob = pinnacle_ou25_data.get(f"p_{sel_key}")
    if not pin_odds or not pin_prob or pin_prob <= 0:
        return 0.0, None

    fair_odds = 1.0 / pin_prob
    edge = betarabia_odds / fair_odds - 1.0
    if edge >= min_edge:
        return round(edge, 4), {
            "devig_prob": pin_prob,
            "decimal_odds": pin_odds,
            "fair_odds": round(fair_odds, 4),
        }
    return 0.0, None


def clv_from_pinnacle_ou25(home: str, away: str, selection: str, entry_odds: float):
    """
    Compute CLV for an O/U 2.5 bet using Pinnacle's stored snapshot.

    selection: "Over 2.5" | "Under 2.5" (or "over"/"under")
    Reads the latest sharp_odds_history row where selection is "over_2.5" or "under_2.5".
    Returns float CLV or None if no data.
    """
    sel_lower = (selection or "").lower()
    if "over" in sel_lower:
        pin_sel = "over_2.5"
    elif "under" in sel_lower:
        pin_sel = "under_2.5"
    else:
        return None

    if not os.path.exists(_COMPLETED_DB):
        return None

    try:
        con = sqlite3.connect(_COMPLETED_DB, timeout=5)
        con.row_factory = sqlite3.Row
        h_norm = _normalize_team(home)
        a_norm = _normalize_team(away)
        row = con.execute(
            "SELECT decimal_odds FROM sharp_odds_history "
            "WHERE LOWER(REPLACE(REPLACE(home_team,'.',''),'-',' '))=? "
            "AND LOWER(REPLACE(REPLACE(away_team,'.',''),'-',' '))=? "
            "AND selection=? ORDER BY ts DESC LIMIT 1",
            (h_norm, a_norm, pin_sel),
        ).fetchone()
        con.close()
        if not row:
            return None
        pin_odds = row["decimal_odds"]
        if not pin_odds or pin_odds <= 1.0:
            return None
        return round(entry_odds / pin_odds - 1.0, 4)
    except Exception:
        return None


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
