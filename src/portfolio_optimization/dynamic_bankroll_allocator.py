import logging
from app_config import config
from portfolio_optimization.portfolio_correlation_engine import correlation_engine

logger = logging.getLogger(__name__)

class DynamicBankrollAllocator:
    """
    Allocates capital using a combination of Kelly Criterion, Correlation Penalties,
    and Regime-Aware Exposure Control.
    """
    def __init__(self):
        self.current_bankroll = config.STARTING_BANKROLL

    def allocate(self, bet_metadata: dict, expected_ev: float, p_fill: float, odds: float, regime: str) -> float:
        """
        Calculates optimal portfolio deployment size.
        """
        if expected_ev <= 0 or odds <= 1.0:
            return 0.0
            
        # 1. Base Kelly
        payout = odds - 1.0
        p_win = (expected_ev + 1.0) / odds
        kelly_pct = ( (p_win * odds) - 1.0 ) / payout
        base_stake_pct = max(0.0, kelly_pct * config.BASE_KELLY_FRACTION)
        
        # 2. Survivability Adjustment
        base_stake_pct *= p_fill
        
        # 3. Regime-Aware Exposure Control
        if regime == "panic":
            base_stake_pct *= 0.35
            logger.debug("[BANKROLL] Panic regime detected. Slashed exposure by 65%.")
        elif regime == "high-frequency-volatility":
            base_stake_pct *= 0.60
            
        # 4. Correlation Penalty (Hidden Overlap Protection)
        correlation_multiplier = correlation_engine.calculate_correlation_penalty(
            fixture_id=bet_metadata.get("fixture_id"),
            market_type=bet_metadata.get("market"),
            player_name=bet_metadata.get("player")
        )
        base_stake_pct *= correlation_multiplier
        
        # 5. Liquidity Constraints (To be processed by LiquidityImpactModel next in chain)
        
        final_stake = self.current_bankroll * base_stake_pct
        return round(final_stake, 2)

bankroll_allocator = DynamicBankrollAllocator()
