import asyncio
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """
    Prevents cascading failures in the execution cluster.
    If a specific route fails repeatedly, it trips open and halts execution on that route.
    """

    def __init__(self, failure_threshold: int = 3, reset_timeout_sec: float = 60.0):
        self.failure_threshold = failure_threshold
        self.reset_timeout_sec = reset_timeout_sec
        self.failure_count = 0
        self.is_open = False
        self.last_failure_time = 0.0

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = asyncio.get_event_loop().time()
        if self.failure_count >= self.failure_threshold:
            self.is_open = True
            logger.critical("[CIRCUIT BREAKER] Tripped OPEN! Halting route execution.")

    def record_success(self):
        self.failure_count = 0
        self.is_open = False

    def can_execute(self) -> bool:
        if not self.is_open:
            return True

        # Check if timeout has expired to attempt a half-open state
        if (
            asyncio.get_event_loop().time() - self.last_failure_time
        ) > self.reset_timeout_sec:
            logger.info("[CIRCUIT BREAKER] Entering HALF-OPEN state. Testing route...")
            return True

        return False


class ActorOrchestrator:
    """
    Execution Orchestration Cluster.
    Distributed async workers, fault-tolerant execution queues, and circuit breakers.
    """

    def __init__(self):
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}

    def _get_circuit_breaker(self, route_id: str) -> CircuitBreaker:
        if route_id not in self.circuit_breakers:
            self.circuit_breakers[route_id] = CircuitBreaker()
        return self.circuit_breakers[route_id]

    async def execute_task(
        self, route_id: str, payload: Dict[str, Any], execute_fn: callable
    ):
        """
        Orchestrates an execution task with fault-tolerance and backpressure.
        """
        cb = self._get_circuit_breaker(route_id)

        if not cb.can_execute():
            logger.warning(
                f"[ORCHESTRATOR] Route {route_id} rejected by Circuit Breaker."
            )
            return {"status": "circuit_open_rejection"}

        try:
            # Simulate execution delegation to worker
            result = await execute_fn(payload)

            if result.get("status") == "success":
                cb.record_success()
            elif result.get("status") == "error":
                cb.record_failure()

            return result

        except Exception as e:
            logger.error(f"[ORCHESTRATOR] Worker exception on {route_id}: {e}")
            cb.record_failure()
            return {"status": "exception", "reason": str(e)}


orchestrator = ActorOrchestrator()
