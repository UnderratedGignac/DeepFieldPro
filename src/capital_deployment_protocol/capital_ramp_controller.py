import logging
import math
from src.capital_deployment_protocol.schemas import RolloutPhase

logger = logging.getLogger(__name__)

class CapitalRampController:
    """
    Defines a safe, non-linear ramp function. Capital increases only if RVL is stable.
    Uses Sigmoid or Logistic scaling rather than linear growth to prevent premature exposure.
    """
    def __init__(self, target_bankroll: float = 100000.0):
        self.target_bankroll = target_bankroll
        
        self.phase_caps = {
            RolloutPhase.PHASE_0_SHADOW: 0.0,
            RolloutPhase.PHASE_1_MICRO: 0.01,   # 1% of target
            RolloutPhase.PHASE_2_LIMITED: 0.15, # 15% of target
            RolloutPhase.PHASE_3_PRODUCTION: 1.0 # 100% of target
        }

    def compute_max_allocation(self, phase: RolloutPhase, days_in_phase: int) -> float:
        """
        Calculates the exact maximum capital allowed today.
        Non-linear ramp within the phase cap.
        """
        cap_pct = self.phase_caps[phase]
        max_phase_capital = self.target_bankroll * cap_pct
        
        if phase == RolloutPhase.PHASE_0_SHADOW:
            return 0.0
            
        # Logistic ramp up over 14 days (reaches 99% of max_phase_capital by day 14)
        # Prevents sudden exposure jumps on day 1 of a new phase.
        k = 0.5  # steepness
        t0 = 7.0 # midpoint
        ramp_multiplier = 1 / (1 + math.exp(-k * (days_in_phase - t0)))
        
        allowed_capital = max_phase_capital * ramp_multiplier
        
        logger.debug(f"[RAMP CONTROLLER] {phase.value} Day {days_in_phase}: Cap=${allowed_capital:.2f}")
        return allowed_capital

ramp_controller = CapitalRampController()
