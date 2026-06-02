import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any

from .lineup_scraper import lineup_scraper
from .event_dispatcher import event_dispatcher

logger = logging.getLogger(__name__)

class FixturesMonitor:
    def __init__(self):
        self.monitored_fixtures = {} # fixture_id -> dict of metadata

    def add_fixture_to_monitor(self, fixture_id: str, kickoff_utc: str):
        """
        Add a fixture to be monitored for lineups.
        """
        self.monitored_fixtures[fixture_id] = {
            "kickoff_utc": datetime.fromisoformat(kickoff_utc.replace("Z", "+00:00")),
            "status": "pending"
        }
        logger.info(f"Added {fixture_id} to monitoring pool. Kickoff: {kickoff_utc}")

    def _calculate_poll_interval(self, time_to_kickoff: timedelta) -> int:
        """
        Determine polling interval in seconds based on proximity to kickoff.
        > 2 hours = 15 mins (900s)
        < 2 hours = 5 mins (300s)
        < 45 mins = 60s
        """
        seconds = time_to_kickoff.total_seconds()
        if seconds > 7200:
            return 900
        elif seconds > 2700:
            return 300
        else:
            return 60

    async def monitor_loop(self):
        """
        Continuously checks fixtures based on dynamic polling.
        """
        logger.info("Starting fixtures monitor loop...")
        while True:
            now = datetime.now(timezone.utc)
            
            for fixture_id, data in list(self.monitored_fixtures.items()):
                if data["status"] == "confirmed":
                    continue
                    
                time_to_kickoff = data["kickoff_utc"] - now
                
                # Check if it's time to poll
                last_polled = data.get("last_polled")
                poll_interval = self._calculate_poll_interval(time_to_kickoff)
                
                if not last_polled or (now - last_polled).total_seconds() >= poll_interval:
                    data["last_polled"] = now
                    
                    try:
                        lineup_payload = await lineup_scraper.fetch_official_lineups(fixture_id)
                        
                        if lineup_payload.get("lineup_status") == "confirmed":
                            data["status"] = "confirmed"
                            logger.info(f"Lineups confirmed for {fixture_id}!")
                            # Dispatch the event
                            asyncio.create_task(event_dispatcher.handle_lineups_confirmed(lineup_payload))
                            
                    except Exception as e:
                        logger.error(f"Error checking lineup for {fixture_id}: {e}")
                        
            # Sleep a base tick to prevent tight looping
            await asyncio.sleep(10)

fixtures_monitor = FixturesMonitor()
