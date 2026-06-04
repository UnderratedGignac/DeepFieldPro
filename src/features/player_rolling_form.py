import pandas as pd
import numpy as np

def calculate_player_rolling_form(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculates rolling performance metrics for individual players (Rolling Form).
    Crucially, these features are calculated using ONLY data available BEFORE kickoff.
    
    Expected Input DataFrame `df`:
    Must contain player-level match aggregates:
    ['Date', 'Player', 'Sh', 'SoT', 'xG', 'xAG', 'Min']
    """
    # 1. Sort chronologically by Player, then Date to prevent future leakage
    df = df.sort_values(by=['Player', 'Date']).reset_index(drop=True)
    
    # 2. Define the metrics we want to create rolling features for
    metrics = ['Sh', 'SoT', 'xG', 'xAG', 'Min']
    windows = [3, 5, 10]
    
    # 3. Calculate Rolling Averages
    # We group by Player and calculate rolling means. 
    # The shift(1) is absolutely critical to avoid data leakage (including the current match).
    for metric in metrics:
        for w in windows:
            # Map FBref column names to clear feature names
            feature_name = metric.lower() if metric != 'Min' else 'minutes'
            col_name = f"{feature_name}_last_{w}"
            
            # Efficient rolling calculation that avoids MemoryError
            shifted = df.groupby('Player')[metric].shift(1)
            df[col_name] = shifted.groupby(df['Player']).rolling(window=w, min_periods=1).mean().reset_index(0, drop=True)
            
    # 4. Calculate Rolling Standard Deviations (Volatility/Variance)
    # This helps models understand if a player is consistent or highly volatile.
    std_metrics = ['Sh', 'SoT', 'xG', 'Min']
    for metric in std_metrics:
        feature_name = metric.lower() if metric != 'Min' else 'minutes'
        col_name = f"rolling_std_{feature_name}"
        
        # We use a 10-match window for standard deviation to ensure enough sample size
        shifted = df.groupby('Player')[metric].shift(1)
        df[col_name] = shifted.groupby(df['Player']).rolling(window=10, min_periods=2).std().reset_index(0, drop=True)
        
    # 5. Handle missing values for rookies / start of season
    # For std dev, 1 match will result in NaN, fill with 0 variance for now
    std_cols = [c for c in df.columns if c.startswith('rolling_std_')]
    df[std_cols] = df[std_cols].fillna(0)
    
    return df

if __name__ == "__main__":
    print("Player Rolling Form Module Loaded.")
