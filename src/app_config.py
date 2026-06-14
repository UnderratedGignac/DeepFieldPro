import os


class Config:
    """
    Centralized configuration to remove hardcoded paths and values.
    """

    # Base Paths
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DB_DIR = os.getenv("DEEPFIELD_DB_DIR", os.path.join(BASE_DIR, "db"))
    DATA_DIR = os.getenv("DEEPFIELD_DATA_DIR", os.path.join(BASE_DIR, "data"))
    MODEL_DIR = os.getenv("DEEPFIELD_MODEL_DIR", os.path.join(BASE_DIR, "models"))
    ADAPTIVE_MEMORY_DB_PATH = os.path.join(DB_DIR, "adaptive_memory.sqlite")

    # Bankroll & Risk
    STARTING_BANKROLL = float(os.getenv("DEEPFIELD_STARTING_BANKROLL", "10000.0"))
    MAX_EXPOSURE_PER_FIXTURE = float(
        os.getenv("DEEPFIELD_MAX_EXPOSURE_FIXTURE", "0.15")
    )  # Max 15% of bankroll per fixture
    BASE_KELLY_FRACTION = float(os.getenv("DEEPFIELD_BASE_KELLY_FRACTION", "0.25"))


config = Config()
