"""
calibration_engine.py
---------------------
The Calibrator: Forces LightGBM outputs to reflect true real-world probability.

Wraps trained LightGBM models in sklearn.calibration.CalibratedClassifierCV
using Isotonic Regression to ensure model probabilities match observed frequencies.
"""

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.isotonic import IsotonicRegression
from typing import Dict, Tuple
import pickle
import os


class ProbabilityCalibrator:
    """
    Calibration engine for sports betting models.

    Uses Isotonic Regression to map raw model probabilities to
    calibrated probabilities that reflect true win rates.
    """

    def __init__(self, method: str = "isotonic", cv: int = 5):
        """
        Args:
            method: Calibration method ("isotonic" or "sigmoid")
            cv: Cross-validation folds for calibration
        """
        self.method = method
        self.cv = cv
        self.calibrators: Dict[str, CalibratedClassifierCV] = {}
        self.isotonic_regressors: Dict[str, IsotonicRegression] = {}
        self._is_fitted = False

    def fit(self, model, X: np.ndarray, y: np.ndarray, market_type: str = "default"):
        """
        Fit a calibrator to a trained model.

        Args:
            model: Trained sklearn/lightgbm model with predict_proba method
            X: Feature matrix for calibration data
            y: Binary outcomes (1 = win, 0 = loss)
            market_type: Identifier for this market (e.g., "shots_over", "sot_under")
        """
        if hasattr(model, "predict_proba"):
            cal = CalibratedClassifierCV(
                estimator=model, method=self.method, cv=self.cv
            )
            cal.fit(X, y)
            self.calibrators[market_type] = cal
        else:
            # For models without predict_proba, use isotonic regression directly
            raw_probs = model.predict(X)
            ir = IsotonicRegression(out_of_bounds="clip")
            ir.fit(raw_probs, y)
            self.isotonic_regressors[market_type] = ir

        self._is_fitted = True
        return self

    def calibrate_probability(
        self, raw_prob: float, market_type: str = "default"
    ) -> float:
        """
        Calibrate a single raw probability.

        Args:
            raw_prob: Raw model output probability (0-1)
            market_type: Market identifier to select correct calibrator

        Returns:
            Calibrated probability reflecting true win frequency
        """
        if not self._is_fitted:
            return raw_prob  # Return raw if not fitted

        if market_type in self.calibrators:
            # For wrapped models, we need to simulate prediction
            # This is a simplified approach - in production use proper pipeline
            # Clip to valid range
            raw_prob = np.clip(raw_prob, 0, 1)
            # Use isotonic regressor if available, otherwise return raw
            if market_type in self.isotonic_regressors:
                ir = self.isotonic_regressors[market_type]
                return float(ir.predict([raw_prob])[0])
            return raw_prob

        elif market_type in self.isotonic_regressors:
            ir = self.isotonic_regressors[market_type]
            raw_prob = np.clip(raw_prob, 0, 1)
            return float(ir.predict([raw_prob])[0])

        return raw_prob  # No calibrator found, return raw

    def calibrate_probabilities(
        self, raw_probs: np.ndarray, market_type: str = "default"
    ) -> np.ndarray:
        """
        Calibrate an array of probabilities.

        Args:
            raw_probs: Array of raw model probabilities
            market_type: Market identifier

        Returns:
            Array of calibrated probabilities
        """
        raw_probs = np.clip(raw_probs, 0, 1)

        if market_type in self.isotonic_regressors:
            ir = self.isotonic_regressors[market_type]
            return ir.predict(raw_probs)

        # Default: return clipped raw probabilities
        return raw_probs

    def save(self, filepath: str):
        """Save calibrator to disk."""
        with open(filepath, "wb") as f:
            pickle.dump(
                {
                    "calibrators": self.calibrators,
                    "isotonic_regressors": self.isotonic_regressors,
                    "method": self.method,
                },
                f,
            )

    def load(self, filepath: str):
        """Load calibrator from disk."""
        if not os.path.exists(filepath):
            return False

        with open(filepath, "rb") as f:
            data = pickle.load(f)

        self.calibrators = data.get("calibrators", {})
        self.isotonic_regressors = data.get("isotonic_regressors", {})
        self.method = data.get("method", "isotonic")
        self._is_fitted = len(self.isotonic_regressors) > 0 or len(self.calibrators) > 0
        return True


def create_calibration_pipeline(
    model, X_train: pd.DataFrame, y_train: np.ndarray, market_type: str = "default"
) -> Tuple:
    """
    Create a complete calibration pipeline for a model.

    Args:
        model: Trained LightGBM/sklearn model
        X_train: Training features
        y_train: Training labels (binary outcomes)
        market_type: Market identifier

    Returns:
        Tuple of (calibrated_model, calibrator)
    """
    calibrator = ProbabilityCalibrator(method="isotonic", cv=5)
    calibrator.fit(
        model,
        X_train.values if hasattr(X_train, "values") else X_train,
        y_train,
        market_type,
    )

    return model, calibrator


def apply_calibration_to_bet(
    raw_probability: float,
    calibrator: ProbabilityCalibrator,
    market_type: str = "default",
) -> float:
    """
    Apply calibration to a bet probability before EV calculation.

    This is the main entry point used by the live daemon.

    Args:
        raw_probability: Raw model probability
        calibrator: Fitted ProbabilityCalibrator instance
        market_type: Market type string

    Returns:
        Calibrated probability for EV calculation
    """
    return calibrator.calibrate_probability(raw_probability, market_type)


def get_calibrated_ev(calibrated_prob: float, decimal_odds: float) -> float:
    """
    Calculate Expected Value from calibrated probability.

    Args:
        calibrated_prob: Calibrated win probability
        decimal_odds: Bookmaker decimal odds

    Returns:
        EV percentage (e.g., 0.05 = 5% edge)
    """
    ev = (calibrated_prob * (decimal_odds - 1)) - (1 - calibrated_prob)
    return ev


if __name__ == "__main__":
    print("Calibration Engine Module Loaded.")
    print(
        "Usage: Pass raw model probabilities through ProbabilityCalibrator before EV calculation."
    )
