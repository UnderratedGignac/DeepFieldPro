import asyncio
import logging
import random
import uuid
import sys
from datetime import datetime, timezone

sys.path.insert(0, "C:/Users/Elie/DeepFieldPro")

from src.data_acquisition.live_execution.adaptive_layer.adaptive_events import (
    MarketVelocityChangedEvent,
)
from src.data_acquisition.live_execution.adaptive_layer.market_velocity_tracker import (
    velocity_tracker,
)
from src.data_acquisition.live_execution.adaptive_layer.market_regime_classifier import (
    regime_classifier,
)
from src.data_acquisition.live_execution.adaptive_layer.edge_decay_predictor import (
    decay_predictor,
)
from src.data_acquisition.live_execution.adaptive_layer.adaptive_execution_engine import (
    adaptive_engine,
)
from src.data_acquisition.live_execution.adaptive_layer.execution_failure_classifier import (
    failure_classifier,
)
from src.data_acquisition.live_execution.adaptive_layer.execution_heatmap_engine import (
    heatmap_engine,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def mock_live_trader(bet):
    """
    Simulates a live execution that fails if latency > decay limit.
    """
    exec_id = str(uuid.uuid4())
    # Mocking that goalscorers fail often due to panic regimes
    latency_ms = random.uniform(500, 2500)

    status = "filled"
    reason = ""

    if bet["regime"] == "panic" and latency_ms > 800:
        status = "rejected"
        reason = "Market suspended"
    elif bet["market"] == "player_goal_anytime" and latency_ms > 1200:
        status = "rejected"
        reason = "Odds changed significantly"

    result = {
        "exec_id": exec_id,
        "status": status,
        "reason": reason,
        "execution_delay_ms": latency_ms,
        "theoretical_ev": bet["expected_ev"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    result["failure_classification"] = failure_classifier.classify(
        result, bet["regime"]
    )

    if status == "filled":
        result["realized_ev"] = bet["expected_ev"] * 0.9  # Slippage
    else:
        result["realized_ev"] = 0.0

    return result


async def run_adaptive_simulation():
    logger.info("===========================================================")
    logger.info("=== ADAPTIVE MARKET INTELLIGENCE LAYER SIMULATION =======")
    logger.info("===========================================================")

    fixture_id = "MOCK_LIVE_1"

    # 1. Market Velocity & Regime Transition
    logger.info("\n[STAGE 1] Lineup Leaked -> Tracking Velocity -> Regime Transition")
    for i in range(5):  # Simulate 5 rapid odds updates
        vel = velocity_tracker.record_odds_update(
            fixture_id, "player_goal_anytime", 2.5, 2.3, None
        )

    vel_event = MarketVelocityChangedEvent(
        fixture_id, "player_goal_anytime", vel, 0.0, str(datetime.now())
    )
    new_regime = regime_classifier.classify(vel_event, None)

    logger.info(
        f"Velocity Score: {vel:.1f} -> Regime dynamically shifted to: {new_regime}"
    )

    # 2. Adaptive Execution Routing
    logger.info("\n[STAGE 2] Evaluating Edges via Autonomous Queue Optimizer")

    mock_edges = [
        {
            "market_type": "player_goal_anytime",
            "normalized_name": "Saka",
            "decimal_odds": 3.0,
            "raw_ev": 0.15,
        },
        {
            "market_type": "player_card_yellow",
            "normalized_name": "Saliba",
            "decimal_odds": 4.0,
            "raw_ev": 0.10,
        },
    ]

    class MockEvent:
        def __init__(self, m, n, o):
            self.fixture_id = fixture_id
            self.market_type = m
            self.normalized_name = n
            self.decimal_odds = o

    for edge in mock_edges:
        event = MockEvent(
            edge["market_type"], edge["normalized_name"], edge["decimal_odds"]
        )
        edge_data = {"raw_ev": edge["raw_ev"]}
        # Route through adaptive engine
        adaptive_engine.evaluate_and_route(edge_data, event, lineup_confidence=0.95)

    # 3. Flush to Mock Execution and trigger Feedback Loop
    logger.info("\n[STAGE 3] Flushing Autonomous Queue to Execution Engine")
    await adaptive_engine.flush_and_execute_batch(mock_live_trader)

    # 4. Check if Decay Predictor adapted to failures
    logger.info("\n[STAGE 4] Edge Decay ML Adaptation")
    logger.info(
        f"New 'player_goal_anytime' Base Half-Life: {decay_predictor.base_half_life_sec['player_goal_anytime']:.2f}s"
    )

    # 5. Generate Heatmap
    logger.info("\n[STAGE 5] Market Microstructure Heatmap Engine")
    heatmap_engine.generate_fill_rate_heatmap()


if __name__ == "__main__":
    asyncio.run(run_adaptive_simulation())
