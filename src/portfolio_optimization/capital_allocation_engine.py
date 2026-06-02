import logging
from src.portfolio_optimization.bayesian_confidence_engine import bayesian_engine
from src.portfolio_optimization.drawdown_governor import drawdown_governor
from src.portfolio_optimization.dynamic_bankroll_allocator import bankroll_allocator
from src.portfolio_optimization.liquidity_impact_model import liquidity_impact_model

logger = logging.getLogger(__name__)

class CapitalAllocationEngine:
    """
    The True Portfolio Brain.
    Jointly optimizes: f(EV, FillProbability, Volatility, Correlation, Liquidity, Latency, DrawdownRisk).
    This answers: "Is this the BEST possible use of capital right now?"
    """
    def __init__(self):
        pass

    def allocate_capital(self, bet_metadata: dict, expected_ev: float, p_fill: float, odds: float, regime: str) -> float:
        """
        Calculates the exact execution stake by piping it through all risk layers.
        """
        market = bet_metadata.get("market")
        
        # 1. Base Multi-Objective Allocation (Kelly + Regime + Correlation + Survivability)
        base_stake = bankroll_allocator.allocate(bet_metadata, expected_ev, p_fill, odds, regime)
        
        if base_stake <= 0.0:
            return 0.0
            
        # 2. Bayesian Confidence Calibration (Uncertainty Penalty)
        bayesian_penalty = bayesian_engine.get_confidence_penalty(market)
        stake_after_bayes = base_stake * bayesian_penalty
        
        # 3. Drawdown Protection System (Global Risk Off)
        drawdown_multiplier = drawdown_governor.calculate_governor_multiplier()
        stake_after_drawdown = stake_after_bayes * drawdown_multiplier
        
        # 4. Liquidity-Constrained Optimization (Market Impact limits)
        final_stake = liquidity_impact_model.constrain_stake(market, stake_after_drawdown, regime)
        
        logger.info(
            f"[CAPITAL ENGINE] {market} | EV: {expected_ev:.3f} | Base: ${base_stake:.2f} | "
            f"BayesPen: {bayesian_penalty:.2f}x | DrawdownPen: {drawdown_multiplier:.2f}x | "
            f"Final: ${final_stake:.2f}"
        )
        
        return round(final_stake, 2)

capital_engine = CapitalAllocationEngine()
