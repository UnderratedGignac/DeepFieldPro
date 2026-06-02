import logging
import time
import uuid
from typing import Dict, Any

logger = logging.getLogger(__name__)

class LatencyTelemetry:
    """
    Provides nanoscopic visibility into the Live Execution DOM interactions.
    Tracks Detection-to-Confirmed-Bet Latency as the ultimate KPI.
    """
    def __init__(self):
        self.active_executions = {}
        self.execution_history = []

    def start_execution(self, bet_payload: Dict[str, Any]) -> str:
        exec_id = str(uuid.uuid4())
        
        # We use time.perf_counter() for microsecond resolution
        start_time = time.perf_counter()
        
        self.active_executions[exec_id] = {
            "player": bet_payload.get("player"),
            "market": bet_payload.get("market"),
            "timestamps": {
                "market_detected": start_time
            }
        }
        return exec_id

    def mark(self, exec_id: str, stage: str):
        """
        Records the exact time a DOM interaction phase completed.
        Stages: click_sent, betslip_opened, stake_entered, confirm_clicked, confirmation_received
        """
        if exec_id in self.active_executions:
            self.active_executions[exec_id]["timestamps"][stage] = time.perf_counter()

    def finalize(self, exec_id: str):
        if exec_id not in self.active_executions:
            return
            
        record = self.active_executions.pop(exec_id)
        timestamps = record["timestamps"]
        
        # Calculate deltas
        t_detect = timestamps.get("market_detected", 0)
        t_click = timestamps.get("click_sent", t_detect)
        t_confirm = timestamps.get("confirm_clicked", t_click)
        t_receipt = timestamps.get("confirmation_received", t_confirm)
        
        bot_latency_ms = (t_confirm - t_detect) * 1000
        book_latency_ms = (t_receipt - t_confirm) * 1000
        total_latency_ms = (t_receipt - t_detect) * 1000
        
        record["metrics"] = {
            "bot_automation_latency_ms": bot_latency_ms,
            "bookmaker_network_latency_ms": book_latency_ms,
            "total_e2e_latency_ms": total_latency_ms
        }
        
        self.execution_history.append(record)
        
        logger.info(f"[TELEMETRY] {record['player']} {record['market']} Execution:")
        logger.info(f"  ├─ Bot DOM Nav    : {bot_latency_ms:.1f}ms")
        logger.info(f"  ├─ Book Network   : {book_latency_ms:.1f}ms")
        logger.info(f"  └─ Total E2E KPI  : {total_latency_ms:.1f}ms")

latency_tracker = LatencyTelemetry()
