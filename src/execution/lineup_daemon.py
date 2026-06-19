import lightgbm as lgb
import pandas as pd
import os
import re

MODEL_PATH = "models/lineup_model.txt"


class LineupPredictor:
    def __init__(self):
        self.model = None
        if os.path.exists(MODEL_PATH):
            self.model = lgb.Booster(model_file=MODEL_PATH)
        else:
            print("WARNING: Lineup model not found.")

    def predict_starter_prob(self, player_features: dict):
        """
        player_features: dict matching feature names
        """
        if not self.model:
            return 0.5  # Fallback

        # Ensure features match what model was trained on
        feature_names = self.model.feature_name()
        input_data = [player_features.get(f, 0) for f in feature_names]

        prob = self.model.predict([input_data])[0]
        return prob


lineup_predictor = LineupPredictor()
