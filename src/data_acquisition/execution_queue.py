# execution_queue.py
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class ExecutionRouteOptimizer:
    """
    Ranks executable edges based on Market Microstructure intelligence.
    Priority = Edge * (1 / DecayRate) * FillProbability
    """
    def __init__(self):
        self.queue = []
        
        # Historical metrics informing execution fragility
        self.market_decay_rates = {
            "player_goal_anytime": 0.85, # Highly fragile, decays fast
            "player_first_goalscorer": 0.90,
            "player_shots_ou": 0.40,
            "player_sot_ou": 0.45,
            "player_card_yellow": 0.15 # Slow decay
        }
        
        self.market_fill_probabilities = {
            "player_goal_anytime": 0.42,
            "player_first_goalscorer": 0.53,
            "player_shots_ou": 0.76,
            "player_sot_ou": 0.73,
            "player_card_yellow": 0.86
        }

    def add_to_queue(self, odds_event: Any, edge_data: Dict[str, Any], approved_stake: float):
        raw_ev = edge_data.get("raw_ev", 0.0)
        market = odds_event.market_type
        
        decay_rate = self.market_decay_rates.get(market, 0.5)
        fill_prob = self.market_fill_probabilities.get(market, 0.5)
        
        # Priority Formula: High EV, High Fill Prob, FAST Decay = Top of Queue
        # We want to execute the most fragile, high-edge bets first.
        priority_score = raw_ev * (1.0 / max(0.01, decay_rate)) * fill_prob
        
        bet_payload = {
            "priority_score": priority_score,
            "fixture_id": odds_event.fixture_id,
            "market": market,
            "player": odds_event.normalized_name,
            "odds": odds_event.decimal_odds,
            "stake": approved_stake,
            "event": odds_event,
            "fragility_classification": "ULTRA_FRAGILE" if decay_rate > 0.8 else "STABLE"
        }
        
        self.queue.append(bet_payload)
        self.queue.sort(key=lambda x: x["priority_score"], reverse=True)
        
        logger.info(f"[ROUTE OPTIMIZER] Added {market} for {odds_event.normalized_name}. Priority: {priority_score:.3f} | Class: {bet_payload['fragility_classification']}")

    async def flush_to_workers(self):
        """
        Distributes bets to parallel execution lanes based on fragility.
        """
        if not self.queue:
            return
            
        fragile_lane = []
        stable_lane = []
        
        for bet in self.queue:
            if bet["fragility_classification"] == "ULTRA_FRAGILE":
                fragile_lane.append(bet)
            else:
                stable_lane.append(bet)
                
        self.queue.clear()
        
        logger.info(f"[ROUTE OPTIMIZER] Dispatching {len(fragile_lane)} bets to FAST Lane, {len(stable_lane)} to BATCH Lane.")
        
        # In live execution, we trigger the live_execution_manager
        # await live_execution_manager.execute_parallel(fragile_lane, stable_lane)
        
        return fragile_lane, stable_lane

execution_queue = ExecutionRouteOptimizer()
