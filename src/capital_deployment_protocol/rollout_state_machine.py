import logging
from src.capital_deployment_protocol.schemas import RolloutPhase, DeploymentState

logger = logging.getLogger(__name__)


class RolloutStateMachine:
    """
    Enforces strict transitions: SHADOW -> MICRO -> LIMITED -> FULL.
    Cannot skip phases. Must support rollback.
    """

    def __init__(self):
        self.phase_requirements = {
            RolloutPhase.PHASE_0_SHADOW: {
                "min_days": 14,
                "max_drawdown": 0.0,
                "next": RolloutPhase.PHASE_1_MICRO,
            },
            RolloutPhase.PHASE_1_MICRO: {
                "min_days": 7,
                "max_drawdown": 0.05,
                "next": RolloutPhase.PHASE_2_LIMITED,
            },
            RolloutPhase.PHASE_2_LIMITED: {
                "min_days": 14,
                "max_drawdown": 0.10,
                "next": RolloutPhase.PHASE_3_PRODUCTION,
            },
            RolloutPhase.PHASE_3_PRODUCTION: {
                "min_days": 0,
                "max_drawdown": 0.15,
                "next": None,
            },
        }

    def evaluate_transition(
        self, current_state: DeploymentState, is_rvl_passing: bool
    ) -> RolloutPhase:
        """
        Determines if the system is allowed to scale up or if it must rollback.
        """
        phase_config = self.phase_requirements[current_state.current_phase]

        # 1. Rollback Condition (Drawdown Violation)
        if current_state.phase_drawdown_pct > phase_config["max_drawdown"]:
            logger.critical(
                f"[STATE MACHINE] Drawdown {current_state.phase_drawdown_pct:.2f} exceeded phase limit {phase_config['max_drawdown']:.2f}!"
            )
            return self._trigger_rollback(current_state.current_phase)

        # 2. Progress Condition
        can_advance = (
            current_state.days_in_phase >= phase_config["min_days"] and is_rvl_passing
        )

        if can_advance and phase_config["next"]:
            logger.info(f"[STATE MACHINE] Promoting system to {phase_config['next']}")
            return phase_config["next"]

        return current_state.current_phase

    def _trigger_rollback(self, current_phase: RolloutPhase) -> RolloutPhase:
        if current_phase == RolloutPhase.PHASE_3_PRODUCTION:
            return RolloutPhase.PHASE_2_LIMITED
        elif current_phase == RolloutPhase.PHASE_2_LIMITED:
            return RolloutPhase.PHASE_1_MICRO
        else:
            return RolloutPhase.PHASE_0_SHADOW


state_machine = RolloutStateMachine()
