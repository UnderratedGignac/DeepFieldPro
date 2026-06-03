import logging
import numpy as np
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


class StatisticalSignificanceTester:
    """
    Answers: "Is observed performance statistically meaningful or just noise?"
    W4 FIX: Implements bootstrap permutation test instead of assuming paired t-test.
    """

    def __init__(self):
        pass

    def run_significance_tests(
        self, dfp_returns: List[float], baseline_returns: List[float]
    ) -> Dict[str, Any]:
        """
        Runs statistical rigor on the returns series using permutation testing.
        """
        if len(dfp_returns) < 30:
            logger.warning(
                "[STAT TESTER] Insufficient sample size for significance testing (<30)."
            )
            return {
                "is_significant": False,
                "p_value": 1.0,
                "dfp_sharpe": 0.0,
                "base_sharpe": 0.0,
            }

        dfp_arr = np.array(dfp_returns)
        base_arr = np.array(baseline_returns)

        # 1. Permutation Test for P-Value
        # Null hypothesis: Both series come from the same distribution.
        observed_diff = np.mean(dfp_arr) - np.mean(base_arr)

        # If DFP is worse, it's not significantly better
        if observed_diff <= 0:
            p_value = 1.0
        else:
            pooled = np.concatenate([dfp_arr, base_arr])
            n_dfp = len(dfp_arr)
            n_permutations = 10000

            # Generate permutations
            count_greater = 0
            for _ in range(n_permutations):
                np.random.shuffle(pooled)
                perm_dfp = pooled[:n_dfp]
                perm_base = pooled[n_dfp:]
                perm_diff = np.mean(perm_dfp) - np.mean(perm_base)
                if perm_diff >= observed_diff:
                    count_greater += 1

            p_value = count_greater / n_permutations

        # 2. Sharpe Ratio (assuming Risk Free Rate = 0)
        dfp_sharpe = (
            (np.mean(dfp_arr) / np.std(dfp_arr)) * np.sqrt(365)
            if np.std(dfp_arr) > 0
            else 0
        )
        base_sharpe = (
            (np.mean(base_arr) / np.std(base_arr)) * np.sqrt(365)
            if np.std(base_arr) > 0
            else 0
        )

        is_significant = p_value < 0.05 and dfp_sharpe > base_sharpe

        logger.info(
            f"[STAT TESTER] Permutation P-Value: {p_value:.4f} | DFP Sharpe: {dfp_sharpe:.2f} | Base Sharpe: {base_sharpe:.2f}"
        )
        logger.info(f"[STAT TESTER] Is Significant Outperformance? {is_significant}")

        return {
            "is_significant": is_significant,
            "p_value": p_value,
            "dfp_sharpe": dfp_sharpe,
            "base_sharpe": base_sharpe,
        }


stat_tester = StatisticalSignificanceTester()
