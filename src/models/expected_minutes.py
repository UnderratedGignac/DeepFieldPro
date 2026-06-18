import lightgbm as lgb
import os
import pandas as pd
import re

MODEL_DIR = "models"
MODEL_PATH = os.path.join(MODEL_DIR, "expected_minutes_model.txt")


class MinutesModel:
    def __init__(self):
        self.model = None
        if os.path.exists(MODEL_PATH):
            self.model = lgb.Booster(model_file=MODEL_PATH)
        else:
            print("WARNING: Expected Minutes model not found.")

    def predict(self, min_roll5, pos_features):
        """
        min_roll5: float
        pos_features: dict, e.g., {'pos_FW': 1, 'pos_MF': 0, ...}
        """
        if not self.model:
            return 90.0  # Fallback

        # Ensure features match what model was trained on
        # [min_roll5, pos_AM, pos_CB, pos_CM, pos_DF, pos_DFFW, pos_DFMF, pos_DM, pos_FW, pos_FWMF, pos_GK, pos_LB, pos_LM, pos_LW, pos_MF, pos_RB, pos_RM, pos_RW]
        feature_names = self.model.feature_name()
        input_data = [min_roll5] + [pos_features.get(f, 0) for f in feature_names[1:]]

        pred = self.model.predict([input_data])[0]
        return max(0.0, min(90.0, pred))


minutes_model = MinutesModel()
