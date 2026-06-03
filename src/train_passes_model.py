# mypy: ignore-errors
import lightgbm as lgb
import pandas as pd
import os
from src.app_config import config

df = pd.read_csv(os.path.join(config.DATA_DIR, "training_dataset.csv"))
df["Percentage of Minutes Played"] = pd.to_numeric(df["Min%"], errors="coerce").fillna(
    0.8
)
gls_col = "Gls" if "Gls" in df.columns else ("onG" if "onG" in df.columns else None)
df["Goals Scored While on Pitch"] = (
    pd.to_numeric(df[gls_col], errors="coerce").fillna(0) if gls_col else 0.0
)

# FEATURE SET
PASSES_FEATURES = [
    "Age",
    "Position",
    "Minutes Played",
    "Mn/Start",
    "Percentage of Minutes Played",
    "Crs",
    "Interceptions",
    "Tackles Won",
    "ppda",
    "opp_possession_allowed",
    "sample_weight",
]

# Encode Position — supports both FBref short codes and StatsBomb full names
position_map = {
    # FBref short
    "MF": 3,
    "DF": 2,
    "FW": 1,
    "GK": 0,
    "MF,FW": 2,
    "DF,MF": 2,
    # StatsBomb full names
    "Center Midfield": 3,
    "Defensive Midfield": 3,
    "Attacking Midfield": 3,
    "Left Midfield": 3,
    "Right Midfield": 3,
    "Center Defensive Midfield": 3,
    "Left Center Midfield": 3,
    "Right Center Midfield": 3,
    "Left Defensive Midfield": 3,
    "Right Defensive Midfield": 3,
    "Center Back": 2,
    "Left Back": 2,
    "Right Back": 2,
    "Left Center Back": 2,
    "Right Center Back": 2,
    "Left Wing Back": 2,
    "Right Wing Back": 2,
    "Left Wing": 1,
    "Right Wing": 1,
    "Center Forward": 1,
    "Left Center Forward": 1,
    "Right Center Forward": 1,
    "Secondary Striker": 1,
    "Goalkeeper": 0,
}
df["Position_encoded"] = df["Position"].map(position_map).fillna(2)
PASSES_FEATURES[1] = "Position_encoded"

df = df.dropna(subset=PASSES_FEATURES + ["passes_per_90"])

X = df[PASSES_FEATURES].apply(pd.to_numeric, errors="coerce")
y = df["passes_per_90"]
weights = df["sample_weight"]

# --- Quantile Regressors ---
passes_models = {}
for q in [0.10, 0.50, 0.90]:
    params = {
        "objective": "quantile",
        "alpha": q,
        "metric": "quantile",
        "num_leaves": 63,
        "learning_rate": 0.03,
        "n_estimators": 500,
        "min_child_samples": 15,
        "verbose": -1,
    }
    m = lgb.LGBMRegressor(**params)
    m.fit(X, y, sample_weight=weights)
    passes_models[f"p{int(q*100)}"] = m
    print(
        f"Passes quantile model q={q} trained. Sample prediction: {m.predict(X.head(1))[0]:.1f} passes/90"
    )

os.makedirs(config.MODEL_DIR, exist_ok=True)
for name, m in passes_models.items():
    m.booster_.save_model(os.path.join(config.MODEL_DIR, f"passes_{name}.txt"))

print("All passes models saved.")
