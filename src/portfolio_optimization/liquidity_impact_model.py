import logging

logger = logging.getLogger(__name__)

class LiquidityImpactModel:
    """
    Prevents the system from assuming infinite scalability.
    Estimates market impact and suspension risk derived directly from stake size.
    """
    def __init__(self):
        # Mocking the maximum absorbable liquidity before Betarabia manual review triggers
        self.market_liquidity_caps = {
            "player_goal_anytime": 250.0,
            "player_first_goalscorer": 100.0,
            "player_shots_ou": 500.0,
            "player_sot_ou": 400.0,
            "player_card_yellow": 750.0
        }

    def constrain_stake(self, market_type: str, requested_stake: float, regime: str) -> float:
        """
        Caps the stake based on the liquidity constraints of the specific market.
        If the market is in panic, liquidity evaporates, so caps are slashed.
        """
        base_cap = self.market_liquidity_caps.get(market_type, 150.0)
        
        # Liquidity dries up in volatile regimes
        if regime == "panic":
            base_cap *= 0.2
        elif regime == "high-frequency-volatility":
            base_cap *= 0.5
            
        constrained_stake = min(requested_stake, base_cap)
        
        if constrained_stake < requested_stake:
            logger.info(f"[LIQUIDITY MODEL] Constrained stake from ${requested_stake:.2f} -> ${constrained_stake:.2f} due to {market_type} liquidity cap.")
            
        return constrained_stake

liquidity_impact_model = LiquidityImpactModel()
