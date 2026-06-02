import logging
from typing import Dict, Any

from src.capital_scaling_intelligence.schemas import CompoundingRegime, ScalingDecision

logger = logging.getLogger(__name__)

class GrowthVsRiskOptimizer:
    """
    The Core Decision Engine of ACSI.
    Maximizes: long_term_growth - drawdown_penalty - regime_instability_penalty
    Outputs the final ScalingDecision.
    """
    def __init__(self):
        pass

    def optimize_scaling_decision(self, regime: CompoundingRegime, projected_ev: float, 
                                  drawdown_momentum: float) -> ScalingDecision:
        """
        Determines the optimal bankroll trajectory action.
        """
        # 1. Survival Override
        if regime == CompoundingRegime.DECAY or drawdown_momentum > 0.05:
            logger.warning("[GROWTH OPTIMIZER] Decay regime or high drawdown momentum. SCALE DOWN.")
            return ScalingDecision.SCALE_DOWN
            
        # 2. Compounding Window
        if regime == CompoundingRegime.COMPOUNDING and projected_ev > 0.03:
            logger.info("[GROWTH OPTIMIZER] Structural compounding window identified. SCALE UP.")
            return ScalingDecision.SCALE_UP
            
        # 3. Holding Pattern (Neutral or low EV)
        if regime == CompoundingRegime.NEUTRAL or projected_ev <= 0.0:
            logger.info("[GROWTH OPTIMIZER] Neutral structural state. HOLD scaling trajectory.")
            return ScalingDecision.HOLD
            
        return ScalingDecision.FREEZE_SCALING

growth_optimizer = GrowthVsRiskOptimizer()
