import asyncio
import logging
import sys

# Add src root to pythonpath
sys.path.insert(0, "C:/Users/Elie/DeepFieldPro")

from src.capital_scaling_intelligence.acsi_engine import acsi_engine

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


class ACSISimulationLab:
    """
    Simulates long-horizon bankroll trajectory analysis.
    """

    async def run_acsi_cycle(self):

        logger.info("\n--- SCENARIO 1: Structural Stability (Safe to Scale) ---")
        stable_inputs = {
            "clv_stability": 0.9,
            "friction_trend": -0.01,
            "rvl_drift": 0.08,
            "drawdown_autocorr": 0.02,
            "current_ev": 0.08,
            "drawdown_momentum": 0.0,
        }

        # Cycle 1: ACSI detects compounding, wants to scale +5%, but velocity is capped
        acsi_engine.evaluate_capital_trajectory(stable_inputs)

        # Cycle 2: Scaling continues, velocity safely accelerates
        acsi_engine.evaluate_capital_trajectory(stable_inputs)

        logger.info("\n--- SCENARIO 2: Structural Decay (Adversarial Degradation) ---")
        # Bookmaker fights back, execution friction trends up, drawdowns cluster
        decay_inputs = {
            "clv_stability": 0.4,
            "friction_trend": 0.08,
            "rvl_drift": -0.15,
            "drawdown_autocorr": 0.4,
            "current_ev": 0.04,
            "drawdown_momentum": 0.08,
        }

        # ACSI should immediately detect the decay regime and aggressively scale down
        acsi_engine.evaluate_capital_trajectory(decay_inputs)


if __name__ == "__main__":
    lab = ACSISimulationLab()
    asyncio.run(lab.run_acsi_cycle())
