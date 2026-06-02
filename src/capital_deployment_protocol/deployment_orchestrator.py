import logging
from typing import Dict, Any

from src.capital_deployment_protocol.schemas import DeploymentState, RolloutPhase, HealthStatus, CapitalAllocationRequest
from src.capital_deployment_protocol.rollout_state_machine import state_machine
from src.capital_deployment_protocol.capital_ramp_controller import ramp_controller
from src.capital_deployment_protocol.live_capital_switch import kill_switch
from src.capital_deployment_protocol.regime_sensitive_position_sizing import position_sizer

logger = logging.getLogger(__name__)

class DeploymentOrchestrator:
    """
    The Master Entrypoint for the Capital Deployment Protocol (CDP).
    1. Reads RVL Output.
    2. Evaluates state transitions (SHADOW -> MICRO -> LIMITED)
    3. Calculates available capital ramp.
    4. Routes execution through the Kill Switch and Position Sizer.
    """
    def __init__(self):
        # Persisted state (would be in DB)
        self.state = DeploymentState()

    def process_daily_lifecycle(self, is_rvl_passing: bool, current_drawdown: float):
        """
        Evaluates if the system should promote to the next phase, rollback, or stay.
        """
        logger.info("================================================")
        logger.info(f"=== CDP DAILY LIFECYCLE (Current Phase: {self.state.current_phase.value}) ===")
        logger.info("================================================")
        
        # Determine next phase
        next_phase = state_machine.evaluate_transition(self.state, is_rvl_passing)
        
        if next_phase != self.state.current_phase:
            days_in_phase = 0 # Reset counter on phase transition
        else:
            days_in_phase = self.state.days_in_phase + 1
            
        # Calculate new capital ceiling based on Ramp Controller
        max_cap = ramp_controller.compute_max_allocation(next_phase, days_in_phase)
        
        # BUG FIX: Health was binary (HEALTHY or CRITICAL). DEGRADED state (5-10%) was unreachable.
        if current_drawdown < 0.05:
            health = HealthStatus.HEALTHY
        elif current_drawdown < 0.12:
            health = HealthStatus.DEGRADED
        else:
            health = HealthStatus.CRITICAL

        # Update State
        self.state = DeploymentState(
            current_phase=next_phase,
            max_capital_allocation=max_cap,
            current_health=health,
            days_in_phase=days_in_phase,
            phase_drawdown_pct=current_drawdown
        )
        
        logger.info(f"[ORCHESTRATOR] State Updated. Phase: {next_phase.value} | Allocated Cap: ${max_cap:.2f}")

    def request_capital_execution(self, request: CapitalAllocationRequest, rvl_signal: str) -> float:
        """
        Execution Engine asks CDP if it can deploy capital for a specific bet.
        Returns the safe allowed stake size in dollars (0.0 if blocked).
        """
        # 1. Kill Switch Check
        is_safe = kill_switch.evaluate_safety_lock(self.state.current_health, rvl_signal)
        if not is_safe or self.state.current_phase == RolloutPhase.PHASE_0_SHADOW:
            return 0.0
            
        # 2. Position Sizing Check (Governed by Phase Cap)
        safe_stake = position_sizer.scale_position(request, self.state.max_capital_allocation)
        
        return safe_stake

cdp_orchestrator = DeploymentOrchestrator()
