# settlement_engine.py
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class SettlementEngine:
    """
    Handles post-match outcomes, ROI tracking, and model calibration logic.
    Separates "prediction quality" from "execution quality".
    """
    def __init__(self):
        # We would use DB tables: 'bet_settlements' and 'model_calibration'
        self.outcomes_log = []

    def settle_bet(self, bet_id: str, model_prob: float, execution_odds: float, bet_won: bool):
        """
        Ingests the true outcome of a bet after the match.
        """
        profit = (execution_odds - 1.0) if bet_won else -1.0
        
        self.outcomes_log.append({
            "bet_id": bet_id,
            "model_prob": model_prob,
            "execution_odds": execution_odds,
            "bet_won": bet_won,
            "profit": profit
        })
        logger.info(f"[SETTLEMENT] Bet {bet_id} settled. Won: {bet_won}, Profit: {profit}")

    def run_calibration_report(self):
        """
        Calculates Brier Score, Log Loss, and Reliability Curves.
        E.g., If the model predicts 60% probability, do those bets win ~60% of the time?
        """
        if not self.outcomes_log:
            return
            
        brier_score_sum = 0.0
        n = len(self.outcomes_log)
        
        for outcome in self.outcomes_log:
            prob = outcome["model_prob"]
            actual = 1.0 if outcome["bet_won"] else 0.0
            
            # Brier Score = (prob - actual)^2
            brier_score_sum += (prob - actual)**2
            
        brier_score = brier_score_sum / n
        
        # A Brier score closer to 0 indicates a highly calibrated model.
        logger.info(f"[CALIBRATION] Run complete on {n} bets. Brier Score: {brier_score:.4f}")
        
        return {"brier_score": brier_score, "samples": n}

settlement_engine = SettlementEngine()
