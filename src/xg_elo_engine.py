"""
xg_elo_engine.py — xG-Elo Divergence Strategy

SCIENTIFIC BASIS:
  Teams are rated by Expected Goals differentials (xG-for − xG-against)
  rather than actual match results. This normalises luck: a team that
  dominates every game (high xG) but loses 3 in a row due to bad finishing
  will be correctly rated STRONG, while a "lucky winner" will be correctly
  rated WEAK.

  When the xG-Elo rating diverges significantly from a team's results-based
  standing (and from the market's implied probability), value exists on the
  underrated team. This gap historically closes over 4–6 weeks.

  Edge mechanism: Market prices recent RESULTS (visible to public).
  This model prices recent PROCESS (xG, invisible to casual bettors).

MATHEMATICAL FRAMEWORK:
  Standard Elo update:
    R_new = R_old + K × (outcome − expected_outcome)
    expected_outcome = 1 / (1 + 10^((R_opp − R_home) / 400))

  xG-Elo: replace binary `outcome` with a continuous xG margin signal:
    outcome_xg = sigmoid(xG_margin / σ)       where σ = 1.5 (normalization)
    R_new = R_old + K × (outcome_xg − expected_outcome)

  This means a 0-1 loss where home xG was 2.8 vs 0.3 leads to a rating
  INCREASE for the home team (they played better than the result shows).

DIVERGENCE SIGNAL:
  When xG-Elo predicts team win probability P_model and
  Betarabia/Pinnacle implies P_market, and:
    Edge = P_model − P_market > threshold (default: 7%)
  → fire a value bet on that team.

DATA SOURCE:
  Reads xg_history.db (populated by the existing xG data pipeline).
  Falls back gracefully to no-signal when data is insufficient.
"""

import os
import math
import sqlite3
import logging
import datetime
from typing import Optional, Tuple, Dict, Any

logger = logging.getLogger(__name__)

_DB = os.path.join(os.path.dirname(__file__), "..", "data", "xg_history.db")
_HISTORY_DB = os.path.join(os.path.dirname(__file__), "..", "data", "history.db")

# ── Elo parameters ──────────────────────────────────────────────────────────
_K = 24          # learning rate (standard for club soccer)
_HOME_ADV = 55   # home team gets a +55 Elo point advantage for expected calc
_INIT_RATING = 1500
_SIGMA = 1.5     # xG margin normalisation factor (1.5 goals = ~0.5 sigmoid)
_DECAY = 0.97    # per-match time-decay applied to old ratings

# ── Strategy parameters ─────────────────────────────────────────────────────
_MIN_MATCHES = 6      # need at least 6 matches before trusting a rating
_MIN_EDGE_PCT = 7.0   # minimum edge % to fire a bet (P_model - P_market)
_MAX_EDGE_PCT = 35.0  # cap: edges above this are almost certainly bad data

# ── In-memory rating store ──────────────────────────────────────────────────
# {team_name_lower: {"rating": float, "n": int, "last_xg_for": float, "last_xg_against": float}}
_RATINGS: Dict[str, Dict] = {}
_RATINGS_LOADED = False


# ─────────────────────────────────────────────────────────────────────────────
# Elo maths
# ─────────────────────────────────────────────────────────────────────────────

def _expected(r_a: float, r_b: float, home_adv: bool = False) -> float:
    """Standard Elo expected outcome for team A vs B."""
    adv = _HOME_ADV if home_adv else 0
    return 1.0 / (1.0 + 10 ** ((r_b - r_a - adv) / 400.0))


def _sigmoid(x: float, sigma: float = _SIGMA) -> float:
    """Map xG margin to [0, 1] outcome signal (continuous replacement for W/L/D)."""
    return 1.0 / (1.0 + math.exp(-x / sigma))


