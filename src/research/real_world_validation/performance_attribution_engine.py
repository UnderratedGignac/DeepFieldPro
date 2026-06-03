import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


class PerformanceAttributionEngine:
    """
    Breaks down system performance to isolate WHERE alpha is coming from or being lost.
    """

    def __init__(self):
        pass

    def attribute_performance(
        self, shadow_executions: List[Dict[str, Any]]
    ) -> Dict[str, float]:
        """
        Decomposes total return into predictive edge, execution friction, and capital efficiency.
        """
        total_theoretical_ev = 0.0
        total_latency_loss = 0.0
        total_realized_ev = 0.0

        for ex in shadow_executions:
            theo_ev = ex.get("expected_ev", 0)
            latency_ms = ex.get("actual_latency_ms", 0)
            realized_pnl = ex.get("realized_pnl", 0)

            total_theoretical_ev += theo_ev
            total_realized_ev += realized_pnl

            # Rough proxy: lose 0.01 EV per 100ms of execution friction latency
            total_latency_loss += (latency_ms / 100.0) * 0.01

        unexplained = total_realized_ev - (total_theoretical_ev - total_latency_loss)

        logger.info(f"[ATTRIBUTION] Total Theo EV: {total_theoretical_ev:.2f}")
        logger.info(f"[ATTRIBUTION] Lost to Latency: -{total_latency_loss:.2f}")
        logger.info(f"[ATTRIBUTION] Realized EV: {total_realized_ev:.2f}")

        return {
            "theoretical_edge": total_theoretical_ev,
            "latency_loss": total_latency_loss,
            "unexplained_variance": unexplained,
        }


attribution_engine = PerformanceAttributionEngine()
