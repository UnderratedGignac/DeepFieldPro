import pandas as pd
import numpy as np

def add_tactical_features(df):
    """
    Adds tactical features based on team profiles.
    Requires 'team_' and 'opponent_' columns.
    """
    # Example: Team Defensive Line Height (1=Low block, 5=High line)
    # This data would ideally come from an external scout report or rolling metrics
    team_tactics = {
        'Manchester City': 5, 'Liverpool': 5, 'Arsenal': 4, 
        'Everton': 2, 'Burnley': 1
    }
    df['team_tactical_profile'] = df['team_'].map(team_tactics).fillna(3)
    df['opp_tactical_profile'] = df['opponent_'].map(team_tactics).fillna(3)
    
    # Interaction: How team style matches opponent
    df['tactical_clash'] = df['team_tactical_profile'] - df['opp_tactical_profile']
    return df

def add_referee_features(df):
    """Adds referee card/foul tendencies."""
    # This data needs to be joined with a referee_logs.csv
    # Placeholder: Assuming referee_id and referee_avg_cards exist
    if 'referee_avg_cards' not in df.columns:
        df['referee_avg_cards'] = 3.5 # Global average fallback
    return df

def enhance_features(df):
    df = add_tactical_features(df)
    df = add_referee_features(df)
    return df