def _update_ratings(home: str, away: str, xg_h: float, xg_a: float):
    """Update xG-Elo ratings for both teams after a match."""
    global _RATINGS
    h = home.lower().strip()
    a = away.lower().strip()

    r_h = _RATINGS.get(h, {}).get("rating", _INIT_RATING)
    r_a = _RATINGS.get(a, {}).get("rating", _INIT_RATING)
    n_h = _RATINGS.get(h, {}).get("n", 0)
    n_a = _RATINGS.get(a, {}).get("n", 0)

    # Time decay: pull ratings slightly toward mean between matches
    r_h = _INIT_RATING + (r_h - _INIT_RATING) * _DECAY
    r_a = _INIT_RATING + (r_a - _INIT_RATING) * _DECAY

    # Expected outcomes
    exp_h = _expected(r_h, r_a, home_adv=True)
    exp_a = 1.0 - exp_h

    # Actual xG-based outcome signals
    xg_margin = (xg_h or 0.0) - (xg_a or 0.0)
    out_h = _sigmoid(xg_margin)
    out_a = 1.0 - out_h

    # Update
    new_r_h = r_h + _K * (out_h - exp_h)
    new_r_a = r_a + _K * (out_a - exp_a)

    _RATINGS[h] = {
        "rating": round(new_r_h, 2),
        "n": n_h + 1,
        "last_xg_for": round(xg_h or 0.0, 3),
        "last_xg_against": round(xg_a or 0.0, 3),
    }
    _RATINGS[a] = {
        "rating": round(new_r_a, 2),
        "n": n_a + 1,
        "last_xg_for": round(xg_a or 0.0, 3),
        "last_xg_against": round(xg_h or 0.0, 3),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Data loading
# ─────────────────────────────────────────────────────────────────────────────

def _load_ratings_from_xg_db():
    """
    Load all historical xG data from xg_history.db and replay to build ratings.
    Called once at startup; subsequent matches update ratings incrementally.
    """
    global _RATINGS, _RATINGS_LOADED
    if _RATINGS_LOADED:
        return

    if not os.path.exists(_DB):
        logger.debug("[XG-ELO] xg_history.db not found — ratings will build incrementally")
        _RATINGS_LOADED = True
        return

    try:
        conn = sqlite3.connect(_DB)
        cur = conn.cursor()
        # Expect columns: home_team, away_team, xg_home, xg_away, match_date
        # Try multiple possible table/column configurations
        tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        if not tables:
            conn.close()
            _RATINGS_LOADED = True
            return

        # Try the most common schema first
        loaded = False
        for tbl in tables:
            try:
                cols = [r[1].lower() for r in cur.execute(f"PRAGMA table_info({tbl})").fetchall()]
                # Need at minimum home, away, and two xg columns
                home_col = next((c for c in cols if "home" in c and "team" in c), None)
                away_col = next((c for c in cols if "away" in c and "team" in c), None)
                xgh_col  = next((c for c in cols if "xg" in c and "home" in c), None) or \
                           next((c for c in cols if c in ("xgh", "home_xg", "xg_h")), None)
                xga_col  = next((c for c in cols if "xg" in c and "away" in c), None) or \
                           next((c for c in cols if c in ("xga", "away_xg", "xg_a")), None)
                date_col = next((c for c in cols if "date" in c or "time" in c), None)

                if home_col and away_col and xgh_col and xga_col:
                    order_clause = f"ORDER BY {date_col} ASC" if date_col else ""
                    rows = cur.execute(
                        f"SELECT {home_col}, {away_col}, {xgh_col}, {xga_col} "
                        f"FROM {tbl} WHERE {xgh_col} IS NOT NULL AND {xga_col} IS NOT NULL "
                        f"{order_clause} LIMIT 50000"
                    ).fetchall()
                    for home, away, xgh, xga in rows:
                        if home and away:
                            _update_ratings(str(home), str(away), float(xgh or 0), float(xga or 0))
                    logger.info(f"[XG-ELO] Loaded {len(rows)} matches from {tbl} → {len(_RATINGS)} teams rated")
                    loaded = True
                    break
            except Exception as e:
                logger.debug(f"[XG-ELO] Skipping table {tbl}: {e}")
                continue

        conn.close()
        if not loaded:
            logger.debug("[XG-ELO] No compatible xG table found — will build from live data")
    except Exception as e:
        logger.warning(f"[XG-ELO] Could not load ratings: {e}")

    _RATINGS_LOADED = True


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def get_ratings(home_team: str, away_team: str) -> Tuple[Optional[Dict], Optional[Dict]]:
    """
    Return (home_rating_dict, away_rating_dict) or (None, None) if insufficient data.
    Each dict: {"rating": float, "n": int, "last_xg_for": float, "last_xg_against": float}
    """
    _load_ratings_from_xg_db()
    h = _RATINGS.get(home_team.lower().strip())
    a = _RATINGS.get(away_team.lower().strip())
    return h, a


def win_probability(home_team: str, away_team: str) -> Dict[str, Any]:
    """
    Returns model-derived match probabilities using xG-Elo ratings.

    Returns:
        {
            "home_win_prob": float,       # 0-100 %
            "away_win_prob": float,       # 0-100 %
            "draw_prob":     float,       # 0-100 %
            "home_rating":   float,
            "away_rating":   float,
            "home_n":        int,         # matches rated
            "away_n":        int,
            "confidence":    float,       # 0-1: low if few matches
            "valid":         bool,
        }
    """
    _load_ratings_from_xg_db()
    h_data, a_data = get_ratings(home_team, away_team)

    base = {
        "home_win_prob": 45.0, "away_win_prob": 30.0, "draw_prob": 25.0,
        "home_rating": _INIT_RATING, "away_rating": _INIT_RATING,
        "home_n": 0, "away_n": 0, "confidence": 0.0, "valid": False,
    }

    if not h_data or not a_data:
        return base
    if h_data["n"] < _MIN_MATCHES or a_data["n"] < _MIN_MATCHES:
        base["home_n"] = h_data.get("n", 0)
        base["away_n"] = a_data.get("n", 0)
        return base

    r_h = h_data["rating"]
    r_a = a_data["rating"]

    # Expected outcome for home team (includes home advantage)
    exp_h = _expected(r_h, r_a, home_adv=True)

    # Convert to 1X2 probabilities using a draw model
    # Standard approximation: draw prob ≈ 25% − 10% × |exp_h − 0.5|
    draw_adj = 0.25 - 0.10 * abs(exp_h - 0.5)
    draw_adj = max(0.10, min(0.30, draw_adj))
    home_win = exp_h * (1 - draw_adj)
    away_win = (1 - exp_h) * (1 - draw_adj)
    # Normalise to sum = 1.0
    total = home_win + away_win + draw_adj
    home_win /= total
    away_win /= total
    draw_p   = draw_adj / total

    confidence = min(1.0, (h_data["n"] + a_data["n"]) / 60.0)

    return {
        "home_win_prob": round(home_win * 100, 2),
        "away_win_prob": round(away_win * 100, 2),
        "draw_prob":     round(draw_p * 100, 2),
        "home_rating":   r_h,
        "away_rating":   r_a,
        "home_n":        h_data["n"],
        "away_n":        a_data["n"],
        "confidence":    round(confidence, 3),
        "valid":         True,
    }


def compute_edge(
    home_team: str,
    away_team: str,
    market: str,
    selection: str,
    market_odds: float,
) -> Dict[str, Any]:
    """
    Core edge computation: model probability vs. market implied probability.

    Returns:
        {
            "edge_pct":    float,     # positive = value bet
            "model_prob":  float,     # 0-100 %
            "market_prob": float,     # 0-100 %
            "fair_odds":   float,
            "confidence":  float,
            "valid":       bool,
            "signal":      str,       # human-readable reason
        }
    """
    probs = win_probability(home_team, away_team)
    if not probs["valid"]:
        return {"edge_pct": 0.0, "valid": False, "signal": "insufficient_data"}

    # Map market selection to model probability
    sel_lower = selection.lower()
    if "(1)" in selection or "home" in sel_lower:
        model_prob = probs["home_win_prob"]
    elif "(2)" in selection or "away" in sel_lower:
        model_prob = probs["away_win_prob"]
    elif "draw" in sel_lower or "(x)" in sel_lower:
        model_prob = probs["draw_prob"]
    else:
        return {"edge_pct": 0.0, "valid": False, "signal": "unknown_market"}

    if market_odds <= 1.0:
        return {"edge_pct": 0.0, "valid": False, "signal": "invalid_odds"}

    market_prob = 100.0 / market_odds   # implied probability (ignores vig)
    edge_pct = model_prob - market_prob  # positive = model says more likely than priced

    fair_odds = round(100.0 / model_prob, 3) if model_prob > 0 else 99.0

    signal = (
        f"xG-Elo: {home_team} {probs['home_rating']:.0f} vs "
        f"{away_team} {probs['away_rating']:.0f} | "
        f"model={model_prob:.1f}% market={market_prob:.1f}% edge={edge_pct:+.1f}%"
    )

    return {
        "edge_pct":   round(edge_pct, 2),
        "model_prob": round(model_prob, 2),
        "market_prob": round(market_prob, 2),
        "fair_odds":  fair_odds,
        "confidence": probs["confidence"],
        "home_rating": probs["home_rating"],
        "away_rating": probs["away_rating"],
        "home_n":     probs["home_n"],
        "away_n":     probs["away_n"],
        "valid":      True,
        "signal":     signal,
    }


def update_from_result(
    home_team: str, away_team: str, xg_home: float, xg_away: float
):
    """
    Called after a match settles to update xG-Elo ratings.
    Integrated into the settlement pipeline.
    """
    _load_ratings_from_xg_db()
    _update_ratings(home_team, away_team, xg_home, xg_away)
    logger.info(
        f"[XG-ELO] Updated: {home_team} xG={xg_home:.2f} / {away_team} xG={xg_away:.2f} | "
        f"H-rating={_RATINGS.get(home_team.lower(), {}).get('rating', '?'):.0f} "
        f"A-rating={_RATINGS.get(away_team.lower(), {}).get('rating', '?'):.0f}"
    )


def is_value_bet(
    home_team: str,
    away_team: str,
    market: str,
    selection: str,
    market_odds: float,
    min_edge_pct: float = _MIN_EDGE_PCT,
    min_confidence: float = 0.25,
) -> Tuple[bool, Dict[str, Any]]:
    """
    High-level entry point: returns (True/False, edge_info).
    Use this in the daemon sweep to check each fixture.
    """
    result = compute_edge(home_team, away_team, market, selection, market_odds)
    if not result.get("valid"):
        return False, result

    edge = result["edge_pct"]
    confidence = result["confidence"]

    # Reject if edge is too small or implausibly large (data error)
    if edge < min_edge_pct or edge > _MAX_EDGE_PCT:
        return False, result

    # Reject if we don't have enough data to trust the rating
    if confidence < min_confidence:
        return False, result

    return True, result


def top_rated_teams(n: int = 20) -> list:
    """Return the n highest-rated teams (for dashboard display)."""
    _load_ratings_from_xg_db()
    rated = [(k, v) for k, v in _RATINGS.items() if v["n"] >= _MIN_MATCHES]
    return sorted(rated, key=lambda x: x[1]["rating"], reverse=True)[:n]


def rating_summary() -> Dict[str, Any]:
    """Summary stats for dashboard / health check."""
    _load_ratings_from_xg_db()
    eligible = [v for v in _RATINGS.values() if v["n"] >= _MIN_MATCHES]
    return {
        "total_teams":    len(_RATINGS),
        "eligible_teams": len(eligible),
        "loaded":         _RATINGS_LOADED,
        "top5": [
            {"team": k, **v}
            for k, v in sorted(_RATINGS.items(), key=lambda x: x[1]["rating"], reverse=True)[:5]
        ],
    }
