import logging
import numpy as np
from scipy.stats import entropy
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class ConceptDriftMonitor:
    """
    Online Learning Pipeline: Detects concept drift in live execution telemetry.
    Uses Population Stability Index (PSI) and KL-Divergence to monitor when 
    the live environment structurally deviates from the training environment.
    """
    def __init__(self, psi_threshold: float = 0.2, kl_threshold: float = 0.5):
        self.psi_threshold = psi_threshold
        self.kl_threshold = kl_threshold
        
    def calculate_psi(self, expected_dist: np.ndarray, actual_dist: np.ndarray, buckets: int = 10) -> float:
        """
        Calculates Population Stability Index.
        PSI < 0.1: No change. 0.1 <= PSI < 0.2: Slight change. PSI >= 0.2: Significant change.
        """
        def get_bucket_proportions(data, bins):
            hist, _ = np.histogram(data, bins=bins)
            prop = hist / np.sum(hist)
            # Add epsilon to avoid division by zero
            return np.where(prop == 0, 1e-6, prop)

        # Create common bin edges spanning both distributions
        min_val = min(np.min(expected_dist), np.min(actual_dist))
        max_val = max(np.max(expected_dist), np.max(actual_dist))
        bins = np.linspace(min_val, max_val, buckets + 1)
        
        expected_prop = get_bucket_proportions(expected_dist, bins)
        actual_prop = get_bucket_proportions(actual_dist, bins)
        
        psi_values = (actual_prop - expected_prop) * np.log(actual_prop / expected_prop)
        total_psi = np.sum(psi_values)
        return total_psi

    def calculate_kl_divergence(self, expected_dist: np.ndarray, actual_dist: np.ndarray, buckets: int = 10) -> float:
        """
        Calculates Kullback-Leibler divergence between actual execution latency
        and the expected latency distribution.
        """
        min_val = min(np.min(expected_dist), np.min(actual_dist))
        max_val = max(np.max(expected_dist), np.max(actual_dist))
        bins = np.linspace(min_val, max_val, buckets + 1)
        
        hist_exp, _ = np.histogram(expected_dist, bins=bins, density=False)
        hist_act, _ = np.histogram(actual_dist, bins=bins, density=False)
        
        # Convert to probability distributions
        hist_exp = hist_exp / (np.sum(hist_exp) + 1e-10)
        hist_act = hist_act / (np.sum(hist_act) + 1e-10)
        
        hist_exp = np.where(hist_exp == 0, 1e-6, hist_exp)
        hist_act = np.where(hist_act == 0, 1e-6, hist_act)
        
        return entropy(hist_act, hist_exp)

    def evaluate_drift(self, expected_latency: List[float], recent_latency: List[float]) -> Dict[str, Any]:
        """
        Evaluates structural market drift. If the sportsbook introduces artificial 
        delays to combat our edge, the distributions will diverge.
        """
        if not expected_latency or not recent_latency:
            return {"status": "insufficient_data"}
            
        exp_arr = np.array(expected_latency)
        act_arr = np.array(recent_latency)
        
        psi = self.calculate_psi(exp_arr, act_arr)
        kl_div = self.calculate_kl_divergence(exp_arr, act_arr)
        
        is_drifting = psi >= self.psi_threshold or kl_div >= self.kl_threshold
        
        status = "DRIFT_DETECTED" if is_drifting else "STABLE"
        
        if is_drifting:
            logger.warning(f"[DRIFT MONITOR] Structural drift! PSI: {psi:.3f}, KL: {kl_div:.3f}")
            
        return {
            "status": status,
            "psi": round(psi, 4),
            "kl_divergence": round(kl_div, 4)
        }

drift_monitor = ConceptDriftMonitor()
