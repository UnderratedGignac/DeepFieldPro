# clv_engine.py
import logging

logger = logging.getLogger(__name__)

class CLVEngine:
    """
    Formalizes Closing Line Value tracking. 
    CLV = (execution_odds / closing_odds) - 1
    This is the ultimate validation metric for the pricing engine.
    """
    def __init__(self):
        # We would normally use a DB table for this, e.g., 'clv_history'
        self.bet_ledger = {}

    def register_execution(self, bet_id: str, execution_odds: float):
        """
        Called when the execution queue successfully places a bet.
        """
        self.bet_ledger[bet_id] = {
            "execution_odds": execution_odds,
            "closing_odds": None,
            "clv_percentage": None
        }

    def record_closing_line(self, bet_id: str, closing_odds: float):
        """
        Called right at kickoff when the market closes.
        """
        if bet_id in self.bet_ledger:
            execution_odds = self.bet_ledger[bet_id]["execution_odds"]
            self.bet_ledger[bet_id]["closing_odds"] = closing_odds
            
            # CLV calculation
            clv = (execution_odds / closing_odds) - 1.0
            self.bet_ledger[bet_id]["clv_percentage"] = clv
            
            direction = "Positive" if clv > 0 else "Negative"
            logger.info(f"[CLV TRACKER] Bet {bet_id}: Execution @ {execution_odds}, Closing @ {closing_odds}. {direction} CLV: {clv*100:.2f}%")

clv_engine = CLVEngine()
