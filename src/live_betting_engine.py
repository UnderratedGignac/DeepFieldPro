"""
live_betting_engine.py — In-play betting opportunity detector.
==============================================================
Monitors live matches and identifies in-play value opportunities based on
expected goals (xG) momentum vs actual goals and live market prices.

Research basis:
  - In-play bets account for 52% of all wagers (2024 industry data)
  - Markets overreact to goals (price crash after a goal → value on the other side)
  - xG models can predict future goals better than live market prices in some scenarios

Strategy:
  1. Track live xG from shots/possession/corners data
  2. Compare running xG to actual goals scored
  3. When xG - actual_goals > threshold, flag as value opportunity
  4. Focus on Over 2.5 Goals (most liquid in-play market)
  5. Also detect momentum shifts (possession + shots swing)

Usage:
    from src.live_betting_engine import scan_live_opportunities

    opportunities = scan_live_opportunities(live_matches)
    # Returns list of dicts with betting signals
"""

import os
import json
import sqlite3
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "bet_log.db")

# Cache for live signals (60-second TTL — live data changes fast)
_CACHE: dict = {}
_TTL = 60


# ── xG estimation from live stats ──────────────────────────────────────────
# Simple xG model based on shots data (no ML needed for in-play signals)
# Average xG per shot by type:
#   - Shot on target: 0.30 xG
#   - Shot off target: 0.05 xG
#   - Shot blocked: 0.02 xG
#   - Corner kick: 0.03 xG (indirect)
SHOT_XG_VALUES = {
    "shots_on_target": 0.30,
    "shots_off_target": 0.05,
    "shots_blocked": 0.02,
    "corners": 0.03,
    "big_chances": 0.40,  # big chances are ~40% conversion
}


def estimate_live_xg(stats: dict) -> float:
    """Estimate expected goals from live match statistics.

    Args:
        stats: dict with keys like 'shots_on_target', 'shots_off_target',
               'corners', 'big_chances', 'possession'

    Returns:
        Estimated xG (float)
    """
    xg = 0.0
    for stat_key, xg_per_unit in SHOT_XG_VALUES.items():
        count = stats.get(stat_key, 0) or 0
        xg += count * xg_per_unit

    # Possession adjustment: high possession (>60%) adds slight xG boost
    possession = stats.get("possession", 50) or 50
    if possession > 60:
        xg *= 1.0 + (possession - 60) * 0.005  # +0.5% per possession point above 60%

    return round(xg, 2)


def detect_momentum_shift(home_stats: dict, away_stats: dict, minute: int) -> dict:
    """Detect if one team is dominating the match (momentum shift).

    Returns:
        {
            "dominating_team": "home" | "away" | None,
            "domination_score": float (0-1),
            "signals": list of strings describing the momentum indicators
        }
    """
    signals = []
    home_score = 0.0
    away_score = 0.0

    # Shots on target differential
    home_sot = home_stats.get("shots_on_target", 0) or 0
    away_sot = away_stats.get("shots_on_target", 0) or 0
    if home_sot > away_sot + 2:
        home_score += 0.3
        signals.append(f"Home +{home_sot - away_sot} shots on target")
    elif away_sot > home_sot + 2:
        away_score += 0.3
        signals.append(f"Away +{away_sot - home_sot} shots on target")

    # Possession differential
    home_poss = home_stats.get("possession", 50) or 50
    away_poss = away_stats.get("possession", 50) or 50
    if home_poss > 60:
        home_score += 0.2
        signals.append(f"Home {home_poss}% possession")
    elif away_poss > 60:
        away_score += 0.2
        signals.append(f"Away {away_poss}% possession")

    # Corners differential
    home_corners = home_stats.get("corners", 0) or 0
    away_corners = away_stats.get("corners", 0) or 0
    if home_corners > away_corners + 3:
        home_score += 0.15
        signals.append(f"Home +{home_corners - away_corners} corners")
    elif away_corners > home_corners + 3:
        away_score += 0.15
        signals.append(f"Away +{away_corners - home_corners} corners")

    # Big chances
    home_bc = home_stats.get("big_chances", 0) or 0
    away_bc = away_stats.get("big_chances", 0) or 0
    if home_bc > away_bc + 1:
        home_score += 0.25
        signals.append(f"Home +{home_bc - away_bc} big chances")
    elif away_bc > home_bc + 1:
        away_score += 0.25
        signals.append(f"Away +{away_bc - home_bc} big chances")

    # Determine dominating team
    dominating = None
    dom_score = 0.0
    if home_score > 0.5 and home_score > away_score * 1.5:
        dominating = "home"
        dom_score = home_score
    elif away_score > 0.5 and away_score > home_score * 1.5:
        dominating = "away"
        dom_score = away_score

    return {
        "dominating_team": dominating,
        "domination_score": round(max(home_score, away_score), 2),
        "signals": signals,
    }


