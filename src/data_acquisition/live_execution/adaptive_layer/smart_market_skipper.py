import logging

logger = logging.getLogger(__name__)

class SmartMarketSkipper:
    """
    Learns to SKIP markets that are too volatile, have low survivability,
    or negative expected realized EV.
    Saves API rate limits and prevents account flagging from excessive failed bets.
    """
    def __init__(self):
        self.MIN_EXPECTED_EV = 0.02 # 2% minimum expected EV
        self.MIN_SURVIVABILITY = 0.15 # Minimum 15% chance of filling

    def should_skip(self, market_type: str, expected_ev: float, p_fill: float, regime: str) -> str:
        """
        Returns a reason string if the market should be skipped, else None.
        """
        if regime == "frozen":
            return "Market is frozen"
            
        if expected_ev < self.MIN_EXPECTED_EV:
            return f"Expected EV ({expected_ev:.3f}) below threshold ({self.MIN_EXPECTED_EV})"
            
        if p_fill < self.MIN_SURVIVABILITY:
            return f"Survivability ({p_fill:.2f}) below threshold ({self.MIN_SURVIVABILITY})"
            
        return None

market_skipper = SmartMarketSkipper()
