"""
advanced_training_pipeline.py — DeepFieldPro Hierarchical Model Training
=========================================================================
Phase 1: Train player-level models (LightGBM classifiers for goal, assist probabilities)
Phase 2: Aggregate Out-Of-Fold (OOF) predictions up to team level
Phase 3: Train team-level models using aggregated player predictions as features

BUG FIX: numpy imported at module level (was erroneously inside __main__ block).
"""
import os
import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.model_selection import KFold
from sklearn.metrics import log_loss, mean_squared_error
import pickle
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AdvancedTrainingPipeline:
    """
    Hierarchical training pipeline for DeepFieldPro.
    Layer 1: Player-level models (Goals, Assists)
    Layer 2: Team-level models (using aggregated Layer 1 Out-Of-Fold outputs)
    """
    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.models_dir = "models"
        os.makedirs(self.models_dir, exist_ok=True)

    def generate_dummy_data(self):
        """Generate synthetic data to demonstrate the pipeline flow."""
        # Player Data
        self.player_df = pd.DataFrame({
            "player_id": range(1, 1001),
            "match_id": np.random.randint(1, 100, 1000),
            "team_id": np.random.randint(1, 20, 1000),
            "goals_p90": np.random.rand(1000),
            "shots_p90": np.random.rand(1000) * 4,
            "target_goal": np.random.binomial(1, 0.1, 1000) # Did they score?
        })
        # Team Data
        self.team_df = pd.DataFrame({
            "match_id": range(1, 100),
            "home_team_id": np.random.randint(1, 20, 99),
            "away_team_id": np.random.randint(1, 20, 99),
            "home_xg_p90": np.random.rand(99) * 2,
            "target_home_goals": np.random.poisson(1.5, 99)
        })

    def train_layer_1_players(self):
        logger.info("--- Training Layer 1: Player Models ---")
        features = ["goals_p90", "shots_p90"]
        target = "target_goal"
        
        X = self.player_df[features]
        y = self.player_df[target]
        
        kf = KFold(n_splits=5, shuffle=True, random_state=42)
        oof_preds = np.zeros(len(X))
        models = []
        
        for train_idx, val_idx in kf.split(X):
            X_train, y_train = X.iloc[train_idx], y.iloc[train_idx]
            X_val, y_val = X.iloc[val_idx], y.iloc[val_idx]
            
            model = lgb.LGBMClassifier(n_estimators=100, learning_rate=0.05, random_state=42)
            model.fit(X_train, y_train, eval_set=[(X_val, y_val)], callbacks=[lgb.early_stopping(10, verbose=False)])
            
            oof_preds[val_idx] = model.predict_proba(X_val)[:, 1]
            models.append(model)
            
        score = log_loss(y, oof_preds)
        logger.info(f"Player Goal Model OOF LogLoss: {score:.4f}")
        
        # Save OOF predictions to use as features for Layer 2
        self.player_df["oof_goal_prob"] = oof_preds
        
        # Save best model
        with open(f"{self.models_dir}/player_goal_lgbm.pkl", "wb") as f:
            pickle.dump(models[0], f)

    def prepare_layer_2_features(self):
        logger.info("--- Aggregating Player OOFs to Team Level ---")
        # Sum the player goal probabilities for each team in each match
        agg_df = self.player_df.groupby(['match_id', 'team_id'])['oof_goal_prob'].sum().reset_index()
        agg_df.rename(columns={'oof_goal_prob': 'team_sum_player_goal_prob'}, inplace=True)
        
        # Merge into team match data (for simplicity, just doing home team here)
        self.team_df = self.team_df.merge(
            agg_df, 
            left_on=['match_id', 'home_team_id'], 
            right_on=['match_id', 'team_id'], 
            how='left'
        )
        self.team_df.fillna(0, inplace=True)

    def train_layer_2_teams(self):
        logger.info("--- Training Layer 2: Team Models ---")
        features = ["home_xg_p90", "team_sum_player_goal_prob"]
        target = "target_home_goals"
        
        X = self.team_df[features]
        y = self.team_df[target]
        
        model = lgb.LGBMRegressor(objective='poisson', n_estimators=100, learning_rate=0.05, random_state=42)
        model.fit(X, y)
        
        preds = model.predict(X)
        rmse = np.sqrt(mean_squared_error(y, preds))
        logger.info(f"Team Goal Model Train RMSE: {rmse:.4f}")
        
        with open(f"{self.models_dir}/team_goals_lgbm.pkl", "wb") as f:
            pickle.dump(model, f)
        
        logger.info("Pipeline Training Complete.")

if __name__ == "__main__":
    # BUG FIX: numpy is now imported at module level — no need to import inside __main__
    pipeline = AdvancedTrainingPipeline()
    pipeline.generate_dummy_data()
    pipeline.train_layer_1_players()
    pipeline.prepare_layer_2_features()
    pipeline.train_layer_2_teams()
