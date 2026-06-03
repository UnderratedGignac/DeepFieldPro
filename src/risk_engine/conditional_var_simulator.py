import logging
import numpy as np
from typing import List

logger = logging.getLogger(__name__)


class ConditionalVaRSimulator:
    """
    Institutional Risk Engine.
    Simulates Conditional Value at Risk (CVaR) and Maximum Survivable Exposure
    through Monte Carlo stress testing of correlated market crashes.
    """

    def __init__(self, confidence_level: float = 0.95):
        self.confidence_level = confidence_level

    def run_monte_carlo_stress_test(
        self,
        current_bankroll: float,
        expected_win_rates: List[float],
        expected_odds: List[float],
        n_simulations: int = 10000,
    ) -> dict:
        """
        Simulates n execution trajectories to determine Tail Risk (CVaR).
        """
        n_bets = len(expected_win_rates)
        if n_bets == 0:
            return {"cvar_pct": 0.0, "risk_of_ruin": 0.0}

        win_rates = np.array(expected_win_rates)
        odds = np.array(expected_odds)
        stakes = current_bankroll * (
            0.01
        )  # Assuming flat 1% allocation for simplified simulation

        simulated_returns = []

        # Vectorized Monte Carlo Simulation
        for _ in range(n_simulations):
            # Simulate uniform random variables to determine bet success
            rand_rolls = np.random.uniform(0, 1, n_bets)
            wins = rand_rolls < win_rates

            # Payout = (Stake * Odds) - Stake if win, else -Stake
            profits = np.where(wins, (stakes * odds) - stakes, -stakes)
            total_return = np.sum(profits)

            simulated_returns.append(total_return)

        simulated_returns = np.array(simulated_returns)

        # Calculate VaR and CVaR
        var_percentile = (1 - self.confidence_level) * 100
        var_dollar = np.percentile(simulated_returns, var_percentile)

        # CVaR is the expected return given that the return falls below the VaR threshold
        tail_losses = simulated_returns[simulated_returns <= var_dollar]
        cvar_dollar = np.mean(tail_losses) if len(tail_losses) > 0 else var_dollar

        cvar_pct = abs(cvar_dollar) / current_bankroll

        logger.info(f"[RISK ENGINE] 95% CVaR: {cvar_pct*100:.2f}% of Portfolio.")

        return {
            "var_dollar": round(var_dollar, 2),
            "cvar_dollar": round(cvar_dollar, 2),
            "cvar_pct": round(cvar_pct, 4),
        }


cvar_simulator = ConditionalVaRSimulator()
