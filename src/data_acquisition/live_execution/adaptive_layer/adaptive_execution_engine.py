import logging
from typing import Dict, Any

from .autonomous_queue_optimizer import queue_optimizer
from .autonomous_stake_allocator import stake_allocator
from .live_execution_feedback_loop import feedback_loop

logger = logging.getLogger(__name__)


class AdaptiveExecutionEngine:
    """
    The orchestrator of the Adaptive Market Intelligence Layer.
    Ties together the queue optimizer, stake allocator, and live execution wrappers.
    This acts as the bridge between the raw betting algorithms and the live sportsbook DOM.
    """

    def __init__(self):
        pass

    def evaluate_and_route(
        self, edge_data: Dict[str, Any], odds_event: Any, lineup_confidence: float
    ):
        """
        Takes raw theoretical EV and passes it through the Adaptive Layer to
        calculate true executable priority, sizing, and survivability.
        """
        market = odds_event.market_type
        fixture_id = odds_event.fixture_id

        # 1. Base Metadata
        bet_metadata = {
            "fixture_id": fixture_id,
            "market": market,
            "player": odds_event.normalized_name,
            "odds": odds_event.decimal_odds,
            "volatility": 0.5,  # In reality, pulled from velocity tracker
            "confidence": lineup_confidence,
            "selection_id": "mock_123",
        }

        # 2. Add to Self-Learning Queue (Calculates p_fill, expected_ev, and skips bad markets)
        # Note: In production, queue_optimizer mutates state and stores the bet.
        queue_optimizer.evaluate_and_queue(edge_data, bet_metadata)

    async def flush_and_execute_batch(self, simulator_or_live_trader):
        """
        Pops bets from the optimized queue, allocates stake, and routes them
        to the execution infrastructure (Live Paper Trader or Simulator).
        """
        if not queue_optimizer.queue:
            return

        logger.info(
            f"[ADAPTIVE ENGINE] Flushing {len(queue_optimizer.queue)} bets from Autonomous Queue."
        )

        for bet in queue_optimizer.queue:
            # 3. Autonomous Stake Allocation
            stake = stake_allocator.allocate_stake(
                expected_ev=bet["expected_ev"],
                p_fill=bet["p_fill"],
                odds=bet["odds"],
                market_regime=bet["regime"],
            )

            if stake <= 0.0:
                logger.info(
                    f"[ADAPTIVE ENGINE] Skipped {bet['market']} for {bet['player']} due to $0.00 stake allocation."
                )
                continue

            bet["stake"] = stake

            # 4. Route to Execution (We pass this to the Live Paper Trader or Simulator)
            # For modularity, we assume the caller provides the execution function
            logger.info(
                f"[ADAPTIVE ENGINE] Routing {bet['market']} | Stake: ${stake} | EV: {bet['expected_ev']:.3f} | p(Fill): {bet['p_fill']:.2f}"
            )

            # Simulated Execution Outcome
            result = simulator_or_live_trader(bet)

            # 5. Live Feedback Loop
            # Enrich with required metadata
            if result:
                result["market_type"] = bet["market"]
                result["fixture_id"] = bet["fixture_id"]
                result["regime"] = bet["regime"]
                result["player_name"] = bet["player"]
                feedback_loop.process_execution_outcome(result, dispatcher=None)

        queue_optimizer.queue.clear()


adaptive_engine = AdaptiveExecutionEngine()
