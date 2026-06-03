import asyncio
import logging
import sys

# Add src root to pythonpath
sys.path.insert(0, "C:/Users/Elie/DeepFieldPro")

from src.data_acquisition.live_execution.predictive_layer.execution_policy_agent import (
    policy_agent,
)
from src.data_acquisition.live_execution.predictive_layer.real_time_edge_decay_forecaster import (
    real_time_decay_forecaster,
)
from src.data_acquisition.live_execution.predictive_layer.suspension_probability_model import (
    suspension_model,
)
from src.data_acquisition.live_execution.predictive_layer.market_movement_forecaster import (
    movement_forecaster,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


class ExecutionResearchLab:
    """
    The central A/B testing and experimentation framework.
    Evaluates RL policies, decay models, and predictive suspension algorithms.
    """

    def __init__(self):
        self.experiments_run = 0

    async def run_policy_ab_test(self):
        logger.info("======================================================")
        logger.info("=== QUANTITATIVE EXECUTION RESEARCH LAB A/B TEST ===")
        logger.info("======================================================")

        markets = [
            ("player_goal_anytime", "EPL", "panic", 0.95),
            ("player_card_yellow", "LaLiga", "stable", 0.5),
        ]

        for market, league, regime, velocity in markets:
            logger.info(f"\n--- Testing Scenario: {market} in {regime} regime ---")

            # 1. Forecast Movement
            forecast = movement_forecaster.forecast_movement(
                market, velocity, 1200, 0.95
            )
            logger.info(
                f"Predicted Move: {forecast['expected_move_ticks']} ticks | P(Move): {forecast['move_probability']}"
            )

            # 2. Predict Suspension
            p_suspend = suspension_model.predict_suspension_probability(
                market, 2.0, regime, velocity, 0.95
            )
            logger.info(f"P(Suspension in 2s): {p_suspend:.2f}")

            # 3. Forecast Edge Decay
            future_ev = real_time_decay_forecaster.forecast_edge_at_execution(
                market, 0.15, 1.5, regime
            )
            logger.info(
                f"Expected EV after 1.5s latency: {future_ev:.3f} (Starting: 0.150)"
            )

            # 4. RL Policy Agent Routing
            action = policy_agent.decide_policy(
                market, regime, 0.4, velocity, future_ev
            )
            logger.info(f"OPTIMAL RL ACTION --> {action}")


if __name__ == "__main__":
    lab = ExecutionResearchLab()
    asyncio.run(lab.run_policy_ab_test())
