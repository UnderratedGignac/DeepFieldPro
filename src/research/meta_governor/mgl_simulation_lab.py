import os
import sys

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
)
import asyncio
import logging

# Add src root to pythonpath
from src.research.meta_governor.mgl_engine import mgl_engine

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


class MGLSimulationLab:
    """
    Simulates the MGL evaluating an aggressive APO proposal in a degrading regime.
    """

    async def run_mgl_flow(self):
        # Scenario: The APO generated a massive regret spike from a noisy backtest
        # and wants to violently raise the execution threshold from 0.05 to 0.15.
        # But the actual System Health is degrading, and the Adaptive System is currently
        # losing to the static baseline (Meta-Regret > 0).
        mgl_inputs = {
            "realized_ev_trend": -0.05,
            "clv_stability": 0.8,
            "current_drawdown": 0.08,
        }
        apo_proposal = {
            "current_min_ev": 0.05,
            "proposed_min_ev": 0.15,  # Massive 0.10 jump! Too fast.
        }
        # MGL should block this due to the safety bounds.
        mgl_engine.evaluate_and_control(mgl_inputs, apo_proposal)
        # Scenario 2: APO makes a reasonable proposal (0.05 to 0.06),
        # but MGL damps it because of High Meta-Regret
        logger.info("\n--- Scenario 2: Reasonable Proposal, but Damped by MGL ---")
        apo_proposal_2 = {"current_min_ev": 0.05, "proposed_min_ev": 0.06}
        mgl_engine.evaluate_and_control(mgl_inputs, apo_proposal_2)


if __name__ == "__main__":
    lab = MGLSimulationLab()
    asyncio.run(lab.run_mgl_flow())
