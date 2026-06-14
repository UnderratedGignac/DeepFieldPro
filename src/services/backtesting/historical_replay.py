# mypy: ignore-errors
"""
Historical Market Replay Engine

Replays historical odds ticks chronologically to reconstruct market state
at any point in time. Supports accelerated replay, deterministic mode,
and event-driven architecture.
"""

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Callable, Dict, List, Optional, Any
from dataclasses import dataclass, field
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from database.models import OddsTick, LineMovement

logger = logging.getLogger(__name__)


class ReplayMode(Enum):
    """Replay execution modes."""

    REAL_TIME = "real_time"
    ACCELERATED = "accelerated"
    DETERMINISTIC = "deterministic"
    MAX_SPEED = "max_speed"


class MarketEventType(Enum):
    """Types of market events during replay."""

    ODDS_UPDATE = "odds_update"
    LINE_MOVEMENT = "line_movement"
    MARKET_OPEN = "market_open"
    MARKET_CLOSE = "market_close"
    SUSPENSION = "suspension"
    RESUMPTION = "resumption"


@dataclass
class MarketEvent:
    """Represents a market event during replay."""

    event_type: MarketEventType
    timestamp: datetime
    market_id: str
    sportsbook_id: str
    data: Dict[str, Any] = field(default_factory=dict)
    sequence: int = 0


@dataclass
class ReplayState:
    """Current state of the replay engine."""

    is_running: bool = False
    current_timestamp: Optional[datetime] = None
    start_timestamp: Optional[datetime] = None
    end_timestamp: Optional[datetime] = None
    speed_multiplier: float = 1.0
    events_processed: int = 0
    markets_active: int = 0
    paused: bool = False


class ReplayClock:
    """
    Virtual clock for controlling replay time.

    Supports real-time, accelerated, and deterministic time progression.
    """

    def __init__(
        self,
        start_time: datetime,
        end_time: datetime,
        speed_multiplier: float = 1.0,
        mode: ReplayMode = ReplayMode.REAL_TIME,
    ):
        self.start_time = start_time
        self.end_time = end_time
        self.speed_multiplier = max(0.1, speed_multiplier)
        self.mode = mode
        self.current_time = start_time
        self._paused = False
        self._pause_start: Optional[datetime] = None
        self._real_start: Optional[datetime] = None

    def pause(self) -> None:
        """Pause the replay clock."""
        if not self._paused:
            self._paused = True
            self._pause_start = datetime.timezone.utcnow()
            logger.info(f"Replay clock paused at {self.current_time}")

    def resume(self) -> None:
        """Resume the replay clock."""
        if self._paused and self._pause_start:
            pause_duration = datetime.timezone.utcnow() - self._pause_start
            if self.mode == ReplayMode.REAL_TIME:
                self._real_start = (
                    self._real_start or datetime.timezone.utcnow()
                ) + pause_duration
            self._paused = False
            self._pause_start = None
            logger.info(f"Replay clock resumed at {self.current_time}")

    def advance(self, delta: timedelta) -> datetime:
        """Advance clock by specified delta."""
        self.current_time += delta
        if self.current_time > self.end_time:
            self.current_time = self.end_time
        return self.current_time

    def get_current_time(self) -> datetime:
        """Get current replay time."""
        if self._paused:
            return self.current_time

        if self.mode == ReplayMode.DETERMINISTIC:
            return self.current_time

        if self.mode == ReplayMode.MAX_SPEED:
            return self.end_time

        # Real-time or accelerated mode
        if self._real_start is None:
            self._real_start = datetime.timezone.utcnow()

        elapsed_real = datetime.timezone.utcnow() - self._real_start
        elapsed_replay = elapsed_real * self.speed_multiplier
        self.current_time = min(self.start_time + elapsed_replay, self.end_time)

        return self.current_time

    def is_finished(self) -> bool:
        """Check if replay has reached end time."""
        return self.current_time >= self.end_time

    def progress(self) -> float:
        """Get replay progress as percentage (0.0-1.0)."""
        total_duration = (self.end_time - self.start_time).total_seconds()
        if total_duration <= 0:
            return 1.0
        elapsed = (self.current_time - self.start_time).total_seconds()
        return min(1.0, max(0.0, elapsed / total_duration))


