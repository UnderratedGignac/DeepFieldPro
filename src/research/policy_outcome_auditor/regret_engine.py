import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class RegretEngine:
    """
    Phase 3: Regret Engine (The Heart).
    Regret is NOT loss. It is: BestPossibleOutcome - ChosenOutcome.
    """
    def __init__(self):
        pass

    def compute_regret(self, decision_action: str, cf_execute_ev: float, cf_skip_ev: float) -> Dict[str, Any]:
        """
        Computes the regret of the chosen action against the counterfactuals.
        """
        regret = 0.0
        label = "UNKNOWN"
        
        if decision_action == "SKIP":
            # If we skipped, our EV is 0. If executing would have yielded positive EV, we regret it.
            regret = max(cf_execute_ev - cf_skip_ev, 0.0)
            
            if regret > 0.05:
                label = "OVER_CONSERVATIVE"
            else:
                label = "CORRECT"
                
        elif decision_action in ["EXECUTE", "BATCH"]:
            # If we executed, our EV is cf_execute_ev. If it was negative, we regret not skipping.
            regret = max(cf_skip_ev - cf_execute_ev, 0.0)
            
            if regret > 0.05:
                label = "OVER_AGGRESSIVE"
            else:
                label = "CORRECT"
                
        logger.debug(f"[REGRET ENGINE] Action: {decision_action} | Regret: {regret:.3f} | Label: {label}")
        
        return {
            "regret_value": round(regret, 4),
            "label": label
        }

regret_engine = RegretEngine()
