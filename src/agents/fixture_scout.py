"""
fixture_scout.py — FixtureScoutAgent
Reads today's (or a given date's) fixtures from odds_stream.db.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import List

from .base import BaseAgent, TaskResult

BASE = Path(__file__).parent.parent.parent   # agents/ -> src/ -> project root
DATA = BASE / "data"
MODELS = BASE / "models"


class FixtureScoutAgent(BaseAgent):

    @property
    def agent_card(self) -> dict:
        return {
            "name": "FixtureScoutAgent",
            "version": "1.0.0",
            "description": "Discovers today's fixtures from odds_stream.db",
        }

    def capabilities(self) -> List[str]:
        return ["fixture_discovery"]

    def run(self, task: dict) -> TaskResult:
        try:
            db_path = DATA / "odds_stream.db"
            if not db_path.exists():
                return TaskResult(success=True, data={"fixtures": []})

            date_filter = task.get("date")
            limit = int(task.get("limit", 50))

            uri = f"file:{db_path}?mode=ro"
            conn = sqlite3.connect(uri, uri=True)
            conn.row_factory = sqlite3.Row
            try:
                if date_filter:
                    rows = conn.execute(
                        """
                        SELECT fixture_id, home_team, away_team,
                               kickoff_time, kickoff_date,
                               tournament_name, league_id
                        FROM fixture
                        WHERE kickoff_date = ?
                        ORDER BY kickoff_time
                        LIMIT ?
                        """,
                        (date_filter, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """
                        SELECT fixture_id, home_team, away_team,
                               kickoff_time, kickoff_date,
                               tournament_name, league_id
                        FROM fixture
                        ORDER BY kickoff_date, kickoff_time
                        LIMIT ?
                        """,
                        (limit,),
                    ).fetchall()
            finally:
                conn.close()

            fixtures = [
                {
                    "fixture_id": r["fixture_id"],
                    "home_team": r["home_team"],
                    "away_team": r["away_team"],
                    "kickoff_time": r["kickoff_time"],
                    "kickoff_date": r["kickoff_date"],
                    "tournament_name": r["tournament_name"],
                    "league_id": r["league_id"],
                }
                for r in rows
            ]
            return TaskResult(success=True, data={"fixtures": fixtures})

        except Exception as exc:
            return TaskResult(success=False, error=str(exc), data={"fixtures": []})
