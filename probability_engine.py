"""
probability_engine.py
---------------------
Core engine for CalibBet v1.0.
Contains CalibBetEngine, TemporalWalkForward validator, IsotonicCalibrator,
and statistical metric functions for evaluating sports betting probabilities.
"""

import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from scipy.stats import linregress
import pickle
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("probability_engine")

class IsotonicCalibrator:
    """
    Calibrator using Isotonic Regression to map raw model predictions
    to well-calibrated probabilities.
    """
    def __init__(self):
        self.ir = IsotonicRegression(out_of_bounds="clip")
        self.is_fitted = False

    def fit(self, raw_probs, outcomes):
        """
        Fits Isotonic Regression.
        raw_probs: np.ndarray, raw uncalibrated probabilities (usually in [0, 1])
        outcomes: np.ndarray, true binary outcomes (0 or 1)
        """
        raw_probs = np.clip(raw_probs, 0.0, 1.0)
        self.ir.fit(raw_probs, outcomes)
        self.is_fitted = True
        return self

    def predict(self, raw_probs):
        """
        Calibrates raw probabilities.
        """
        if not self.is_fitted:
            raise ValueError("Calibrator is not fitted yet.")
        raw_probs = np.clip(raw_probs, 0.0, 1.0)
        return self.ir.predict(raw_probs)


class TemporalWalkForward:
    """
    Performs chronological walk-forward splits on historical data to prevent look-ahead bias.
    """
    def __init__(self, date_col="date_parsed"):
        self.date_col = date_col

    def get_splits(self, df, windows):
        """
        Generates train/validation/test splits based on years or dates.
        windows: List of dicts, e.g.:
          [
            {
              "train_years": [2021, 2022, 2023],
              "val_years": [2024],
              "test_years": [2025]
            },
            ...
          ]
        """
        df = df.copy()
        df["year"] = df[self.date_col].dt.year
        
        splits = []
        for w in windows:
            train_mask = df["year"].isin(w["train_years"])
            val_mask = df["year"].isin(w["val_years"])
            test_mask = df["year"].isin(w["test_years"])
            
            splits.append({
                "train": df[train_mask],
                "val": df[val_mask],
                "test": df[test_mask]
            })
            logger.info(f"Split generated: Train={train_mask.sum()}, Val={val_mask.sum()}, Test={test_mask.sum()}")
        return splits


class CalibBetEngine:
    """
    CalibBet Engine predicting calibrated 1X2 match probabilities using residual LightGBM training.
    """
    def __init__(self, features=None):
        if features is None:
            self.features = [
                "elo_diff", "recent_xg_diff", "rest_days_home", "rest_days_away",
                "rest_diff", "home_fatigue", "away_fatigue", "home_advantage",
                "implied_prob_ch_norm", "implied_prob_cd_norm", "implied_prob_ca_norm"
            ]
        else:
            self.features = features
            
        self.models = {}  # outcome -> LightGBM Regressor
        self.calibrators = {}  # outcome -> IsotonicCalibrator
        self.outcomes = ["home_win", "draw", "away_win"]

    def fit(self, train_df, val_df, lgb_params=None):
        """
        Trains residual LightGBM models on train_df and fits Isotonic Calibrators on val_df.
        """
        if lgb_params is None:
            lgb_params = {
                "n_estimators": 150,
                "learning_rate": 0.03,
                "num_leaves": 15,
                "min_child_samples": 20,
                "verbosity": -1,
                "random_state": 42
            }

        X_train = train_df[self.features]
        X_val = val_df[self.features]

        for outcome in self.outcomes:
            logger.info(f"Training base residual model for: {outcome}")
            # Target = Win/Loss - Implied probability (Market Odds residual)
            implied_col = f"implied_prob_c{outcome[0]}_norm"  # e.g., implied_prob_ch_norm
            y_train_true = train_df[outcome]
            p_train_implied = train_df[implied_col]
            y_train_resid = y_train_true - p_train_implied

            # LightGBM Regressor to predict the market inefficiency residual
            model = lgb.LGBMRegressor(**lgb_params)
            model.fit(X_train, y_train_resid)
            self.models[outcome] = model

            # Validate and Fit Calibrator
            # Predict raw prob on validation set: p_raw = p_implied + model_pred
            y_val_true = val_df[outcome]
            p_val_implied = val_df[implied_col]
            
            raw_val_preds = p_val_implied + model.predict(X_val)
            raw_val_preds = np.clip(raw_val_preds, 0.0, 1.0)

            logger.info(f"Fitting Isotonic Calibrator for: {outcome}")
            calibrator = IsotonicCalibrator()
            calibrator.fit(raw_val_preds, y_val_true)
            self.calibrators[outcome] = calibrator

    def predict_proba(self, df):
        """
        Predicts calibrated, normalized probabilities for Home Win, Draw, and Away Win.
        """
        X = df[self.features]
        raw_preds = {}
        cal_preds = {}

        for outcome in self.outcomes:
            implied_col = f"implied_prob_c{outcome[0]}_norm"
            p_implied = df[implied_col].values
            
            # Predict residual and compute raw prob
            model = self.models[outcome]
            pred_resid = model.predict(X)
            raw_prob = np.clip(p_implied + pred_resid, 0.0, 1.0)
            raw_preds[outcome] = raw_prob
            
            # Apply Isotonic Calibration
            calibrator = self.calibrators[outcome]
            cal_prob = calibrator.predict(raw_prob)
            cal_preds[outcome] = cal_prob

        # Convert to numpy arrays
        home_probs = cal_preds["home_win"]
        draw_probs = cal_preds["draw"]
        away_probs = cal_preds["away_win"]

        # Normalize to sum to 1.0 across outcomes
        total_probs = home_probs + draw_probs + away_probs
        # Avoid division by zero
        total_probs = np.where(total_probs == 0, 1.0, total_probs)
        
        home_probs_norm = home_probs / total_probs
        draw_probs_norm = draw_probs / total_probs
        away_probs_norm = away_probs / total_probs

        return pd.DataFrame({
            "home_win": home_probs_norm,
            "draw": draw_probs_norm,
            "away_win": away_probs_norm
        }, index=df.index)

    def save(self, file_path):
        """
        Saves CalibBetEngine instance to disk.
        """
        os.makedirs(os.path.dirname(file_path) if os.path.dirname(file_path) else ".", exist_ok=True)
        with open(file_path, "wb") as f:
            pickle.dump({
                "features": self.features,
                "models": self.models,
                "calibrators": self.calibrators
            }, f)
        logger.info(f"CalibBetEngine saved to {file_path}")

    def load(self, file_path):
        """
        Loads CalibBetEngine instance from disk.
        """
        with open(file_path, "rb") as f:
            data = pickle.load(f)
        self.features = data["features"]
        self.models = data["models"]
        self.calibrators = data["calibrators"]
        logger.info(f"CalibBetEngine loaded from {file_path}")
        return self


