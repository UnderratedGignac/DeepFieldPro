import os
import joblib
import logging
import pandas as pd
from typing import List, Optional, Any

logger = logging.getLogger(__name__)


class SafeModelLoader:
    """
    Wrapper around AI models to ensure inference safety.
    Validates features before calling .predict() to prevent system crashes.
    """

    def __init__(self, model_name: str, model_path: str, expected_features: List[str]):
        self.model_name = model_name
        self.model_path = model_path
        self.expected_features = expected_features
        self.model = None
        self._load_model()

    def _load_model(self):
        """Safely load the model from disk."""
        if not os.path.exists(self.model_path):
            logger.critical(f"[SAFE LOADER] Model file missing: {self.model_path}")
            return

        try:
            self.model = joblib.load(self.model_path)
            logger.info(f"[SAFE LOADER] Successfully loaded model: {self.model_name}")
        except Exception as e:
            logger.critical(
                f"[SAFE LOADER] Failed to load model {self.model_name}: {e}"
            )
            self.model = None

    def predict_safe(self, df: pd.DataFrame) -> Optional[Any]:
        """
        Perform inference only after validating that all required features exist.
        """
        if self.model is None:
            logger.error(
                f"[SAFE LOADER] Inference skipped: {self.model_name} is not loaded."
            )
            return None

        # Feature Validation Logic
        missing_features = [f for f in self.expected_features if f not in df.columns]

        if missing_features:
            logger.critical(
                f"[SAFE LOADER] FEATURE DRIFT DETECTED. Model: {self.model_name}. "
                f"Missing features: {missing_features}. Inference aborted."
            )
            return None

        try:
            # Ensure we only pass the expected features to the model
            input_data = df[self.expected_features]
            return self.model.predict(input_data)
        except Exception as e:
            logger.error(f"[SAFE LOADER] Inference crash in {self.model_name}: {e}")
            return None


# --- Integration Example: Expected Minutes Model ---

# Define features expected by models/lgbm_minutes_v1.pkl
LGBM_MINUTES_FEATURES = [
    "started_last_match",
    "started_last_3",
    "minutes_last_5",
    "Pos",
    "Comp",
    "days_rest",
]

# Instantiate the safe wrapper
minutes_model_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "..",
    "models",
    "lgbm_minutes_v1.pkl",
)

safe_minutes_model = SafeModelLoader(
    model_name="Expected Minutes LGBM",
    model_path=minutes_model_path,
    expected_features=LGBM_MINUTES_FEATURES,
)


def get_minutes_prediction(player_df: pd.DataFrame):
    """Utility function to use the safe wrapper."""
    return safe_minutes_model.predict_safe(player_df)
