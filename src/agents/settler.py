"""
settler.py — SettlerAgent
Grades open bets in bet_log.db using free_results_scraper.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from typing import List

from .base import BaseAgent, TaskResult

BASE = Path(__file__).parent.parent.parent
DATA = BASE / "data"
MODELS = BASE / "models"


def _match_teams(bet_match: str, home_team: str, away_team: str) -> bool:
    """Return True if both team names appear in the bet match string (case-insensitive)."""
    bm = bet_match.lower()
    return home_team.lower() in bm and away_team.lower() in bm


def _grade_1x2(home_score: int, away_score: int, selection: str) -> str:
    """Grade a 1X2 bet given the final scores. Returns WIN/LOSS/VOID."""
    if home_score > away_score:
        result = "home"
    elif home_score < away_score:
        result = "away"
    else:
        result = "draw"

    sel_lower = selection.lower()
    if sel_lower in ("home", "1", "h"):
        return "WIN" if result == "home" else "LOSS"
    if sel_lower in ("away", "2", "a"):
        return "WIN" if result == "away" else "LOSS"
    if sel_lower in ("draw", "x", "d"):
        return "WIN" if result == "draw" else "VOID"
    # For VOID / unrecognised draw handling
    if home_score == away_score:
        return "VOID"
    return "LOSS"


class SettlerAgent(BaseAgent):

    @property
    def agent_card(self) -> dict:
        return {
            "name": "SettlerAgent",
            "version": "1.0.0",
            "description": "Grades open bets via free_results_scraper",
        }

    def capabilities(self) -> List[str]:
        return ["bet_grading"]

    def run(self, task: dict) -> TaskResult:
        try:
            date_str = task.get("date")

            # Import free_results_scraper via sys.path trick
            src_path = str(BASE / "src")
            if src_path not in sys.path:
                sys.path.insert(0, src_path)

            try:
                from free_results_scraper import get_finished_results
            except ImportError as ie:
                return TaskResult(
                    success=True,
                    data={"settled": 0, "wins": 0, "losses": 0, "voids": 0},
                    error=f"free_results_scraper import failed: {ie}",
                )

            # Fetch results
            if date_str:
                results_raw = get_finished_results(dates=[date_str])
            else:
                results_raw = get_finished_results()

            # Normalise results: {"Home vs Away": (home_score, away_score)}
            # The scraper may return dicts or tuples
            results: dict = {}
            for key, val in results_raw.items():
                if isinstance(val, (list, tuple)) and len(val) >= 2:
                    results[key] = (int(val[0]), int(val[1]))

            db_path = DATA / "bet_log.db"
            if not db_path.exists():
                return TaskResult(
                    success=True,
                    data={"settled": 0, "wins": 0, "losses": 0, "voids": 0},
                )

            # Read-write connection for updates
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute(
                    """
                    SELECT id, match, selection
                    FROM bet_log
                    WHERE result IS NULL OR result = 'OPEN'
                    """
                ).fetchall()

                settled = wins = losses = voids = 0

                for bet in rows:
                    bet_id = bet["id"]
                    bet_match = bet["match"] or ""
                    selection = bet["selection"] or ""

                    # Try to find a matching result
                    matched_result = None
                    for result_key, (hs, as_) in results.items():
                        # result_key is "Home vs Away"
                        parts = result_key.split(" vs ", 1)
                        if len(parts) != 2:
                            continue
                        home_t, away_t = parts[0].strip(), parts[1].strip()
                        if _match_teams(bet_match, home_t, away_t):
                            matched_result = (hs, as_)
                            break

                    if matched_result is None:
                        continue

                    grade = _grade_1x2(matched_result[0], matched_result[1], selection)
                    conn.execute(
                        "UPDATE bet_log SET result = ? WHERE id = ?",
                        (grade, bet_id),
                    )
                    settled += 1
                    if grade == "WIN":
                        wins += 1
                    elif grade == "LOSS":
                        losses += 1
                    else:
                        voids += 1

                conn.commit()
            finally:
                conn.close()

            return TaskResult(
                success=True,
                data={
                    "settled": settled,
                    "wins": wins,
                    "losses": losses,
                    "voids": voids,
                },
            )

        except Exception as exc:
            return TaskResult(
                success=False,
                error=str(exc),
                data={"settled": 0, "wins": 0, "losses": 0, "voids": 0},
            )
