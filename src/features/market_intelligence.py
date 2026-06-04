import pandas as pd
import numpy as np

def calculate_market_intelligence(df: pd.DataFrame) -> pd.DataFrame:
    """
    Engineers betting-market features based on historical odds data.
    
    Expected Input DataFrame `df`:
    Must contain match-level odds data merged onto the player log:
    ['Date', 'Match_ID', 'opening_odds', 'current_odds', 'closing_odds']
    
    *Note: If calculating pre-match, 'closing_odds' will not be available, 
    so we use 'current_odds' for live inference.
    """
    
    # Check if the dataframe actually contains the odds columns
    odds_cols = ['opening_odds', 'current_odds', 'closing_odds']
    for col in odds_cols:
        if col not in df.columns:
            # Placeholder for missing odds data
            df[col] = 1.0
            
    # Calculate Line Movement (absolute difference)
    # Negative line movement means the odds dropped (became more favored)
    df['line_movement'] = df['current_odds'] - df['opening_odds']
    
    # Calculate Odds Drift (percentage change)
    # Positive drift means the market is losing confidence (odds increasing)
    df['odds_drift'] = (df['current_odds'] - df['opening_odds']) / df['opening_odds']
    
    # Steam Move Indicator
    # A "steam move" is a massive, sudden line movement usually caused by sharp money.
    # We define it arbitrarily here as a >15% drop from opening odds.
    df['steam_move'] = np.where(df['odds_drift'] < -0.15, 1, 0)
    
    # Convert Odds to Implied Probability
    # Useful for feeding the model raw probabilities rather than European decimal odds
    df['implied_prob_opening'] = 1 / df['opening_odds']
    df['implied_prob_current'] = 1 / df['current_odds']
    
    return df

if __name__ == "__main__":
    print("Market Intelligence Features Module Loaded.")
