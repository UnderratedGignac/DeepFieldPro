"""
bet_timing.py — Optimal bet timing signal filter.
=================================================
Research shows that the best time to bet is:
  1. EARLY: within 6-12 hours after Pinnacle opens the market
     (soft books haven't adjusted yet → maximum edge)
  2. NOT TOO CLOSE TO KICKOFF: within 2 hours of kickoff, prices are efficient
     (all information is already priced in → no edge)
  3. AFTER LINEUP CONFIRMATION: if possible, bet after lineups are out
     (reduces uncertainty, but edges may have already moved)

This module provides:
  - is_good_time_to_bet(fixture_id, kickoff_time) → bool
  - get_timing_score(fixture_id, kickoff_time) → int (0-100)
  - get_timing_recommendation(fixture_id, kickoff_time) → str

Research basis:
  - OddsIndex (2025): "Sharp money moves lines within 24-48 hours of opening"
  - Boyd's Bets: "Opening lines are less refined and more likely to contain errors"
  - Pinnacle: "Closing line is the most efficient price — hard to beat after close"
"""

import os
import sqlite3
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
COMPLETED_DB = os.path.join(DATA_DIR, "deepfield_browser_data", "completed_fixtures.db")

# Cache for timing results (2-minute TTL)
_CACHE: dict = {}
_TTL = 120


def _get_first_pinnacle_snapshot(fixture_id: int, home: str = "", away: str = "") -> Optional[datetime]:
    """Get the timestamp of the first Pinnacle snapshot for a fixture.

    This tells us when the market opened — the earlier we bet after this,
    the more edge we capture from soft books' slow adjustment.
    """
    if not os.path.exists(COMPLETED_DB):
        return None

    try:
        con = sqlite3.connect(COMPLETED_DB, timeout=5)
        con.row_factory = sqlite3.Row

        # Try by fixture_id first
        if fixture_id:
            row = con.execute(
                "SELECT MIN(ts) as first_ts FROM sharp_odds_history "
                "WHERE fixture_id=?",
                (str(fixture_id),)
            ).fetchone()
            if row and row["first_ts"]:
                con.close()
                try:
                    return datetime.fromisoformat(row["first_ts"].replace("Z", "+00:00"))
                except Exception:
                    return None

        # Fall back to team name matching
        if home and away:
            from tools.pinnacle_value import _normalize_team
            h_norm = _normalize_team(home)
            a_norm = _normalize_team(away)
            row = con.execute(
                "SELECT MIN(ts) as first_ts FROM sharp_odds_history "
                "WHERE LOWER(REPLACE(REPLACE(home_team,'.',''),'-',' '))=? "
                "AND LOWER(REPLACE(REPLACE(away_team,'.',''),'-',' '))=?",
                (h_norm, a_norm)
            ).fetchone()
            if row and row["first_ts"]:
                con.close()
                try:
                    return datetime.fromisoformat(row["first_ts"].replace("Z", "+00:00"))
                except Exception:
                    return None

        con.close()
        return None
    except Exception as e:
        logger.debug(f"[BET_TIMING] Error getting first snapshot: {e}")
        return None


def _get_pinnacle_snapshot_count(fixture_id: int = None, home: str = "", away: str = "") -> int:
    """Get the total number of Pinnacle snapshots for a fixture.

    More snapshots = more reliable price = better timing signal.
    """
    if not os.path.exists(COMPLETED_DB):
        return 0

    try:
        con = sqlite3.connect(COMPLETED_DB, timeout=5)
        if fixture_id:
            row = con.execute(
                "SELECT COUNT(*) as cnt FROM sharp_odds_history WHERE fixture_id=?",
                (str(fixture_id),)
            ).fetchone()
        elif home and away:
            from tools.pinnacle_value import _normalize_team
            h_norm = _normalize_team(home)
            a_norm = _normalize_team(away)
            row = con.execute(
                "SELECT COUNT(*) as cnt FROM sharp_odds_history "
                "WHERE LOWER(REPLACE(REPLACE(home_team,'.',''),'-',' '))=? "
                "AND LOWER(REPLACE(REPLACE(away_team,'.',''),'-',' '))=?",
                (h_norm, a_norm)
            ).fetchone()
        else:
            con.close()
            return 0

        con.close()
        return row[0] if row else 0
    except Exception:
        return 0


