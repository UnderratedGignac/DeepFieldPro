"""
base.py — shared base types for the DeepFieldPro A2A agent layer.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, List


@dataclass
class TaskResult:
    success: bool
    data: Any = None
    error: str = ""
    duration_ms: float = 0.0
    agent: str = ""


class BaseAgent(ABC):
    """Abstract base for all DeepFieldPro agents."""

    @property
    @abstractmethod
    def agent_card(self) -> dict:
        """Return a dict describing this agent (name, version, description)."""

    @abstractmethod
    def capabilities(self) -> List[str]:
        """Return list of capability strings this agent supports."""

    @abstractmethod
    def run(self, task: dict) -> TaskResult:
        """Execute the task and return a TaskResult."""

    def _timed_run(self, task: dict) -> TaskResult:
        """Wrap run() with wall-clock timing and top-level exception handling."""
        t0 = time.monotonic()
        try:
            result = self.run(task)
        except Exception as exc:
            elapsed = (time.monotonic() - t0) * 1000
            return TaskResult(
                success=False,
                error=str(exc),
                duration_ms=round(elapsed, 2),
                agent=self.agent_card.get("name", type(self).__name__),
            )
        elapsed = (time.monotonic() - t0) * 1000
        result.duration_ms = round(elapsed, 2)
        result.agent = self.agent_card.get("name", type(self).__name__)
        return result
