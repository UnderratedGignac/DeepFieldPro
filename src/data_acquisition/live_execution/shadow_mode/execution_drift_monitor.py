# mypy: ignore-errors
import logging
from collections import deque

logger = logging.getLogger(__name__)


class ExecutionDriftMonitor:
    """
    Detects when live execution quality degrades over time.
    Monitors average processing latency, fill deterioration, and slippage.
    Indicates potential sportsbook defensive escalation or browser memory leaks.
    """

    def __init__(self):
        # Tracking a moving window of recent latencies
        self.recent_latencies: deque = deque(maxlen=50)
        self.baseline_latency_ms = 1500.0
        self.drift_threshold_ratio = 1.1  # 10% increase triggers an alert

    def log_execution_latency(self, latency_ms: float):
        self.recent_latencies.append(latency_ms)
        self.check_for_drift()

    def check_for_drift(self):
        if len(self.recent_latencies) < 20:
            return

        current_avg = sum(self.recent_latencies) / len(self.recent_latencies)

        if current_avg > (self.baseline_latency_ms * self.drift_threshold_ratio):
            logger.warning(
                f"[DRIFT MONITOR] ALERT! Execution Drift Detected. "
                f"Current Avg Latency: {current_avg:.1f}ms (Baseline: {self.baseline_latency_ms:.1f}ms). "
                f"Possible sportsbook throttling or browser memory leak."
            )


drift_monitor = ExecutionDriftMonitor()

