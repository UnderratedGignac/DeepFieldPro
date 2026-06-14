"""
DeepFieldPro - World Cup Player Prop Model Training (v2)
- Uses pre-built wc_player_name_mapping.csv for fast O(1) player lookups
- Trains LightGBM for Goals, Shots, Assists, SoT, Yellow Cards, Minutes
"""

import pandas as pd
import numpy as np
import lightgbm as lgb
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import mean_squared_error
import pickle
import os
import warnings
import unicodedata
import re
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
warnings.filterwarnings("ignore")

DATA_PATH = os.path.join(os.path.dirname(__file__), "../data/model_ready_features.csv")
MODEL_DIR = os.path.join(os.path.dirname(__file__), "../models")
WC_NAMES_PATH = os.path.join(
    os.path.dirname(__file__), "../data/wc_player_name_mapping.csv"
)
WC_PLAYERS_PATH = os.path.join(
    os.path.dirname(__file__), "../data/worldcup_players.csv"
)

os.makedirs(MODEL_DIR, exist_ok=True)


def normalize_name(name):
    if not isinstance(name, str):
        return ""
    name = name.lower().strip()
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    name = re.sub(r"[^a-z\s]", "", name)
    return re.sub(r"\s+", " ", name).strip()


print("=" * 65)
print("DeepFieldPro WC Prop Model Training v2")
print("=" * 65)

# ── 1. BUILD FAST WC PLAYER LOOKUP ─────────────────────────────────────────
print("\n[1/6] Building WC player lookup from pre-computed name mapping...")

mapping = pd.read_csv(WC_NAMES_PATH)

# FBref names from mapping (already matched)
fbref_wc_names = set(mapping["fbref_name"].dropna().str.strip())

# Manual aliases for key stars with known name mismatches
MANUAL_ALIASES = {
    # Legal name (normalized) -> FBref name in dataset
    "carlos henrique casimiro": "Casemiro",
    "breel donald embolo": "Breel Embolo",
    "raphael dias belloli": "Raphael",  # Raphael (Brazil)
    "marcos aoas correa": "Marquinhos",
    "lucas tolentino coelho de lima": "Lucas",
    "rodrygo silva de goes": "Rodrygo",
    "vinicius jose paaixao de oliveira junior": "Vinicius Jr",
    "vinicius junior": "Vinicius Jr",
    "richarlison de andrade": "Richarlison",
    "kieffer roberto francisco moore": "Kieffer Moore",
    "aleksandar mitrovic": "Aleksandar Mitrovic",
}

# Build the complete set of FBref names to filter on
all_wc_fbref_names = fbref_wc_names.copy()
for alias_target in MANUAL_ALIASES.values():
    all_wc_fbref_names.add(alias_target)

# Normalized lookup set
all_wc_norm = set(normalize_name(n) for n in all_wc_fbref_names)
# Also add manual alias keys (normalized legal names) for direct matching
for legal, fbref in MANUAL_ALIASES.items():
    all_wc_norm.add(normalize_name(fbref))

print(f"  WC FBref names in lookup: {len(all_wc_fbref_names)}")

# ── 2. LOAD DATASET ────────────────────────────────────────────────────────
print("\n[2/6] Loading feature dataset...")
df = pd.read_csv(DATA_PATH, low_memory=False)
df["Date"] = pd.to_datetime(df["Date"])
df = df.sort_values("Date").reset_index(drop=True)
df = df[df["Min"] > 0].copy()
print(f"  Loaded: {len(df):,} rows × {df.shape[1]} columns")

# ── 3. FILTER TO WC PLAYERS ────────────────────────────────────────────────
print("\n[3/6] Filtering to World Cup players...")
df["player_norm"] = df["Player"].apply(normalize_name)

# Direct name match (O(1) using set lookup)
wc_mask = df["player_norm"].isin(all_wc_norm)
df_wc = df[wc_mask].copy()
print(f"  WC players in training set: {df_wc['Player'].nunique():,}")
print(f"  WC training rows: {len(df_wc):,}")

if len(df_wc) == 0:
    print("  WARNING: No WC players found — training on full dataset as fallback.")
    df_wc = df.copy()

# ── 4. BUILD FEATURES ──────────────────────────────────────────────────────
print("\n[4/6] Building feature matrix...")

# Encode position
if "Pos" in df_wc.columns:
    pos_map = {
        "GK": 0,
        "DF": 1,
        "CB": 1,
        "LB": 1,
        "RB": 1,
        "WB": 1,
        "DM": 2,
        "CM": 3,
        "AM": 4,
        "LM": 3,
        "RM": 3,
        "LW": 5,
        "RW": 5,
        "FW": 6,
        "CF": 6,
        "SS": 5,
        "MF": 3,
        "FW,MF": 5,
        "MF,FW": 5,
        "DF,MF": 2,
        "MF,DF": 2,
    }
    df_wc["pos_encoded"] = (
        df_wc["Pos"]
        .fillna("MF")
        .apply(lambda p: pos_map.get(str(p).strip().upper(), 3))
    )

if "age_" in df_wc.columns:
    df_wc["age_years"] = df_wc["age_"].apply(
        lambda x: int(str(x).split("-")[0]) if pd.notna(x) else 25
    )

