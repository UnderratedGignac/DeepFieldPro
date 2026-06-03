import logging

from .execution_behavior_memory import behavior_memory

logger = logging.getLogger(__name__)

class ExecutionSurvivabilityModel:
    """
    Estimates the probability that a bet survives execution friction before we even attempt it.
    """
    def __init__(self):
        pass

    def estimate_survivability(self, market_type: str, queue_delay_sec: float, market_volatility: float, regime: str) -> float:
        """
        Calculates P(fill).
        """
        # Base historical fill rate
        base_fill_rate = behavior_memory.get_historical_fill_rate(market_type, min_volatility=market_volatility*0.8)
        
        # Penalize for queue delay
        delay_penalty = min(0.5, queue_delay_sec * 0.05) # 5% drop per second in queue
        
        # Penalize for regime
        regime_penalty = 0.0
        if regime == "panic":
            regime_penalty = 0.4
        elif regime == "high-frequency-volatility":
            regime_penalty = 0.2
            
        p_survive = max(0.01, base_fill_rate - delay_penalty - regime_penalty)
        return p_survive

survivability_model = ExecutionSurvivabilityModel()
