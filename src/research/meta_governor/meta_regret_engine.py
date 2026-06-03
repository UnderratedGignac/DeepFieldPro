import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class MetaRegretMetrics:
    baseline_ev: float
    adaptive_system_ev: float
    meta_regret: float


class MetaRegretEngine:
    """
    Computes the Meta-Regret: The performance of the (POA + APO + SCG) adaptive
    system compared to a static baseline policy over a rolling window.

    Formula: MetaRegret = max(BaselineRealizedEV - AdaptiveSystemRealizedEV, 0)
    """

    def __init__(self):
        pass

    def compute_meta_regret(self, rolling_decisions: list) -> MetaRegretMetrics:
        """
        Calculates if the learning system itself is actually producing value.
        """
        # Mock calculation logic
        baseline_ev = 0.0
        adaptive_ev = 0.0

        for decision in rolling_decisions:
            # Reconstruct what the static baseline would have realized
            static_outcome = decision.get("baseline_realized_ev", 0)
            baseline_ev += static_outcome

            # What the adaptive system realized
            adaptive_outcome = decision.get("adaptive_realized_ev", 0)
            adaptive_ev += adaptive_outcome

        meta_regret = max(baseline_ev - adaptive_ev, 0.0)

        return MetaRegretMetrics(
            baseline_ev=baseline_ev,
            adaptive_system_ev=adaptive_ev,
            meta_regret=meta_regret,
        )


meta_regret_engine = MetaRegretEngine()
