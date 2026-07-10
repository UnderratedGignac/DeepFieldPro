import logging

from src.capital_deployment_protocol.schemas import CapitalAllocationRequest
from src.capital_deployment_protocol.cdp_config import cdp_config

logger = logging.getLogger(__name__)


class RegimeSensitivePositionSizing:
    """
    Dynamically sizes positions based on market regime and execution fragility.
    
    All regime multipliers are configurable via environment variables to enable
    optimization based on empirical performance data.
    """

    def __init__(self):
        # Multipliers based on regime hostility (loaded from config, no hardcoding)
        self.regime_multipliers = cdp_config.REGIME_MULTIPLIERS

    def scale_position(
        self, request: CapitalAllocationRequest, current_phase_max_capital: float
    ) -> float:
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

        scaled_stake = (
            request.base_stake * regime_mult * survival_mult * correlation_mult
        )

        # 4. Phase Constraint ceiling (e.g. if we are in MICRO phase, we can't bet $1000)
        # Cap a single bet at configurable % of the currently allocated phase capital max
        max_single_bet = current_phase_max_capital * cdp_config.MAX_SINGLE_BET_PCT

        final_stake = min(scaled_stake, max_single_bet)

        logger.debug(
            f"[POSITION SIZING] Base: ${request.base_stake:.2f} | Regime: {request.regime} | Final: ${final_stake:.2f}"
        )
        return final_stake


position_sizer = RegimeSensitivePositionSizing()
