from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    """
    Centralized configuration for DeepFieldPro.
    Loads variables from environment or .env file.
    """

    # Internal API Security
    DEEPFIELD_API_KEY: str = "dfp_secret_key_change_me"
    SHADOW_MODE: bool = True

    # Database Configuration
    DATABASE_URL: str = "sqlite:///src/data/deepfield.db"

    # External API Keys (Sportsbook & Intelligence)
    STAIR_AI_API_KEY: Optional[str] = None
    API_FOOTBALL_KEY: Optional[str] = None
    ODDS_API_KEY: Optional[str] = None
    DISCORD_WEBHOOK_URL: Optional[str] = None
    WHATSAPP_PHONE: Optional[str] = None  # Format: +961XXXXXXXX
    WHATSAPP_API_KEY: Optional[str] = None # CallMeBot API Key

    # Sportsbook Credentials
    BETARABIA_USERNAME: Optional[str] = None
    BETARABIA_PASSWORD: Optional[str] = None

    # Model Configuration
    MODEL_THRESHOLD_MIN_EDGE: float = 0.05  # Increased from 0.03
    MODEL_MIN_ODDS: float = 2.00           # Increased from 1.25
    MODEL_KELLY_FRACTION: float = 0.20     # Slightly more conservative sizing

    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
