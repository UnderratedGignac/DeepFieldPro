# mypy: ignore-errors
"""
WebSocket Ingestion Service - Production Grade

Handles live WebSocket connections to sportsbooks for real-time odds updates.
Implements automatic reconnection, stream health monitoring, and tick persistence.

Features:
- WebSocket frame interception and decoding
- Automatic reconnection with exponential backoff
- Stream staleness detection
- Market movement tracking
- Immutable odds tick storage
"""

import asyncio
import json
import logging
from typing import Optional, Dict, List, Any, Callable
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
import hashlib

from playwright.async_api import Page, WebSocket

logger = logging.getLogger(__name__)


class WebSocketState(Enum):
    """WebSocket connection states."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"


@dataclass
class WebSocketMetrics:
    """Metrics for WebSocket connection health."""

    connect_time: Optional[datetime] = None
    last_message_time: Optional[datetime] = None
    messages_received: int = 0
    reconnect_count: int = 0
    consecutive_failures: int = 0
    avg_latency_ms: float = 0.0
    total_bytes_received: int = 0


@dataclass
class OddsTick:
    """Immutable odds tick record."""

    tick_id: str
    fixture_id: str
    sportsbook: str
    market_type: str
    outcome: str
    odds_before: float
    odds_after: float
    timestamp: datetime
    sequence_number: int
    metadata: Dict[str, Any] = field(default_factory=dict)


class WebSocketIngestor:
    """
    Production-grade WebSocket ingestion for live odds streams.

    Handles:
    - WebSocket connection management
    - Frame interception and parsing
    - Automatic reconnection
    - Stream health monitoring
    - Tick buffering and persistence
    """

    # Configuration
    RECONNECT_BASE_DELAY_MS = 1000
    RECONNECT_MAX_DELAY_MS = 60000
    STALE_STREAM_THRESHOLD_SECONDS = 30
    MAX_BUFFER_SIZE = 1000

    def __init__(
        self,
        sportsbook: str,
        session_manager=None,
        persist_callback: Optional[Callable] = None,
    ):
        self.sportsbook = sportsbook
        self.session_manager = session_manager
        self.persist_callback = persist_callback

        self._state = WebSocketState.DISCONNECTED
        self._metrics = WebSocketMetrics()
        self._websocket: Optional[WebSocket] = None
        self._page: Optional[Page] = None
        self._session_id: Optional[str] = None

        self._message_handlers: List[Callable] = []
        self._tick_buffer: List[OddsTick] = []
        self._sequence_numbers: Dict[str, int] = {}  # Per-market sequence tracking

        self._reconnect_task: Optional[asyncio.Task] = None
        self._health_check_task: Optional[asyncio.Task] = None
        self._is_running = False

        # Reconnection state
        self._last_reconnect_attempt: Optional[datetime] = None
        self._reconnect_delay_ms = self.RECONNECT_BASE_DELAY_MS

    async def start(self, session_id: str, ws_url: Optional[str] = None) -> None:
        """
        Start WebSocket ingestion.

        Args:
            session_id: Session to use for WebSocket connection
            ws_url: Optional WebSocket URL override
        """
        if self._is_running:
            logger.warning("WebSocket ingestor already running")
            return

        self._session_id = session_id
        self._is_running = True
        self._state = WebSocketState.CONNECTING

        logger.info(f"Starting WebSocket ingestor for {self.sportsbook}")

        # Get or create page
        if self.session_manager:
            self._page = await self.session_manager.engine.new_page(session_id)

            # Setup WebSocket interception
            await self._setup_websocket_interception(ws_url)

            # Navigate to trigger WebSocket connection
            await self._navigate_to_streaming_page()
        else:
            # Direct WebSocket connection (fallback)
            await self._connect_direct(ws_url)

        # Start background tasks
        self._health_check_task = asyncio.create_task(self._run_health_checks())

        logger.info(f"WebSocket ingestor started for {self.sportsbook}")

    async def stop(self) -> None:
        """Stop WebSocket ingestion gracefully."""
        self._is_running = False

        # Cancel background tasks
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass

        if self._reconnect_task:
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass

        # Flush buffer before closing
        await self._flush_tick_buffer()

        # Close WebSocket
        if self._websocket:
            try:
                await self._websocket.disconnect()
            except Exception:
                pass

        # Close page
        if self._page:
            try:
                await self._page.close()
            except Exception:
                pass

        self._state = WebSocketState.DISCONNECTED
        logger.info(f"WebSocket ingestor stopped for {self.sportsbook}")

    async def _setup_websocket_interception(self, ws_url: Optional[str] = None) -> None:
        """Setup WebSocket frame interception."""
        if not self._page:
            return

        @self._page.on("websocket")
        async def handle_websocket(websocket: WebSocket):
            logger.info(f"WebSocket opened: {websocket.url}")

            # Filter by URL if specified
            if ws_url and ws_url not in websocket.url:
                logger.debug(f"Skipping WebSocket: {websocket.url}")
                return

            self._websocket = websocket
            self._state = WebSocketState.CONNECTED
            self._metrics.connect_time = datetime.utcnow()
            self._metrics.reconnect_count += 1

            # Register message handler
            websocket.on("framereceived", lambda frame: self._handle_frame(frame))
            websocket.on("close", lambda: self._handle_close())

        logger.debug("WebSocket interception configured")

    async def _navigate_to_streaming_page(self) -> None:
        """Navigate to page that establishes WebSocket connection."""
        if not self._page:
            return

        # Sportsbook-specific streaming pages
        streaming_pages = {
            "bet365": "https://www.bet365.com/#/IP/",
            "pinnacle": "https://www.pinnacle.com/en/live",
            "betfair": "https://www.betfair.com/exchange/plus/football",
        }

        url = streaming_pages.get(self.sportsbook, "https://example.com")

        try:
            await self._page.goto(url, wait_until="networkidle", timeout=30000)
            logger.info(f"Navigated to {url} for WebSocket streaming")
        except Exception as e:
            logger.error(f"Navigation failed: {e}")

    async def _connect_direct(self, ws_url: Optional[str] = None) -> None:
        """Direct WebSocket connection (if browser interception not available)."""
        if not ws_url:
            logger.error("No WebSocket URL provided for direct connection")
            self._state = WebSocketState.FAILED
            return

        logger.warning(
            "Direct WebSocket connection not fully implemented - use browser interception"
        )

    def _handle_frame(self, frame_data: Any) -> None:
        """Handle incoming WebSocket frame."""
        try:
            self._metrics.messages_received += 1
            self._metrics.last_message_time = datetime.utcnow()

            # Parse frame data
            payload = frame_data
            if isinstance(frame_data, bytes):
                payload = frame_data.decode("utf-8")

            # Try to parse as JSON
            try:
                message = json.loads(payload)
            except json.JSONDecodeError:
                message = {"raw": payload}

            # Process message
            asyncio.create_task(self._process_message(message))

            # Call registered handlers
            for handler in self._message_handlers:
                try:
                    handler(message)
                except Exception as e:
                    logger.error(f"Message handler error: {e}")

        except Exception as e:
            logger.error(f"Frame handling error: {e}")

    def _handle_close(self) -> None:
        """Handle WebSocket close event."""
        logger.warning(f"WebSocket closed for {self.sportsbook}")
        self._state = WebSocketState.DISCONNECTED

        # Trigger reconnection
        if self._is_running:
            self._schedule_reconnect()

    async def _process_message(self, message: Dict) -> None:
        """Process incoming WebSocket message and extract odds ticks."""
        try:
            # Extract odds data from message
            # This is sportsbook-specific - implement per-sportsbook parsers
            ticks = await self._parse_odds_message(message)

            for tick in ticks:
                await self._process_tick(tick)

        except Exception as e:
            logger.error(f"Message processing error: {e}")

    async def _parse_odds_message(self, message: Dict) -> List[OddsTick]:
        """
        Parse odds data from WebSocket message.

        This is a template - override for specific sportsbooks.
        """
        ticks = []

        try:
            # Generic parser - actual implementation needs sportsbook-specific logic
            # Look for common patterns in odds messages

            # Pattern 1: Direct odds update
            if "odds" in message:
                odds_data = message["odds"]
                tick = await self._create_tick_from_odds(odds_data, message)
                if tick:
                    ticks.append(tick)

            # Pattern 2: Market update
            elif "market" in message or "markets" in message:
                markets = message.get("markets", [message.get("market")])
                for market in markets:
                    tick = await self._create_tick_from_market(market, message)
                    if tick:
                        ticks.append(tick)

            # Pattern 3: Event stream
            elif "event" in message and message.get("type") == "odds_update":
                event_data = message.get("data", {})
                tick = await self._create_tick_from_odds(event_data, message)
                if tick:
                    ticks.append(tick)

        except Exception as e:
            logger.debug(f"Failed to parse message: {e}")

        return ticks

    async def _create_tick_from_odds(
        self, odds_data: Dict, context: Dict
    ) -> Optional[OddsTick]:
        """Create odds tick from odds data."""
        try:
            fixture_id = odds_data.get("fixture_id") or context.get(
                "fixture_id", "unknown"
            )
            market_type = odds_data.get("market_type", "unknown")
            outcome = odds_data.get("outcome", "unknown")
            odds_after = float(odds_data.get("odds", 0))

            # Get previous odds
            key = f"{fixture_id}:{market_type}:{outcome}"
            odds_before = self._get_previous_odds(key)

            # Generate sequence number
            seq_num = self._get_next_sequence(key)

            # Generate tick ID
            tick_id = self._generate_tick_id(fixture_id, market_type, seq_num)

            tick = OddsTick(
                tick_id=tick_id,
                fixture_id=fixture_id,
                sportsbook=self.sportsbook,
                market_type=market_type,
                outcome=outcome,
                odds_before=odds_before,
                odds_after=odds_after,
                timestamp=datetime.utcnow(),
                sequence_number=seq_num,
                metadata=context,
            )

            return tick

        except Exception as e:
            logger.error(f"Tick creation error: {e}")
            return None

    async def _create_tick_from_market(
        self, market_data: Dict, context: Dict
    ) -> Optional[OddsTick]:
        """Create odds tick from market data."""
        # Similar to _create_tick_from_odds but handles market structures
        return await self._create_tick_from_odds(market_data, context)

    def _get_previous_odds(self, key: str) -> float:
        """Get previous odds for a market/outcome."""
        if self._tick_buffer:
            for tick in reversed(self._tick_buffer):
                tick_key = f"{tick.fixture_id}:{tick.market_type}:{tick.outcome}"
                if tick_key == key:
                    return tick.odds_after
        return 0.0

    def _get_next_sequence(self, key: str) -> int:
        """Get next sequence number for a market."""
        if key not in self._sequence_numbers:
            self._sequence_numbers[key] = 0
        self._sequence_numbers[key] += 1
        return self._sequence_numbers[key]

    def _generate_tick_id(self, fixture_id: str, market_type: str, seq_num: int) -> str:
        """Generate unique tick ID."""
        data = f"{self.sportsbook}:{fixture_id}:{market_type}:{seq_num}:{datetime.utcnow().isoformat()}"
        return hashlib.sha256(data.encode()).hexdigest()[:32]

    async def _process_tick(self, tick: OddsTick) -> None:
        """Process and buffer an odds tick."""
        # Add to buffer
        self._tick_buffer.append(tick)

        # Detect line movement
        if tick.odds_before != tick.odds_after:
            logger.debug(
                f"Line movement: {tick.fixture_id} {tick.market_type} "
                f"{tick.outcome}: {tick.odds_before} -> {tick.odds_after}"
            )

        # Flush if buffer is full
        if len(self._tick_buffer) >= self.MAX_BUFFER_SIZE:
            await self._flush_tick_buffer()

        # Persist immediately via callback
        if self.persist_callback:
            try:
                await self.persist_callback(tick)
            except Exception as e:
                logger.error(f"Persist callback error: {e}")

    async def _flush_tick_buffer(self) -> None:
        """Flush tick buffer to persistent storage."""
        if not self._tick_buffer:
            return

        ticks_to_flush = self._tick_buffer.copy()
        self._tick_buffer.clear()

        logger.debug(f"Flushing {len(ticks_to_flush)} ticks to storage")

        # Persist callback will handle storage
        if self.persist_callback:
            for tick in ticks_to_flush:
                try:
                    await self.persist_callback(tick)
                except Exception as e:
                    logger.error(f"Tick persist error: {e}")

    def _schedule_reconnect(self) -> None:
        """Schedule reconnection with exponential backoff."""
        if self._reconnect_task and not self._reconnect_task.done():
            return

        self._state = WebSocketState.RECONNECTING
        self._reconnect_task = asyncio.create_task(self._reconnect_loop())

    async def _reconnect_loop(self) -> None:
        """Reconnection loop with exponential backoff."""
        while self._is_running and self._state != WebSocketState.CONNECTED:
            try:
                now = datetime.utcnow()

                # Check if enough time has passed since last attempt
                if self._last_reconnect_attempt:
                    elapsed_ms = (
                        now - self._last_reconnect_attempt
                    ).total_seconds() * 1000
                    if elapsed_ms < self._reconnect_delay_ms:
                        await asyncio.sleep(
                            (self._reconnect_delay_ms - elapsed_ms) / 1000
                        )

                self._last_reconnect_attempt = now

                logger.info(
                    f"Attempting reconnection to {self.sportsbook} "
                    f"(attempt {self._metrics.reconnect_count + 1}, "
                    f"delay {self._reconnect_delay_ms}ms)"
                )

                # Attempt reconnection
                if self.session_manager and self._session_id:
                    self._page = await self.session_manager.engine.new_page(
                        self._session_id
                    )
                    await self._setup_websocket_interception()
                    await self._navigate_to_streaming_page()

                if self._state == WebSocketState.CONNECTED:
                    # Success - reset backoff
                    self._reconnect_delay_ms = self.RECONNECT_BASE_DELAY_MS
                    self._metrics.consecutive_failures = 0
                    logger.info("Reconnection successful")
                    return
                else:
                    # Failed - increase backoff
                    self._metrics.consecutive_failures += 1
                    self._reconnect_delay_ms = min(
                        self._reconnect_delay_ms * 2, self.RECONNECT_MAX_DELAY_MS
                    )

            except Exception as e:
                logger.error(f"Reconnection error: {e}")
                self._metrics.consecutive_failures += 1
                self._reconnect_delay_ms = min(
                    self._reconnect_delay_ms * 2, self.RECONNECT_MAX_DELAY_MS
                )

    async def _run_health_checks(self) -> None:
        """Background health check task."""
        while self._is_running:
            try:
                await asyncio.sleep(10)  # Check every 10 seconds
                await self._check_stream_health()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check error: {e}")

    async def _check_stream_health(self) -> None:
        """Check if stream is stale."""
        if self._state != WebSocketState.CONNECTED:
            return

        if not self._metrics.last_message_time:
            return

        elapsed = (datetime.utcnow() - self._metrics.last_message_time).total_seconds()

        if elapsed > self.STALE_STREAM_THRESHOLD_SECONDS:
            logger.warning(
                f"Stream stale for {self.sportsbook} - "
                f"no messages for {elapsed:.1f}s"
            )

            # Disconnect to trigger reconnection
            if self._websocket:
                try:
                    await self._websocket.disconnect()
                except Exception:
                    pass

    def register_message_handler(self, handler: Callable) -> None:
        """Register a message handler callback."""
        self._message_handlers.append(handler)

    def get_metrics(self) -> Dict[str, Any]:
        """Get WebSocket metrics."""
        return {
            "sportsbook": self.sportsbook,
            "state": self._state.value,
            "is_connected": self._state == WebSocketState.CONNECTED,
            "messages_received": self._metrics.messages_received,
            "reconnect_count": self._metrics.reconnect_count,
            "consecutive_failures": self._metrics.consecutive_failures,
            "buffer_size": len(self._tick_buffer),
            "last_message_ago_seconds": (
                (datetime.utcnow() - self._metrics.last_message_time).total_seconds()
                if self._metrics.last_message_time
                else None
            ),
        }

    def is_healthy(self) -> bool:
        """Check if WebSocket connection is healthy."""
        if self._state != WebSocketState.CONNECTED:
            return False

        if not self._metrics.last_message_time:
            return True  # Just connected, no messages yet

        elapsed = (datetime.utcnow() - self._metrics.last_message_time).total_seconds()
        return elapsed < self.STALE_STREAM_THRESHOLD_SECONDS

