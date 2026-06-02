import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class AutonomousStakeAllocator:
    """
    Dynamic stake sizing (Kelly Criterion + Execution Friction modification).
    Adjusts stake based on edge confidence, market survivability, and latency regime.
    """
    def __init__(self):
        self.bankroll = 10000.0
        self.KELLY_FRACTION = 0.25 # Quarter Kelly for safety

    def allocate_stake(self, expected_ev: float, p_fill: float, odds: float, market_regime: str) -> float:
        """
        Calculates optimal stake size.
        """
        if expected_ev <= 0 or odds <= 1.0:
            return 0.0
            
        # Standard Kelly Criterion (Edge / Payout)
        payout = odds - 1.0
        # P_win can be back-calculated from EV
        # EV = P_win * payout - (1 - P_win)
        # EV = P_win(payout + 1) - 1 => P_win = (EV + 1) / odds
        p_win = (expected_ev + 1.0) / odds
        
        kelly_percentage = ( (p_win * odds) - 1.0 ) / payout
        
        if kelly_percentage <= 0:
            return 0.0
            
        # Fractionate Kelly
        base_stake_pct = kelly_percentage * self.KELLY_FRACTION
        
        # Modify by Survivability (P_fill)
        # If we are unlikely to fill, we shouldn't attempt a massive stake which might trigger manual review
        base_stake_pct *= p_fill
        
        # Modify by Regime
        if market_regime == "panic":
            base_stake_pct *= 0.3 # Reduce stake heavily in panic markets to avoid slippage traps
        elif market_regime == "high-frequency-volatility":
            base_stake_pct *= 0.6
            
        # Hard limits
        max_stake_pct = 0.05 # Max 5% of bankroll per bet
        final_stake_pct = min(base_stake_pct, max_stake_pct)
        
        allocated_stake = self.bankroll * final_stake_pct
        
        logger.info(f"[STAKE ALLOCATOR] Allocated ${allocated_stake:.2f} (EV: {expected_ev:.3f}, p(Fill): {p_fill:.2f}, Regime: {market_regime})")
        return round(allocated_stake, 2)

stake_allocator = AutonomousStakeAllocator()
