# -*- coding: utf-8 -*-
"""
train_models.py — DeepFieldPro Model Training Pipeline
======================================================
Trains all 4 LightGBM models with competition_type feature and international normalization.

NAMING CONVENTIONS:
- Parameters: ProperCase suffix _P  (e.g. CompType_P)
- Variables:  ProperCase suffix _V  (e.g. BrierScore_V)
- SQL table/column names: lowercase
- SQL keywords: UPPERCASE
- Comments: single line, human-readable, max 1 line
"""

import os
import pickle
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
import lightgbm as lgb
import statsmodels.api as sm
from statsmodels.discrete.discrete_model import NegativeBinomial
import optuna
from sklearn.metrics import mean_absolute_error
from sklearn.feature_selection import SequentialFeatureSelector

def prune_features(model, X, y):
    """Prune features using Sequential Feature Selection."""
    sfs = SequentialFeatureSelector(model, n_features_to_select=5, direction='backward')
    sfs.fit(X, y)
    selected_features = X.columns[sfs.get_support()].tolist()
    print(f"Selected {len(selected_features)} features: {selected_features}")
    return selected_features

def objective(trial, X, y):
    """Optuna objective function for LightGBM."""
    param = {
        'n_estimators': trial.suggest_int('n_estimators', 100, 500),
        'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.1),
        'max_depth': trial.suggest_int('max_depth', 3, 10),
        'subsample': trial.suggest_float('subsample', 0.5, 1.0),
        'colsample_bytree': trial.suggest_float('colsample_bytree', 0.5, 1.0),
        'verbose': -1
    }
    
    X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.2, random_state=42)
    model = lgb.LGBMRegressor(**param)
    model.fit(X_train, y_train)
    
    preds = model.predict(X_val)
    return mean_absolute_error(y_val, preds)

def tune_lgbm(X, y):
    """Run Optuna study."""
    study = optuna.create_study(direction='minimize')
    study.optimize(lambda trial: objective(trial, X, y), n_trials=20)
    return study.best_params

def train_nb_model(X, y):
    """Train a Negative Binomial model."""
    # Add constant for intercept
    X_V = sm.add_constant(X)
    # Using 'add' parameterization for overdispersion
    model = NegativeBinomial(y, X_V).fit(disp='add', cov_type='HC0', maxiter=100)
    return model

BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
MODEL_DIR = os.path.join(BASE_DIR, "models")
DATA_DIR = os.path.join(BASE_DIR, "data")
WORLD_CUP_CSV = os.path.join(DATA_DIR, "world_cup_players_match_logs.csv")
CLUB_CSV = os.path.join(DATA_DIR, "club_match_logs.csv")

LgbmParams_V = {
    "n_estimators": 300,
    "learning_rate": 0.05,
    "max_depth": 5,
    "min_child_samples": 10,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "random_state": 42,
    "class_weight": "balanced",
}


def load_and_prepare_data():
    """Load and prepare training data with competition_type tagging."""
    print("=" * 60)
    print("STEP 1: Loading and preparing training data")
    print("=" * 60)

    if not os.path.exists(WORLD_CUP_CSV):
        raise FileNotFoundError(f"World Cup CSV not found: {WORLD_CUP_CSV}")

    RawDf_V = pd.read_csv(WORLD_CUP_CSV)
    print(f"Loaded World Cup data: {len(RawDf_V)} rows")

    RawDf_V["competition_type"] = 1

    if os.path.exists(CLUB_CSV):
        ClubDf_V = pd.read_csv(CLUB_CSV)
        ClubDf_V["competition_type"] = 0
        print(f"Loaded club data: {len(ClubDf_V)} rows")
        CombinedDf_V = pd.concat([RawDf_V, ClubDf_V], ignore_index=True)
    else:
        print("Club dataset not found. Creating synthetic club data...")
        ClubDf_V = RawDf_V.copy()
        ClubDf_V["competition_type"] = 0

        shot_cols = [col for col in ClubDf_V.columns if "Sh" in col or "SoT" in col]
        for col in shot_cols:
            if col in ClubDf_V.columns:
                ClubDf_V[col] = ClubDf_V[col].fillna(0) * 1.8

        print(f"Created synthetic club data: {len(ClubDf_V)} rows")
        CombinedDf_V = pd.concat([RawDf_V, ClubDf_V], ignore_index=True)

    print(f"\nTotal combined dataset: {len(CombinedDf_V)} rows")
    print(
        f"International samples: {len(CombinedDf_V[CombinedDf_V['competition_type'] == 1])}"
    )
    print(f"Club samples: {len(CombinedDf_V[CombinedDf_V['competition_type'] == 0])}")

    return CombinedDf_V