class EventScheduler:
    """
    Event-driven scheduler for replay engine.

    Manages event queue, scheduling, and dispatch.
    """

    def __init__(self):
        self._event_queue: List[MarketEvent] = []
        self._subscribers: Dict[MarketEventType, List[Callable]] = {}
        self._sequence_counter = 0

    def subscribe(
        self, event_type: MarketEventType, callback: Callable[[MarketEvent], Any]
    ) -> None:
        """Subscribe to specific event type."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)
        logger.debug(f"Subscribed to {event_type.value}")

    def unsubscribe(
        self, event_type: MarketEventType, callback: Callable[[MarketEvent], Any]
    ) -> None:
        """Unsubscribe from event type."""
        if event_type in self._subscribers:
            self._subscribers[event_type].remove(callback)

    def schedule_event(self, event: MarketEvent) -> None:
        """Schedule an event for processing."""
        event.sequence = self._sequence_counter
        self._sequence_counter += 1
        self._event_queue.append(event)
        self._event_queue.sort(key=lambda e: e.timestamp)

    def schedule_events(self, events: List[MarketEvent]) -> None:
        """Schedule multiple events."""
        for event in events:
            self.schedule_event(event)

    async def dispatch_next(self) -> Optional[MarketEvent]:
        """Dispatch next event in queue."""
        if not self._event_queue:
            return None

        event = self._event_queue.pop(0)
        await self._dispatch_event(event)
        return event

    async def dispatch_until(self, target_time: datetime) -> int:
        """Dispatch all events until target time."""
        dispatched = 0
        while self._event_queue and self._event_queue[0].timestamp <= target_time:
            await self.dispatch_next()
            dispatched += 1
        return dispatched

    async def _dispatch_event(self, event: MarketEvent) -> None:
        """Dispatch event to all subscribers."""
        callbacks = self._subscribers.get(event.event_type, [])

        # Also dispatch to wildcard subscribers
        if "*" in self._subscribers:
            callbacks = callbacks + self._subscribers["*"]

        for callback in callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event)
                else:
                    callback(event)
            except Exception as e:
                logger.error(f"Error in event callback for {event.event_type}: {e}")

    def clear(self) -> None:
        """Clear all scheduled events."""
        self._event_queue.clear()
        logger.debug("Event queue cleared")

    def pending_count(self) -> int:
        """Get number of pending events."""
        return len(self._event_queue)


class HistoricalReplayEngine:
    """
    Main historical market replay engine.

    Reconstructs historical market conditions from immutable odds ticks,
    enabling realistic backtesting and market analysis.
    """

    def __init__(
        self,
        db_session: AsyncSession,
        start_time: datetime,
        end_time: datetime,
        speed_multiplier: float = 1.0,
        mode: ReplayMode = ReplayMode.REAL_TIME,
    ):
        self.db_session = db_session
        self.clock = ReplayClock(start_time, end_time, speed_multiplier, mode)
        self.scheduler = EventScheduler()
        self.state = ReplayState(
            start_timestamp=start_time,
            end_timestamp=end_time,
            speed_multiplier=speed_multiplier,
        )

        self._market_states: Dict[str, Dict[str, Any]] = {}
        self._running = False
        self._pause_event = asyncio.Event()
        self._pause_event.set()

        # Subscribe to internal events
        self.scheduler.subscribe(MarketEventType.ODDS_UPDATE, self._on_odds_update)
        self.scheduler.subscribe(MarketEventType.LINE_MOVEMENT, self._on_line_movement)

    async def initialize(self) -> None:
        """Initialize replay engine by loading historical data."""
        logger.info(
            f"Initializing replay: {self.clock.start_time} to {self.clock.end_time} "
            f"(speed: {self.clock.speed_multiplier}x)"
        )

        # Load odds ticks for the replay period
        await self._load_historical_data()

        self.state.is_running = True
        logger.info("Replay engine initialized")

    async def _load_historical_data(self) -> None:
        """Load historical odds ticks and schedule events."""
        logger.info("Loading historical odds ticks...")

        # Query odds ticks in batches
        batch_size = 1000
        offset = 0

        while True:
            stmt = (
                select(OddsTick)
                .where(
                    and_(
                        OddsTick.timestamp >= self.clock.start_time,
                        OddsTick.timestamp <= self.clock.end_time,
                    )
                )
                .order_by(OddsTick.timestamp)
                .limit(batch_size)
                .offset(offset)
            )

            result = await self.db_session.execute(stmt)
            ticks = result.scalars().all()

            if not ticks:
                break

            # Convert ticks to events
            events = []
            for tick in ticks:
                event = MarketEvent(
                    event_type=MarketEventType.ODDS_UPDATE,
                    timestamp=tick.timestamp,
                    market_id=tick.market_id,
                    sportsbook_id=tick.sportsbook_id,
                    data={
                        "outcome": tick.outcome,
                        "odds_decimal": float(tick.odds_decimal),
                        "odds_american": tick.odds_american,
                        "probability": float(tick.implied_probability),
                        "volume": tick.volume,
                    },
                )
                events.append(event)

            self.scheduler.schedule_events(events)
            offset += batch_size

            logger.debug(f"Loaded {offset} ticks")

            # Small delay to prevent DB overload
            await asyncio.sleep(0.01)

        # Load and schedule line movements
        await self._load_line_movements()

        logger.info(f"Loaded {self.scheduler.pending_count()} events for replay")

    async def _load_line_movements(self) -> None:
        """Load significant line movements."""
        stmt = (
            select(LineMovement)
            .where(
                and_(
                    LineMovement.start_time >= self.clock.start_time,
                    LineMovement.start_time <= self.clock.end_time,
                )
            )
            .order_by(LineMovement.start_time)
        )

        result = await self.db_session.execute(stmt)
        movements = result.scalars().all()

        events = []
        for movement in movements:
            event = MarketEvent(
                event_type=MarketEventType.LINE_MOVEMENT,
                timestamp=movement.start_time,
                market_id=movement.market_id,
                sportsbook_id=movement.sportsbook_id,
                data={
                    "movement_id": str(movement.id),
                    "start_odds": float(movement.start_odds),
                    "end_odds": float(movement.end_odds),
                    "change_pct": float(movement.percentage_change),
                    "velocity": (
                        movement.velocity if hasattr(movement, "velocity") else 0.0
                    ),
                },
            )
            events.append(event)

        self.scheduler.schedule_events(events)

    async def run(self) -> None:
        """Run the replay engine."""
        if not self.state.is_running:
            raise RuntimeError("Replay engine not initialized")

        logger.info("Starting replay engine")
        self._running = True

        try:
            while self._running and not self.clock.is_finished():
                # Wait if paused
                await self._pause_event.wait()

                # Advance clock
                current_time = self.clock.get_current_time()
                self.state.current_timestamp = current_time

                # Dispatch events up to current time
                dispatched = await self.scheduler.dispatch_until(current_time)
                self.state.events_processed += dispatched

                # Update active markets count
                self.state.markets_active = len(self._market_states)

                # Calculate sleep duration based on mode
                if self.clock.mode == ReplayMode.MAX_SPEED:
                    sleep_ms = 0
                elif self.clock.mode == ReplayMode.DETERMINISTIC:
                    sleep_ms = 0
                else:
                    # Sleep based on speed multiplier
                    base_sleep = 0.01  # 10ms base
                    sleep_ms = base_sleep / self.clock.speed_multiplier

                if sleep_ms > 0:
                    await asyncio.sleep(sleep_ms)

            logger.info(
                f"Replay completed: {self.state.events_processed} events processed"
            )

        except asyncio.CancelledError:
            logger.info("Replay engine cancelled")
        finally:
            self._running = False
            self.state.is_running = False

    async def stop(self) -> None:
        """Stop the replay engine."""
        logger.info("Stopping replay engine")
        self._running = False
        self._pause_event.set()  # Ensure we're not stuck waiting

    def pause(self) -> None:
        """Pause replay."""
        self.clock.pause()
        self._pause_event.clear()
        self.state.paused = True

    def resume(self) -> None:
        """Resume replay."""
        self.clock.resume()
        self._pause_event.set()
        self.state.paused = False

    def set_speed(self, multiplier: float) -> None:
        """Change replay speed multiplier."""
        self.clock.speed_multiplier = max(0.1, multiplier)
        self.state.speed_multiplier = self.clock.speed_multiplier
        logger.info(f"Replay speed changed to {self.state.speed_multiplier}x")

    def get_market_state(self, market_id: str) -> Optional[Dict[str, Any]]:
        """Get current state of a specific market."""
        return self._market_states.get(market_id)

    def get_all_market_states(self) -> Dict[str, Dict[str, Any]]:
        """Get states of all active markets."""
        return self._market_states.copy()

    async def _on_odds_update(self, event: MarketEvent) -> None:
        """Handle odds update event."""
        market_key = f"{event.market_id}:{event.sportsbook_id}"

        if market_key not in self._market_states:
            self._market_states[market_key] = {
                "market_id": event.market_id,
                "sportsbook_id": event.sportsbook_id,
                "last_update": None,
                "outcomes": {},
                "update_count": 0,
            }

        state = self._market_states[market_key]
        state["last_update"] = event.timestamp
        state["outcomes"][event.data["outcome"]] = {
            "odds_decimal": event.data["odds_decimal"],
            "odds_american": event.data["odds_american"],
            "probability": event.data["probability"],
            "volume": event.data.get("volume"),
        }
        state["update_count"] += 1

    async def _on_line_movement(self, event: MarketEvent) -> None:
        """Handle line movement event."""
        logger.debug(
            f"Line movement detected: {event.market_id} "
            f"({event.data['start_odds']} -> {event.data['end_odds']}, "
            f"{event.data['change_pct']:.2f}%)"
        )

    def get_statistics(self) -> Dict[str, Any]:
        """Get replay statistics."""
        return {
            "is_running": self.state.is_running,
            "paused": self.state.paused,
            "current_timestamp": (
                self.state.current_timestamp.isoformat()
                if self.state.current_timestamp
                else None
            ),
            "start_timestamp": (
                self.state.start_timestamp.isoformat()
                if self.state.start_timestamp
                else None
            ),
            "end_timestamp": (
                self.state.end_timestamp.isoformat()
                if self.state.end_timestamp
                else None
            ),
            "speed_multiplier": self.state.speed_multiplier,
            "events_processed": self.state.events_processed,
            "markets_active": self.state.markets_active,
            "progress_pct": round(self.clock.progress() * 100, 2),
            "pending_events": self.scheduler.pending_count(),
        }


class MarketSimulator:
    """
    Market state simulator for replay engine.

    Maintains realistic market conditions including:
    - Bid/ask spreads
    - Market depth
    - Liquidity constraints
    - Suspension periods
    """

    def __init__(self):
        self._markets: Dict[str, MarketState] = {}
        self._suspensions: Dict[str, datetime] = {}

    def get_or_create_market(self, market_id: str, sportsbook_id: str) -> "MarketState":
        """Get or create market state."""
        key = f"{market_id}:{sportsbook_id}"
        if key not in self._markets:
            self._markets[key] = MarketState(market_id, sportsbook_id)
        return self._markets[key]

    def suspend_market(
        self, market_id: str, sportsbook_id: str, until: datetime
    ) -> None:
        """Suspend a market."""
        key = f"{market_id}:{sportsbook_id}"
        self._suspensions[key] = until
        if key in self._markets:
            self._markets[key].suspended = True

    def is_market_available(self, market_id: str, sportsbook_id: str) -> bool:
        """Check if market is available for betting."""
        key = f"{market_id}:{sportsbook_id}"

        if key in self._suspensions:
            if datetime.timezone.utcnow() < self._suspensions[key]:
                return False
            del self._suspensions[key]

        if key in self._markets:
            return not self._markets[key].suspended

        return True

    def get_best_odds(
        self, market_id: str, outcome: str
    ) -> Optional[tuple[str, Decimal]]:
        """Get best available odds across all sportsbooks."""
        best_book = None
        best_odds = Decimal(0)

        for key, market in self._markets.items():
            if not key.startswith(f"{market_id}:"):
                continue
            if market.suspended:
                continue

            if outcome in market.outcomes:
                odds = market.outcomes[outcome]["odds_decimal"]
                if odds > best_odds:
                    best_odds = odds
                    best_book = market.sportsbook_id

        if best_book:
            return (best_book, best_odds)
        return None


@dataclass
class MarketState:
    """State of a single market in simulation."""

    market_id: str
    sportsbook_id: str
    outcomes: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    suspended: bool = False
    last_update: Optional[datetime] = None
    update_count: int = 0
    spread: Decimal = Decimal("0.05")  # Default 5% margin
    liquidity: float = 1.0  # 0.0-1.0 scale
