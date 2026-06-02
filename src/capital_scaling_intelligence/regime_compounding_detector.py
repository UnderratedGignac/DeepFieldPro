import logging
from typing import Dict, Any
from src.capital_scaling_intelligence.schemas import CompoundingRegime

logger = logging.getLogger(__name__)

class RegimeCompoundingDetector:
    """
    Detects whether the system is in a structural compounding regime (safe to scale),
    a neutral regime (flat scaling), or a decay regime (reduce exposure).
    """
    def __init__(self):
        pass

    def detect_regime(self, clv_stability: float, friction_trend: float, 
                      rvl_drift: float, drawdown_autocorr: float) -> CompoundingRegime:
        """
        Determines the long-term structural health of the edge.
        """
        # If drawdown autocorrelation is high, losses are clustering.
        # If execution friction is rising (trend > 0), scaling is toxic.
        
        if drawdown_autocorr > 0.3 or friction_trend > 0.05 or rvl_drift < -0.1:
            logger.warning("[COMPOUND DETECTOR] Structural fragility detected. Transitioning to DECAY regime.")
            return CompoundingRegime.DECAY
            
        if clv_stability > 0.8 and friction_trend <= 0.0 and rvl_drift > 0.05 and drawdown_autocorr < 0.1:
            logger.info("[COMPOUND DETECTOR] System is deeply stable. Transitioning to COMPOUNDING regime.")
            return CompoundingRegime.COMPOUNDING
            
        return CompoundingRegime.NEUTRAL

compounding_detector = RegimeCompoundingDetector()