def clean_features(Df_P):
    """Convert all columns to float for LightGBM. Handle special formats."""
    Df_V = Df_P.copy()
    for col in Df_V.columns:
        if col == "age_":
            # age_ is stored as '25-108' (years-days) — take integer part before dash
            Df_V[col] = Df_V[col].astype(str).str.split("-").str[0]
            Df_V[col] = pd.to_numeric(Df_V[col], errors="coerce").fillna(25.0)
        elif col == "pos_encoded":
            Df_V[col] = pd.to_numeric(Df_V[col], errors="coerce").fillna(2.0)
        elif Df_V[col].dtype == "object":
            Df_V[col] = pd.to_numeric(Df_V[col], errors="coerce").fillna(0.0)
        else:
            Df_V[col] = Df_V[col].fillna(0.0)
    return Df_V


def encode_position(PosStr_P) -> int:
    """Encode position string to integer."""
    PosUpper_V = str(PosStr_P).upper()
    if "GK" in PosUpper_V:
        return 0
    elif "FW" in PosUpper_V:
        return 1
    elif "DF" in PosUpper_V:
        return 2
    else:  # MF default
        return 3


def train_sot_club_model(df):
    """Train ensemble (LGBM + NB) for SoT model for club competitions."""
    print("\n" + "=" * 60)
    print("MODEL 1: Training ensemble (lgbm_sot_club_v2.pkl)")
    print("=" * 60)

    ClubDf_V = df[df["competition_type"] == 0].copy()
    print(f"Club samples: {len(ClubDf_V)}")

    if len(ClubDf_V) < 100:
        print("ERROR: Not enough club samples. Skipping.")
        return None

    # Encode position — pos_ is a string like 'FW', 'MF,FW'
    ClubDf_V["pos_encoded"] = ClubDf_V["pos_"].apply(encode_position)

    # Feature set — only numeric columns confirmed in CSV
    FeatureCols_V = [
        "age_",
        "competition_type",
        "min_",
        "pos_encoded",
        "Performance_Sh",
        "Performance_Crs",
        "Performance_Int",
        "Performance_TklW",
    ]

    TargetCol_V = "Performance_SoT"
    
    X_V = clean_features(ClubDf_V[FeatureCols_V])
    Y_V = ClubDf_V[TargetCol_V].fillna(0)
    
    # Prune features
    base_model = lgb.LGBMRegressor(verbose=-1)
    selected_features = prune_features(base_model, X_V, Y_V)
    X_V = X_V[selected_features]

    X_Train_V, X_Val_V, Y_Train_V, Y_Val_V = train_test_split(
        X_V, Y_V, test_size=0.2, random_state=42
    )

    # Train Ensemble with HPO
    print("Optimizing LGBM hyperparameters...")
    best_params = tune_lgbm(X_V, Y_V)
    print(f"Best params: {best_params}")
    
    print("Training LGBM...")
    lgbm_model = lgb.LGBMRegressor(**best_params)
    lgbm_model.fit(X_Train_V, Y_Train_V)
    
    print("Training NB...")
    nb_model = train_nb_model(X_Train_V, Y_Train_V)
    
    # Save ensemble
    ensemble = {'lgbm': lgbm_model, 'nb': nb_model}
    ModelPath_V = os.path.join(MODEL_DIR, "lgbm_sot_club_v2.pkl")
    with open(ModelPath_V, "wb") as f:
        pickle.dump(ensemble, f)
    
    print(f"Ensemble model saved to {ModelPath_V}")
    return ensemble
    print(f"\n[OK] Saved: {ModelPath_V}")

    return Model_V


