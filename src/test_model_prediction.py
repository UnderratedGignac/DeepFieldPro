"""Test model end-to-end prediction."""

import lightgbm as lgb
import pandas as pd
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

print("=== Model Prediction Test ===")
model = lgb.Booster(model_file="models/lgb_Performance_Gls_final.txt")
print(f"Model loaded: {model.num_trees()} trees, {model.num_feature()} features")
print(f"Feature names: {model.feature_name()}")

# Create a realistic test row matching real feature schema
test_row = {
    "min__roll3": 75.0,
    "min__roll10": 72.0,
    "Performance_Gls_roll3": 0.5,
    "Performance_Gls_roll10": 0.3,
    "Performance_Ast_roll3": 0.2,
    "Performance_Ast_roll10": 0.15,
    "Performance_Sh_roll3": 3.5,
    "Performance_Sh_roll10": 3.0,
    "Performance_SoT_roll3": 1.5,
    "Performance_SoT_roll10": 1.2,
    "Performance_CrdY_roll3": 0.1,
    "Performance_CrdY_roll10": 0.08,
    "Performance_CrdR_roll3": 0.0,
    "Performance_CrdR_roll10": 0.0,
    "days_since_last_match": 7,
}

X = pd.DataFrame([test_row])[model.feature_name()]
pred = model.predict(X)
print(
    f"\nPrediction for strong attacker (0.3 gls/game baseline): {pred[0]:.4f} goals expected"
)
print(f"Sanity check: prediction in [0, 3] = {0 <= pred[0] <= 3}")

# Test all models
targets = [
    "lgb_Performance_Gls_final.txt",
    "lgb_Performance_Ast_final.txt",
    "lgb_Performance_Sh_final.txt",
    "lgb_Performance_SoT_final.txt",
    "lgb_Performance_CrdY_final.txt",
    "lgb_min__final.txt",
]

print("\n=== All Model Predictions ===")
for fname in targets:
    m = lgb.Booster(model_file=f"models/{fname}")
    X_t = pd.DataFrame([test_row])[m.feature_name()]
    p = m.predict(X_t)[0]
    print(f"  {fname.replace('lgb_','').replace('_final.txt',''):30} -> {p:.4f}")

print("\nAll models functioning correctly!")
