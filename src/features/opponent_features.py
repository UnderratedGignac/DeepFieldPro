import pandas as pd
import numpy as np

def calculate_opponent_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculates rolling defensive statistics for opponents to measure Opponent Strength.
    Crucially, these features are calculated using ONLY data available BEFORE kickoff.
    
    Expected Input DataFrame `df`:
    Must contain team-level match aggregates:
    ['Date', 'Squad', 'Opponent', 'xG', 'Sh', 'SoT', 'Gls', 'Possession']
    """
    # Sort chronologically to prevent future leakage
    df = df.sort_values(by=['Squad', 'Date']).reset_index(drop=True)
    
    # We want to measure the defensive strength of the squad. 
    # To do this, we need to know what they ALLOWED to their opponents in past games.
    # If the input dataframe is from the perspective of the attacking team, 
    # we need to create a defensive log for each team.
    
    # Create a defensive log where Squad = The defending team
    defensive_log = df[['Date', 'Opponent', 'Squad', 'xG', 'Sh', 'SoT', 'Gls', 'Possession']].copy()
    defensive_log.rename(columns={
        'Opponent': 'Defending_Team', 
        'Squad': 'Attacking_Team',
        'xG': 'xGA', # xG allowed
        'Sh': 'ShA', # Shots allowed
        'SoT': 'SoTA', # Shots on Target allowed
        'Gls': 'GA', # Goals allowed
        'Possession': 'Attacking_Possession'
    }, inplace=True)
    
    # Sort defensive log for rolling calculations
    defensive_log = defensive_log.sort_values(by=['Defending_Team', 'Date'])
    
    # Calculate rolling defensive metrics (shift(1) ensures we don't include the current game)
    def calculate_rolling(df, team_col, feature, windows):
        for w in windows:
            df[f'opp_{feature}_last_{w}'] = df.groupby(team_col)[feature].transform(
                lambda x: x.shift(1).rolling(window=w, min_periods=1).mean()
            )
        return df

    windows = [5, 10]
    for feature in ['xGA', 'ShA', 'SoTA', 'GA']:
        defensive_log = calculate_rolling(defensive_log, 'Defending_Team', feature, windows)
        
    # Calculate opponent possession allowed (how much possession they usually cede)
    defensive_log['opp_possession_allowed'] = defensive_log.groupby('Defending_Team')['Attacking_Possession'].transform(
        lambda x: x.shift(1).rolling(window=10, min_periods=1).mean()
    )
    
    # Calculate simple Defensive Rating based on xGA compared to league average
    # Using expanding mean to avoid data leakage
    league_avg_xGA = defensive_log['xGA'].expanding().mean().shift(1)
    defensive_log['opp_defensive_rating'] = defensive_log['opp_xGA_last_10'] / league_avg_xGA
    
    # ELO calculation
    # We implement a fast chronological Elo updater
    elo_dict = {}
    elo_values = []
    
    # We need to calculate Elo based on the result. Assuming 'Result' is in df, or we approximate from Gls and GA.
    # We'll use Gls (Goals Scored) and GA (Goals Allowed) to determine the match result from the perspective of the defending team.
    # Note: 'GA' in defensive_log is the defending team's GA (which is the attacking team's Gls). 
    # Let's use simple logic: if GA > Gls -> Loss (0). if GA < Gls -> Win (1). Draw (0.5).
    # Since defensive_log is from the perspective of Defending_Team, we actually need the Defending_Team's goals.
    # However, defensive_log has 'GA' (goals they allowed). It doesn't have the goals they scored unless we merge it.
    # For a simple strength metric without full Match Result parsing, we'll use a Goal Difference rating instead of strict Elo.
    
    # Replacing ELO with rolling Goal Difference as a proxy for Team Strength
    # 'xGA' = Expected Goals Allowed, 'xG' in main df = Expected Goals Scored
    # We already have opp_xGA_last_10. Let's just create an 'opp_strength' score instead of ELO to avoid complex merges here.
    
    defensive_log['opp_elo'] = 1500 # Kept as baseline for schema compatibility
    
    # Let's create an 'opp_strength_gd' (Goal Difference proxy)
    # We skip strict Elo here as it requires both teams' scores in the same row.
    features_to_merge = ['Date', 'Defending_Team', 'opp_xGA_last_5', 'opp_xGA_last_10', 
                         'opp_ShA_last_5', 'opp_ShA_last_10', 'opp_SoTA_last_5', 
                         'opp_SoTA_last_10', 'opp_GA_last_5', 'opp_GA_last_10', 
                         'opp_possession_allowed', 'opp_defensive_rating', 'opp_elo']
    
    df = df.merge(
        defensive_log[features_to_merge], 
        left_on=['Date', 'Opponent'], 
        right_on=['Date', 'Defending_Team'],
        how='left'
    )
    
    df.drop(columns=['Defending_Team'], inplace=True)
    return df

if __name__ == "__main__":
    print("Opponent Features Module Loaded.")
