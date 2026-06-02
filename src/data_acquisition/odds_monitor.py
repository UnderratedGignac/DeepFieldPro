import asyncio
import logging
from typing import List, Dict, Any

from .betarabia_scraper import betarabia_scraper
from .db_writer import db_writer
from .validation_engine import validation_engine

logger = logging.getLogger(__name__)

class OddsMonitor:
    def __init__(self):
        self.active_fixtures = {} # fixture_id -> { "starters": [...] }

    def start_monitoring_fixture(self, fixture_id: str, confirmed_starters: List[Dict[str, Any]]):
        """
        Registers a fixture for continuous odds monitoring.
        """
        self.active_fixtures[fixture_id] = {
            "starters": confirmed_starters,
            "interval": 20 # seconds between scrapes
        }
        logger.info(f"Started continuous odds monitoring for {fixture_id}.")

    def stop_monitoring_fixture(self, fixture_id: str):
        if fixture_id in self.active_fixtures:
            del self.active_fixtures[fixture_id]
            logger.info(f"Stopped odds monitoring for {fixture_id}.")

    async def monitor_loop(self):
        """
        Continuously polls active fixtures for odds updates every 15-30 seconds.
        """
        logger.info("Starting continuous odds monitor loop...")
        while True:
            for fixture_id, data in list(self.active_fixtures.items()):
                try:
                    # Fetch fresh odds from the websocket cache (no DOM scraping)
                    fresh_odds = betarabia_scraper.get_latest_odds()
                    
                    # Validate
                    valid_odds = validation_engine.validate_odds(fresh_odds)
                    
                    if valid_odds:
                        # Write to SQLite odds_stream and odds_history
                        await db_writer.insert_odds(valid_odds)
                        
                except Exception as e:
                    logger.error(f"Error in odds monitoring loop for {fixture_id}: {e}")
            
            # Sleep 1 second since we rely on websockets, 
            # we just frequently flush cache to DB.
            await asyncio.sleep(1)

odds_monitor = OddsMonitor()
