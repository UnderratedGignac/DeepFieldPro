import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class ExecutionFailureClassifier:
    """
    Automatically classifies execution failures to guide the adaptive learning loops.
    Distinguishes between odds crashes, suspensions, network timeouts, and anti-bot flags.
    """

    def __init__(self):
        pass

    def classify(self, execution_result: Dict[str, Any], market_regime: str) -> str:
        """
        Determines the root cause of a rejected bet.
        """
        if execution_result.get("status") == "filled":
            return "none"

        reason = execution_result.get("reason", "").lower()
        latency = execution_result.get("execution_delay_ms", 0)

        if "suspended" in reason:
            if latency < 500:
                return "instant_suspension"  # Book reacted faster than us
            return "latency_suspension"  # We were too slow

        if "odds changed" in reason or "slippage" in reason:
            if market_regime in ["panic", "high-frequency-volatility"]:
                return "odds_crash_volatile"
            return "odds_crash_stable"

        if "timeout" in reason or latency > 8000:
            return "network_timeout"

        if "rejected" in reason or "limit" in reason:
            return "stake_limited"

        return "unknown_failure"


failure_classifier = ExecutionFailureClassifier()