def train_sot_international_model(df):
    """Train SoT model for international competitions."""
    print("\n" + "=" * 60)
    print("MODEL 2: Training lgbm_sot_international_v2.pkl")
    print("=" * 60)

    IntlDf_V = df[df["competition_type"] == 1].copy()
    print(f"International samples: {len(IntlDf_V)}")

    if len(IntlDf_V) < 100:
        print("ERROR: Not enough international samples. Skipping.")
        return None

    IntlDf_V["pos_encoded"] = IntlDf_V["pos_"].apply(encode_position)

    FeatureCols_V = [
        "age_",
        "competition_type",
        "min_",
        "pos_encoded",
        "Performance_Sh",
        "Performance_Crs",
        "Performance_Int",
        "Performance_TklW",
    ]

    TargetCol_V = "Performance_SoT"
    print(f"Using features: {FeatureCols_V}")
    print(f"Using target column: {TargetCol_V} (>= 1 shots on target = 1)")

    X_V = clean_features(IntlDf_V[FeatureCols_V])
    Y_V = IntlDf_V[TargetCol_V].fillna(0)
    X_V["sample_weight"] = 1.0

    print(
        f"Features shape: {X_V.shape}, Target distribution: {Y_V.value_counts().to_dict()}"
    )

    X_Train_V, X_Val_V, Y_Train_V, Y_Val_V = train_test_split(
        X_V, Y_V, test_size=0.2, random_state=42
    )

    Model_V = lgb.LGBMRegressor(**LgbmParams_V)
    Model_V.fit(X_Train_V, Y_Train_V, eval_set=[(X_Val_V, Y_Val_V)])

    Y_PredProb_V = Model_V.predict(X_Val_V)
    from sklearn.metrics import mean_absolute_error

    MAE_V = mean_absolute_error(Y_Val_V, Y_PredProb_V)

    print("\nValidation Results:")
    print("\nValidation Results:")
    print(f"  MAE: {MAE_V:.4f}")

    ModelPath_V = os.path.join(MODEL_DIR, "lgbm_sot_international_v2.pkl")
    with open(ModelPath_V, "wb") as f:
        pickle.dump(Model_V, f)
    print(f"  [OK] Saved: {ModelPath_V}")

    return Model_V


def train_passes_model(df):
    """Train Passes/Shots model (all competitions)."""
    print("\n" + "=" * 60)
    print("MODEL 3: Training lgbm_passes_v1.pkl")
    print("=" * 60)

    AllDf_V = df.copy()
    AllDf_V["pos_encoded"] = AllDf_V["pos_"].apply(encode_position)
    print(f"Total samples: {len(AllDf_V)}")

    # Feature set — no UUID string columns
    FeatureCols_V = [
        "age_",
        "competition_type",
        "min_",
        "pos_encoded",
        "Performance_Crs",
        "Performance_Int",
    ]

    # Target: player had at least 1 shot (proxy for high-activity players)
    # Performance_Sh = total shots per match (confirmed column)
    TargetCol_V = "Performance_Sh"
    print(f"Using features: {FeatureCols_V}")
    print(f"Using target column: {TargetCol_V} (>= 1 total shot = 1)")

    X_V = clean_features(AllDf_V[FeatureCols_V])
    Y_V = AllDf_V[TargetCol_V].fillna(0)
    X_V["sample_weight"] = 1.0

    print(
        f"Features shape: {X_V.shape}, Target distribution: {Y_V.value_counts().to_dict()}"
    )

    X_Train_V, X_Val_V, Y_Train_V, Y_Val_V = train_test_split(
        X_V, Y_V, test_size=0.2, random_state=42
    )

    Model_V = lgb.LGBMRegressor(**LgbmParams_V)
    Model_V.fit(X_Train_V, Y_Train_V, eval_set=[(X_Val_V, Y_Val_V)])

    print(f"Using target column: {TargetCol_V}")

    X_V = clean_features(AllDf_V[FeatureCols_V])
    Y_V = AllDf_V[TargetCol_V].fillna(0)
    X_V["sample_weight"] = 1.0

    print(
        f"Features shape: {X_V.shape}, Target distribution: {Y_V.value_counts().to_dict()}"
    )

    X_Train_V, X_Val_V, Y_Train_V, Y_Val_V = train_test_split(
        X_V, Y_V, test_size=0.2, random_state=42
    )

    Model_V = lgb.LGBMRegressor(**LgbmParams_V)
    Model_V.fit(X_Train_V, Y_Train_V, eval_set=[(X_Val_V, Y_Val_V)])

    Y_Pred_V = Model_V.predict(X_Val_V)
    from sklearn.metrics import mean_absolute_error

    MAE_V = mean_absolute_error(Y_Val_V, Y_Pred_V)

    print("\nValidation Results:")
    print(f"  MAE: {MAE_V:.4f}")

    ModelPath_V = os.path.join(MODEL_DIR, "lgbm_passes_v1.pkl")
    with open(ModelPath_V, "wb") as f:
        pickle.dump(Model_V, f)
    print(f"Saved: {ModelPath_V}")

    return Model_V


