import logging
from portfolio_optimization.bayesian_confidence_engine import bayesian_engine
from portfolio_optimization.drawdown_governor import drawdown_governor
from portfolio_optimization.dynamic_bankroll_allocator import bankroll_allocator
from portfolio_optimization.liquidity_impact_model import liquidity_impact_model
from app_config import config

logger = logging.getLogger(__name__)

class CapitalAllocationEngine:
    """
    The True Portfolio Brain.
    Jointly optimizes: f(EV, FillProbability, Volatility, Correlation, Liquidity, Latency, DrawdownRisk).
    This answers: "Is this the BEST possible use of capital right now?"
    """
    def __init__(self):
        self.slate_exposure = {} # Tracks total exposure per fixture_id

    def allocate_capital(self, bet_metadata: dict, expected_ev: float, p_fill: float, odds: float, regime: str) -> float:
        """
        Calculates the exact execution stake by piping it through all risk layers.
        """
        market = bet_metadata.get("market")
        fixture_id = bet_metadata.get("fixture_id", "UNKNOWN")
        
        # TASK 4: STOP_LOSS GUARD
        import os, pandas as pd
        BET_LOG_CSV = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'bet_log.csv')
        StartingBankroll_P = config.STARTING_BANKROLL
        
        system_status = getattr(self, 'system_status', 'ACTIVE')
        
        if os.path.exists(BET_LOG_CSV):
            df = pd.read_csv(BET_LOG_CSV)
            settled = df[df['status'] == 'SETTLED'].sort_values('timestamp', ascending=False)
            if len(settled) > 0:
                RollingPnl_V = settled.head(20)['profit_loss'].sum()
                
                if RollingPnl_V < -0.15 * StartingBankroll_P:
                    if system_status != 'DRAWDOWN_PAUSE':
                        logger.warning(f"[STOP_LOSS] Rolling P&L (${RollingPnl_V:.2f}) < -15% Bankroll. Pausing system.")
                        self.system_status = 'DRAWDOWN_PAUSE'
                    return 0.0
                elif RollingPnl_V > -0.05 * StartingBankroll_P and system_status == 'DRAWDOWN_PAUSE':
                    logger.info(f"[STOP_LOSS] Rolling P&L (${RollingPnl_V:.2f}) recovered. Resuming system.")
                    self.system_status = 'ACTIVE'
                    
        if getattr(self, 'system_status', 'ACTIVE') == 'DRAWDOWN_PAUSE':
            return 0.0
            
        # SLATE EXPOSURE CAP
        current_fixture_exposure = self.slate_exposure.get(fixture_id, 0.0)
        max_exposure = config.STARTING_BANKROLL * config.MAX_EXPOSURE_PER_FIXTURE
        
        if current_fixture_exposure >= max_exposure:
            logger.warning(f"[CAPITAL ENGINE] Max slate exposure hit for {fixture_id}. Aborting bet.")
            return 0.0

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
