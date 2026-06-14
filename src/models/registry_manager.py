import json
import os
import logging
from typing import List, Dict, Any
from src.models.inference_wrapper import SafeModelLoader

logger = logging.getLogger(__name__)

class ModelRegistry:
    """
    Registry manager to track and load production-approved models.
    Prevents unauthorized or unversioned models from entering the execution pipeline.
    """

    def __init__(self, registry_path: str = "models/model_registry.json"):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.registry_path = os.path.join(self.base_dir, registry_path)
        self.models_metadata = []
        self._load_registry()

    def _load_registry(self):
        """Parse the registry JSON file."""
        if not os.path.exists(self.registry_path):
            logger.error(f"[REGISTRY] Registry file not found: {self.registry_path}")
            return

        try:
            with open(self.registry_path, "r") as f:
                data = json.load(f)
                self.models_metadata = data.get("models", [])
            logger.info(f"[REGISTRY] Loaded {len(self.models_metadata)} model definitions.")
        except Exception as e:
            logger.error(f"[REGISTRY] Failed to parse model registry: {e}")

    def get_production_models(self) -> List[Dict[str, Any]]:
        """Return only models marked as 'production'."""
        return [m for m in self.models_metadata if m.get("status") == "production"]

    def load_production_pipeline(self) -> Dict[str, SafeModelLoader]:
        """
        Initializes SafeModelLoader wrappers for all production models.
        Returns a dictionary mapping target_variable -> SafeModelLoader.
        """
        pipeline = {}
        production_models = self.get_production_models()

        for meta in production_models:
            model_name = meta["model_name"]
            # Construct absolute path for the model file
            model_file_path = os.path.join(self.base_dir, meta["file_path"])
            
            loader = SafeModelLoader(
                model_name=model_name,
                model_path=model_file_path,
                expected_features=meta["expected_features"]
            )
            
            if loader.model is not None:
                pipeline[meta["target_variable"]] = loader
                logger.info(f"[REGISTRY] Production model {model_name} initialized for {meta['target_variable']}.")
            else:
                logger.warning(f"[REGISTRY] Failed to initialize production model: {model_name}")

        return pipeline

# Singleton instance for global access
registry_manager = ModelRegistry()
