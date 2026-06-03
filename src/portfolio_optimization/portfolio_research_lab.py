import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
import asyncio
import logging

# Add src root to pythonpath
from src.portfolio_optimization.capital_allocation_engine import capital_engine
from src.portfolio_optimization.drawdown_governor import drawdown_governor

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


class PortfolioResearchLab:
    """
    Institutional-grade research framework simulating portfolio growth, correlation drag,
    and drawdown mechanics over thousands of mocked executions.
    """

    def __init__(self):
        pass

    async def run_portfolio_simulation(self):
        logger.info("==========================================================")
        logger.info("=== CAPITAL ALLOCATION & PORTFOLIO SIMULATION LAB ======")
        logger.info("==========================================================")
        # Mocking an open portfolio with existing exposure
        from src.portfolio_optimization.portfolio_correlation_engine import (
            correlation_engine,
        )

        correlation_engine.add_exposure(
            "bet_1", "FIX_123", "player_shots_ou", "Saka", 250.0
        )
        # Simulating a new edge on a highly correlated prop (Saka Anytime Goal)
        bet_metadata = {
            "fixture_id": "FIX_123",
            "market": "player_goal_anytime",
            "player": "Saka",
        }
        logger.info("\n--- SCENARIO 1: Heavily Correlated Player Prop ---")
        stake1 = capital_engine.allocate_capital(  # noqa: F841
            bet_metadata, expected_ev=0.20, p_fill=0.5, odds=3.0, regime="stable"
        )
        logger.info("\n--- SCENARIO 2: Panic Regime + Bayesian Uncertainty ---")
        bet_metadata_2 = {
            "fixture_id": "FIX_999",
            "market": "player_first_goalscorer",  # We have no priors for this -> high bayesian penalty
            "player": "Haaland",
        }
        stake2 = capital_engine.allocate_capital(  # noqa: F841
            bet_metadata_2, expected_ev=0.30, p_fill=0.2, odds=4.0, regime="panic"
        )
        logger.info("\n--- SCENARIO 3: Deep Drawdown Protection ---")
        drawdown_governor.record_equity(10000.0)  # Peak
        drawdown_governor.record_equity(8600.0)  # 14% Drawdown
        bet_metadata_3 = {
            "fixture_id": "FIX_444",
            "market": "player_card_yellow",
            "player": "Saliba",
        }
        stake3 = capital_engine.allocate_capital(  # noqa: F841
            bet_metadata_3, expected_ev=0.10, p_fill=0.8, odds=2.5, regime="stable"
        )


if __name__ == "__main__":
    lab = PortfolioResearchLab()
    asyncio.run(lab.run_portfolio_simulation())
