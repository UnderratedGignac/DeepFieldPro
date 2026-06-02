"""
W3 FIX: Probabilistic Regime Compounding Detector.
Replaces hard boolean thresholds with a soft-score model that outputs a
continuous decay_probability in [0, 1]. COMPOUNDING/NEUTRAL/DECAY zones
are determined by probability bands, not crisp if/else boundaries.
"""
import math
import logging
from typing import Tuple
from src.capital_scaling_intelligence.schemas import CompoundingRegime

logger = logging.getLogger(__name__)


def _sigmoid(x: float) -> float:
    """Standard sigmoid: maps any real to (0, 1)."""
    return 1.0 / (1.0 + math.exp(-x))


class RegimeCompoundingDetector:
    """
    Detects structural compounding regime using a weighted soft-score model.

    Each input signal is normalized and pushed through a sigmoid to produce
    a partial decay score in [0, 1]. These partial scores are combined via
    a weighted sum into a single decay_probability.

      decay_prob → 1.0  means high confidence of DECAY (reduce exposure)
      decay_prob → 0.0  means high confidence of COMPOUNDING (safe to scale)
      0.3 – 0.7  means NEUTRAL (hold flat)

    Signal weights (tunable):
      drawdown_autocorr  0.35  — cluster losses are the most dangerous signal
      friction_trend     0.30  — rising friction → bookmaker is adapting
      rvl_drift          0.20  — negative RVL drift → real-world edge is eroding
      clv_instability    0.15  — low CLV stability → edge is noise, not structure
    """
    # Weights must sum to 1.0
    _W_DRAWDOWN_AUTOCORR = 0.35
    _W_FRICTION_TREND    = 0.30
    _W_RVL_DRIFT         = 0.20
    _W_CLV_INSTABILITY   = 0.15

    # Probability bands
    _DECAY_THRESHOLD      = 0.60   # decay_prob > 0.60 → DECAY
    _COMPOUNDING_THRESHOLD = 0.35  # decay_prob < 0.35 → COMPOUNDING

    def detect_regime(self, clv_stability: float, friction_trend: float,
                      rvl_drift: float, drawdown_autocorr: float) -> CompoundingRegime:
        """
        Returns the regime AND a decay confidence score.
        All inputs are raw floats:
          clv_stability:    [0, 1]   higher = more stable
          friction_trend:   [-∞, ∞]  positive = friction rising (bad)
          rvl_drift:        [-∞, ∞]  positive = RVL improving (good)
          drawdown_autocorr:[0, 1]   higher = losses clustering (bad)
        """
        decay_prob, details = self._compute_decay_probability(
            clv_stability, friction_trend, rvl_drift, drawdown_autocorr
        )

        if decay_prob > self._DECAY_THRESHOLD:
            regime = CompoundingRegime.DECAY
            logger.warning(
                f"[COMPOUND DETECTOR] DECAY regime | decay_prob={decay_prob:.3f} | {details}"
            )
        elif decay_prob < self._COMPOUNDING_THRESHOLD:
            regime = CompoundingRegime.COMPOUNDING
            logger.info(
                f"[COMPOUND DETECTOR] COMPOUNDING regime | decay_prob={decay_prob:.3f} | {details}"
            )
        else:
            regime = CompoundingRegime.NEUTRAL
            logger.info(
                f"[COMPOUND DETECTOR] NEUTRAL regime | decay_prob={decay_prob:.3f} | {details}"
            )

        return regime

    def _compute_decay_probability(
        self, clv_stability: float, friction_trend: float,
        rvl_drift: float, drawdown_autocorr: float
    ) -> Tuple[float, str]:
        """
        Computes weighted soft-score decay probability.
        Each signal is normalized to a partial decay score in [0, 1].
        """
        # Drawdown autocorrelation: already in [0,1]; 0=good, 1=bad
        # Scale sensitivity: center at 0.2 (mild), steep at 0.5
        s_drawdown = _sigmoid((drawdown_autocorr - 0.25) * 8.0)

        # Friction trend: positive=bad; center at 0, scale 20
        s_friction = _sigmoid(friction_trend * 20.0)

        # RVL drift: negative=bad; flip sign so decay_prob increases on bad drift
        # center at 0, scale 10
        s_rvl = _sigmoid(-rvl_drift * 10.0)

        # CLV instability: inverse of stability; low stability = high instability = bad
        clv_instability = 1.0 - clv_stability
        s_clv = _sigmoid((clv_instability - 0.3) * 8.0)

        decay_prob = (
            self._W_DRAWDOWN_AUTOCORR * s_drawdown +
            self._W_FRICTION_TREND    * s_friction +
            self._W_RVL_DRIFT         * s_rvl +
            self._W_CLV_INSTABILITY   * s_clv
        )

        details = (
            f"s_drawdown={s_drawdown:.2f} s_friction={s_friction:.2f} "
            f"s_rvl={s_rvl:.2f} s_clv={s_clv:.2f}"
        )
        return decay_prob, details


compounding_detector = RegimeCompoundingDetector()

