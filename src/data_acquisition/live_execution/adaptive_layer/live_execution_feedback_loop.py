# mypy: ignore-errors
import logging
from typing import Dict, Any

from .execution_behavior_memory import behavior_memory
from .edge_decay_predictor import decay_predictor
from .adaptive_events import ExecutionFailureEvent

logger = logging.getLogger(__name__)


class LiveExecutionFeedbackLoop:
    """
    Closes the loop between execution outcome and adaptive models.
    Every live execution outcome must immediately feed back into:
    survivability models, queue optimization, regime classification, and latency adjustments.
    """

    def __init__(self):
        pass

    def process_execution_outcome(self, exec_data: Dict[str, Any], dispatcher):
        """
        Called immediately after a live/simulated bet confirms or fails.
        """
        # 1. Record to SQLite Database
        behavior_memory.record_execution(exec_data)

        status = exec_data.get("status")
        market_type = exec_data.get("market_type")
        time_elapsed = exec_data.get("time_since_lineup", 0)

        # 2. Update Edge Decay Half-Life if bet failed due to odds crash
        if (
            status == "rejected"
            and exec_data.get("failure_classification") == "odds_crash"
        ):
            # Market decayed faster than we anticipated. Reduce the base half-life.
            # Very simplistic ML heuristic: we assume the true half-life was 0.8x the elapsed time
            implied_half_life = max(0.5, time_elapsed * 0.8)
            decay_predictor.update_base_half_life(market_type, implied_half_life)

        # 3. Emit Failure Events for Anomaly Detection
        if status == "rejected":
            failure_event = ExecutionFailureEvent(  # noqa: F841
                exec_id=exec_data.get("exec_id", "unknown"),
                failure_classification=exec_data.get(
                    "failure_classification", "unknown"
                ),
                latency_ms=exec_data.get("total_latency_ms", 0.0),
                market_regime=exec_data.get("regime", "unknown"),
                timestamp=exec_data.get("timestamp"),
            )
            # dispatcher.emit(failure_event)

        logger.info(
            f"[FEEDBACK LOOP] Processed outcome for {market_type}. Status: {status}"
        )


feedback_loop = LiveExecutionFeedbackLoop()