def analyze_live_match(match_data: dict) -> Optional[dict]:
    """Analyze a single live match for in-play betting opportunities.

    Args:
        match_data: dict from dashboard state with live match data:
            {
                "match": "Home vs Away",
                "fixture_id": int,
                "fixture": {"status": {"short": "1H"|"2H"|"HT"}, "minute": int},
                "home_score": int,
                "away_score": int,
                "stats_home": {...},
                "stats_away": {...},
                "league": str,
            }

    Returns:
        dict with opportunity details or None if no opportunity found.
    """
    fixture = match_data.get("fixture", {})
    status = (fixture.get("status") or {}).get("short", "")
    minute = fixture.get("minute") or match_data.get("minute", 0)

    # Only analyze matches in progress
    if status not in ("1H", "2H", "HT", "ET1", "ET2"):
        return None

    # Get live stats
    home_stats = match_data.get("stats_home", {}) or {}
    away_stats = match_data.get("stats_away", {}) or {}

    if not home_stats and not away_stats:
        # Fall back to flat stats in match_data
        home_stats = {
            "shots_on_target": match_data.get("shots_on_target_home", 0),
            "shots_home": match_data.get("shots_home", 0),
            "corners": match_data.get("corners_home", 0),
            "possession": match_data.get("possession_home", 50),
        }
        away_stats = {
            "shots_on_target": match_data.get("shots_on_target_away", 0),
            "shots_away": match_data.get("shots_away", 0),
            "corners": match_data.get("corners_away", 0),
            "possession": match_data.get("possession_away", 50),
        }

    # Compute xG for both teams
    home_xg = estimate_live_xg(home_stats)
    away_xg = estimate_live_xg(away_stats)
    total_xg = home_xg + away_xg

    # Actual goals
    home_goals = match_data.get("home_score", 0) or 0
    away_goals = match_data.get("away_score", 0) or 0
    actual_goals = home_goals + away_goals

    # xG discrepancy signal
    xg_gap = total_xg - actual_goals
    over_signal = xg_gap > 0.5  # xG significantly exceeds actual goals

    # Momentum shift detection
    momentum = detect_momentum_shift(home_stats, away_stats, minute)

    # Projected final goals (xG-based)
    if minute and minute > 0:
        pace = total_xg / (minute / 90.0) if minute < 90 else total_xg
    else:
        pace = total_xg

    # Time decay: less time remaining = less likely to score more
    remaining_minutes = max(0, 90 - (minute or 0))
    time_factor = remaining_minutes / 90.0
    projected_additional_goals = (pace - actual_goals) * time_factor

    opportunities = []

    # OPPORTUNITY 1: Over 2.5 Goals when xG >> actual and time remains
    if over_signal and remaining_minutes > 15 and actual_goals < 3:
        confidence = min(0.9, 0.5 + xg_gap * 0.2 + (remaining_minutes / 90.0) * 0.2)
        opportunities.append({
            "market": "Over 2.5 Goals",
            "selection": "Over 2.5",
            "signal_strength": round(confidence, 2),
            "reason": (
                f"xG {total_xg:.1f} vs {actual_goals} actual goals, "
                f"{remaining_minutes}min remaining"
            ),
        })

    # OPPORTUNITY 2: Next goal / match winner when one team is dominating
    if momentum["dominating_team"] and remaining_minutes > 10:
        dom_team = momentum["dominating_team"]
        dom_name = match_data.get("match", "").split(" vs ")[
            0 if dom_team == "home" else 1
        ].strip() if " vs " in match_data.get("match", "") else dom_team

        # Only signal if score is level or the dominating team is behind
        dom_goals = home_goals if dom_team == "home" else away_goals
        opp_goals = away_goals if dom_team == "home" else home_goals

        if dom_goals <= opp_goals:
            confidence = min(0.85, 0.4 + momentum["domination_score"] * 0.3)
            opportunities.append({
                "market": "Next Goal / Match Winner",
                "selection": f"{dom_name}",
                "signal_strength": round(confidence, 2),
                "reason": (
                    f"{dom_name} dominating ({', '.join(momentum['signals'][:2])}), "
                    f"currently {'level' if dom_goals == opp_goals else 'behind'}"
                ),
            })

    # OPPORTUNITY 3: Under when xG is low and match is winding down
    if total_xg < 1.0 and remaining_minutes < 30 and actual_goals <= 1:
        confidence = min(0.8, 0.5 + (1.0 - total_xg) * 0.2)
        opportunities.append({
            "market": "Under 2.5 Goals",
            "selection": "Under 2.5",
            "signal_strength": round(confidence, 2),
            "reason": (
                f"Low xG ({total_xg:.1f}), {remaining_minutes}min remaining, "
                f"only {actual_goals} goal(s) so far"
            ),
        })

    if not opportunities:
        return None

    return {
        "match": match_data.get("match", "Unknown"),
        "fixture_id": match_data.get("fixture_id"),
        "league": match_data.get("league", ""),
        "minute": minute,
        "status": status,
        "score": f"{home_goals}-{away_goals}",
        "home_xg": home_xg,
        "away_xg": away_xg,
        "total_xg": total_xg,
        "actual_goals": actual_goals,
        "xg_gap": round(xg_gap, 2),
        "projected_pace": round(pace, 2),
        "momentum": momentum,
        "opportunities": opportunities,
    }


