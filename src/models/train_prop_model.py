import pandas as pd
import lightgbm as lgb
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import mean_squared_error
import numpy as np

def build_unified_feature_store(df_base, opponent_df, rolling_df, venue_df, tactics_df, market_df, fatigue_df):
    """
    Combines all engineered features into a unified 150+ feature modeling dataset.
    In production, this would be handled by a Feature Store (e.g., Feast).
    """
    # Merge sequentially on Match/Player keys
    df = df_base.merge(opponent_df, on=['Date', 'Opponent'], how='left')
    df = df.merge(rolling_df, on=['Date', 'Player'], how='left')
    df = df.merge(venue_df, on=['Date', 'Player'], how='left')
    df = df.merge(tactics_df, on=['Date', 'Squad'], how='left')
    df = df.merge(market_df, on=['Match_ID'], how='left')
    df = df.merge(fatigue_df, on=['Date', 'Player'], how='left')
    
    # Fill remaining NaNs from cold starts
    df = df.fillna(0)
    return df

def train_prop_model_lightgbm(df: pd.DataFrame, target: str, features: list):
    """
    Trains the final Player Prop model using LightGBM.
    We use Poisson regression because Shots/Goals are count data (0, 1, 2, 3...).
    """
    # Ensure chronological order
    df = df.sort_values(by='Date').reset_index(drop=True)
    
    X = df[features]
    y = df[target]
    
    # We must predict per-90 rates, not raw counts, so we use Minutes as the "exposure" variable
    # In LightGBM, we can pass this as init_score = np.log(Minutes)
    # For simplicity in this example, we assume `target` is already scaled to per-90
    
    tscv = TimeSeriesSplit(n_splits=5)
    cv_scores = []
    
    # LightGBM is chosen for speed, categorical handling, and Poisson support
    model = lgb.LGBMRegressor(
        objective='poisson',
        n_estimators=300,
        learning_rate=0.03,
        max_depth=6,
        colsample_bytree=0.8,
        subsample=0.8,
        random_state=42,
        verbose=-1
    )
    
    print(f"Training Unified Framework for: {target}")
    
    for train_index, test_index in tscv.split(X):
        X_train, X_test = X.iloc[train_index], X.iloc[test_index]
        y_train, y_test = y.iloc[train_index], y.iloc[test_index]
        
        model.fit(X_train, y_train)
        preds = model.predict(X_test)
        
        score = np.sqrt(mean_squared_error(y_test, preds))
        cv_scores.append(score)
        
    print(f"TimeSeries Validation RMSE for {target}: {np.mean(cv_scores):.4f}")
    
    # Final Fit
    model.fit(X, y)
    return model

def backtest_framework(model, df, features, target, odds_df):
    """
    Backtesting workflow to simulate betting profitability.
    """
    # Walk-forward simulation using Kelly Criterion
    # For a Poisson model, target is lambda. P(X >= x) can be calculated.
    # In this mock backtest, we just demonstrate +EV calculation against an over/under line of 1.5
    
    from scipy.stats import poisson
    
    results = df.copy()
    results['predicted_lambda'] = model.predict(df[features])
    
    # Assume we are betting "Over 1.5" (meaning 2 or more goals/shots)
    # P(X >= 2) = 1 - P(X = 0) - P(X = 1)
    results['prob_over_1_5'] = 1 - poisson.cdf(1, results['predicted_lambda'])
    
    # If odds_df was provided, we merge it. Let's assume we have 'odds_over_1_5'
    if 'odds_over_1_5' in results.columns:
        results['implied_prob'] = 1 / results['odds_over_1_5']
        
        # Expected Value = (Prob_Win * Profit) - (Prob_Loss * Wager)
        results['EV'] = (results['prob_over_1_5'] * (results['odds_over_1_5'] - 1)) - (1 - results['prob_over_1_5'])
        
        # Kelly Criterion = (bp - q) / b
        # where b is net fractional odds (decimal - 1), p is prob win, q is prob loss
        results['b'] = results['odds_over_1_5'] - 1
        results['kelly_fraction'] = (results['b'] * results['prob_over_1_5'] - (1 - results['prob_over_1_5'])) / results['b']
        
        # Only bet if EV > 0 (meaning kelly > 0)
        # We cap Kelly at 0.05 (5% bankroll) for safety
        results['bet_size_pct'] = np.where(results['kelly_fraction'] > 0, np.minimum(results['kelly_fraction'], 0.05), 0)
        
        print(f"Total +EV Bets Identified: {(results['bet_size_pct'] > 0).sum()}")
    
    return results

if __name__ == "__main__":
    print("Final Modeling Framework Module Loaded.")
