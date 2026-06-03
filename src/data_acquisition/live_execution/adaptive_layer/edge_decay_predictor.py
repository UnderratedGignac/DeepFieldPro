# mypy: ignore-errors
import logging
import math
from typing import Dict

logger = logging.getLogger(__name__)


class EdgeDecayPredictor:
    """
    Builds mathematical edge decay curves Edge(t).
    Estimates the half-life of an edge based on market regime and type.
    """

    def __init__(self):
        # Base half-life in seconds (to be overwritten by ML/historical data)
        self.base_half_life_sec: Dict[str, float] = {
            "player_goal_anytime": 1.5,
            "player_first_goalscorer": 1.0,
            "player_shots_ou": 4.0,
            "player_sot_ou": 3.5,
            "player_card_yellow": 8.0,
        }

    def predict_remaining_edge(
        self, market_type: str, initial_ev: float, time_elapsed_sec: float, regime: str
    ) -> float:
        """
        Uses exponential decay to estimate remaining EV.
        Decay accelerates under 'panic' regimes.
        """
        half_life = self.base_half_life_sec.get(market_type, 3.0)

        # Adjust half-life based on regime
        if regime == "panic":
            half_life *= 0.3
        elif regime == "high-frequency-volatility":
            half_life *= 0.6
        elif regime == "stable":
            half_life *= 1.5

        # N(t) = N0 * (1/2)^(t / t_half)
        if half_life <= 0:
            return 0.0

        remaining_ev = initial_ev * math.pow(0.5, time_elapsed_sec / half_life)
        return remaining_ev

    def update_base_half_life(self, market_type: str, new_half_life: float):
        """
        Called by the live feedback loop when new empirical data proves the decay is faster/slower.
        """
        old = self.base_half_life_sec.get(market_type, 0)
        # EMA update
        self.base_half_life_sec[market_type] = (old * 0.8) + (new_half_life * 0.2)
        logger.info(
            f"[EDGE DECAY] Adapted half-life for {market_type}: {self.base_half_life_sec[market_type]:.2f}s"
        )


decay_predictor = EdgeDecayPredictor()
