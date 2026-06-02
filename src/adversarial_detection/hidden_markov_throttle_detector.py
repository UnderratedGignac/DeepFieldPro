import logging
import numpy as np

logger = logging.getLogger(__name__)

class HiddenMarkovThrottleDetector:
    """
    Adversarial Sportsbook Detection Engine.
    Uses Hidden Markov modeling heuristics to estimate P(account_restricted | recent_behavior).
    Hidden states: [GREEN (Normal), YELLOW (Scrutinized), RED (Throttled)]
    """
    def __init__(self):
        # States: 0=GREEN, 1=YELLOW, 2=RED
        try:
            # Try to fetch empirically mined transition matrix from warehouse
            from src.telemetry_warehouse.adversarial_pattern_miner import pattern_miner
            self.transition_matrix = pattern_miner.get_state_transition_matrix()
            logger.info("[HMM ADVERSARIAL] Successfully loaded empirical state transition matrix.")
        except Exception:
            logger.warning("[HMM ADVERSARIAL] Pattern miner unavailable. Falling back to default transition matrix.")
            self.transition_matrix = np.array([
                [0.90, 0.09, 0.01], # From GREEN
                [0.10, 0.70, 0.20], # From YELLOW
                [0.01, 0.20, 0.79]  # From RED
            ])
        
        # Current belief state (Probability distribution over states)
        self.belief = np.array([1.0, 0.0, 0.0]) # Start 100% in GREEN

    def update_belief(self, execution_latency: float, rejection_flag: bool):
        """
        Updates the belief state based on the emission (latency and rejection).
        """
        # Emission probabilities (Probability of seeing this execution outcome given the state)
        emission = np.array([0.0, 0.0, 0.0])
        
        if rejection_flag and execution_latency > 2500:
            emission = np.array([0.05, 0.35, 0.60]) # Very likely to be in RED
        elif execution_latency > 1800:
            emission = np.array([0.20, 0.60, 0.20]) # Likely YELLOW
        else:
            emission = np.array([0.90, 0.09, 0.01]) # Likely GREEN
            
        # Bayesian update: Belief = Transition * Belief * Emission
        predicted_belief = np.dot(self.belief, self.transition_matrix)
        updated_belief = predicted_belief * emission
        
        # Normalize
        self.belief = updated_belief / np.sum(updated_belief)
        
        logger.debug(f"[HMM ADVERSARIAL] Account States -> GREEN: {self.belief[0]:.2f}, YELLOW: {self.belief[1]:.2f}, RED: {self.belief[2]:.2f}")

    def get_restriction_probability(self) -> float:
        """
        Returns P(account_restricted) which is the probability of being in YELLOW or RED state.
        """
        return self.belief[1] + self.belief[2]

hmm_detector = HiddenMarkovThrottleDetector()
