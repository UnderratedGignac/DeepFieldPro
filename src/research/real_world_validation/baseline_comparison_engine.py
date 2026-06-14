import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


class BaselineComparisonEngine:
    """
    Compares DeepFieldPro's Realized EV against static baselines in shadow mode.
    Baselines:
    1. Always Execute Positive EV
    2. Static EV Threshold (no adaptation)
    3. Random Execution
    4. Simple CLV heuristic
    """

    def __init__(self):
        pass

    def compare_against_baselines(
        self, shadow_executions: List[Dict[str, Any]]
    ) -> Dict[str, float]:
        """
        Calculates the theoretical return of baseline strategies against the same dataset.
        Returns the delta between DeepFieldPro and the baselines.
        """
        if not shadow_executions:
            return {}

        dfp_return = sum(ex.get("realized_pnl", 0) for ex in shadow_executions)

        # 1. Always Execute +EV (No survivability filtering)
        baseline_always_exec = sum(
            ex.get("theoretical_pnl_if_executed", 0)
            for ex in shadow_executions
            if ex.get("expected_ev", 0) > 0
        )

        # 2. Static Threshold (e.g. EV > 0.05, no APO/MGL adaptation)
        baseline_static = sum(
            ex.get("theoretical_pnl_if_executed", 0)
            for ex in shadow_executions
            if ex.get("expected_ev", 0) > 0.05
        )

        logger.info(f"[BASELINE ENGINE] DFP Return: ${dfp_return:.2f}")
        logger.info(
            f"[BASELINE ENGINE] Always Execute +EV Return: ${baseline_always_exec:.2f}"
        )
        logger.info(
            f"[BASELINE ENGINE] Static Threshold Return: ${baseline_static:.2f}"
        )

        return {
            "dfp_return": dfp_return,
            "baseline_always_execute": baseline_always_exec,
            "baseline_static_threshold": baseline_static,
            "delta_vs_best_baseline": dfp_return
            - max(baseline_always_exec, baseline_static),
        }


baseline_engine = BaselineComparisonEngine()
