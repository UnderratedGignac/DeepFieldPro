# replay_analytics.py
import logging
import statistics
from collections import defaultdict
from typing import Dict, List

logger = logging.getLogger(__name__)


class ReplayAnalyticsDashboard:
    """
    Research-grade analytics dashboard for Market Microstructure analysis.
    Tracks CLV Distribution, Edge Decay, Fill Probabilities, and Execution Friction.
    """

    def __init__(self):
        self.metrics = {
            "theoretical_ev_sum": 0.0,
            "realized_ev_sum": 0.0,
            "total_attempts": 0,
            "total_fills": 0,
            "total_rejections": 0,
            "total_slippage_ticks": 0.0,
            "average_latency_ms": 0.0,
        }

        # Segmented Data
        self.clv_records: List[float] = []
        self.fills_by_market: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {"attempts": 0, "fills": 0}
        )
        self.ev_by_confidence: Dict[str, Dict[str, float]] = defaultdict(
            lambda: {"theoretical": 0.0, "realized": 0.0}
        )
        self.edge_decay: List[Dict[str, float]] = []

    def record_attempt(self, result: dict):
        self.metrics["total_attempts"] += 1

        market = result.get("market", "unknown")
        confidence = result.get("confidence", 1.0)
        conf_bucket = f"{max(0.0, min(1.0, (confidence // 0.1) * 0.1)):.1f}-{max(0.0, min(1.0, (confidence // 0.1) * 0.1 + 0.1)):.1f}"

        self.fills_by_market[market]["attempts"] += 1

        theoretical = result.get("theoretical_ev", 0.0)
        self.ev_by_confidence[conf_bucket]["theoretical"] += theoretical
        self.metrics["theoretical_ev_sum"] += theoretical

        # Record decay timing
        if "time_since_lineup" in result:
            self.edge_decay.append(
                {"time_sec": result["time_since_lineup"], "edge": theoretical}
            )

        if result["status"] == "rejected":
            self.metrics["total_rejections"] += 1
            return

        if result["status"] == "filled":
            self.metrics["total_fills"] += 1
            self.fills_by_market[market]["fills"] += 1
            self.metrics["total_slippage_ticks"] += result["slippage"]

            # Recalculate EV based on realized odds
            requested_odds = result["requested_odds"]
            realized_odds = result["realized_odds"]
            ev_drop_ratio = (
                realized_odds / requested_odds if requested_odds > 0 else 1.0
            )

            realized = theoretical * ev_drop_ratio
            self.metrics["realized_ev_sum"] += realized
            self.ev_by_confidence[conf_bucket]["realized"] += realized

            # Assume closing line is efficient for mock purposes if absent, or use actual
            closing_odds = result.get(
                "closing_odds", realized_odds * 0.95
            )  # Mock closing line beat
            clv = (realized_odds / closing_odds) - 1.0 if closing_odds > 0 else 0.0
            self.clv_records.append(clv)

            current_avg = self.metrics["average_latency_ms"]
            n = self.metrics["total_fills"]
            new_val = result["execution_delay_ms"]
            self.metrics["average_latency_ms"] = (
                current_avg + (new_val - current_avg) / n
            )

    def generate_report(self):
        theor_ev = self.metrics["theoretical_ev_sum"]
        realized_ev = self.metrics["realized_ev_sum"]
        realization_rate = (realized_ev / theor_ev) if theor_ev > 0 else 0.0
        fill_rate = (
            (self.metrics["total_fills"] / self.metrics["total_attempts"])
            if self.metrics["total_attempts"] > 0
            else 0.0
        )

        # CLV Stats
        mean_clv = statistics.mean(self.clv_records) if self.clv_records else 0.0
        median_clv = statistics.median(self.clv_records) if self.clv_records else 0.0
        std_clv = (
            statistics.stdev(self.clv_records) if len(self.clv_records) > 1 else 0.0
        )

        logger.info("\n=== MARKET MICROSTRUCTURE & REPLAY ANALYTICS ===")
        logger.info(f"Total Execution Attempts : {self.metrics['total_attempts']}")
        logger.info(f"Fill Rate                : {fill_rate * 100:.1f}%")
        logger.info(f"Rejections               : {self.metrics['total_rejections']}")
        logger.info(
            f"Avg Execution Latency    : {self.metrics['average_latency_ms']:.0f} ms"
        )
        logger.info(
            f"Avg Slippage (ticks)     : {self.metrics['total_slippage_ticks'] / max(1, self.metrics['total_fills']):.3f}"
        )
        logger.info("-------------------------------------------------")
        logger.info(f"Theoretical EV Captured  : {theor_ev:.3f}")
        logger.info(f"Realized EV Achieved     : {realized_ev:.3f}")
        logger.info(f"EDGE REALIZATION RATE    : {realization_rate * 100:.1f}%")
        logger.info("-------------------------------------------------")
        logger.info(f"Mean CLV                 : {mean_clv * 100:.2f}%")
        logger.info(f"Median CLV               : {median_clv * 100:.2f}%")
        logger.info(f"CLV Std Dev              : {std_clv * 100:.2f}%")
        logger.info("-------------------------------------------------")

        logger.info("--- Fill Probability by Market ---")
        for market, stats in self.fills_by_market.items():
            rate = (
                (stats["fills"] / stats["attempts"]) if stats["attempts"] > 0 else 0.0
            )
            logger.info(
                f"{market.ljust(25)}: {rate*100:.1f}% ({stats['fills']}/{stats['attempts']})"
            )

        logger.info("-------------------------------------------------")
        logger.info("--- Edge Persistence by Confidence Bucket ---")
        for bucket, vals in sorted(self.ev_by_confidence.items()):
            r_rate = (
                (vals["realized"] / vals["theoretical"])
                if vals["theoretical"] > 0
                else 0.0
            )
            logger.info(
                f"Conf {bucket.ljust(10)} | Theor EV: {vals['theoretical']:.2f} | Realized EV: {vals['realized']:.2f} | Retention: {r_rate*100:.1f}%"
            )

        logger.info("=================================================\n")
        return realization_rate


replay_dashboard = ReplayAnalyticsDashboard()
