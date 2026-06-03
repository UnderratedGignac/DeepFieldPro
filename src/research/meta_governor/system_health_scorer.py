import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SystemHealthState:
    score: float
    is_collapsing: bool
    status: str


class SystemHealthScorer:
    """
    Evaluates system-wide performance using external truth signals.
    Combines Realized EV, CLV Stability, Drawdown, and Meta-Regret.

    Formula: Health = (w1 * RealizedEV) + (w2 * CLV_Stability) - (w3 * Drawdown) - (w4 * MetaRegret)
    """

    def __init__(self):
        self.w1 = 0.4
        self.w2 = 0.3
        self.w3 = 0.2
        self.w4 = 0.1

    def evaluate_health(
        self,
        realized_ev_trend: float,
        clv_stability: float,
        current_drawdown: float,
        meta_regret: float,
    ) -> SystemHealthState:
        """
        Determines the global health score of the executing organism.
        """
        # Normalize metrics to [0, 1] range internally (mock logic)
        score = (
            (self.w1 * realized_ev_trend)
            + (self.w2 * clv_stability)
            - (self.w3 * current_drawdown)
            - (self.w4 * meta_regret)
        )

        is_collapsing = False
        status = "HEALTHY"

        if score < -0.2 or current_drawdown > 0.20:
            is_collapsing = True
            status = "COLLAPSING"
        elif score < 0.0:
            status = "DEGRADING"

        logger.info(f"[HEALTH SCORER] Score: {score:.3f} | Status: {status}")

        return SystemHealthState(
            score=round(score, 3), is_collapsing=is_collapsing, status=status
        )


health_scorer = SystemHealthScorer()
