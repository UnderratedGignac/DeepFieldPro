import logging
from typing import Dict, Any

from src.capital_scaling_intelligence.schemas import (
    ACSIScalingState,
    ScalingDecision,
)
from src.capital_scaling_intelligence.regime_compounding_detector import (
    compounding_detector,
)
from src.capital_scaling_intelligence.long_horizon_ev_forecaster import ev_forecaster
from src.capital_scaling_intelligence.growth_vs_risk_optimizer import growth_optimizer
from src.capital_scaling_intelligence.capital_velocity_controller import (
    velocity_controller,
)

logger = logging.getLogger(__name__)


class ACSIEngine:
    """
    Autonomous Capital Scaling Intelligence (ACSI).
    The long-horizon capital growth optimization system.
    Determines HOW FAST, WHEN, and UNDER WHAT CONDITIONS capital should scale.
    """

    def __init__(self):
        self.state = ACSIScalingState()

    def evaluate_capital_trajectory(
        self, system_inputs: Dict[str, Any]
    ) -> ACSIScalingState:
        """
        The Master ACSI Flow.
        """
        logger.info("==================================================")
        logger.info("=== ACSI CAPITAL TRAJECTORY OPTIMIZATION CYCLE ===")
        logger.info("==================================================")

        # 1. Detect structural compounding regime
        regime = compounding_detector.detect_regime(
            clv_stability=system_inputs.get("clv_stability", 0.0),
            friction_trend=system_inputs.get("friction_trend", 0.0),
            rvl_drift=system_inputs.get("rvl_drift", 0.0),
            drawdown_autocorr=system_inputs.get("drawdown_autocorr", 0.0),
        )

        # 2. Forecast EV under scaling pressure (using current velocity)
        projected_ev = ev_forecaster.forecast_ev_trajectory(
            current_ev=system_inputs.get("current_ev", 0.0),
            scaling_velocity=self.state.scaling_velocity,
        )

        # 3. Growth vs Risk Decision Engine
        decision = growth_optimizer.optimize_scaling_decision(
            regime=regime,
            projected_ev=projected_ev,
            drawdown_momentum=system_inputs.get("drawdown_momentum", 0.0),
        )

        # 4. Target velocity translation based on decision
        target_velocity = 0.0
        if decision == ScalingDecision.SCALE_UP:
            target_velocity = 0.05  # Accelerate: +5% allocation
        elif decision == ScalingDecision.SCALE_DOWN:
            target_velocity = -0.10  # Decelerate: -10% (fast derisking)
        elif decision == ScalingDecision.HOLD:
            target_velocity = 0.0  # Maintain: flat trajectory
        elif decision == ScalingDecision.FREEZE_SCALING:
            # BUG FIX: This branch was missing. FREEZE means slow to near-zero, NOT hold.
            # Gently bleeds out any positive velocity without aggressively scaling down.
            target_velocity = -0.01

        # 5. Capital Velocity Controller (Damps acceleration)
        final_velocity = velocity_controller.compute_safe_velocity(
            current_velocity=self.state.scaling_velocity,
            target_velocity=target_velocity,
        )

        # Update internal state
        self.state = ACSIScalingState(
            current_compounding_regime=regime,
            long_horizon_ev_trend=projected_ev,
            scaling_velocity=final_velocity,
            current_decision=decision,
        )

        logger.info(
            f"[ACSI ENGINE] Final Trajectory State -> Decision: {decision.value} | Approved Scaling Velocity: {final_velocity*100:.2f}%"
        )
        return self.state


acsi_engine = ACSIEngine()