def get_timing_score(
    fixture_id: Optional[int] = None,
    kickoff_time: Optional[datetime] = None,
    home: str = "",
    away: str = "",
    min_hours_before: float = 2.0,
    max_hours_after_open: float = 48.0,
    optimal_window_hours: float = 12.0,
) -> dict:
    """Compute a timing quality score for a bet.

    Args:
        fixture_id: Fixture ID for Pinnacle lookup
        kickoff_time: Match kickoff time (UTC)
        home, away: Team names (fallback for lookup)
        min_hours_before: Don't bet closer than this to kickoff
        max_hours_after_open: Don't bet later than this after market opens
        optimal_window_hours: Ideal time after market opens to bet

    Returns:
        {
            "score": int,              # 0-100 timing quality (higher = better time to bet)
            "recommendation": str,     # "BET NOW", "WAIT", "TOO LATE", "UNKNOWN"
            "hours_to_kickoff": float, # hours until match starts
            "hours_since_open": float, # hours since Pinnacle opened market
            "is_in_window": bool,      # True if currently in optimal betting window
            "details": str,            # human-readable explanation
        }
    """
    cache_key = f"timing_{fixture_id}_{home}_{away}"
    now = datetime.now(timezone.utc)
    cached = _CACHE.get(cache_key)
    if cached and (now.timestamp() - cached[0]) < _TTL:
        return cached[1]

    result = {
        "score": 50,
        "recommendation": "UNKNOWN",
        "hours_to_kickoff": None,
        "hours_since_open": None,
        "is_in_window": False,
        "details": "Insufficient timing data",
    }

    # Compute hours to kickoff
    if kickoff_time:
        if kickoff_time.tzinfo is None:
            kickoff_time = kickoff_time.replace(tzinfo=timezone.utc)
        hours_to_ko = (kickoff_time - now).total_seconds() / 3600
        result["hours_to_kickoff"] = round(hours_to_ko, 1)

        # TOO LATE: within 2 hours of kickoff — prices are efficient
        if hours_to_ko < min_hours_before:
            result["score"] = 10
            result["recommendation"] = "TOO LATE"
            result["details"] = (
                f"Match in {hours_to_ko:.1f}h — prices are efficient within "
                f"{min_hours_before}h of kickoff. Wait for next match."
            )
            _CACHE[cache_key] = (now.timestamp(), result)
            return result

        # TOO EARLY: match is days away — not enough market data
        if hours_to_ko > 72:
            result["score"] = 30
            result["recommendation"] = "WAIT"
            result["details"] = f"Match in {hours_to_ko:.0f}h — market may not be fully formed yet."
            _CACHE[cache_key] = (now.timestamp(), result)
            return result

    # Get first Pinnacle snapshot
    first_snap = _get_first_pinnacle_snapshot(fixture_id or 0, home, away)
    if first_snap:
        if first_snap.tzinfo is None:
            first_snap = first_snap.replace(tzinfo=timezone.utc)
        hours_since_open = (now - first_snap).total_seconds() / 3600
        result["hours_since_open"] = round(hours_since_open, 1)

        # EXPIRED: market has been open too long — edge likely gone
        if hours_since_open > max_hours_after_open:
            result["score"] = 20
            result["recommendation"] = "EXPIRED"
            result["details"] = (
                f"Market open {hours_since_open:.0f}h — soft books likely adjusted. "
                f"Edge window closed."
            )
            _CACHE[cache_key] = (now.timestamp(), result)
            return result

        # OPTIMAL WINDOW: 2-12 hours after market opens
        if 2 <= hours_since_open <= optimal_window_hours:
            # This is the sweet spot — soft books are still stale
            score = 90
            if hours_since_open < 6:
                score = 95  # Early edge window (highest value)
            elif hours_since_open < 12:
                score = 85  # Still good but edge may be shrinking
            result["score"] = score
            result["recommendation"] = "BET NOW"
            result["is_in_window"] = True
            result["details"] = (
                f"Market open {hours_since_open:.0f}h — optimal betting window. "
                f"Soft books haven't fully adjusted to Pinnacle's sharp price."
            )
            _CACHE[cache_key] = (now.timestamp(), result)
            return result

        # LATE WINDOW: 12-24 hours after open — some edge may remain
        if optimal_window_hours < hours_since_open <= 24:
            result["score"] = 60
            result["recommendation"] = "CONSIDER"
            result["is_in_window"] = False
            result["details"] = (
                f"Market open {hours_since_open:.0f}h — past optimal window but "
                f"some edge may remain on slow-to-update soft books."
            )
            _CACHE[cache_key] = (now.timestamp(), result)
            return result

    # DEFAULT: we have kickoff info but no Pinnacle data
    if kickoff_time and result["hours_to_kickoff"] is not None:
        if 4 <= result["hours_to_kickoff"] <= 48:
            result["score"] = 70
            result["recommendation"] = "BET NOW"
            result["is_in_window"] = True
            result["details"] = (
                f"Match in {result['hours_to_kickoff']:.0f}h — reasonable betting window "
                f"even without Pinnacle timing data."
            )
        else:
            result["score"] = 40
            result["recommendation"] = "WAIT"
            result["details"] = (
                f"Match in {result['hours_to_kickoff']:.0f}h — timing not optimal."
            )

    _CACHE[cache_key] = (now.timestamp(), result)
    return result


def is_good_time_to_bet(
    fixture_id: Optional[int] = None,
    kickoff_time: Optional[datetime] = None,
    home: str = "",
    away: str = "",
    min_score: int = 50,
) -> bool:
    """Quick boolean check: is this a good time to bet?

    Returns True if the timing score >= min_score (default 50).
    """
    timing = get_timing_score(fixture_id, kickoff_time, home, away)
    return timing["score"] >= min_score
