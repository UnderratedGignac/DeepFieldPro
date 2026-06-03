# mypy: ignore-errors
import lightgbm as lgb
import pandas as pd
from sklearn.model_selection import TimeSeriesSplit
import os

df = pd.read_csv("C:/Users/Elie/DeepFieldPro/data/training_dataset.csv")

# Use Min% instead of Percentage of Minutes Played
# And rename if needed, but we can just use Min% directly
df["Percentage of Minutes Played"] = df["Min%"]

# FEATURE SET
MINUTES_FEATURES = [
    "Age",
    "Starts",
    "Percentage of Minutes Played",
    "Mn/Start",
    "Mn/MP",
    "PPM",
    "ppda",
    "opp_possession_allowed",
    "sample_weight",
]

# Target: did the player start and play 60+ minutes?
df["target_started"] = ((df["Starts"] > 0) & (df["Minutes Played"] >= 60)).astype(int)

# Also build quantile targets for p10/p50/p90 minutes
df["target_minutes"] = df["Minutes Played"]

df = df.dropna(subset=MINUTES_FEATURES + ["target_started", "target_minutes"])

X = df[MINUTES_FEATURES].apply(pd.to_numeric, errors="coerce")
y_class = df["target_started"]
y_minutes = df["target_minutes"]
weights = df["sample_weight"]

# TIME-SERIES CROSS-VALIDATION
tscv = TimeSeriesSplit(n_splits=5)

# --- Model 1A: Binary Classifier ---
params_classifier = {
    "objective": "binary",
    "metric": "binary_logloss",
    "num_leaves": 31,
    "learning_rate": 0.05,
    "n_estimators": 300,
    "min_child_samples": 20,
    "verbose": -1,
}

model_start = lgb.LGBMClassifier(**params_classifier)
model_start.fit(X, y_class, sample_weight=weights)

# --- Model 1B: Quantile Regressors ---
models_quantile = {}
for q in [0.10, 0.50, 0.90]:
    params_q = {
        "objective": "quantile",
        "alpha": q,
        "metric": "quantile",
        "num_leaves": 31,
        "learning_rate": 0.05,
        "n_estimators": 300,
        "verbose": -1,
    }
    m = lgb.LGBMRegressor(**params_q)
    m.fit(X, y_minutes, sample_weight=weights)
    models_quantile[f"p{int(q*100)}"] = m
    print(f"Quantile model q={q} trained.")

# Save all models
os.makedirs("C:/Users/Elie/DeepFieldPro/models", exist_ok=True)
model_start.booster_.save_model(
    "C:/Users/Elie/DeepFieldPro/models/minutes_start_classifier.txt"
)
for name, m in models_quantile.items():
    m.booster_.save_model(
        f"C:/Users/Elie/DeepFieldPro/models/minutes_{name}_regressor.txt"
    )

print("All minutes models saved.")

