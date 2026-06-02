# execution_simulator.py
import logging
import random
from typing import Dict, Any

from .simulation_clock import sim_clock

logger = logging.getLogger(__name__)

class ExecutionSimulator:
    """
    Replaces the live Betarabia execution engine during backtests.
    Injects network latency, slippage penalties, and rejection probabilities
    to calculate True Achievable CLV.
    """
    def __init__(self):
        self.total_simulated_profit = 0.0
        self.theoretical_profit = 0.0

    def attempt_execution(self, bet_payload: Dict[str, Any], market_volatility: float = 0.5, 
                          delay_range: tuple = (250, 4500)) -> Dict[str, Any]:
        """
        Simulates the reality of submitting a bet to the sportsbook.
        Injects network latency, dynamic slippage, and regime-based rejection probabilities.
        """
        requested_odds = bet_payload["odds"]
        theoretical_ev = bet_payload.get("priority_score", 0.0)
        market_type = bet_payload.get("market", "unknown")
        
        # 1. Latency Injection (Network lag + Execution Queue Delay)
        execution_delay_ms = random.randint(delay_range[0], delay_range[1])
        
        # Market-specific volatility multipliers
        if market_type == "player_goal_anytime":
            market_volatility = min(1.0, market_volatility * 1.5) # Goalscorer markets are highly volatile
        elif market_type == "player_card_yellow":
            market_volatility = market_volatility * 0.5 # Card markets are slower
            
        # 2. Dynamic Suspension Probability
        # P(suspension) = f(velocity, time_to_kickoff, edge_size)
        # We approximate this with volatility and execution delay.
        # If delay is long, book has more time to suspend.
        delay_penalty = execution_delay_ms / 10000.0 # Up to 1.0 at 10s
        rejection_prob = min(0.95, (market_volatility * 0.5) + delay_penalty)
        
        if random.random() < rejection_prob:
            logger.info(f"[EXEC SIM] Bet Rejected: Market suspended during {execution_delay_ms}ms delay. Volatility: {market_volatility:.2f}")
            return {"status": "rejected", "reason": "Market suspended", "execution_delay_ms": execution_delay_ms, "theoretical_ev": theoretical_ev}
            
        # 3. Volatility-Conditioned Slippage
        # Faster moving markets often result in partial fills or reduced odds
        slippage_penalty = 0.0
        if market_volatility > 0.6:
            # Drop odds by 5-30 ticks depending on volatility
            slippage_multiplier = 3.0 if market_volatility > 0.8 else 1.0
            slippage_penalty = random.uniform(0.05, 0.10) * slippage_multiplier
            
        realized_odds = max(1.01, requested_odds - slippage_penalty)
        
        # 4. Fill Probability
        # If odds dropped too much, book might just reject it entirely.
        if realized_odds < requested_odds - (0.15 * requested_odds):
            if random.random() < 0.8: # High chance of rejection if odds crash
                return {"status": "rejected", "reason": "Odds changed significantly", "execution_delay_ms": execution_delay_ms, "theoretical_ev": theoretical_ev}
                
        # Simulated Fill Success
        logger.info(f"[EXEC SIM] FILLED: {bet_payload['player']} @ {realized_odds:.2f} (Requested {requested_odds:.2f}). Delay: {execution_delay_ms}ms")
        
        return {
            "status": "filled",
            "requested_odds": requested_odds,
            "realized_odds": realized_odds,
            "execution_delay_ms": execution_delay_ms,
            "timestamp": sim_clock.now().isoformat(),
            "slippage": slippage_penalty,
            "theoretical_ev": theoretical_ev
        }

execution_sim = ExecutionSimulator()