def train_minutes_model(df):
    """Train Minutes Played model (all competitions)."""
    print("\n" + "=" * 60)
    print("MODEL 4: Training lgbm_minutes_v1.pkl")
    print("=" * 60)

    from sklearn.metrics import mean_absolute_error

    AllDf_V = df.copy()
    AllDf_V["pos_encoded"] = AllDf_V["pos_"].apply(encode_position)
    print(f"Total samples: {len(AllDf_V)}")

    # Only numeric columns — no game_id_ UUID
    FeatureCols_V = [
        "age_",
        "competition_type",
        "pos_encoded",
        "Performance_Crs",
        "Performance_Int",
        "Performance_TklW",
    ]

    TargetCol_V = "min_"
    print(f"Using features: {FeatureCols_V}")
    print(f"Target: {TargetCol_V} (minutes played per game)")

    X_V = clean_features(AllDf_V[FeatureCols_V])
    Y_V = AllDf_V[TargetCol_V].fillna(0)
    X_V["sample_weight"] = 1.0

    print(f"Features shape: {X_V.shape}")

    X_Train_V, X_Val_V, Y_Train_V, Y_Val_V = train_test_split(
        X_V, Y_V, test_size=0.2, random_state=42
    )

    MinutesParams_V = {
        "n_estimators": 200,
        "learning_rate": 0.05,
        "max_depth": 4,
        "random_state": 42,
    }
    Model_V = lgb.LGBMRegressor(**MinutesParams_V)
    Model_V.fit(X_Train_V, Y_Train_V, eval_set=[(X_Val_V, Y_Val_V)])

    Y_Pred_V = Model_V.predict(X_Val_V)
    Mae_V = mean_absolute_error(Y_Val_V, Y_Pred_V)
    print(f"\nValidation MAE: {Mae_V:.2f} minutes")

    ModelPath_V = os.path.join(MODEL_DIR, "lgbm_minutes_v1.pkl")
    with open(ModelPath_V, "wb") as f:
        pickle.dump(Model_V, f)
    print(f"Saved: {ModelPath_V}")

    return Model_V


def print_calibration_buckets(y_true, y_pred_prob, model_name):
    """Print calibration bucket summary."""
    Buckets_V = [(0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.0)]

    print(f"\n  Calibration Buckets ({model_name}):")
    for low, high in Buckets_V:
        mask = (y_pred_prob > low) & (y_pred_prob <= high)
        if mask.sum() < 5:
            continue

        expected = y_pred_prob[mask].mean()
        actual = y_true[mask].mean()
        gap = abs(expected - actual) * 100

        print(
            f"    ({low:.1f}, {high:.1f}]: n={mask.sum()}, exp={expected:.1%}, "
            f"act={actual:.1%}, gap={gap:.1f}pp"
        )