CORE_FEATS = [
    c
    for c in [
        "Min",
        "Sh",
        "SoT",
        "xG",
        "Gls",
        "Ast",
        "CrdY",
        "CrdR",
        "PKatt",
        "pos_encoded",
        "age_years",
    ]
    if c in df_wc.columns
]
ROLLING_FEATS = [
    c
    for c in df_wc.columns
    if any(
        c.startswith(p)
        for p in [
            "sh_last_",
            "sot_last_",
            "gls_last_",
            "ast_last_",
            "xg_last_",
            "minutes_last_",
            "crdy_last_",
            "rolling_std_",
        ]
    )
]
OPP_FEATS = [c for c in df_wc.columns if c.startswith("opp_")]
TEAM_FEATS = [c for c in df_wc.columns if c.startswith("team_")]
AVAIL_FEATS = [
    c
    for c in [
        "is_starter",
        "started_last_match",
        "started_last_3",
        "days_since_last_match",
        "is_captain",
        "key_teammate_missing",
    ]
    if c in df_wc.columns
]

ALL_FEATURES = list(
    set(CORE_FEATS + ROLLING_FEATS + OPP_FEATS + TEAM_FEATS + AVAIL_FEATS)
)
df_wc[ALL_FEATURES] = df_wc[ALL_FEATURES].fillna(0)

print(f"  Total features: {len(ALL_FEATURES)}")
print(f"    Rolling:  {len(ROLLING_FEATS)}")
print(f"    Opponent: {len(OPP_FEATS)}")
print(f"    Team:     {len(TEAM_FEATS)}")
print(f"    Avail:    {len(AVAIL_FEATS)}")

# ── 5. TRAIN MODELS ────────────────────────────────────────────────────────
print("\n[5/6] Training LightGBM models...")

TARGETS = {
    "goals": {"col": "Gls", "objective": "poisson"},
    "shots": {"col": "Sh", "objective": "poisson"},
    "assists": {"col": "Ast", "objective": "poisson"},
    "shots_on_target": {"col": "SoT", "objective": "poisson"},
    "yellow_cards": {"col": "CrdY", "objective": "poisson"},
    "minutes": {"col": "Min", "objective": "regression"},
}

trained_models = {}
results_log = []
tscv = TimeSeriesSplit(n_splits=5)

LGBM_PARAMS = dict(
    n_estimators=500,
    learning_rate=0.02,
    max_depth=7,
    num_leaves=63,
    colsample_bytree=0.7,
    subsample=0.8,
    min_child_samples=20,
    reg_alpha=0.1,
    reg_lambda=0.1,
    random_state=42,
    verbose=-1,
    n_jobs=-1,
)

for target_name, config in TARGETS.items():
    col = config["col"]
    if col not in df_wc.columns:
        print(f"  [SKIP] {target_name}: missing column '{col}'")
        continue

    feats = [f for f in ALL_FEATURES if f != col]
    X = df_wc[feats]
    y = df_wc[col].clip(lower=0)

    model = lgb.LGBMRegressor(objective=config["objective"], **LGBM_PARAMS)

    cv_rmses = []
    for train_idx, test_idx in tscv.split(X):
        model.fit(
            X.iloc[train_idx],
            y.iloc[train_idx],
            eval_set=[(X.iloc[test_idx], y.iloc[test_idx])],
            callbacks=[
                lgb.early_stopping(30, verbose=False),
                lgb.log_evaluation(False),
            ],
        )
        preds = np.clip(model.predict(X.iloc[test_idx]), 0, None)
        cv_rmses.append(np.sqrt(mean_squared_error(y.iloc[test_idx], preds)))

    avg_rmse = np.mean(cv_rmses)
    model.fit(X, y)  # Final fit on all data

    feat_imp = pd.Series(model.feature_importances_, index=feats).nlargest(3)
    model_path = os.path.join(MODEL_DIR, f"lgbm_{target_name}.pkl")
    with open(model_path, "wb") as f:
        pickle.dump({"model": model, "features": feats, "target": col}, f)

    print(f"  ✓ {target_name:20s} | RMSE={avg_rmse:.4f} | Top: {feat_imp.index[0]}")
    results_log.append(
        {
            "target": target_name,
            "cv_rmse": round(avg_rmse, 4),
            "n_features": len(feats),
            "model_path": model_path,
        }
    )
    trained_models[target_name] = model

# Save metadata
meta = {
    "features": feats,
    "targets": list(TARGETS.keys()),
    "wc_players_in_training": int(df_wc["Player"].nunique()),
    "training_rows": int(len(df_wc)),
    "date_range": f"{df_wc['Date'].min().date()} to {df_wc['Date'].max().date()}",
}
with open(os.path.join(MODEL_DIR, "training_meta.pkl"), "wb") as f:
    pickle.dump(meta, f)

# ── 6. SUMMARY ─────────────────────────────────────────────────────────────
print("\n[6/6] Training Complete!")
print("=" * 65)
print(
    pd.DataFrame(results_log)[["target", "cv_rmse", "n_features"]].to_string(
        index=False
    )
)
print()
print(f"  WC Players trained on: {df_wc['Player'].nunique():,}")
print(f"  Training rows:         {len(df_wc):,}")
print(
    f"  Date coverage:         {df_wc['Date'].min().date()} → {df_wc['Date'].max().date()}"
)
print(f"  Models saved to:       {MODEL_DIR}")
print("=" * 65)
