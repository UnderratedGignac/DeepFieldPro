import logging
from dataclasses import dataclass
from typing import Dict, Any

logger = logging.getLogger(__name__)


@dataclass
class CounterfactualOutcome:
    execute_ev: float
    skip_ev: float
    delayed_ev: float


class CounterfactualEngine:
    """
    Phase 2: Counterfactual Engine.
    Implements a 3-world simulation model to evaluate what would have happened
    if we made a different execution policy decision.
    """

    def __init__(self):
        pass

    def simulate_skip(self, row: Dict[str, Any]) -> float:
        """
        World A: What if you did nothing?
        Returns 0.0 if market CLV is negative (good skip), or the negative of
        the CLV opportunity cost if we skipped a winner (negative regret exposure).
        This is the correct economic value of inaction.
        """
        closing_odds = row.get("closing_odds")
        odds_at_decision = row.get("odds_at_decision")
        if closing_odds and odds_at_decision and odds_at_decision > 0:
            # If closing_odds > decision_odds, the market drifted favourably.
            # Skipping had an opportunity cost (we missed positive CLV).
            # Return 0 always for skip EV (no capital deployed = no gain/loss).
            # Regret is calculated separately by the RegretEngine.
            pass
        return 0.0

    def simulate_execute(self, row: Dict[str, Any]) -> float:
        """
        World B: What if you executed?
        Depends on fill probability and the actual closing line (CLV).
        """
        closing_odds = row.get("closing_odds")
        odds_at_decision = row.get("odds_at_decision")
        p_fill = row.get("predicted_p_fill", 0.5)

        if not closing_odds or not odds_at_decision:
            return 0.0

        # CLV = (closing_odds - entry_odds) / entry_odds
        realized_clv = (closing_odds - odds_at_decision) / odds_at_decision

        # EV = Fill Probability * Realized CLV Movement
        # Does not assume perfect execution.
        return realized_clv * p_fill

    def simulate_delayed(self, row: Dict[str, Any]) -> float:
        """
        World B: What if you waited (delayed batch execution, e.g. 5 seconds)?
        Models CLV edge erosion due to odds movement and reduced fill probability.
        """
        closing_odds = row.get("closing_odds")
        odds_at_decision = row.get("odds_at_decision")
        if not closing_odds or not odds_at_decision:
            return 0.0

        # Assuming delay caused 20% of the CLV edge to evaporate
        realized_clv = (closing_odds - odds_at_decision) / odds_at_decision
        delayed_clv = realized_clv * 0.8

        # P_fill drops significantly because of the delay
        p_fill = row.get("predicted_p_fill", 0.5) * 0.4

        return delayed_clv * p_fill

    def compute_counterfactuals(self, row: Dict[str, Any]) -> CounterfactualOutcome:
        """
        Calculates the outcomes of all three possible worlds given a single decision log.
        """
        return CounterfactualOutcome(
            execute_ev=self.simulate_execute(row),
            skip_ev=self.simulate_skip(row),
            delayed_ev=self.simulate_delayed(row),
        )


counterfactual_engine = CounterfactualEngine()
