import pandas as pd
import numpy as np

def calculate_availability_features(df: pd.DataFrame, key_players_dict: dict = None) -> pd.DataFrame:
    """
    Calculates lineup, availability, and key-teammate absence features.
    
    Expected Input DataFrame `df`:
    Must contain player-level match aggregates:
    ['Date', 'Player', 'Squad', 'Start', 'Min', 'Captain']
    """
    df = df.sort_values(by=['Player', 'Date']).reset_index(drop=True)
    
    # 1. Starting Status Features (Redundant with Minutes model, but useful globally)
    if 'is_starter' not in df.columns:
        if 'Start' in df.columns:
            df['is_starter'] = df['Start'].apply(lambda x: 1 if str(x).upper() in ['Y', '1', 'YES', 'TRUE'] else 0)
        else:
            # Proxy: if they played >= 45 mins, assume they started
            df['is_starter'] = np.where(df['Min'] >= 45, 1, 0)
        
    df['started_last_match'] = df.groupby('Player')['is_starter'].shift(1).fillna(0)
    df['started_last_3'] = df.groupby('Player')['is_starter'].transform(
        lambda x: x.shift(1).rolling(3, min_periods=1).sum()
    ).fillna(0)
    
    # 2. Captaincy
    # FBref provides 'Captain' in summary tables as 'Y'/'N'
    if 'Captain' in df.columns:
        df['is_captain'] = df['Captain'].apply(lambda x: 1 if str(x).upper() in ['Y', '1', 'YES'] else 0)
    else:
        df['is_captain'] = 0
        
    # 3. Key Teammate Missing Logic
    # In sports betting, if Messi is out, Di Maria's shot volume spikes.
    # We must detect if the "alpha" of the squad played in the match.
    
    df['key_teammate_missing'] = 0
    
    if key_players_dict:
        # key_players_dict format: {'Argentina': ['Lionel Messi'], 'France': ['Kylian Mbappé']}
        
        # Create a boolean mask of matches where key players actually played > 0 minutes
        key_player_matches = df[(df['Player'].isin(
            [p for players in key_players_dict.values() for p in players]
        )) & (df['Min'] > 0)][['Date', 'Squad', 'Player']].copy()
        
        key_player_matches['key_player_active'] = 1
        
        for squad, alphas in key_players_dict.items():
            df[df['Squad'] == squad].copy()
            
            # For each match this squad played, did the alpha play?
            for alpha in alphas:
                alpha_active_dates = key_player_matches[key_player_matches['Player'] == alpha]['Date'].values
                
                # If a player is on this squad, and the date is NOT in alpha_active_dates, the key teammate is missing
                mask = (df['Squad'] == squad) & (~df['Date'].isin(alpha_active_dates))
                df.loc[mask, 'key_teammate_missing'] = 1
                
    # 4. Projected Starting Status (for future inference)
    # If evaluating a future game where Start is unknown, we predict it.
    # Simple heuristic: If you started 3 of the last 3, you are projected to start.
    df['projected_starting_status'] = np.where(df['started_last_3'] >= 2, 1, 0)
    
    return df

if __name__ == "__main__":
    print("Availability Features Module Loaded.")
