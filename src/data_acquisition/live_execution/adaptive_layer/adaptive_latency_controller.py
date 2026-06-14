import logging

logger = logging.getLogger(__name__)


class AdaptiveLatencyController:
    """
    Dynamically adjusts the queue delay and execution aggressiveness
    based on the current market velocity and bookmaker profile.
    """

    def __init__(self):
        # Target E2E latency in milliseconds
        self.target_latency = 1500

    def get_latency_profile(self, regime: str, volatility: float) -> str:
        """
        Determines how aggressively the Live Execution Manager should act.
        """
        if regime == "panic" or volatility > 0.8:
            return "ULTRA_AGGRESSIVE"  # Skip batching, execute immediately, accept higher slippage

        if regime == "stable":
            return "BATCH_MODE"  # Safe to batch, minimize API load

        return "STANDARD"


latency_controller = AdaptiveLatencyController()
