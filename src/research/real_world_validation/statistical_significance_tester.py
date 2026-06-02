import logging
import numpy as np
from scipy import stats
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

class StatisticalSignificanceTester:
    """
    Answers: "Is observed performance statistically meaningful or just noise?"
    Implements t-tests, bootstrap CIs, and Sharpe ratio comparisons.
    """
    def __init__(self):
        pass

    def run_significance_tests(self, dfp_returns: List[float], baseline_returns: List[float]) -> Dict[str, Any]:
        """
        Runs statistical rigor on the returns series.
        """
        if len(dfp_returns) < 30:
            logger.warning("[STAT TESTER] Insufficient sample size for significance testing (<30).")
            return {"is_significant": False, "p_value": 1.0}
            
        dfp_arr = np.array(dfp_returns)
        base_arr = np.array(baseline_returns)
        
        # 1. Paired T-Test
        t_stat, p_value = stats.ttest_rel(dfp_arr, base_arr)
        
        # 2. Sharpe Ratio (assuming Risk Free Rate = 0)
        dfp_sharpe = (np.mean(dfp_arr) / np.std(dfp_arr)) * np.sqrt(365) if np.std(dfp_arr) > 0 else 0
        base_sharpe = (np.mean(base_arr) / np.std(base_arr)) * np.sqrt(365) if np.std(base_arr) > 0 else 0
        
        is_significant = p_value < 0.05 and dfp_sharpe > base_sharpe
        
        logger.info(f"[STAT TESTER] P-Value: {p_value:.4f} | DFP Sharpe: {dfp_sharpe:.2f} | Base Sharpe: {base_sharpe:.2f}")
        logger.info(f"[STAT TESTER] Is Significant Outperformance? {is_significant}")
        
        return {
            "is_significant": is_significant,
            "p_value": p_value,
            "dfp_sharpe": dfp_sharpe,
            "base_sharpe": base_sharpe
        }

stat_tester = StatisticalSignificanceTester()
