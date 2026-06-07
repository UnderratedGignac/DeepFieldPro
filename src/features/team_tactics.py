import pandas as pd
import numpy as np

def calculate_team_tactics(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculates team-level tactical metrics to establish the environment the player operates in.
    Crucially, features are calculated using ONLY data available BEFORE kickoff.
    
    Expected Input DataFrame `df`:
    Must contain team-level match aggregates (or be player-level that we group up):
    ['Date', 'Squad', 'Sh', 'SoT', 'xG', 'Possession', 'PPDA']
    """
    # 1. Sort chronologically to prevent future leakage
    df = df.sort_values(by=['Squad', 'Date']).reset_index(drop=True)
    
    # 2. Extract Team-Level Base Metrics
    # If df is player-level, we would first do a groupby(['Squad', 'Date']).sum() for Sh, SoT, xG.
    # We'll assume df already contains team-aggregated columns for this function.
    
    # We want to measure the offensive and tactical strength of the Squad.
    team_log = df[['Date', 'Squad', 'xG', 'Sh', 'SoT', 'Possession']].copy()
    
    # Add a mock PPDA or Proxy PPDA if missing
    if 'PPDA' not in team_log.columns:
        if 'Tkl' in team_log.columns and 'Int' in team_log.columns:
            team_log['PPDA'] = 100 / (team_log['Tkl'] + team_log['Int'] + 1)
        else:
            team_log['PPDA'] = 12.0 # League average placeholder
        
    team_log.rename(columns={
        'xG': 'team_xg',
        'Sh': 'team_shots',
        'SoT': 'team_sot',
        'Possession': 'team_possession',
        'PPDA': 'team_ppda'
    }, inplace=True)
    
    # Aggregate to exactly 1 row per team per match to avoid merge explosion
    team_log = team_log.groupby(['Date', 'Squad']).agg({
        'team_xg': 'sum',
        'team_shots': 'sum',
        'team_sot': 'sum',
        'team_possession': 'mean',
        'team_ppda': 'mean'
    }).reset_index()
    
    team_log = team_log.sort_values(by=['Squad', 'Date']).reset_index(drop=True)
    
    # 3. Calculate Rolling Team Tactics (shift(1) prevents leakage)
    def calculate_rolling(df_log, team_col, feature, windows):
        for w in windows:
            shifted = df_log.groupby(team_col)[feature].shift(1)
            df_log[f'{feature}_last_{w}'] = shifted.groupby(df_log[team_col]).rolling(window=w, min_periods=1).mean().reset_index(0, drop=True)
        return df_log

    windows = [5]
    for feature in ['team_xg', 'team_shots', 'team_sot', 'team_possession', 'team_ppda']:
        team_log = calculate_rolling(team_log, 'Squad', feature, windows)
        
    # 4. Merge these team features back into the main dataframe
    features_to_merge = ['Date', 'Squad'] + \
                        [f'{feat}_last_5' for feat in ['team_xg', 'team_shots', 'team_sot', 'team_possession', 'team_ppda']]
    
    df = df.merge(
        team_log[features_to_merge], 
        on=['Date', 'Squad'], 
        how='left'
    )
    
    return df

if __name__ == "__main__":
    print("Team Tactics Module Loaded.")
