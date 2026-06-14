import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


class ValidationEngine:

    @staticmethod
    def validate_lineup(lineup_payload: Dict[str, Any]) -> bool:
        """
        Validates the overall lineup payload.
        """
        if not lineup_payload:
            logger.error("Empty lineup payload")
            return False

        players = lineup_payload.get("players", [])
        if not players:
            logger.error("No players found in lineup")
            return False

        if len(players) < 11:
            logger.warning(f"Incomplete lineup detected. Found {len(players)} players.")

        # Check for duplicates
        seen = set()
        for p in players:
            identifier = (p.get("team"), p.get("normalized_name"))
            if identifier in seen:
                logger.error(f"Duplicate player found in lineup: {identifier}")
                return False
            seen.add(identifier)

        return True

    @staticmethod
    def validate_odds(odds_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Validates a list of scraped odds. Filters out invalid ones.
        """
        valid_odds = []
        for odd in odds_list:
            decimal_odds = odd.get("decimal_odds")
            if decimal_odds is None or decimal_odds <= 1.00:
                logger.warning(
                    f"Invalid decimal odds: {decimal_odds} for {odd.get('market')}"
                )
                continue

            implied_prob = odd.get("implied_probability")
            if implied_prob is None or implied_prob <= 0 or implied_prob > 1:
                logger.warning(f"Invalid implied probability: {implied_prob}")
                continue

            line = odd.get("line")
            if line is not None and line < 0:
                logger.warning(f"Negative line value found: {line}")
                continue

            valid_odds.append(odd)

        return valid_odds


validation_engine = ValidationEngine()
