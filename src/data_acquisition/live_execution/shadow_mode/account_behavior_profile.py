import os
from app_config import config
import logging
import sqlite3
import time

logger = logging.getLogger(__name__)


class AccountBehaviorProfile:
    """
    Longitudinal telemetry to detect sportsbook adaptation signatures.
    Measures confirmation delays over time, rejection rates, and account throttling.
    """

    def __init__(
        self,
        db_path: str = os.path.join(
            config.DB_DIR,
            "adversarial_telemetry.sqlite",
        ),
    ):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        import os

        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS account_telemetry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL,
                    avg_confirmation_delay_ms REAL,
                    rejection_rate_pct REAL,
                    suspension_aggressiveness_score REAL,
                    session_uptime_hours REAL
                );
            """)

    def log_session_telemetry(
        self,
        avg_delay: float,
        rejection_rate: float,
        suspension_score: float,
        uptime: float,
    ):
        """
        Periodically records the global state of the account's execution health.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO account_telemetry (
                    timestamp, avg_confirmation_delay_ms, rejection_rate_pct, 
                    suspension_aggressiveness_score, session_uptime_hours
                ) VALUES (?, ?, ?, ?, ?)
            """,
                (time.time(), avg_delay, rejection_rate, suspension_score, uptime),
            )

        logger.debug(
            f"[ACCOUNT PROFILE] Logged telemetry. Rejection Rate: {rejection_rate*100:.1f}%"
        )


account_profile = AccountBehaviorProfile()
