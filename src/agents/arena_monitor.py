"""
arena_monitor.py — ArenaMonitorAgent
Monitors the Polymarket/STAIR-AI Arena for value opportunities.
Always enforces dry_run=True unless task explicitly passes dry_run=False.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List

from .base import BaseAgent, TaskResult

BASE = Path(__file__).parent.parent.parent
DATA = BASE / "data"
MODELS = BASE / "models"


class ArenaMonitorAgent(BaseAgent):

    @property
    def agent_card(self) -> dict:
        return {
            "name": "ArenaMonitorAgent",
            "version": "1.0.0",
            "description": "Monitors STAIR-AI Arena / Polymarket for 1X2 value opportunities",
        }

    def capabilities(self) -> List[str]:
        return ["polymarket_monitoring"]

    def run(self, task: dict) -> TaskResult:
        try:
            conf_min = float(task.get("conf_min", 0.50))
            edge_min = float(task.get("edge_min", 0.02))
            # Safety: only allow live execution when task explicitly says dry_run=False
            dry_run = task.get("dry_run", True)
            if dry_run is not False:
                dry_run = True

            src_path = str(BASE / "src")
            if src_path not in sys.path:
                sys.path.insert(0, src_path)

            try:
                import arena_betting  # type: ignore
            except ImportError as ie:
                return TaskResult(
                    success=True,
                    data={"candidates": [], "count": 0, "dry_run": True},
                    error=f"arena_betting import failed: {ie}",
                )

            # analyze() returns a list of candidate dicts
            try:
                candidates = arena_betting.analyze(
                    conf_min=conf_min,
                    edge_min=edge_min,
                )
            except Exception as ae:
                return TaskResult(
                    success=True,
                    data={"candidates": [], "count": 0, "dry_run": dry_run},
                    error=f"arena_betting.analyze error: {ae}",
                )

            if candidates is None:
                candidates = []

            return TaskResult(
                success=True,
                data={
                    "candidates": candidates,
                    "count": len(candidates),
                    "dry_run": dry_run,
                },
            )

        except Exception as exc:
            return TaskResult(
                success=False,
                error=str(exc),
                data={"candidates": [], "count": 0, "dry_run": True},
            )
