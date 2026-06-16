"""
steam_detector.py — SteamDetectorAgent
Detects line movement (steam) by comparing earliest vs latest odds snapshots
stored in bet_log.db's odds_history table.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Dict, List

from .base import BaseAgent, TaskResult

BASE = Path(__file__).parent.parent.parent
DATA = BASE / "data"
MODELS = BASE / "models"


def _devig_snapshot(rows: list) -> Dict[str, float]:
    """
    Given a list of (selection, odds) tuples for ONE snapshot,
    de-vig and return {selection: probability}.
    """
    if not rows:
        return {}
    try:
        raw = {sel: 1.0 / float(odds) for sel, odds in rows if float(odds) > 0}
        total = sum(raw.values())
        if total <= 0:
            return {}
        return {sel: p / total for sel, p in raw.items()}
    except (ValueError, ZeroDivisionError):
        return {}


class SteamDetectorAgent(BaseAgent):

    @property
    def agent_card(self) -> dict:
        return {
            "name": "SteamDetectorAgent",
            "version": "1.0.0",
            "description": "Detects line movement from odds_history in bet_log.db",
        }

    def capabilities(self) -> List[str]:
        return ["line_movement_detection"]

    def run(self, task: dict) -> TaskResult:
        try:
            fixture_id = int(task.get("fixture_id", 0))
            market_type = task.get("market_type", "1X2")

            db_path = DATA / "bet_log.db"
            if not db_path.exists():
                return TaskResult(success=True, data={"moves": {}})

            uri = f"file:{db_path}?mode=ro"
            conn = sqlite3.connect(uri, uri=True)
            try:
                # Pull all snapshots for this fixture+market ordered by timestamp
                rows = conn.execute(
                    """
                    SELECT selection, odds, timestamp
                    FROM odds_history
                    WHERE fixture_id = ? AND market = ?
                    ORDER BY timestamp ASC
                    """,
                    (fixture_id, market_type),
                ).fetchall()
            finally:
                conn.close()

            if not rows:
                return TaskResult(success=True, data={"moves": {}})

            # Group by timestamp, collect distinct timestamps
            by_ts: Dict[str, List] = {}
            for sel, odds, ts in rows:
                by_ts.setdefault(ts, []).append((sel, odds))

            distinct_ts = sorted(by_ts.keys())
            if len(distinct_ts) < 2:
                return TaskResult(success=True, data={"moves": {}})

            earliest_ts = distinct_ts[0]
            latest_ts = distinct_ts[-1]

            earliest_probs = _devig_snapshot(by_ts[earliest_ts])
            latest_probs = _devig_snapshot(by_ts[latest_ts])

            # Compute move per selection
            all_sels = set(earliest_probs) | set(latest_probs)
            moves = {}
            for sel in all_sels:
                e = earliest_probs.get(sel, 0.0)
                l = latest_probs.get(sel, 0.0)
                moves[sel] = round(l - e, 6)

            return TaskResult(success=True, data={"moves": moves})

        except Exception as exc:
            return TaskResult(success=False, error=str(exc), data={"moves": {}})
