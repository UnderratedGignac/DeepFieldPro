import asyncio
import logging
import json
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any
from playwright.async_api import async_playwright

from .market_mapper import market_mapper, MARKET_STATE
from .normalization_engine import normalize_engine
from .websocket_parser import frame_parser, CanonicalOddsEvent

logger = logging.getLogger(__name__)

class BetarabiaAPIClient:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        
        # In-memory odds cache for staleness detection and deduplication
        self.odds_cache = {} 
        self.STALE_THRESHOLD_SECONDS = 15

    async def initialize(self):
        """
        Starts the Playwright browser. Use Undetected Chromium conceptually here.
        """
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=True)
        self.context = await self.browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        self.page = await self.context.new_page()
        
        # Setup Network Interception
        self.page.on("response", self._intercept_xhr_response)
        self.page.on("websocket", self._intercept_websocket)

    async def _intercept_xhr_response(self, response):
        """
        Intercept XHR/Fetch API responses to grab JSON payloads directly instead of DOM scraping.
        """
        if "api/markets" in response.url or "api/events" in response.url:
            try:
                # We need the raw text to pass to the frame parser for archiving
                raw_payload = await response.text()
                logger.info(f"Intercepted API Payload from {response.url}")
                # Pass to parser layer
                events = frame_parser.parse_frame(raw_payload)
                self._cache_canonical_events(events)
            except Exception as e:
                pass

    async def _intercept_websocket(self, ws):
        """
        Intercept websocket connections to capture real-time odds streams.
        """
        logger.info(f"WebSocket connection opened: {ws.url}")
        
        ws.on("framesent", lambda payload: logger.debug(f"WS sent: {payload}"))
        ws.on("framereceived", lambda payload: asyncio.create_task(self._handle_ws_frame(payload)))

    async def _handle_ws_frame(self, payload):
        """
        Passes websocket frames directly to the canonical event parser.
        """
        if isinstance(payload, bytes):
            payload = payload.decode('utf-8', errors='ignore')
            
        events = frame_parser.parse_frame(payload)
        self._cache_canonical_events(events)

    def _cache_canonical_events(self, events: List[CanonicalOddsEvent]):
        """
        Stores canonical events in the in-memory cache for the Odds Monitor to poll.
        """
        for event in events:
            # We use the event's selection traits to build a unique cache key
            cache_key = f"{event.market_type}_{event.normalized_name}_{event.line}_{event.side}"
            
            # Update cache with dictionary representation for downstream
            self.odds_cache[cache_key] = {
                "fixture_id": event.fixture_id,
                "market": event.market_type,
                "player_name": event.player_name,
                "normalized_name": event.normalized_name,
                "line": event.line,
                "side": event.side,
                "decimal_odds": event.decimal_odds,
                "implied_probability": event.implied_probability,
                "market_status": event.status,
                "scraped_at": event.book_timestamp # Using book timestamp for true freshness
            }

    def get_latest_odds(self) -> List[Dict[str, Any]]:
        """
        Returns all valid odds currently in the cache, verifying staleness.
        """
        valid_odds = []
        now = datetime.now(timezone.utc)
        
        for key, odd in list(self.odds_cache.items()):
            scraped_at = datetime.fromisoformat(odd["scraped_at"])
            age_seconds = (now - scraped_at).total_seconds()
            
            if age_seconds > self.STALE_THRESHOLD_SECONDS:
                logger.warning(f"Stale odds detected for {key} (Age: {age_seconds}s). Marking suspended.")
                odd["market_status"] = MARKET_STATE["SUSPENDED"]
                
            valid_odds.append(odd)
            
        return valid_odds

    async def scrape_player_props(self, fixture_id: str, confirmed_starters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Navigates to the fixture page and triggers the XHR/WS interception.
        """
        if not self.page:
            await self.initialize()
            
        logger.info(f"Navigating to Betarabia event page for fixture {fixture_id}")
        
        # Example Navigation (URL would be dynamically resolved via fixture mapping)
        # await self.page.goto(f"https://www.betarabia.com/sports/football/event/{fixture_id}")
        
        # Wait a few seconds for XHR and Websocket payloads to populate the cache
        await asyncio.sleep(5)
        
        # Retrieve the latest parsed odds from the cache
        return self.get_latest_odds()

    async def close(self):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

betarabia_scraper = BetarabiaAPIClient()
