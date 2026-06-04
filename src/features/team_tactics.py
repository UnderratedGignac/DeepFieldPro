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
    # True PPDA requires Opponent Passes / Team Defensive Actions.
    # As a proxy, if we have 'Tkl' and 'Int' from advanced tables, we can invert them to get pressing intensity.
    if 'PPDA' not in team_log.columns:
        if 'Tkl' in team_log.columns and 'Int' in team_log.columns:
            # Proxy: 100 / (Tackles + Interceptions + 1)
            # Higher tackles/int = lower proxy score (meaning higher press)
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
    
    # 3. Calculate Rolling Team Tactics (shift(1) prevents leakage)
    def calculate_rolling(df_log, team_col, feature, windows):
        for w in windows:
            df_log[f'{feature}_last_{w}'] = df_log.groupby(team_col)[feature].transform(
                lambda x: x.shift(1).rolling(window=w, min_periods=1).mean()
            )
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
