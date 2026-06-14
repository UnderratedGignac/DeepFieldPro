# lineup_confidence_engine.py
import logging
from typing import List, Dict, Any
from .lineup_sources import lineup_registry

logger = logging.getLogger(__name__)


class LineupConfidenceEngine:
    def __init__(self):
        # Tracking seen lineups per fixture to compute multi-source agreement
        self.fixture_state = {}

    def compute_confidence(
        self, fixture_id: str, source: str, lineup: List[Dict[str, Any]]
    ) -> float:
        """
        Computes a probabilistic confidence score [0.0, 1.0] for a lineup payload.
        Instead of a binary True/False, downstream models use this weight.
        """
        metrics = lineup_registry.get_source_metrics(source)
        base_confidence = metrics["reliability"]

        # Initialize fixture state tracking
        if fixture_id not in self.fixture_state:
            self.fixture_state[fixture_id] = {
                "sources_seen": set(),
                "formations": set(),
            }

        state = self.fixture_state[fixture_id]
        state["sources_seen"].add(source)

        # Check formation consistency
        formation_home = next(
            (p.get("formation") for p in lineup if p.get("team_side") == "home"), None
        )
        if formation_home:
            state["formations"].add(formation_home)

        confidence = base_confidence

        # 1. Official Badge Bump
        if source in ["official_club_socials", "official_league_feed"]:
            confidence = min(1.0, confidence + 0.1)

        # 2. Multi-Source Agreement Bump
        if len(state["sources_seen"]) >= 2 and base_confidence < 1.0:
            confidence = min(0.99, confidence + 0.15)
            logger.info(
                f"Multi-source agreement for {fixture_id}. Confidence boosted to {confidence}"
            )

        # 3. Formation Inconsistency Penalty
        if len(state["formations"]) > 1:
            confidence -= 0.1
            logger.warning(
                f"Formation disagreement detected for {fixture_id}. Confidence dropped to {confidence}"
            )

        return round(max(0.0, min(1.0, confidence)), 3)


confidence_engine = LineupConfidenceEngine()
