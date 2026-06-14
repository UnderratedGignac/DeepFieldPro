import pandas as pd
import lightgbm as lgb
import os
import joblib

DATA_DIR = 'data'
MODEL_DIR = 'models'
GLOBAL_CSV = os.path.join(DATA_DIR, 'world_cup_players_match_logs_global.csv')
MODEL_PATH = os.path.join(MODEL_DIR, 'expected_minutes_model.txt')

def train_expected_minutes_model():
    print("Loading data for Expected Minutes model...")
    df = pd.read_csv(GLOBAL_CSV)
    
    # Feature engineering for minutes prediction
    # 1. Rolling average of last 5 matches
    df = df.sort_values(['player_', 'game_'])
    df['min_roll5'] = df.groupby('player_')['min_'].transform(lambda x: x.shift(1).rolling(5, min_periods=1).mean())
    
    # 2. Positional base
    df = pd.get_dummies(df, columns=['pos_'], prefix='pos')
    
    # Target and features
    target = 'min_'
    # Clean feature names (remove special chars)
    df.columns = [re.sub(r'[^a-zA-Z0-9_]', '', c) for c in df.columns]
    
    features = ['min_roll5'] + [c for c in df.columns if c.startswith('pos')]
    
    # Train/Val split
    train = df.dropna(subset=[target] + features)
    X = train[features]
    y = train[target]
    
    print(f"Training on {len(X)} samples with features: {features}...")
    model = lgb.LGBMRegressor(n_estimators=100, learning_rate=0.1)
    model.fit(X, y)
    
    # Save model
    os.makedirs(MODEL_DIR, exist_ok=True)
    model.booster_.save_model(MODEL_PATH)
    print(f"Expected Minutes model saved to {MODEL_PATH}")

if __name__ == "__main__":
    import re
    train_expected_minutes_model()
