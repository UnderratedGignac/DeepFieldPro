import logging

from src.research.meta_governor.system_health_scorer import SystemHealthState

logger = logging.getLogger(__name__)


class LearningRateController:
    """
    Controls the learning speed of the APO (Policy Updates) and SCG (Stability Damping).
    Adapts the update magnitude based on the System Health and Meta-Regret.

    Formula: LR(t) = LR_base * exp(-alpha * max(0, MetaRegret - Threshold)) * HealthMultiplier
    """

    def __init__(self, base_lr: float = 0.05):
        self.base_lr = base_lr

    def compute_learning_rate(
        self, health: SystemHealthState, meta_regret: float
    ) -> float:
        """
        Dynamically throttles or freezes APO learning rates to prevent overfitting
        to noisy regret signals or oscillation collapse.
        """
        if health.is_collapsing:
            logger.critical("[LR CONTROLLER] System collapsing! FREEZING ALL LEARNING.")
            return 0.0

        if health.status == "DEGRADING":
            logger.warning(
                "[LR CONTROLLER] System degrading. Throttling learning rate by 75%."
            )
            return self.base_lr * 0.25

        # If Meta-Regret is climbing, the adaptive system is making things worse. Throttle.
        if meta_regret > 0.1:
            logger.warning(
                "[LR CONTROLLER] High Meta-Regret detected. Damping APO adaptation."
            )
            return self.base_lr * 0.5

        return self.base_lr


lr_controller = LearningRateController()
