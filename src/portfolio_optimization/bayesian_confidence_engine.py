import logging
import math

logger = logging.getLogger(__name__)

class BayesianConfidenceEngine:
    """
    Replaces static point estimates with posterior uncertainty.
    If the system has very few data points on a specific execution route, 
    the Bayesian confidence is low, and stake/aggression should be reduced.
    """
    def __init__(self):
        # Tracking successes (alpha) and failures (beta) per market for Beta distribution
        self.market_priors = {
            "player_goal_anytime": {"alpha": 2, "beta": 5},
            "player_card_yellow": {"alpha": 8, "beta": 2}
        }

    def update_posterior(self, market_type: str, fill_success: bool):
        if market_type not in self.market_priors:
            self.market_priors[market_type] = {"alpha": 1, "beta": 1}
            
        if fill_success:
            self.market_priors[market_type]["alpha"] += 1
        else:
            self.market_priors[market_type]["beta"] += 1

    def get_confidence_interval_width(self, market_type: str) -> float:
        """
        Returns the variance of the Beta distribution.
        Higher variance = wider interval = lower confidence.
        """
        prior = self.market_priors.get(market_type, {"alpha": 1, "beta": 1})
        a = prior["alpha"]
        b = prior["beta"]
        
        # Variance of Beta(a,b) = (a*b) / ((a+b)^2 * (a+b+1))
        variance = (a * b) / (math.pow(a + b, 2) * (a + b + 1))
        return variance

    def get_confidence_penalty(self, market_type: str) -> float:
        """
        Returns a multiplier to shrink stake when uncertainty is high.
        """
        variance = self.get_confidence_interval_width(market_type)
        # Empirical scaling: high variance (e.g. 0.08) -> heavy penalty (0.5x)
        # low variance (e.g. 0.01) -> no penalty (1.0x)
        penalty = max(0.2, 1.0 - (variance * 10.0))
        return penalty

bayesian_engine = BayesianConfidenceEngine()