def run_sanity_check():
    """Run sanity check on all trained models."""
    print("\n" + "=" * 60)
    print("STEP 5: Running sanity check on all models")
    print("=" * 60)

    ModelsToTest_V = [
        ("lgbm_sot_club_v1.pkl", "SoT Club"),
        ("lgbm_sot_international_v2.pkl", "SoT International"),
        ("lgbm_passes_v1.pkl", "Passes"),
        ("lgbm_minutes_v1.pkl", "Minutes"),
    ]

    AllPassed_V = True

    for model_file, model_name in ModelsToTest_V:
        model_path = os.path.join(MODEL_DIR, model_file)

        if not os.path.exists(model_path):
            print(f"[FAIL] {model_name}: Model file not found")
            AllPassed_V = False
            continue

        with open(model_path, "rb") as f:
            Model_V = pickle.load(f)

        np.random.seed(42)
        n_samples = 5
        n_features = (
            len(Model_V.feature_name_) if hasattr(Model_V, "feature_name_") else 10
        )

        X_Test_V = pd.DataFrame(
            np.random.rand(n_samples, n_features),
            columns=(
                Model_V.feature_name_
                if hasattr(Model_V, "feature_name_")
                else [f"f{i}" for i in range(n_features)]
            ),
        )

        if isinstance(Model_V, lgb.LGBMRegressor):
            predictions = Model_V.predict(X_Test_V)
        else:
            predictions = Model_V.predict_proba(X_Test_V)[:, 1]

        unique_preds = len(set(predictions))
        min_pred = predictions.min()
        max_pred = predictions.max()

        if unique_preds == n_samples and 0.0 <= min_pred and max_pred <= 1.0:
            print(
                f"[OK] {model_name}: PASS (unique probs: {unique_preds}, range: [{min_pred:.3f}, {max_pred:.3f}])"
            )
        elif isinstance(Model_V, lgb.LGBMRegressor):
            if unique_preds == n_samples:
                print(f"[OK] {model_name}: PASS (unique predictions: {unique_preds})")
            else:
                print(f"[FAIL] {model_name}: FAIL (duplicate predictions)")
                AllPassed_V = False
        else:
            print(f"[FAIL] {model_name}: FAIL (duplicate probs or out of range)")
            AllPassed_V = False

    return AllPassed_V


def main():
    """Main training pipeline."""
    print("\n" + "=" * 60)
    print("DeepFieldPro Model Training Pipeline")
    print("=" * 60)

    os.makedirs(MODEL_DIR, exist_ok=True)

    CombinedDf_V = load_and_prepare_data()

    print("\n" + "=" * 60)
    print("Available columns in dataset:")
    print("=" * 60)
    for i, col in enumerate(CombinedDf_V.columns):
        print(f"  {i+1}. {col}")

    Models_V = {}

    Models_V["sot_club"] = train_sot_club_model(CombinedDf_V)
    Models_V["sot_intl"] = train_sot_international_model(CombinedDf_V)
    Models_V["passes"] = train_passes_model(CombinedDf_V)
    Models_V["minutes"] = train_minutes_model(CombinedDf_V)

    SanityPassed_V = run_sanity_check()

    print("\n" + "=" * 60)
    print("TRAINING COMPLETE")
    print("=" * 60)

    TrainedModels_V = [f for f in os.listdir(MODEL_DIR) if f.endswith(".pkl")]
    print(f"Models saved: {len(TrainedModels_V)}")
    for model in sorted(TrainedModels_V):
        print(f"  - {model}")

    if SanityPassed_V:
        print("\n[OK] All sanity checks PASSED")
    else:
        print("\n[FAIL] Some sanity checks FAILED - review models before deployment")

    print("\nNext steps:")
    print("  1. Run: python tests/test_imports.py")
    print("  2. Run: python src/calibration_trainer.py")
    print("  3. Run: python tests/test_pipeline_e2e.py")


if __name__ == "__main__":
    main()

def train_sot_int_model(df):
    IntDf_V = df[df['competition_type'] == 1].copy()
    IntDf_V['pos_encoded'] = IntDf_V['pos_'].apply(encode_position)
    FeatureCols_V = ['age_', 'competition_type', 'min_', 'pos_encoded', 'Performance_Sh']
    TargetCol_V = 'Performance_SoT'
    X_V = clean_features(IntDf_V[FeatureCols_V])
    Y_V = IntDf_V[TargetCol_V].fillna(0)
    best_params = tune_lgbm(X_V, Y_V)
    lgbm_model = lgb.LGBMRegressor(**best_params)
    lgbm_model.fit(X_V, Y_V)
    nb_model = train_nb_model(X_V, Y_V)
    ensemble = {'lgbm': lgbm_model, 'nb': nb_model}
    ModelPath_V = os.path.join(MODEL_DIR, 'lgbm_sot_int_v2.pkl')
    with open(ModelPath_V, 'wb') as f:
        pickle.dump(ensemble, f)
    return ensemble

