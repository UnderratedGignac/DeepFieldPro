import logging
import os
import sqlite3
import pandas as pd
from datetime import datetime
from src.app_config import config

logger = logging.getLogger(__name__)


class TelemetryArchiver:
    """
    Transitions DeepFieldPro into an institutional data-harvesting organism.
    Dumps SQLite fast-memory into partitioned, compressed Parquet files for heavy ML mining.
    """

    def __init__(self, db_path: str = config.ADAPTIVE_MEMORY_DB_PATH):
        self.db_path = db_path
        self.warehouse_dir = os.path.join(
            config.BASE_DIR, "telemetry_warehouse", "parquet"
        )
        os.makedirs(self.warehouse_dir, exist_ok=True)

    def archive_executions(self):
        """
        Extracts executions from SQLite, writes to Parquet, and prunes SQLite to prevent bloat.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                df = pd.read_sql_query("SELECT * FROM execution_outcomes", conn)

            if df.empty:
                logger.info("[TELEMETRY ARCHIVER] No new executions to archive.")
                return

            # Partitioning by date
            today_str = datetime.timezone.utcnow().strftime("%Y-%m-%d")
            out_file = os.path.join(
                self.warehouse_dir, f"executions_{today_str}.parquet"
            )

            # Append if exists
            if os.path.exists(out_file):
                existing_df = pd.read_parquet(out_file)
                combined_df = pd.concat([existing_df, df]).drop_duplicates(
                    subset=["exec_id"]
                )
            else:
                combined_df = df

            # Write compressed Parquet
            combined_df.to_parquet(out_file, compression="snappy")

            # Prune sqlite (Keep last 24 hours only for fast-memory feedback loop)
            # In production, we'd prune using the timestamp column
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "DELETE FROM execution_outcomes"
                )  # Simplified for architecture demo

            logger.info(
                f"[TELEMETRY ARCHIVER] Successfully archived {len(df)} executions to Parquet."
            )

        except Exception as e:
            logger.error(f"[TELEMETRY ARCHIVER] Archival failed: {e}")


archiver = TelemetryArchiver()
