"""
fatigue_detector.py — Fixture congestion & fatigue adjustment for xG.

Teams playing a 3rd match within 7 days show measurable performance drops:
  - Offensive xG: −8% per extra game in congested window
  - Defensive xG: slight improvement (more compact shape when tired)
  - Source: Stüttgen et al. (2025), Sports Medicine meta-analysis (2021)

Uses odds_stream.db fixture history to count each team's recent schedule.
No external API needed — all data is already scraped by betarabia_scraper.py.

Returns xG multipliers (home_mult, away_mult) ready to apply after DC output.
"""

import os
import sqlite3
import datetime
import logging

logger = logging.getLogger(__name__)

_DB = os.path.join(os.path.dirname(__file__), "..", "data", "odds_stream.db")

# How many days to look back for the congestion window
_WINDOW_DAYS = 7
# xG penalty per match beyond 2 in the window (offensive multiplier)
_PENALTY_PER_EXTRA = 0.08
# Maximum total penalty cap (don't reduce xG by more than 25%)
_MAX_PENALTY = 0.25


def _recent_matches(team_name: str, before_date: datetime.date, days: int = 7) -> int:
    """Count fixtures the team played in the last `days` days before `before_date`."""
    cutoff = before_date - datetime.timedelta(days=days)
    try:
        conn = sqlite3.connect(_DB)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT COUNT(*) FROM fixture
            WHERE (LOWER(home_team) = LOWER(?) OR LOWER(away_team) = LOWER(?))
              AND DATE(kickoff_time) >= ?
              AND DATE(kickoff_time) < ?
        """,
            (team_name, team_name, cutoff.isoformat(), before_date.isoformat()),
        )
        row = cur.fetchone()
        conn.close()
        return int(row[0]) if row else 0
    except Exception as e:
        logger.debug(f"[FATIGUE] DB error for {team_name}: {e}")
        return 0


def xg_multipliers(
    home_team: str, away_team: str, kickoff_date: datetime.date | None = None
) -> tuple:
    """
    Returns (home_mult, away_mult) for xG adjustment based on fixture congestion.

    Examples:
      home played 2 games in last 7 days → (1.0, 1.0)  no penalty
      home played 3 games in last 7 days → (0.92, 1.0) −8% home xG
      away played 4 games in last 7 days → (1.0, 0.84) −16% away xG

    Apply AFTER Dixon-Coles expected goals:
        exp_h, exp_a = _dc_expected_goals(home, away, league)
        fh, fa = fatigue_detector.xg_multipliers(home, away, kickoff_date)
        exp_h *= fh
        exp_a *= fa
    """
    if kickoff_date is None:
        kickoff_date = datetime.date.today()

    home_games = _recent_matches(home_team, kickoff_date, _WINDOW_DAYS)
    away_games = _recent_matches(away_team, kickoff_date, _WINDOW_DAYS)

    def _mult(games: int) -> float:
        extra = max(0, games - 2)  # penalty starts after 2 games in the window
        penalty = min(extra * _PENALTY_PER_EXTRA, _MAX_PENALTY)
        return round(1.0 - penalty, 3)

    home_mult = _mult(home_games)
    away_mult = _mult(away_games)

    if home_mult < 1.0 or away_mult < 1.0:
        logger.info(
            f"[FATIGUE] {home_team} ({home_games}g) vs {away_team} ({away_games}g) "
            f"→ xG mult {home_mult:.2f}/{away_mult:.2f}"
        )

    return home_mult, away_mult


def congestion_summary(
    home_team: str, away_team: str, kickoff_date: datetime.date | None = None
) -> dict:
    """
    Returns a dict with game counts and multipliers for dashboard display.
    {
        "home_games_7d": int, "away_games_7d": int,
        "home_mult": float,   "away_mult": float,
        "home_fatigued": bool, "away_fatigued": bool,
    }
    """
    if kickoff_date is None:
        kickoff_date = datetime.date.today()
    hg = _recent_matches(home_team, kickoff_date)
    ag = _recent_matches(away_team, kickoff_date)
    hm, am = xg_multipliers(home_team, away_team, kickoff_date)
    return {
        "home_games_7d": hg,
        "away_games_7d": ag,
        "home_mult": hm,
        "away_mult": am,
        "home_fatigued": hg >= 3,
        "away_fatigued": ag >= 3,
    }
