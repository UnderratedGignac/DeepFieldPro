"""
DeepField Orchestrator - Production Grade

Main entry point for the DeepField sportsbook acquisition system.
Coordinates all services and manages the complete data acquisition pipeline.

Features:
- Service orchestration and lifecycle management
- Graceful shutdown handling
- Health monitoring
- Metrics collection
- Automatic recovery
"""

import sys
import os

# Add root directory to pythonpath
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import logging
import signal
from typing import Dict, List, Optional
from datetime import datetime, timezone

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("data/deepfield_orchestrator.log"),
    ],
)
logger = logging.getLogger(__name__)


class DeepFieldOrchestrator:
    """
    Main orchestrator for the DeepField acquisition system.

    Coordinates:
    - Session manager and browser engine
    - WebSocket ingestors for each sportsbook
    - Database connections
    - Health monitoring
    - Metrics collection
    """

    def __init__(
        self,
        headless: bool = True,
        user_data_dir: str = "data/deepfield_browser_data",
        database_url: Optional[str] = None,
        sportsbooks: Optional[List[str]] = None,
    ):
        self.headless = headless
        self.user_data_dir = user_data_dir
        self.database_url = (
            database_url or "postgresql://deepfield:deepfield@localhost:5432/deepfield"
        )
        self.sportsbooks = sportsbooks or ["bet365", "pinnacle", "betfair"]

        # Services
        self.session_manager = None
        self.websocket_ingestors: Dict = {}
        self.database_session = None

        # State
        self._is_running = False
        self._shutdown_event = asyncio.Event()

        # Configuration
        self.health_check_interval = 30  # seconds
        self.metrics_interval = 60  # seconds

    async def start(self):
        """Start all services."""
        logger.info("Starting DeepField Orchestrator...")
        self._is_running = True

        try:
            # Initialize session manager
            await self._initialize_session_manager()

            # Initialize database
            await self._initialize_database()

            # Start WebSocket ingestors for each sportsbook
            await self._start_websocket_ingestors()

            # Start background tasks
            asyncio.create_task(self._health_monitor())
            asyncio.create_task(self._metrics_collector())

            logger.info("DeepField Orchestrator started successfully")

        except Exception as e:
            logger.error(f"Failed to start orchestrator: {e}")
            await self.stop()
            raise

    async def stop(self):
        """Stop all services gracefully."""
        logger.info("Stopping DeepField Orchestrator...")
        self._is_running = False
        self._shutdown_event.set()

        # Stop WebSocket ingestors
        for sportsbook, ingestor in self.websocket_ingestors.items():
            try:
                logger.info(f"Stopping WebSocket ingestor for {sportsbook}")
                await ingestor.stop()
            except Exception as e:
                logger.error(f"Error stopping {sportsbook} ingestor: {e}")

        # Stop session manager
        if self.session_manager:
            try:
                await self.session_manager.stop()
            except Exception as e:
                logger.error(f"Error stopping session manager: {e}")

        logger.info("DeepField Orchestrator stopped")

    async def _initialize_session_manager(self):
        """Initialize the session manager service."""
        from src.services.session_manager.service import SessionManager

        logger.info("Initializing session manager...")

        self.session_manager = SessionManager(
            headless=self.headless,
            user_data_dir=self.user_data_dir,
        )

        await self.session_manager.start()
        logger.info("Session manager initialized")

    async def _initialize_database(self):
        """Initialize database connection."""
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker

        logger.info("Initializing database connection...")

        try:
            engine = create_async_engine(
                self.database_url,
                echo=False,
                pool_size=10,
                max_overflow=20,
            )

            async_session = sessionmaker(
                engine, class_=AsyncSession, expire_on_commit=False
            )

            self.database_session = async_session
            logger.info("Database connection established")

        except Exception as e:
            logger.warning(f"Database initialization failed: {e}")
            logger.warning("Continuing without database connection")

    async def _start_websocket_ingestors(self):
        """Start WebSocket ingestors for configured sportsbooks."""
        from src.services.odds_acquisition.websocket_ingestor import WebSocketIngestor

        logger.info(
            f"Starting WebSocket ingestors for {len(self.sportsbooks)} sportsbooks..."
        )

        for sportsbook in self.sportsbooks:
            try:
                # Create session for this sportsbook
                session_id = f"ws_{sportsbook}"

                await self.session_manager.create_session(
                    session_id=session_id,
                    sportsbook=sportsbook,
                )

                # Create and start WebSocket ingestor
                ingestor = WebSocketIngestor(
                    sportsbook=sportsbook,
                    session_manager=self.session_manager,
                    persist_callback=self._persist_tick,
                )

                self.websocket_ingestors[sportsbook] = ingestor

                # Start ingestion (will connect when page loads)
                asyncio.create_task(ingestor.start(session_id))

                logger.info(f"Started WebSocket ingestor for {sportsbook}")

            except Exception as e:
                logger.error(f"Failed to start ingestor for {sportsbook}: {e}")

    async def _persist_tick(self, tick):
        """Persist an odds tick to the database."""
        if not self.database_session:
            return

        try:
            from src.database.models import OddsTick

            async with self.database_session() as session:
                db_tick = OddsTick(
                    tick_id=tick.tick_id,
                    fixture_id=tick.fixture_id,
                    sportsbook=tick.sportsbook,
                    market_type=tick.market_type,
                    outcome=tick.outcome,
                    odds_before=tick.odds_before,
                    odds_after=tick.odds_after,
                    timestamp=tick.timestamp,
                    sequence_number=tick.sequence_number,
                    metadata=tick.metadata,
                )

                session.add(db_tick)
                await session.commit()

        except Exception as e:
            logger.error(f"Failed to persist tick: {e}")

    async def _health_monitor(self):
        """Background task to monitor service health."""
        logger.info("Starting health monitor...")

        while self._is_running:
            try:
                await asyncio.sleep(self.health_check_interval)

                # Check session manager health
                if self.session_manager:
                    summary = self.session_manager.get_metrics_summary()

                    # Log unhealthy sessions
                    for session_id, info in summary.get("sessions", {}).items():
                        if info.get("health_score", 1.0) < 0.5:
                            logger.warning(
                                f"Session {session_id} health score low: "
                                f"{info.get('health_score')}"
                            )

                # Check WebSocket ingestor health
                for sportsbook, ingestor in self.websocket_ingestors.items():
                    if not ingestor.is_healthy():
                        metrics = ingestor.get_metrics()
                        logger.warning(
                            f"WebSocket ingestor for {sportsbook} unhealthy: "
                            f"state={metrics.get('state')}, "
                            f"messages={metrics.get('messages_received')}"
                        )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health monitor error: {e}")

    async def _metrics_collector(self):
        """Background task to collect and log metrics."""
        logger.info("Starting metrics collector...")

        while self._is_running:
            try:
                await asyncio.sleep(self.metrics_interval)

                # Collect metrics
                metrics = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "sessions": {},
                    "websocket": {},
                }

                if self.session_manager:
                    summary = self.session_manager.get_metrics_summary()
                    metrics["sessions"] = {
                        "total": summary.get("total_sessions", 0),
                        "healthy": sum(
                            1
                            for s in summary.get("sessions", {}).values()
                            if s.get("health_score", 0) > 0.7
                        ),
                    }

                for sportsbook, ingestor in self.websocket_ingestors.items():
                    ws_metrics = ingestor.get_metrics()
                    metrics["websocket"][sportsbook] = {
                        "connected": ws_metrics.get("is_connected", False),
                        "messages": ws_metrics.get("messages_received", 0),
                        "reconnects": ws_metrics.get("reconnect_count", 0),
                    }

                logger.info(f"Metrics: {metrics}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Metrics collector error: {e}")

    async def run_forever(self):
        """Run the orchestrator until shutdown signal."""
        logger.info("Running DeepField Orchestrator (press Ctrl+C to stop)...")

        # Wait for shutdown signal
        await self._shutdown_event.wait()

    def request_shutdown(self):
        """Request graceful shutdown."""
        logger.info("Shutdown requested")
        self._shutdown_event.set()


async def main():
    """Main entry point."""
    orchestrator = DeepFieldOrchestrator(
        headless=True,
        sportsbooks=["bet365", "pinnacle", "betfair"],
    )

    # Setup signal handlers
    loop = asyncio.get_event_loop()

    def signal_handler(sig):
        logger.info(f"Received signal {sig}")
        orchestrator.request_shutdown()

    import sys

    if sys.platform != "win32":
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda s=sig: signal_handler(s))

    try:
        await orchestrator.start()
        await orchestrator.run_forever()
    finally:
        await orchestrator.stop()


if __name__ == "__main__":
    asyncio.run(main())
