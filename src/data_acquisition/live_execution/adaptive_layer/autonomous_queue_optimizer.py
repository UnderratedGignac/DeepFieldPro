import logging
from typing import Dict, Any

from .edge_decay_predictor import decay_predictor
from .execution_survivability_model import survivability_model
from .market_regime_classifier import regime_classifier

logger = logging.getLogger(__name__)

class AutonomousQueueOptimizer:
    """
    Self-learning queue that dynamically reranks bets based on expected decay speed,
    historical fill probability, and current market regime.
    """
    def __init__(self):
        self.queue = []

    def evaluate_and_queue(self, edge_data: Dict[str, Any], bet_metadata: Dict[str, Any]):
        """
        Calculates true executable priority and queues it.
        """
        market = bet_metadata["market"]
        fixture_id = bet_metadata["fixture_id"]
        raw_ev = edge_data["raw_ev"]
        
        # Determine regime
        regime = regime_classifier.regimes.get(fixture_id, {}).get(market, "stable")
        
        # Estimate queue delay (e.g. 50ms per item ahead of it)
        expected_queue_delay_sec = len(self.queue) * 0.05
        
        # 1. Decay Prediction
        # Calculate EV remaining AFTER expected queue delay
        expected_ev = decay_predictor.predict_remaining_edge(
            market, raw_ev, expected_queue_delay_sec, regime
        )
        
        # 2. Survivability
        # Fetch expected fill probability given the regime and delay
        p_fill = survivability_model.estimate_survivability(
            market, expected_queue_delay_sec, bet_metadata.get("volatility", 0.5), regime
        )
        
        # 3. Smart Market Skipper Integration
        from .smart_market_skipper import market_skipper
        skip_reason = market_skipper.should_skip(market, expected_ev, p_fill, regime)
        if skip_reason:
            logger.info(f"[SMART SKIPPER] Skipped {market} for {bet_metadata.get('player')}: {skip_reason}")
            return
            
        # Priority = EV * Fill_Probability
        # (Since expected_ev already accounts for decay, we don't divide by decay rate again)
        priority_score = expected_ev * p_fill
        
        bet_payload = bet_metadata.copy()
        bet_payload["priority_score"] = priority_score
        bet_payload["expected_ev"] = expected_ev
        bet_payload["p_fill"] = p_fill
        bet_payload["regime"] = regime
        
        self.queue.append(bet_payload)
        # Rerank
        self.queue.sort(key=lambda x: x["priority_score"], reverse=True)
        
        logger.info(f"[AUTONOMOUS QUEUE] Added {market} with Priority {priority_score:.3f} | p(Fill): {p_fill:.2f} | Regime: {regime}")

queue_optimizer = AutonomousQueueOptimizer()
