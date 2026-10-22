"""
tests/test_probability_engine.py
--------------------------------
Unit tests for CalibBet v1.0 probability engine.
Ensures strict temporal splitting and checks for look-ahead bias/leakage.
"""

import pytest
import pandas as pd
import numpy as np
from feature_store import build_features
from probability_engine import CalibBetEngine, TemporalWalkForward

def test_temporal_leakage():
    """
    Leakage Shield test: changing future data must not affect past engineered features.
    """
    # Create synthetic chronologically ordered match logs
    data = {
        "date": ["01/01/2024", "05/01/2024", "10/01/2024", "15/01/2024"],
        "home": ["Arsenal", "Chelsea", "Arsenal", "Liverpool"],
        "away": ["Chelsea", "Liverpool", "Liverpool", "Arsenal"],
        "home_goals": [2, 1, 3, 0],
        "away_goals": [1, 2, 1, 2],
        "odds_h": [1.8, 2.1, 1.9, 2.0],
        "odds_d": [3.4, 3.3, 3.4, 3.3],
        "odds_a": [4.2, 3.2, 3.8, 3.5],
        "odds_ch": [1.85, 2.15, 1.95, 2.05],
        "odds_cd": [3.45, 3.35, 3.45, 3.35],
        "odds_ca": [4.15, 3.15, 3.75, 3.45]
    }
    df1 = pd.DataFrame(data)
    
    # Generate features for df1
    df1_features = build_features(df1, k_factor=32, rolling_window=2)
    
    # Create df2 where we modify the last (future) match result
    df2 = pd.DataFrame(data)
    df2.loc[3, "home_goals"] = 5  # Modify the future result
    df2.loc[3, "away_goals"] = 0
    df2_features = build_features(df2, k_factor=32, rolling_window=2)
    
    # Check that features for the first 3 matches (past) are identical
    for col in ["home_elo", "away_elo", "elo_diff", "recent_xg_diff", "rest_days_home"]:
        pd.testing.assert_series_equal(
            df1_features.loc[0:2, col],
            df2_features.loc[0:2, col],
            obj=f"Leakage detected in feature: {col}"
        )

def test_walk_forward_no_overlap():
    """
    Ensure walk-forward splits do not overlap chronologically.
    """
    dates = pd.date_range(start="2021-01-01", end="2026-06-01", freq="W")
    df = pd.DataFrame({
        "date": dates,
        "home": ["Arsenal"] * len(dates),
        "away": ["Chelsea"] * len(dates),
        "home_goals": [1] * len(dates),
        "away_goals": [1] * len(dates),
        "odds_h": [2.0] * len(dates),
        "odds_d": [3.0] * len(dates),
        "odds_a": [3.0] * len(dates),
        "odds_ch": [2.0] * len(dates),
        "odds_cd": [3.0] * len(dates),
        "odds_ca": [3.0] * len(dates)
    })
    # Run build features to generate required columns
    df = build_features(df)
    
    windows = [
        {
            "train_years": [2021, 2022],
            "val_years": [2023],
            "test_years": [2024]
        },
        {
            "train_years": [2021, 2022, 2023],
            "val_years": [2024],
            "test_years": [2025]
        }
    ]
    
    twf = TemporalWalkForward()
    splits = twf.get_splits(df, windows)
    
    for split in splits:
        train_years = split["train"]["date_parsed"].dt.year.unique()
        val_years = split["val"]["date_parsed"].dt.year.unique()
        test_years = split["test"]["date_parsed"].dt.year.unique()
        
        # Ensure no overlap
        assert len(set(train_years).intersection(val_years)) == 0
        assert len(set(train_years).intersection(test_years)) == 0
        assert len(set(val_years).intersection(test_years)) == 0
        
        # Chronological order check
        assert max(train_years) < min(val_years)
        assert max(val_years) < min(test_years)

def test_calib_bet_engine_outputs():
    """
    Verify engine outputs sum to 1.0 and predictions are in valid range.
    """
    train_data = {
        "date": ["01/01/2021", "05/01/2021", "10/01/2021", "15/01/2021", "20/01/2021"],
        "home": ["Arsenal", "Chelsea", "Arsenal", "Liverpool", "Man United"],
        "away": ["Chelsea", "Liverpool", "Liverpool", "Arsenal", "Chelsea"],
        "home_goals": [2, 1, 3, 0, 1],
        "away_goals": [1, 2, 1, 2, 1],
        "odds_h": [1.8, 2.1, 1.9, 2.0, 2.2],
        "odds_d": [3.4, 3.3, 3.4, 3.3, 3.2],
        "odds_a": [4.2, 3.2, 3.8, 3.5, 3.1],
        "odds_ch": [1.85, 2.15, 1.95, 2.05, 2.25],
        "odds_cd": [3.45, 3.35, 3.45, 3.35, 3.25],
        "odds_ca": [4.15, 3.15, 3.75, 3.45, 3.15]
    }
    
    val_data = {
        "date": ["01/01/2022", "05/01/2022", "10/01/2022"],
        "home": ["Arsenal", "Chelsea", "Liverpool"],
        "away": ["Liverpool", "Arsenal", "Man United"],
        "home_goals": [1, 2, 2],
        "away_goals": [1, 0, 1],
        "odds_h": [2.0, 1.9, 1.8],
        "odds_d": [3.3, 3.4, 3.5],
        "odds_a": [3.5, 3.8, 4.0],
        "odds_ch": [2.05, 1.95, 1.85],
        "odds_cd": [3.35, 3.45, 3.55],
        "odds_ca": [3.45, 3.75, 3.95]
    }
    
    train_df = build_features(pd.DataFrame(train_data))
    val_df = build_features(pd.DataFrame(val_data))
    
    engine = CalibBetEngine()
    engine.fit(train_df, val_df, lgb_params={"n_estimators": 5, "num_leaves": 3, "min_child_samples": 1, "verbosity": -1})
    
    preds = engine.predict_proba(val_df)
    
    # Check that predicted probabilities are in [0, 1]
    assert np.all(preds.values >= 0.0)
    assert np.all(preds.values <= 1.0)
    
    # Check that they sum to 1.0 for each match
    sums = preds.sum(axis=1).values
    np.testing.assert_allclose(sums, 1.0, rtol=1e-5)
