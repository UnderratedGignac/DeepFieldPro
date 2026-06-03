import logging
from typing import List

logger = logging.getLogger(__name__)


class DrawdownGovernor:
    """
    Dynamically reduces system aggressiveness during poor execution regimes,
    volatility spikes, or model drift. Professional systems prioritize survival first.
    """

    def __init__(self):
        self.equity_curve: List[float] = []
        self.peak_equity = 0.0

    def record_equity(self, current_bankroll: float):
        self.equity_curve.append(current_bankroll)
        if current_bankroll > self.peak_equity:
            self.peak_equity = current_bankroll

    def calculate_governor_multiplier(self) -> float:
        """
        Returns a multiplier [0.0 - 1.0] that scales down all execution stakes globally.
        If drawdown exceeds 15%, the system aggressively dials back.
        """
        if not self.equity_curve or self.peak_equity == 0:
            return 1.0

        current_equity = self.equity_curve[-1]
        drawdown_pct = (self.peak_equity - current_equity) / self.peak_equity

        if drawdown_pct <= 0.05:
            return 1.0  # Normal operation
        elif drawdown_pct <= 0.10:
            logger.warning(
                f"[DRAWDOWN GOVERNOR] System in {drawdown_pct*100:.1f}% drawdown. Scaling exposure by 0.7x"
            )
            return 0.7
        elif drawdown_pct <= 0.15:
            logger.warning(
                f"[DRAWDOWN GOVERNOR] System in {drawdown_pct*100:.1f}% drawdown. Scaling exposure by 0.3x"
            )
            return 0.3
        else:
            logger.critical(
                f"[DRAWDOWN GOVERNOR] System in {drawdown_pct*100:.1f}% drawdown! Halting automated execution."
            )
            return 0.0  # Halt execution


drawdown_governor = DrawdownGovernor()
