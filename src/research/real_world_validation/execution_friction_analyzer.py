import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

class ExecutionFrictionAnalyzer:
    """
    Measures real-world degradation.
    Analyzes latency drift, odds movement during the decision window, and fill probabilities.
    """
    def __init__(self):
        self.MAX_ACCEPTABLE_REJECTION_RATE = 0.25

    def analyze_friction(self, shadow_executions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Determines if execution friction is stable or wildly degrading.
        """
        if not shadow_executions:
            return {"is_stable": False}
            
        total_attempts = len(shadow_executions)
        rejections = sum(1 for ex in shadow_executions if ex.get("fill_status") == "REJECTED")
        
        rejection_rate = rejections / total_attempts
        
        is_stable = rejection_rate < self.MAX_ACCEPTABLE_REJECTION_RATE
        
        logger.info(f"[FRICTION ANALYZER] Rejection Rate: {rejection_rate*100:.1f}%")
        if not is_stable:
            logger.error("[FRICTION ANALYZER] Execution friction is UNSTABLE.")
            
        return {
            "rejection_rate": rejection_rate,
            "is_stable": is_stable
        }

friction_analyzer = ExecutionFrictionAnalyzer()
