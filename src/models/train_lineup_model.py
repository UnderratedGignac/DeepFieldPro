import pandas as pd
import lightgbm as lgb
import os
import re

DATA_PATH = "data/lineup_training_data.csv"
MODEL_PATH = "models/lineup_model.txt"


def train_lineup_model():
    df = pd.read_csv(DATA_PATH)

    # Clean feature names (remove special chars)
    df.columns = [re.sub(r"[^a-zA-Z0-9_]", "", c) for c in df.columns]

    target = "is_starter"
    features = [c for c in df.columns if c not in ["player_", "team_", target]]

    X = df[features]
    y = df[target]

    print(f"Training on {len(df)} samples with features: {features}...")

    model = lgb.LGBMClassifier(n_estimators=100, learning_rate=0.1)
    model.fit(X, y)

    os.makedirs("models", exist_ok=True)
    model.booster_.save_model(MODEL_PATH)
    print(f"Lineup model saved to {MODEL_PATH}")


if __name__ == "__main__":
    train_lineup_model()
