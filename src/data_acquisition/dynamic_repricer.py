# dynamic_repricer.py
import logging
from typing import Dict, Any

from .event_dispatcher import LineupConfirmedEvent
from .formation_impact_engine import formation_impact_engine
# from src.model_runner import get_base_predictions (Conceptual import)

logger = logging.getLogger(__name__)

class DynamicRepricingEngine:
    """
    Event-reactive pricing engine. 
    Consumes canonical events and incrementally recalculates only affected players/markets.
    Applies tactical adjustments (e.g. formation multipliers) to raw model outputs.
    """
    def __init__(self):
        # Cache of the latest fair probabilities per fixture
        # fixture_id -> market -> normalized_name -> fair_probability
        self.fair_price_cache = {}

    async def handle_lineup_event(self, event: LineupConfirmedEvent, players: list):
        """
        Triggered when a LineupConfirmedEvent is emitted.
        Recomputes probabilities applying formation & positional multipliers.
        """
        logger.info(f"[REPRICER] Processing Lineup Event for {event.fixture_id}")
        
        if event.fixture_id not in self.fair_price_cache:
            self.fair_price_cache[event.fixture_id] = {}
            
        changes = event.changes_summary
        formation = changes.get("new_formation", changes.get("old_formation"))
        
        # If it's just a partial change, we would normally only recompute affected players.
        # For simplicity in this structure, we recompute the starters in the payload.
        recomputed_count = 0
        
        for player in players:
            if not player.get("starter"):
                continue
                
            norm_name = player.get("normalized_name")
            canonical_pos = player.get("canonical_position")
            
            # 1. Fetch raw base model outputs (Poisson Lambdas, Quantiles)
            # raw_stats = get_base_predictions(norm_name)
            raw_stats = {"shots": 1.5, "offsides": 0.5, "goals": 0.2, "tackles": 1.2} # Mock
            
            # 2. Apply Tactical Adjustment Layer (Formation Impact)
            multipliers = formation_impact_engine.get_multipliers(formation, canonical_pos)
            
            adjusted_stats = {}
            for stat, base_val in raw_stats.items():
                adjusted_stats[stat] = base_val * multipliers.get(stat, 1.0)
                
            # 3. Convert expected stats into market probabilities (Poisson/NegBinom)
            # This is where the heavy math from pricing_engine.py goes
            fair_probs = self._calculate_market_probs(adjusted_stats)
            
            # 4. Store in cache
            for market, prob in fair_probs.items():
                if market not in self.fair_price_cache[event.fixture_id]:
                    self.fair_price_cache[event.fixture_id][market] = {}
                self.fair_price_cache[event.fixture_id][market][norm_name] = prob
                
            recomputed_count += 1
            
        logger.info(f"[REPRICER] Recomputed fair probabilities for {recomputed_count} players. Tactical multipliers applied.")

    def _calculate_market_probs(self, adjusted_stats: Dict[str, float]) -> Dict[str, float]:
        """
        Transforms expected raw stats into exact market probabilities.
        """
        # Mock logic representing Poisson survival function / Negative Binomial CDF
        return {
            "player_goal_anytime": min(0.99, adjusted_stats.get("goals", 0) * 0.8),
            "player_shots_ou": min(0.99, adjusted_stats.get("shots", 0) * 0.5)
        }

    def get_fair_probability(self, fixture_id: str, market: str, normalized_name: str) -> float:
        return self.fair_price_cache.get(fixture_id, {}).get(market, {}).get(normalized_name, 0.0)

repricer = DynamicRepricingEngine()
