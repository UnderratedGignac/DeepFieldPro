import pandas as pd
import numpy as np
import lightgbm as lgb
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import mean_absolute_error


def prepare_minutes_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Engineers the specific features required to predict Expected Minutes.
    Requires 'Min', 'Start', 'Pos', 'Comp' from base dataframe.
    """
    df = df.sort_values(by=["Player", "Date"]).reset_index(drop=True)

    # Target Variable
    df["target_minutes"] = df["Min"]

    # 1. Start History
    # 'Start' usually comes as Y/N or 1/0. Ensure binary.
    df["is_starter"] = df["Start"].apply(
        lambda x: 1 if str(x).upper() in ["Y", "1", "YES", "TRUE"] else 0
    )

    df["started_last_match"] = df.groupby("Player")["is_starter"].shift(1).fillna(0)
    df["started_last_3"] = (
        df.groupby("Player")["is_starter"]
        .transform(lambda x: x.shift(1).rolling(3, min_periods=1).sum())
        .fillna(0)
    )

    # 2. Minutes History
    df["minutes_last_5"] = (
        df.groupby("Player")["Min"]
        .transform(lambda x: x.shift(1).rolling(5, min_periods=1).mean())
        .fillna(0)
    )

    # 3. Categorical Encodings
    df["Pos"] = df["Pos"].astype("category")
    df["Comp"] = df["Comp"].astype("category")

    # 4. Rest/Fatigue (Placeholder for Phase 9)
    # Assume 'days_rest' is provided or calculate roughly via Date diff
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"])
        df["days_rest"] = df.groupby("Player")["Date"].diff().dt.days.shift(1).fillna(7)
        # Cap at 14 days to prevent outliers for summer breaks
        df["days_rest"] = df["days_rest"].clip(upper=14)
    else:
        df["days_rest"] = 7

    # Drop rows without targets (e.g. future matches we want to predict)
    # For training we keep them, for inference we use this same pipeline.

    return df


def train_expected_minutes_model(df: pd.DataFrame):
    """
    Trains a LightGBM regressor to predict how many minutes a player will play.
    """
    df = prepare_minutes_features(df)

    # Filter out NaNs in target for training
    train_df = df.dropna(subset=["target_minutes"]).copy()

    features = [
        "started_last_match",
        "started_last_3",
        "minutes_last_5",
        "Pos",
        "Comp",
        "days_rest",
    ]

    X = train_df[features]
    y = train_df["target_minutes"]

    # TimeSeriesSplit prevents future leakage during cross-validation
    tscv = TimeSeriesSplit(n_splits=3)
    cv_scores = []

    model = lgb.LGBMRegressor(
        objective="regression",
        n_estimators=100,
        learning_rate=0.05,
        max_depth=5,
        random_state=42,
        verbose=-1,
    )

    print("Validating Expected Minutes Model...")
    for train_index, test_index in tscv.split(X):
        X_train, X_test = X.iloc[train_index], X.iloc[test_index]
        y_train, y_test = y.iloc[train_index], y.iloc[test_index]

        model.fit(X_train, y_train, categorical_feature=["Pos", "Comp"])
        preds = model.predict(X_test)

        # Ensure predictions are physically possible
        preds = np.clip(preds, 0, 100)
        mae = mean_absolute_error(y_test, preds)
        cv_scores.append(mae)

    print(f"Validation MAE: {np.mean(cv_scores):.2f} minutes")

    # Train final model on all data
    model.fit(X, y, categorical_feature=["Pos", "Comp"])

    return model, features


def predict_expected_minutes(model, features, inference_df: pd.DataFrame):
    """
    Applies the trained model to generate expected minutes.
    Returns dictionary with p10, p50, p90 percentiles for each player.
    """
    X_inf = inference_df[features]
    preds = model.predict(X_inf)
    
    # Calculate uncertainty spread using quantile regression forests approach
    # We simulate variance based on historical residuals
    base_preds = np.clip(preds, 0, 100)
    
    # Estimate uncertainty based on player consistency (placeholder)
    # In production, this would come from quantile models
    uncertainty = np.where(
        inference_df.get("minutes_last_5", 0) > 60,
        10,  # Consistent players have lower uncertainty
        20   # Inconsistent players have higher uncertainty
    )
    
    results = {}
    for idx, row in inference_df.iterrows():
        player_key = row.get("player_name", f"player_{idx}")
        base = base_preds[idx]
        unc = uncertainty[idx] if isinstance(uncertainty, np.ndarray) else uncertainty
        
        results[player_key] = {
            "p10": max(0, base - 1.28 * unc),
            "p50": base,
            "p90": min(100, base + 1.28 * unc)
        }
    
    return results


def get_xmin_for_player(model, features, player_data: dict) -> dict:
    """
    Get Expected Minutes for a single player with P10/P50/P90 outputs.
    
    Input: Player historical usage, days of rest, manager substitution history
    Output: {"p10": 45, "p50": 78, "p90": 95}
    """
    df = pd.DataFrame([player_data])
    df = prepare_minutes_features(df)
    
    X_inf = df[features]
    pred = model.predict(X_inf)[0]
    base = np.clip(pred, 0, 100)
    
    # Calculate uncertainty based on data quality
    minutes_history = player_data.get("minutes_last_5", 45)
    if minutes_history > 60:
        unc = 10
    elif minutes_history > 30:
        unc = 15
    else:
        unc = 25
    
    return {
        "p10": int(max(0, base - 1.28 * unc)),
        "p50": int(base),
        "p90": int(min(100, base + 1.28 * unc))
    }


if __name__ == "__main__":
    print("Expected Minutes Model Module Loaded.")
