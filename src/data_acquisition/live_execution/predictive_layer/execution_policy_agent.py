import logging

from .suspension_probability_model import suspension_model

logger = logging.getLogger(__name__)

class ExecutionPolicyAgent:
    """
    Reinforcement-Learned Execution Policy.
    Learns optimal actions: instant execute, batch execute, skip, split stake, etc.
    """
    def __init__(self):
        # Q-table mock (State -> Action -> Reward)
        # States: Regime_Volatility_QueueDepth
        # Actions: INSTANT, BATCH, SKIP, SPLIT_STAKE
        self.q_table = {}

    def decide_policy(self, market_type: str, regime: str, p_fill: float, 
                      velocity: float, ev: float) -> str:
        """
        Determines the execution strategy based on the RL policy.
        """
        # Feature inference
        p_suspend = suspension_model.predict_suspension_probability(
            market_type, time_horizon_sec=2.0, regime=regime, velocity_score=velocity, lineup_confidence=0.9
        )
        
        # Policy Logic (Heuristics acting as an RL argmax for now)
        if p_suspend > 0.8 or ev < 0.02:
            action = "SKIP"
        elif p_suspend > 0.5 and p_fill < 0.6:
            action = "SPLIT_STAKE" # Mitigate rejection risk
        elif regime in ["panic", "high-frequency-volatility"] or "goal" in market_type:
            action = "INSTANT" # Front-run the suspension
        else:
            action = "BATCH" # Safe to aggregate
            
        logger.info(f"[RL POLICY] State: {regime} | P(Suspend): {p_suspend:.2f} | Action: {action}")
        return action

policy_agent = ExecutionPolicyAgent()
