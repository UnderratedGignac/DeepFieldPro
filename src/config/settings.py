"""
Application Settings and Configuration

Centralized configuration management using environment variables.
"""

import os
from pathlib import Path


class Settings:
    """Application settings loaded from environment variables."""

    # Base directories
    BASE_DIR = Path(__file__).resolve().parent.parent.parent
    DATA_DIR = os.getenv("DEEPFIELD_DATA_DIR", BASE_DIR / "data")
    DB_DIR = os.getenv("DEEPFIELD_DB_DIR", BASE_DIR / "db")
    LOGS_DIR = os.getenv("DEEPFIELD_LOGS_DIR", BASE_DIR / "logs")

    # Database
    DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DB_DIR}/deepfield.db")
    ASYNC_DATABASE_URL = os.getenv(
        "ASYNC_DATABASE_URL", f"sqlite+aiosqlite:///{DB_DIR}/deepfield.db"
    )

    # API Keys
    API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY", "")
    FOOTBALL_DATA_ORG_KEY = os.getenv("FOOTBALL_DATA_ORG_KEY", "")
    BETFAIR_APP_KEY = os.getenv("BETFAIR_APP_KEY", "")
    BETFAIR_USERNAME = os.getenv("BETFAIR_USERNAME", "")
    BETFAIR_PASSWORD = os.getenv("BETFAIR_PASSWORD", "")
    BETFAIR_CERTS_DIR = os.getenv("BETFAIR_CERTS_DIR", "")

    # Bankroll & Risk
    STARTING_BANKROLL = float(os.getenv("DEEPFIELD_STARTING_BANKROLL", "10000.0"))
    MAX_EXPOSURE_PER_FIXTURE = float(
        os.getenv("DEEPFIELD_MAX_EXPOSURE_FIXTURE", "0.15")
    )
    BASE_KELLY_FRACTION = float(os.getenv("DEEPFIELD_BASE_KELLY_FRACTION", "0.25"))
    MAX_KELLY_FRACTION = float(os.getenv("DEEPFIELD_MAX_KELLY_FRACTION", "0.5"))

    # Browser/Session Settings
    BROWSER_HEADLESS = os.getenv("BROWSER_HEADLESS", "true").lower() == "true"
    BROWSER_TIMEOUT = int(os.getenv("BROWSER_TIMEOUT", "30000"))
    MAX_CONCURRENT_SESSIONS = int(os.getenv("MAX_CONCURRENT_SESSIONS", "5"))

    # Odds Collection
    ODDS_COLLECTION_INTERVAL = int(os.getenv("ODDS_COLLECTION_INTERVAL", "30"))
    MAX_REQUESTS_PER_MINUTE = int(os.getenv("MAX_REQUESTS_PER_MINUTE", "60"))

    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # Telemetry
    TELEMETRY_ENABLED = os.getenv("TELEMETRY_ENABLED", "true").lower() == "true"
    TELEMETRY_DIR = os.getenv("TELEMETRY_DIR", BASE_DIR / "telemetry_warehouse")

    # Model Settings
    MODEL_DIR = os.getenv("MODEL_DIR", BASE_DIR / "models")
    CALIBRATION_WINDOW = int(os.getenv("CALIBRATION_WINDOW", "90"))
    MIN_TRAINING_SAMPLES = int(os.getenv("MIN_TRAINING_SAMPLES", "100"))

    def ensure_directories(self):
        """Create necessary directories if they don't exist."""
        for directory in [self.DATA_DIR, self.DB_DIR, self.LOGS_DIR, self.MODEL_DIR]:
            Path(directory).mkdir(parents=True, exist_ok=True)


# Global settings instance
settings = Settings()
settings.ensure_directories()
