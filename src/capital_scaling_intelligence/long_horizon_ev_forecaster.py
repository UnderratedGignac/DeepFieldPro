import logging
import math

logger = logging.getLogger(__name__)

class LongHorizonEVForecaster:
    """
    Forecasts expected EV trajectory over rolling windows, explicitly modeling 
    EV decay under scaling pressure.
    """
    def __init__(self):
        pass

    def forecast_ev_trajectory(self, current_ev: float, scaling_velocity: float) -> float:
        """
        Projects EV over a long horizon.
        If we scale too fast (high velocity), liquidity constraints and bookmaker 
        defenses will aggressively decay the edge.
        W5 FIX: Uses exponential decay with quadratic penalty instead of linear.
        """
        if current_ev <= 0:
            return current_ev

        # Penalty for scaling pressure: Exponential decay based on squared velocity
        # Beta is a sensitivity parameter. Higher beta = steeper decay.
        beta = 100.0
        
        # We only penalize positive scaling velocity (growth). Shrinking doesn't decay edge.
        velocity_penalty = max(0.0, scaling_velocity)
        
        projected_ev = current_ev * math.exp(-beta * (velocity_penalty ** 2))
        
        logger.debug(f"[EV FORECASTER] Current EV: {current_ev:.3f} | Projected EV (under scaling): {projected_ev:.3f}")
        return projected_ev

ev_forecaster = LongHorizonEVForecaster()
