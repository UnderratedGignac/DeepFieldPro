import pandas as pd

def calculate_referee_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Engineers referee tendency features to predict card and penalty probabilities.
    
    Expected Input DataFrame `df`:
    Must contain match-level logs including the Referee's name:
    ['Date', 'Referee', 'CrdY', 'CrdR', 'PKatt']
    """
    
    if 'Referee' not in df.columns:
        # If referee data is missing, we cannot engineer these features.
        return df
        
    df = df.sort_values(by=['Referee', 'Date']).reset_index(drop=True)
    
    # 1. We must aggregate match totals first. 
    # Because player logs contain individual cards, we need the TOTAL cards/pens in the match.
    match_totals = df.groupby(['Date', 'Referee', 'Match_ID'])[['CrdY', 'CrdR', 'PKatt']].sum().reset_index()
    match_totals = match_totals.sort_values(by=['Referee', 'Date'])
    
    # 2. Calculate the Referee's historical rolling averages
    # We use expanding means but shifted to prevent leakage
    match_totals['ref_yellow_avg'] = match_totals.groupby('Referee')['CrdY'].transform(
        lambda x: x.shift(1).expanding().mean()
    )
    
    match_totals['ref_red_avg'] = match_totals.groupby('Referee')['CrdR'].transform(
        lambda x: x.shift(1).expanding().mean()
    )
    
    match_totals['ref_penalties_awarded'] = match_totals.groupby('Referee')['PKatt'].transform(
        lambda x: x.shift(1).expanding().mean()
    )
    
    # 3. Handle early-career referees (fill with league average)
    league_avg_y = match_totals['CrdY'].expanding().mean().shift(1)
    league_avg_r = match_totals['CrdR'].expanding().mean().shift(1)
    league_avg_pk = match_totals['PKatt'].expanding().mean().shift(1)
    
    match_totals['ref_yellow_avg'] = match_totals['ref_yellow_avg'].fillna(league_avg_y)
    match_totals['ref_red_avg'] = match_totals['ref_red_avg'].fillna(league_avg_r)
    match_totals['ref_penalties_awarded'] = match_totals['ref_penalties_awarded'].fillna(league_avg_pk)
    
    # 4. Merge back onto the player logs
    # We only need the calculated averages, not the match totals
    features_to_merge = ['Match_ID', 'ref_yellow_avg', 'ref_red_avg', 'ref_penalties_awarded']
    
    df = df.merge(match_totals[features_to_merge], on='Match_ID', how='left')
    
    return df

if __name__ == "__main__":
    print("Referee Features Module Loaded.")
