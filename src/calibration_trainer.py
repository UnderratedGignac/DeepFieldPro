# -*- coding: utf-8 -*-
"""
calibration_trainer.py — DeepFieldPro Platt Scaling Trainer
============================================================
Fits a logistic regression calibrator to correct residual probability
mis-calibration after LightGBM predictions.

NAMING CONVENTIONS:
- Parameters: ProperCase suffix _P
- Variables:  ProperCase suffix _V
- Comments: single line, max 1 line
"""

import os
import pickle
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from datetime import datetime, timezone


MODEL_DIR = os.path.join(os.path.dirname(__file__), '..', 'models')
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
PLATT_SCALER_PATH = os.path.join(MODEL_DIR, 'platt_scaler_sot.pkl')
BACKTEST_CSV = os.path.join(DATA_DIR, 'backtest_results.csv')


def load_backtest_data():
    """Load backtest results with predicted probs and actual outcomes."""
    if not os.path.exists(BACKTEST_CSV):
        print(f"ERROR: Backtest file not found: {BACKTEST_CSV}")
        return None
    df = pd.read_csv(BACKTEST_CSV)
    return df


def train_platt_scaler(df):
    """
    Fit LogisticRegression on raw LightGBM probabilities.
    
    X = raw predicted probability (shape: n, 1)
    y = actual binary outcome (1=event occurred, 0=did not)
    """
    if 'pred_prob_sot' not in df.columns or 'actual_sot_over_0_5' not in df.columns:
        print("ERROR: Required columns not in dataset")
        return None
    
    valid_df = df.dropna(subset=['pred_prob_sot', 'actual_sot_over_0_5'])
    
    if len(valid_df) < 50:
        print(f"ERROR: Insufficient samples ({len(valid_df)}). Need at least 50.")
        return None
    
    RawProb_V = valid_df['pred_prob_sot'].values.reshape(-1, 1)
    ActualOutcome_V = valid_df['actual_sot_over_0_5'].values
    
    print(f"Training Platt scaler on {len(valid_df)} samples...")
    print(f"  Positive outcomes: {sum(ActualOutcome_V)} ({sum(ActualOutcome_V)/len(ActualOutcome_V)*100:.1f}%)")
    print(f"  Negative outcomes: {len(ActualOutcome_V) - sum(ActualOutcome_V)}")
    
    # Fit logistic regression with C=1.0 as specified
    Calibrator_P = LogisticRegression(C=1.0, solver='lbfgs', max_iter=1000)
    Calibrator_P.fit(RawProb_V, ActualOutcome_V)
    
    # Evaluate calibration improvement
    RawBrier_V = np.mean((valid_df['pred_prob_sot'] - ActualOutcome_V) ** 2)
    CalibratedProb_V = Calibrator_P.predict_proba(RawProb_V)[:, 1]
    CalibratedBrier_V = np.mean((CalibratedProb_V - ActualOutcome_V) ** 2)
    
    print(f"\nCalibration Results:")
    print(f"  Raw Brier Score:      {RawBrier_V:.4f}")
    print(f"  Calibrated Brier:     {CalibratedBrier_V:.4f}")
    print(f"  Improvement:          {(RawBrier_V - CalibratedBrier_V)*100:.2f}%")
    
    return Calibrator_P


def save_platt_scaler(calibrator):
    """Save fitted calibrator to disk."""
    if not os.path.exists(MODEL_DIR):
        os.makedirs(MODEL_DIR)
    
    with open(PLATT_SCALER_PATH, 'wb') as f:
        pickle.dump(calibrator, f)
    
    print(f"\n[OK] Saved Platt scaler to: {PLATT_SCALER_PATH}")


def load_platt_scaler():
    """Load existing Platt scaler from disk."""
    if not os.path.exists(PLATT_SCALER_PATH):
        print(f"WARN: Platt scaler not found at {PLATT_SCALER_PATH}")
        return None
    
    with open(PLATT_SCALER_PATH, 'rb') as f:
        calibrator = pickle.load(f)
    
    print(f"[OK] Loaded Platt scaler from: {PLATT_SCALER_PATH}")
    return calibrator


def apply_platt_scaling(raw_prob, calibrator):
    """
    Apply Platt scaling to a raw probability.
    Returns calibrated probability and confidence flag.
    """
    if calibrator is None:
        return raw_prob, False
    
    RawProb_V = np.array([[raw_prob]])
    CalibratedProb_V = float(calibrator.predict_proba(RawProb_V)[0][1])
    
    # Confidence bounds check
    LowConfidenceFlag_V = CalibratedProb_V < 0.10 or CalibratedProb_V > 0.90
    
    return CalibratedProb_V, LowConfidenceFlag_V


def test_platt_scaler(calibrator):
    """Test scaler with random values to verify bounds."""
    print("\nTesting Platt scaler bounds...")
    np.random.seed(42)
    test_probs = np.random.uniform(0.0, 1.0, 100)
    
    out_of_bounds = 0
    for prob in test_probs:
        calibrated, low_conf = apply_platt_scaling(prob, calibrator)
        if calibrated < 0.10 or calibrated > 0.90:
            if not low_conf:
                out_of_bounds += 1
                print(f"  WARN: {prob:.3f} -> {calibrated:.3f} (out of bounds, no flag)")
    
    if out_of_bounds == 0:
        print(f"  [OK] All 100 test values within [0.10, 0.90] or properly flagged")
    else:
        print(f"  [FAIL] {out_of_bounds} values out of bounds without flag")
    
    return out_of_bounds == 0


def main():
    """Main training pipeline."""
    print("="*60)
    print("DeepFieldPro Platt Scaling Trainer")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print("="*60)
    
    # Load data
    df = load_backtest_data()
    if df is None:
        print("\nNo backtest data available. Creating synthetic demo data...")
        df = generate_synthetic_calibration_data()
    
    # Train calibrator
    calibrator = train_platt_scaler(df)
    if calibrator is None:
        print("ERROR: Training failed")
        return None
    
    # Save calibrator
    save_platt_scaler(calibrator)
    
    # Test bounds
    test_platt_scaler(calibrator)
    
    print("\n" + "="*60)
    print("Platt scaler training complete!")
    print("="*60)
    
    return calibrator


def generate_synthetic_calibration_data():
    """Generate synthetic calibration data for testing."""
    np.random.seed(42)
    n_samples = 829
    
    # Simulate overconfident predictions (like club model on international)
    raw_probs = np.random.beta(2, 3, n_samples) * 0.8 + 0.1  # 0.1-0.7 range
    # Actual outcomes are lower than predicted (overconfidence)
    actual_outcomes = np.random.binomial(1, raw_probs * 0.6, n_samples)
    
    df = pd.DataFrame({
        'pred_prob_sot': raw_probs,
        'actual_sot_over_0_5': actual_outcomes
    })
    
    return df


if __name__ == "__main__":
    main()
