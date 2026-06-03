import sqlite3
import pandas as pd
import logging

logger = logging.getLogger(__name__)


class ExecutionHeatmapEngine:
    """
    Generates multidimensional heatmaps of fill-rates, slippage, and rejections.
    Useful for visualizing Market Microstructure performance.
    """

    def __init__(
        self, db_path: str = "C:/Users/Elie/DeepFieldPro/db/adaptive_memory.sqlite"
    ):
        self.db_path = db_path

    def generate_fill_rate_heatmap(self):
        """
        Generates a text-based (or dataframes) heatmap of Fill Rates by Market and Confidence Bucket.
        """
        query = """
            SELECT market_type, 
                   ROUND(lineup_confidence * 10) / 10.0 AS conf_bucket,
                   AVG(CASE WHEN execution_status = 'filled' THEN 1 ELSE 0 END) AS fill_rate,
                   COUNT(*) AS attempts
            FROM execution_outcomes
            GROUP BY market_type, conf_bucket
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                df = pd.read_sql_query(query, conn)

            if df.empty:
                logger.info("[HEATMAP] No data available for Fill Rate Heatmap.")
                return

            pivot = df.pivot(
                index="market_type", columns="conf_bucket", values="fill_rate"
            )
            logger.info("\n=== FILL RATE HEATMAP (Market x Confidence) ===")
            logger.info(
                "\n" + pivot.to_string(na_rep="N/A", float_format="{:.1%}".format)
            )
            logger.info("===============================================\n")

        except Exception as e:
            logger.error(f"[HEATMAP] Failed to generate heatmap: {e}")


heatmap_engine = ExecutionHeatmapEngine()
