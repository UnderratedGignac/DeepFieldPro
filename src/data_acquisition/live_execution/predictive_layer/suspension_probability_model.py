import logging
import math
from typing import Dict, Any

logger = logging.getLogger(__name__)

class SuspensionProbabilityModel:
    """
    Estimates P(suspension within t).
    Suspensions destroy execution survivability. If probability is high, we must front-run execution.
    """
    def __init__(self):
        # Historical base suspension rates
        self.market_fragility = {
            "player_goal_anytime": 0.8,
            "player_first_goalscorer": 0.9,
            "player_shots_ou": 0.4,
            "player_sot_ou": 0.45,
            "player_card_yellow": 0.1
        }

    def predict_suspension_probability(self, market_type: str, time_horizon_sec: float, 
                                       regime: str, velocity_score: float, lineup_confidence: float) -> float:
        """
        Estimates the probability the bookmaker will lock the market within the given horizon.
        """
        fragility_base = self.market_fragility.get(market_type, 0.5)
        
        # Logistic regression-style approach (simplified for architecture)
        # P = 1 / (1 + e^-z)
        
        z = -2.0 # Base intercept
        z += (fragility_base * 2.0)
        z += (time_horizon_sec * 0.2) # Longer horizon = more likely to suspend
        
        if regime == "panic":
            z += 3.0
        elif regime == "high-frequency-volatility":
            z += 1.5
            
        z += (velocity_score * 0.1)
        
        if lineup_confidence > 0.9:
            z += 1.0 # Confirmed lineups trigger suspensions fast
            
        p_suspend = 1.0 / (1.0 + math.exp(-z))
        
        logger.debug(f"[SUSPENSION MODEL] P(Suspend in {time_horizon_sec}s) for {market_type} = {p_suspend:.2f}")
        return p_suspend

suspension_model = SuspensionProbabilityModel()
