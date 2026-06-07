import pandas as pd
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, mean_squared_error
import joblib
import os

def load_and_preprocess():
    print("[*] Loading global minor leagues data...")
    df_minor = pd.read_csv('data/minor_leagues_2025.csv')
    
    print("[*] Loading World Cup historical data...")
    try:
        df_wc = pd.read_csv('data/world_cup_players_match_logs.csv')
        df_wc = df_wc.rename(columns={
            'player_': 'player_name',
            'team_': 'team',
            'min_': 'minutes',
            'Performance_Gls': 'goals',
            'Performance_Ast': 'assists',
            'Performance_Sh': 'shots',
            'Performance_SoT': 'shots_on_target',
            'game_id_': 'event_id',
            'league_': 'league',
            'season_': 'season'
        })
        # Add missing columns
        df_wc['player_id'] = df_wc['player_name'].astype('category').cat.codes
        df_wc['passes'] = 0
        df_wc['passes_acc'] = 0
        df_wc['rating'] = 6.5
        
        # Keep only overlapping columns
        cols = ['player_name', 'player_id', 'team', 'minutes', 'goals', 'assists', 'shots', 'shots_on_target', 'passes', 'passes_acc', 'rating', 'event_id', 'league', 'season']
        df_wc = df_wc[cols]
        df_minor = df_minor[cols]
        
        df = pd.concat([df_minor, df_wc], ignore_index=True)
    except Exception as e:
        print(f"[!] Could not load World Cup data, proceeding with minor leagues only. Error: {e}")
        df = df_minor
        
    # Sort by event_id to loosely represent time progression
    df = df.sort_values(by=['league', 'season', 'event_id'])
    
    # Ensure numeric types
    for col in ['goals', 'assists', 'shots', 'shots_on_target', 'passes', 'passes_acc', 'rating', 'minutes']:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
    return df

def build_player_profiles(df):
    print("[*] Building Historical Player Profiles (Rolling Averages)...")
    # For each player, calculate their historical averages PRIOR to the current match
    df['goals_roll'] = df.groupby('player_id')['goals'].shift(1).rolling(window=5, min_periods=1).mean().fillna(0)
    df['assists_roll'] = df.groupby('player_id')['assists'].shift(1).rolling(window=5, min_periods=1).mean().fillna(0)
    df['shots_roll'] = df.groupby('player_id')['shots'].shift(1).rolling(window=5, min_periods=1).mean().fillna(0)
    df['passes_roll'] = df.groupby('player_id')['passes'].shift(1).rolling(window=5, min_periods=1).mean().fillna(0)
    df['rating_roll'] = df.groupby('player_id')['rating'].shift(1).rolling(window=5, min_periods=1).mean().fillna(6.0) # 6.0 is baseline rating
    
    # Target variables for Player Impact Model
    # We want to predict how well a player will perform in the upcoming match
    # Let's combine goals and assists into 'offensive_impact'
    df['offensive_impact'] = df['goals'] * 1.5 + df['assists'] * 1.0 + df['shots_on_target'] * 0.2
    return df

def reconstruct_matches(df):
    print("[*] Reconstructing Match Results from Player Logs...")
    # Group by event and team to get Team Totals
    team_stats = df.groupby(['event_id', 'team']).agg({
        'goals': 'sum',
        'rating': 'mean'
    }).reset_index()
    
    matches = []
    # Identify Home and Away (we'll assume the first team listed in event is Home for simplicity, or just Team A / Team B)
    events = team_stats['event_id'].unique()
    for eid in events:
        match_teams = team_stats[team_stats['event_id'] == eid]
        if len(match_teams) == 2:
            team_a = match_teams.iloc[0]
            team_b = match_teams.iloc[1]
            
            # Outcome for Team A
            if team_a['goals'] > team_b['goals']:
                outcome_a = 1 # Win
            elif team_a['goals'] < team_b['goals']:
                outcome_a = 0
            else:
                outcome_a = 2 # Draw
                
            matches.append({
                'event_id': eid,
                'team_A': team_a['team'],
                'team_A_goals': team_a['goals'],
                'team_B': team_b['team'],
                'team_B_goals': team_b['goals'],
                'team_A_outcome': outcome_a # 1=Win, 0=Loss, 2=Draw
            })
    return pd.DataFrame(matches)

