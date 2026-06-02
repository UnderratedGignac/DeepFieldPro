import logging
from typing import Dict, Any

from src.capital_deployment_protocol.schemas import CapitalAllocationRequest

logger = logging.getLogger(__name__)

class RegimeSensitivePositionSizing:
    """
    Dynamically sizes positions based on market regime and execution fragility.
    """
    def __init__(self):
        # Multipliers based on regime hostility
        self.regime_multipliers = {
            "stable": 1.0,
            "reactive": 0.6,
            "high-frequency-volatility": 0.25,
            "panic": 0.05
        }

    def scale_position(self, request: CapitalAllocationRequest, current_phase_max_capital: float) -> float:
        """
        Scales the base stake utilizing regime context and survivability (p_fill).
        Also bounds it by the current phase's absolute max capital ceiling.
        """
        # 1. Regime Multiplier
        regime_mult = self.regime_multipliers.get(request.regime, 0.0)
        
        # 2. Survivability Multiplier (Only bet big if we are confident it fills)
        survival_mult = request.p_fill
        
        # 3. Correlation Penalty
        correlation_mult = 1.0 - request.correlation_risk_score
        
        scaled_stake = request.base_stake * regime_mult * survival_mult * correlation_mult
        
        # 4. Phase Constraint ceiling (e.g. if we are in MICRO phase, we can't bet $1000)
        # Cap a single bet at 10% of the currently allocated phase capital max
        max_single_bet = current_phase_max_capital * 0.10
        
        final_stake = min(scaled_stake, max_single_bet)
        
        logger.debug(f"[POSITION SIZING] Base: ${request.base_stake:.2f} | Regime: {request.regime} | Final: ${final_stake:.2f}")
        return final_stake

position_sizer = RegimeSensitivePositionSizing()
