import logging

from src.research.real_world_validation.baseline_comparison_engine import baseline_engine
from src.research.real_world_validation.statistical_significance_tester import stat_tester
from src.research.real_world_validation.performance_attribution_engine import attribution_engine
from src.research.real_world_validation.execution_friction_analyzer import friction_analyzer
from src.research.real_world_validation.reality_alignment_check import reality_checker

logger = logging.getLogger(__name__)

class SystemReadinessGate:
    """
    The RVL Final Decision Layer.
    Only allows READY_FOR_CAPITAL if all scientific checks pass.
    """
    def __init__(self):
        pass

    def evaluate_readiness(self, dfp_returns: list, base_returns: list, shadow_logs: list) -> str:
        """
        The Master Gate.
        """
        logger.info("================================================")
        logger.info("=== REAL-WORLD VALIDATION LAYER (RVL) GATE ===")
        logger.info("================================================")
        
        # 1. Baseline Compare
        base_metrics = baseline_engine.compare_against_baselines(shadow_logs)
        beats_baseline = base_metrics.get("delta_vs_best_baseline", -1) > 0
        
        # 2. Stats Test
        stat_metrics = stat_tester.run_significance_tests(dfp_returns, base_returns)
        is_significant = stat_metrics.get("is_significant", False)
        
        # 3. Attribution
        attribution_engine.attribute_performance(shadow_logs)
        
        # 4. Friction
        fric_metrics = friction_analyzer.analyze_friction(shadow_logs)
        is_friction_stable = fric_metrics.get("is_stable", False)
        
        # 5. Reality Alignment
        is_aligned = reality_checker.check_alignment(
            dfp_return=base_metrics.get("dfp_return", 0), 
            theo_edge=sum(ex.get("expected_ev", 0) for ex in shadow_logs)
        )
        
        # --- THE FINAL VOTE (all checks evaluated independently, no short-circuits) ---
        # Priority 1: Hard failure — didn't beat any baseline at all
        if not beats_baseline:
            logger.critical("[RVL GATE] FAILED: Did not beat simple baselines.")
            return "NOT_READY"
            
        # Priority 2: Reality drift or execution instability — needs more data
        if not is_aligned or not is_friction_stable:
            logger.warning("[RVL GATE] CONDITIONALLY FAILED: Reality divergence or friction instability.")
            return "SHADOW_VALIDATION_REQUIRED"

        # Priority 3: Beat baseline but can't prove it statistically — accumulate more data
        if not is_significant:
            logger.warning("[RVL GATE] CONDITIONAL: Outperformed baseline, but not statistically significant yet.")
            return "CONDITIONALLY_READY"
            
        # Priority 4: All checks pass
        logger.info("[RVL GATE] PASSED! ALL CHECKS CLEAR. SYSTEM IS ROBUST.")
        return "READY_FOR_CAPITAL"

rvl_gate = SystemReadinessGate()
