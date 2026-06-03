import logging
import time
from collections import deque
from typing import Dict, Deque, Tuple

from .adaptive_events import MarketVelocityChangedEvent

logger = logging.getLogger(__name__)


class MarketVelocityTracker:
    """
    Tracks odds acceleration and update frequency to determine Market Velocity.
    """

    def __init__(self):
        # Dict[fixture_id -> Dict[market_type -> Deque[(timestamp, odds_change_magnitude)]]]
        self.market_updates: Dict[str, Dict[str, Deque[Tuple[float, float]]]] = {}
        self.TIME_WINDOW_SEC = 60.0

    def record_odds_update(
        self,
        fixture_id: str,
        market_type: str,
        old_odds: float,
        new_odds: float,
        dispatcher,
    ):
        if fixture_id not in self.market_updates:
            self.market_updates[fixture_id] = {}
        if market_type not in self.market_updates[fixture_id]:
            self.market_updates[fixture_id][market_type] = deque()

        now = time.time()
        magnitude = abs(new_odds - old_odds)

        self.market_updates[fixture_id][market_type].append((now, magnitude))

        # Prune old updates
        while (
            self.market_updates[fixture_id][market_type]
            and self.market_updates[fixture_id][market_type][0][0]
            < now - self.TIME_WINDOW_SEC
        ):
            self.market_updates[fixture_id][market_type].popleft()

        # Calculate velocity
        updates = self.market_updates[fixture_id][market_type]
        frequency = len(updates)
        total_magnitude = sum(m for t, m in updates)

        velocity_score = (frequency * 0.5) + (total_magnitude * 10.0)  # Weighted metric

        # Note: In a real system we track previous velocity to calculate acceleration
        acceleration = 0.0

        event = MarketVelocityChangedEvent(  # noqa: F841
            fixture_id=fixture_id,
            market_type=market_type,
            velocity_score=velocity_score,
            acceleration=acceleration,
            timestamp=str(now),
        )

        # dispatcher.emit(event)
        return velocity_score


velocity_tracker = MarketVelocityTracker()
