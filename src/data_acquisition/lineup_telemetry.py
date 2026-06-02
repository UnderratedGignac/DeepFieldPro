# lineup_telemetry.py
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class LineupTelemetry:
    """
    Handles tracking latency of lineup detection vs official release, 
    and monitors subsequent market reactions (odds movement).
    """
    def __init__(self):
        self.latency_records = []
        
    def record_latency(self, fixture_id: str, source: str, official_release_time: str, detection_time: str):
        """
        Track how fast the system captures lineups compared to the official club timestamps.
        """
        try:
            t_official = datetime.fromisoformat(official_release_time.replace("Z", "+00:00"))
            t_detect = datetime.fromisoformat(detection_time.replace("Z", "+00:00"))
            
            latency_seconds = (t_detect - t_official).total_seconds()
            
            self.latency_records.append({
                "fixture_id": fixture_id,
                "source": source,
                "latency_seconds": latency_seconds
            })
            logger.info(f"Lineup Detection Latency for {fixture_id} ({source}): {latency_seconds} seconds.")
        except Exception as e:
            logger.error(f"Failed to record lineup latency: {e}")

    def track_market_reaction(self, fixture_id: str, player: str, old_odds: float, new_odds: float, time_since_lineup: float):
        """
        Tracks odds movement after a lineup release to quantify market efficiency.
        Example: Saka confirmed: 1.90 -> 1.72 within 14 seconds.
        """
        movement = new_odds - old_odds
        logger.info(f"Market Reaction [{fixture_id}]: {player} odds moved {movement:+.2f} ({old_odds} -> {new_odds}) in {time_since_lineup}s since lineup release.")

telemetry_tracker = LineupTelemetry()