def scan_live_opportunities(
    live_matches: list,
    min_confidence: float = 0.6,
    min_xg_gap: float = 0.5,
) -> list:
    """Scan all live matches for in-play betting opportunities.

    Args:
        live_matches: List of live match dicts from dashboard state
        min_confidence: Minimum signal strength to include
        min_xg_gap: Minimum xG - actual_goals gap

    Returns:
        List of opportunity dicts sorted by signal strength (best first)
    """
    all_opportunities = []

    for match in live_matches:
        result = analyze_live_match(match)
        if not result:
            continue

        for opp in result["opportunities"]:
            if opp["signal_strength"] >= min_confidence:
                opp.update({
                    "match": result["match"],
                    "fixture_id": result["fixture_id"],
                    "league": result["league"],
                    "minute": result["minute"],
                    "score": result["score"],
                    "home_xg": result["home_xg"],
                    "away_xg": result["away_xg"],
                    "total_xg": result["total_xg"],
                    "xg_gap": result["xg_gap"],
                })
                all_opportunities.append(opp)

    # Sort by signal strength (best opportunities first)
    all_opportunities.sort(key=lambda x: x["signal_strength"], reverse=True)

    # Log top opportunities
    if all_opportunities:
        top = all_opportunities[0]
        print(
            f"[LIVE BETTING] Top signal: {top['match']} | "
            f"{top['market']} {top['selection']} | "
            f"confidence {top['signal_strength']:.0%} | {top['reason']}"
        )

    return all_opportunities


def get_live_betting_stats() -> dict:
    """Get summary stats for the live betting engine.

    Returns current state: how many live matches, opportunities found, etc.
    """
    dash_path = os.path.join(DATA_DIR, "todays_dashboard_state.json")
    live_count = 0
    try:
        if os.path.exists(dash_path):
            with open(dash_path, "r", encoding="utf-8") as f:
                state = json.load(f)
            live_count = sum(
                1 for m in state
                if (m.get("fixture") or {}).get("status", {}).get("short", "")
                in ("1H", "2H", "HT")
            )
    except Exception:
        pass

    # Count live bets placed today
    live_bets_today = 0
    try:
        if os.path.exists(DB_PATH):
            conn = sqlite3.connect(DB_PATH)
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            row = conn.execute(
                "SELECT COUNT(*) FROM bet_log WHERE bet_source='LIVE' "
                "AND placed_at LIKE ?",
                (f"{today}%",)
            ).fetchone()
            live_bets_today = row[0] if row else 0
            conn.close()
    except Exception:
        pass

    return {
        "live_matches": live_count,
        "live_bets_today": live_bets_today,
        "engine_status": "active" if live_count > 0 else "idle",
        "last_scan": datetime.now(timezone.utc).isoformat(),
    }
