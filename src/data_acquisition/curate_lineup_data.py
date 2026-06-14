import pandas as pd
import numpy as np

def curate_lineup_data():
    df = pd.read_csv('data/world_cup_players_match_logs_global.csv')
    
    # Define starter: min_ > 0 is a simplification for "started or played".
    # We need a better heuristic, perhaps min_ > 45.
    df['is_starter'] = (df['min_'] > 45).astype(int)
    
    # Sort for rolling features
    df = df.sort_values(['player_', 'game_'])
    
    # Engineering features:
    # 1. Last 5 starts rate
    df['starts_roll5'] = df.groupby('player_')['is_starter'].transform(lambda x: x.shift(1).rolling(5, min_periods=1).mean())
    
    # 2. Positional features (dummy)
    df = pd.get_dummies(df, columns=['pos_'], prefix='pos')
    
    # Save training dataset
    cols_to_keep = ['player_', 'team_', 'starts_roll5', 'is_starter'] + [c for c in df.columns if c.startswith('pos_')]
    training_df = df[cols_to_keep].dropna()
    
    training_df.to_csv('data/lineup_training_data.csv', index=False)
    print(f"Curated lineup data saved: {len(training_df)} samples.")

if __name__ == "__main__":
    curate_lineup_data()