# --- Statistics and Evaluation Metrics ---

def calculate_ece(y_true, y_prob, n_bins=10):
    """
    Computes the Expected Calibration Error (ECE) for binary predictions.
    """
    y_true = np.array(y_true)
    y_prob = np.array(y_prob)
    
    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    
    for i in range(n_bins):
        bin_lower = bin_boundaries[i]
        bin_upper = bin_boundaries[i + 1]
        
        # Determine samples in current bin
        in_bin = (y_prob >= bin_lower) & (y_prob < bin_upper)
        prop_in_bin = np.mean(in_bin)
        
        if prop_in_bin > 0:
            accuracy_in_bin = np.mean(y_true[in_bin])
            avg_confidence_in_bin = np.mean(y_prob[in_bin])
            ece += prop_in_bin * np.abs(avg_confidence_in_bin - accuracy_in_bin)
            
    return ece

def calculate_reliability_slope(y_true, y_prob, n_bins=10):
    """
    Calculates the slope of the reliability curve. A perfect model has slope = 1.0.
    """
    y_true = np.array(y_true)
    y_prob = np.array(y_prob)
    
    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    bin_accs = []
    bin_confs = []
    
    for i in range(n_bins):
        bin_lower = bin_boundaries[i]
        bin_upper = bin_boundaries[i + 1]
        
        in_bin = (y_prob >= bin_lower) & (y_prob < bin_upper)
        if np.sum(in_bin) > 5:  # Require at least a few samples to compute stable win rate
            bin_accs.append(np.mean(y_true[in_bin]))
            bin_confs.append(np.mean(y_prob[in_bin]))
            
    if len(bin_accs) < 2:
        return np.nan
        
    slope, _, _, _, _ = linregress(bin_confs, bin_accs)
    return slope

def evaluate_predictions(y_true, y_prob, name="Model"):
    """
    Computes and displays Brier Score, Log Loss, ECE, ROC-AUC, and Reliability Slope.
    """
    bs = brier_score_loss(y_true, y_prob)
    ll = log_loss(y_true, np.clip(y_prob, 1e-15, 1 - 1e-15))
    ece = calculate_ece(y_true, y_prob)
    auc = roc_auc_score(y_true, y_prob)
    slope = calculate_reliability_slope(y_true, y_prob)
    
    metrics = {
        "brier_score": bs,
        "log_loss": ll,
        "ece": ece,
        "roc_auc": auc,
        "reliability_slope": slope
    }
    
    print(f"\nEvaluation Metrics for {name}:")
    print(f"  Brier Score:       {bs:.4f}")
    print(f"  Log Loss:          {ll:.4f}")
    print(f"  ECE:               {ece * 100:.2f}%")
    print(f"  ROC-AUC:           {auc:.4f}")
    print(f"  Reliability Slope: {slope:.3f}")
    
    return metrics
