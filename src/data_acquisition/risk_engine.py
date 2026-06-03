# risk_engine.py
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class PortfolioRiskEngine:
    """
    Prevents catastrophic ruin by enforcing strict exposure limits,
    detecting correlated markets, and preventing team/player stacking.
    """

    def __init__(self):
        # Global bankroll
        self.total_bankroll = 10000.0  # Mock initial

        # Risk thresholds
        self.MAX_EXPOSURE_PER_MATCH = 0.08  # 8% of bankroll per match
        self.MAX_EXPOSURE_PER_PLAYER = 0.03  # 3% of bankroll per player

        # Current active exposure state
        # fixture_id -> float
        self.match_exposure = {}
        # player_id -> float
        self.player_exposure = {}
        # List of approved but unsettled bet schemas
        self.active_bets = []

    def evaluate_risk(
        self, edge_data: Dict[str, Any], odds_event: Any, recommended_stake: float
    ) -> Dict[str, Any]:
        """
        Validates if a recommended bet violates any portfolio risk parameters.
        """
        fixture_id = odds_event.fixture_id
        player = odds_event.normalized_name

        current_match_exp = self.match_exposure.get(fixture_id, 0.0)
        current_player_exp = self.player_exposure.get(player, 0.0)

        # 1. Check Match Exposure Limit
        if (
            current_match_exp + recommended_stake
        ) / self.total_bankroll > self.MAX_EXPOSURE_PER_MATCH:
            return {"approved": False, "reason": "Match exposure limit breached"}

        # 2. Check Player Exposure Limit
        if (
            current_player_exp + recommended_stake
        ) / self.total_bankroll > self.MAX_EXPOSURE_PER_PLAYER:
            return {"approved": False, "reason": "Player exposure limit breached"}

        # 3. Correlated Market Prevention
        # E.g., Do not bet Over 0.5 Goals AND Anytime Goalscorer for the same player
        for bet in self.active_bets:
            if bet["player"] == player and bet["fixture"] == fixture_id:
                # Simplistic correlation block: only 1 bet per player
                return {
                    "approved": False,
                    "reason": "Correlated player market already active",
                }

        return {"approved": True, "approved_stake": recommended_stake}

    def register_executed_bet(self, fixture_id: str, player: str, stake: float):
        """
        Updates internal risk state after a bet clears execution.
        """
        self.match_exposure[fixture_id] = (
            self.match_exposure.get(fixture_id, 0.0) + stake
        )
        self.player_exposure[player] = self.player_exposure.get(player, 0.0) + stake

        self.active_bets.append(
            {"fixture": fixture_id, "player": player, "stake": stake}
        )
        logger.info(
            f"[RISK] Registered new exposure. Match: {self.match_exposure[fixture_id]}, Player: {self.player_exposure[player]}"
        )


risk_engine = PortfolioRiskEngine()
