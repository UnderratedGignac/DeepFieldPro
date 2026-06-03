# lineup_change_detector.py
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class LineupChangeDetector:
    def __init__(self):
        # Stores the last known lineup configuration for diffing
        # fixture_id -> dict of normalized_names -> canonical_position
        self.last_known_state = {}
        # fixture_id -> last known formation
        self.last_known_formation = {}

    def detect_changes(
        self, fixture_id: str, new_lineup: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Compares the new lineup against the last known state.
        Detects late scratches, tactical formation changes, and positional swaps.
        """
        changes = {
            "has_changes": False,
            "scratched_players": [],
            "new_starters": [],
            "formation_changed": False,
            "old_formation": None,
            "new_formation": None,
            "positional_swaps": [],
        }

        if fixture_id not in self.last_known_state:
            # First time seeing the lineup, store it and return no "changes"
            self._update_state(fixture_id, new_lineup)
            return changes

        old_state = self.last_known_state[fixture_id]
        old_formation = self.last_known_formation.get(fixture_id)

        new_state = {}
        new_formation = None
        for p in new_lineup:
            if p.get("starter"):
                new_state[p.get("normalized_name")] = p.get(
                    "canonical_position", p.get("position")
                )
                # Grab the formation from one of the starters
                if not new_formation and p.get("formation"):
                    new_formation = p.get("formation")

        # 1. Detect Formation Change
        if old_formation and new_formation and old_formation != new_formation:
            changes["has_changes"] = True
            changes["formation_changed"] = True
            changes["old_formation"] = old_formation
            changes["new_formation"] = new_formation
            logger.warning(
                f"Tactical Formation Change detected for {fixture_id}: {old_formation} -> {new_formation}"
            )

        # 2. Detect Scratches and Additions
        old_players = set(old_state.keys())
        new_players = set(new_state.keys())

        scratched = old_players - new_players
        if scratched:
            changes["has_changes"] = True
            changes["scratched_players"] = list(scratched)
            logger.warning(f"Late scratch detected for {fixture_id}: {scratched}")

        added = new_players - old_players
        if added:
            changes["has_changes"] = True
            changes["new_starters"] = list(added)
            logger.info(f"Surprise starters detected for {fixture_id}: {added}")

        # 3. Detect Positional Swaps (same player, different tactical deployment)
        for player in old_players.intersection(new_players):
            old_pos = old_state[player]
            new_pos = new_state[player]
            if old_pos != new_pos:
                changes["has_changes"] = True
                changes["positional_swaps"].append(
                    {"player": player, "old": old_pos, "new": new_pos}
                )
                logger.info(f"Positional swap for {player}: {old_pos} -> {new_pos}")

        # Update state for next cycle
        if changes["has_changes"]:
            self._update_state(fixture_id, new_lineup)

        return changes

    def _update_state(self, fixture_id: str, lineup: List[Dict[str, Any]]):
        state = {}
        formation = None
        for p in lineup:
            if p.get("starter"):
                state[p.get("normalized_name")] = p.get(
                    "canonical_position", p.get("position")
                )
                if not formation and p.get("formation"):
                    formation = p.get("formation")

        self.last_known_state[fixture_id] = state
        self.last_known_formation[fixture_id] = formation


change_detector = LineupChangeDetector()
