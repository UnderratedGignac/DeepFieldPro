# edge_engine.py
import logging
from typing import Dict, Any

from .dynamic_repricer import repricer
from .websocket_parser import CanonicalOddsEvent

logger = logging.getLogger(__name__)

class MarketEdgeEngine:
    """
    Calculates pure Expected Value (EV) using standard quantitative formulas.
    EV = (P_model * payout) - (1 - P_model)
    Applies confidence, latency, and liquidity weighting.
    """
    def __init__(self):
        pass

    def evaluate_edge(self, odds_event: CanonicalOddsEvent, lineup_confidence: float = 1.0) -> Dict[str, Any]:
        """
        Consumes an odds event, fetches the dynamic fair probability, and computes the edge.
        """
        if odds_event.status == "suspended":
            return {"has_edge": False, "reason": "Market suspended"}
            
        fair_prob = repricer.get_fair_probability(
            odds_event.fixture_id, 
            odds_event.market_type, 
            odds_event.normalized_name
        )
        
        if fair_prob <= 0:
            return {"has_edge": False, "reason": "No fair probability modeled"}
            
        # Payout is decimal_odds - 1 (e.g., 2.50 odds means you win 1.50 per 1.00 wagered)
        payout = odds_event.decimal_odds - 1.0
        
        # Raw EV Calculation
        # EV = (Probability of Win * Profit) - (Probability of Loss * Stake)
        expected_profit = fair_prob * payout
        expected_loss = (1.0 - fair_prob) * 1.0
        raw_ev = expected_profit - expected_loss
        
        if raw_ev <= 0:
            return {"has_edge": False, "ev": raw_ev}
            
        # Confidence-Weighted Pricing (Phase 4)
        # We penalize the edge if the lineup is unconfirmed or leaked from a bad source
        market_integrity_score = 0.95 # Mock penalty for Betarabia liquidity
        execution_confidence = 0.98 # Mock penalty for slippage
        
        adjusted_ev = raw_ev * lineup_confidence * market_integrity_score * execution_confidence
        
        has_edge = adjusted_ev > 0.05 # 5% minimum EV threshold
        
        return {
            "has_edge": has_edge,
            "raw_ev": raw_ev,
            "adjusted_ev": adjusted_ev,
            "fair_prob": fair_prob,
            "market_prob": odds_event.implied_probability,
            "lineup_confidence": lineup_confidence
        }

edge_engine = MarketEdgeEngine()