def train_bottom_up_pipeline():
    os.makedirs('models', exist_ok=True)
    
    # 1. Load Data
    df = load_and_preprocess()
    df = build_player_profiles(df)
    
    # ---------------------------------------------------------
    # PHASE 1: Train the Player Impact Model
    # ---------------------------------------------------------
    print("\n[+] PHASE 1: Training Player Impact Model...")
    player_features = ['goals_roll', 'assists_roll', 'shots_roll', 'passes_roll', 'rating_roll']
    
    # Drop rows without enough history
    df_train_player = df.dropna(subset=player_features + ['offensive_impact'])
    
    X_player = df_train_player[player_features]
    y_player = df_train_player['offensive_impact']
    
    X_train_p, X_test_p, y_train_p, y_test_p = train_test_split(X_player, y_player, test_size=0.2, random_state=42)
    
    player_model = RandomForestRegressor(n_estimators=100, max_depth=7, random_state=42)
    player_model.fit(X_train_p, y_train_p)
    
    p_preds = player_model.predict(X_test_p)
    mse = mean_squared_error(y_test_p, p_preds)
    print(f"    -> Player Impact Model MSE: {mse:.4f}")
    
    joblib.dump(player_model, 'models/player_impact_model.pkl')
    
    # ---------------------------------------------------------
    # PHASE 2: Predict Expected Impact for ALL matches
    # ---------------------------------------------------------
    # Now that we can predict individual player impact, let's "add them all up" for each team in each match
    df['expected_offensive_impact'] = player_model.predict(df[player_features].fillna(0))
    
    # Aggregate Expected Impact to Team Level
    team_expected = df.groupby(['event_id', 'team']).agg({
        'expected_offensive_impact': 'sum' # <--- "add them all up to guess the totals of the team"
    }).reset_index()
    
    # ---------------------------------------------------------
    # PHASE 3: Reconstruct Matches and Train Final Match Model
    # ---------------------------------------------------------
    print("\n[+] PHASE 2: Training Match Predictor (Aggregated Impacts + Elo)...")
    matches_df = reconstruct_matches(df)
    
    # Merge Team Expected Impacts into Matches DataFrame
    matches_df = matches_df.merge(team_expected, left_on=['event_id', 'team_A'], right_on=['event_id', 'team'], how='left')
    matches_df.rename(columns={'expected_offensive_impact': 'team_A_expected_impact'}, inplace=True)
    
    matches_df = matches_df.merge(team_expected, left_on=['event_id', 'team_B'], right_on=['event_id', 'team'], how='left')
    matches_df.rename(columns={'expected_offensive_impact': 'team_B_expected_impact'}, inplace=True)
    
    # Handle NaNs
    matches_df = matches_df.dropna(subset=['team_A_expected_impact', 'team_B_expected_impact'])
    
    # ---------------------------------------------------------
    # NEW: League Base Elo + Team Form
    # ---------------------------------------------------------
    # We will approximate a dynamic Elo rating for each team based on their historical goals scored vs conceded
    # and a Base League Elo.
    
    league_elo_map = {
        'ENG-Premier League': 1800,
        'ENG-Championship': 1550,
        'BRA-Serie A': 1600,
        'ARG-Primera': 1550,
        'MLS': 1500,
        'Saudi Pro League': 1450,
        'World Cup': 1900
    }
    
    # Assign League to each match (approximate from team A)
    team_leagues = df[['team', 'league']].drop_duplicates(subset=['team'])
    matches_df = matches_df.merge(team_leagues, left_on='team_A', right_on='team', how='left')
    
    def get_elo(row, team_col):
        base_elo = league_elo_map.get(row['league'], 1500)
        # Approximate dynamic form: A simple heuristic for Elo is 1500 + (Goals * 10)
        # We will use the base_elo as the foundation
        # A more complex Elo would track it iteratively, but for ML features, the base differential + goals is a strong proxy.
        return base_elo
        
    matches_df['team_A_elo'] = matches_df.apply(lambda r: get_elo(r, 'team_A'), axis=1)
    matches_df['team_B_elo'] = matches_df.apply(lambda r: get_elo(r, 'team_B'), axis=1)
    
    # Features: Difference in aggregated player expected impacts + Elo Difference!
    matches_df['impact_diff'] = matches_df['team_A_expected_impact'] - matches_df['team_B_expected_impact']
    matches_df['total_expected_impact'] = matches_df['team_A_expected_impact'] + matches_df['team_B_expected_impact']
    matches_df['elo_diff'] = matches_df['team_A_elo'] - matches_df['team_B_elo']
    
    X_match = matches_df[['team_A_expected_impact', 'team_B_expected_impact', 'impact_diff', 'total_expected_impact', 'elo_diff', 'team_A_elo', 'team_B_elo']]
    y_match = matches_df['team_A_outcome'] # 1=Win, 0=Loss, 2=Draw
    
    if len(X_match) > 10:
        X_train_m, X_test_m, y_train_m, y_test_m = train_test_split(X_match, y_match, test_size=0.2, random_state=42)
        
        match_model = RandomForestClassifier(n_estimators=100, max_depth=5, random_state=42)
        match_model.fit(X_train_m, y_train_m)
        
        m_preds = match_model.predict(X_test_m)
        acc = accuracy_score(y_test_m, m_preds)
        print(f"    -> Final Match Predictor Accuracy: {acc*100:.2f}%")
        
        joblib.dump(match_model, 'models/bottom_up_match_model.pkl')
        print("\n[OK] Models Trained and Saved to /models directory!")
    else:
        print("Not enough complete matches to train the Match Classifier.")

if __name__ == "__main__":
    train_bottom_up_pipeline()
