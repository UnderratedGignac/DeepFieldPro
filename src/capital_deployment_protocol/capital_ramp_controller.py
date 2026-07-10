import logging
import math
from src.capital_deployment_protocol.schemas import RolloutPhase
from src.capital_deployment_protocol.cdp_config import cdp_config

logger = logging.getLogger(__name__)


class CapitalRampController:
    """
    Defines a safe, non-linear ramp function. Capital increases only if RVL is stable.
    Uses Sigmoid/Logistic scaling rather than linear growth to prevent premature exposure.
    W2 FIX: Now accepts acsi_velocity from the ACSI engine to modulate the ceiling
    dynamically — ACSI SCALE_DOWN actually compresses the allowed capital.
    
    All parameters are configurable via environment variables for optimization.
    """

    def __init__(self, target_bankroll: float = None):
        # Use config value if not explicitly provided (allows override)
        self.target_bankroll = target_bankroll if target_bankroll is not None else cdp_config.TARGET_BANKROLL
        # Phase caps loaded from centralized config (no hardcoding)
        self.phase_caps = {
            RolloutPhase.PHASE_0_SHADOW: cdp_config.PHASE_0_CAP_PCT,
            RolloutPhase.PHASE_1_MICRO: cdp_config.PHASE_1_CAP_PCT,
            RolloutPhase.PHASE_2_LIMITED: cdp_config.PHASE_2_CAP_PCT,
            RolloutPhase.PHASE_3_PRODUCTION: cdp_config.PHASE_3_CAP_PCT,
        }

    def compute_max_allocation(
        self, phase: RolloutPhase, days_in_phase: int, acsi_velocity: float = 0.0
    ) -> float:
        """
        Calculates the exact maximum capital allowed today.
        Non-linear logistic ramp within the phase cap, modulated by ACSI velocity.

        acsi_velocity: float in [-0.10, +0.10]
          - Positive → ACSI says SCALE_UP  → multiplier > 1.0 (up to 1.5x)
          - Zero     → ACSI says HOLD      → multiplier = 1.0 (baseline)
          - Negative → ACSI says SCALE_DOWN → multiplier < 1.0 (down to 0.5x)
        """
        cap_pct = self.phase_caps[phase]
        max_phase_capital = self.target_bankroll * cap_pct

        if phase == RolloutPhase.PHASE_0_SHADOW:
            return 0.0

        # Logistic day-ramp with configurable parameters
        # Default: reaches ~99% of max_phase_capital by day 14
        k = cdp_config.RAMP_STEEPNESS
        t0 = cdp_config.RAMP_MIDPOINT_DAY
        day_ramp = 1 / (1 + math.exp(-k * (days_in_phase - t0)))

        # W2 FIX: ACSI velocity modulation.
        # Map velocity [-0.10, +0.10] linearly to multiplier [0.5, 1.5]
        # Clamp to safe bounds: min 0.5x, max 1.5x.
        acsi_multiplier = 1.0 + (acsi_velocity * cdp_config.ACSI_MULTIPLIER_SCALE)
        acsi_multiplier = max(
            cdp_config.ACSI_MULTIPLIER_MIN, 
            min(cdp_config.ACSI_MULTIPLIER_MAX, acsi_multiplier)
        )

        allowed_capital = max_phase_capital * day_ramp * acsi_multiplier

        logger.debug(
            f"[RAMP CONTROLLER] {phase.value} Day {days_in_phase} | "
            f"DayRamp={day_ramp:.3f} | ACSIMult={acsi_multiplier:.2f} | "
            f"Cap=${allowed_capital:.2f}"
        )
        return allowed_capital


ramp_controller = CapitalRampController()
