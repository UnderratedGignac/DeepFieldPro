# mypy: ignore-errors
"""
Database Models - Production Grade

SQLAlchemy models for the DeepField betting system with support for:
- Immutable odds tick storage
- WebSocket event tracking
- Session health monitoring
- Line movement history
- TimescaleDB-compatible patterns
"""

from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    DateTime,
    Boolean,
    Text,
    JSON,
    ForeignKey,
    Index,
    BigInteger,
    Numeric,
)
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


class Fixture(Base):
    """Football fixture/match model."""

    __tablename__ = "fixtures"

    id = Column(Integer, primary_key=True)
    api_id = Column(String, unique=True, nullable=False)  # External API ID
    home_team = Column(String, nullable=False)
    away_team = Column(String, nullable=False)
    league = Column(String, nullable=False)
    country = Column(String, nullable=False)
    kickoff_time = Column(DateTime, nullable=False)
    status = Column(String, default="scheduled")  # scheduled, live, finished, cancelled

    home_score = Column(Integer, nullable=True)
    away_score = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    odds_ticks = relationship("OddsTick", back_populates="fixture", lazy="dynamic")
    odds_snapshots = relationship(
        "OddsSnapshot", back_populates="fixture", lazy="dynamic"
    )
    predictions = relationship("Prediction", back_populates="fixture", lazy="dynamic")
    bets = relationship("Bet", back_populates="fixture", lazy="dynamic")

    __table_args__ = (
        Index("idx_kickoff_time", "kickoff_time"),
        Index("idx_status", "status"),
        Index("idx_league_country", "league", "country"),
    )

    def __repr__(self):
        return f"<Fixture {self.home_team} vs {self.away_team}>"


class OddsTick(Base):
    """
    Immutable odds tick - every odds change is recorded.

    This table grows continuously and should be partitioned by time
    in production (TimescaleDB hypertable or native PostgreSQL partitioning).
    """

    __tablename__ = "odds_ticks"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    tick_id = Column(String(64), unique=True, nullable=False, index=True)  # SHA256 hash

    # Foreign keys
    fixture_id = Column(Integer, ForeignKey("fixtures.id"), nullable=False, index=True)

    # Source identification
    sportsbook = Column(String, nullable=False, index=True)

    # Market identification
    market_type = Column(String, nullable=False, index=True)  # 1x2, over_under, etc.
    outcome = Column(String, nullable=False)  # home, draw, away, over, under, etc.

    # Odds values
    odds_before = Column(Numeric(10, 5), nullable=True)  # Previous odds
    odds_after = Column(Numeric(10, 5), nullable=False)  # New odds

    # Sequence tracking for ordering
    sequence_number = Column(Integer, nullable=False)

    # Timestamps
    timestamp = Column(DateTime, nullable=False, index=True)
    ingested_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Additional metadata (renamed from 'metadata' which is reserved)\n    extra_data = Column(JSON, nullable=True)

    # Relationships
    fixture = relationship("Fixture", back_populates="odds_ticks")

    __table_args__ = (
        Index("idx_fixture_sportsbook_time", "fixture_id", "sportsbook", "timestamp"),
        Index("idx_market_time", "market_type", "timestamp"),
        Index("idx_sportsbook_time", "sportsbook", "timestamp"),
    )

    def __repr__(self):
        return f"<OddsTick {self.sportsbook} {self.market_type} {self.outcome} @ {self.odds_after}>"


class OddsSnapshot(Base):
    """
    Periodic snapshot of all odds for a fixture.

    Captured at regular intervals (e.g., every 30 seconds) to enable
    historical analysis without querying the full ticks table.
    """

    __tablename__ = "odds_snapshots"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    snapshot_id = Column(String(64), unique=True, nullable=False, index=True)

    # Foreign keys
    fixture_id = Column(Integer, ForeignKey("fixtures.id"), nullable=False, index=True)

    # Snapshot time
    captured_at = Column(DateTime, nullable=False, index=True)

    # All odds stored as JSON for flexibility
    # Structure: {sportsbook: {market_type: {outcome: odds}}}
    odds_data = Column(JSON, nullable=False)

    # Metadata
    source_count = Column(Integer, default=0)  # Number of sportsbooks captured
    market_count = Column(Integer, default=0)  # Number of markets captured

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    fixture = relationship("Fixture", back_populates="odds_snapshots")

    __table_args__ = (Index("idx_fixture_captured", "fixture_id", "captured_at"),)

    def __repr__(self):
        return f"<OddsSnapshot {self.fixture_id} @ {self.captured_at}>"


class LineMovement(Base):
    """
    Aggregated line movement events.

    Derived from odds_ticks to track significant movements.
    """

    __tablename__ = "line_movements"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # Foreign keys
    fixture_id = Column(Integer, ForeignKey("fixtures.id"), nullable=False, index=True)
    first_tick_id = Column(String(64), nullable=False)  # First tick in movement
    last_tick_id = Column(String(64), nullable=False)  # Last tick in movement

    # Identification
    sportsbook = Column(String, nullable=False, index=True)
    market_type = Column(String, nullable=False, index=True)
    outcome = Column(String, nullable=False)

    # Movement details
    start_odds = Column(Numeric(10, 5), nullable=False)
    end_odds = Column(Numeric(10, 5), nullable=False)
    min_odds = Column(Numeric(10, 5), nullable=False)
    max_odds = Column(Numeric(10, 5), nullable=False)
    movement_pct = Column(Float, nullable=False)  # Percentage change

    # Timing
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    duration_seconds = Column(Integer, nullable=False)

    # Classification
    movement_type = Column(String)  # 'sharp_move', 'gradual', 'correction', etc.

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_movement_time", "fixture_id", "start_time"),
        Index("idx_movement_type", "movement_type"),
    )

    def __repr__(self):
        return f"<LineMovement {self.market_type} {self.outcome}: {self.start_odds}->{self.end_odds}>"


class WebSocketEvent(Base):
    """WebSocket connection and message events."""

    __tablename__ = "websocket_events"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # Connection identification
    session_id = Column(String, nullable=False, index=True)
    sportsbook = Column(String, nullable=False, index=True)

    # Event type
    event_type = Column(
        String, nullable=False, index=True
    )  # connected, disconnected, message, error, reconnect

    # Event details
    url = Column(String, nullable=True)
    message_count = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)

    # Timing
    occurred_at = Column(DateTime, nullable=False, index=True)
    duration_ms = Column(Integer, nullable=True)  # For connection events

    # Metrics snapshot
    metrics = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (Index("idx_session_time", "session_id", "occurred_at"),)

    def __repr__(self):
        return f"<WebSocketEvent {self.sportsbook} {self.event_type}>"


class SessionLog(Base):
    """Session lifecycle and health logs."""

    __tablename__ = "session_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # Session identification
    session_id = Column(String, nullable=False, index=True)
    sportsbook = Column(String, nullable=False, index=True)

    # Event type
    event_type = Column(
        String, nullable=False
    )  # created, authenticated, expired, recovered, failed, closed

    # State information
    state_before = Column(String, nullable=True)
    state_after = Column(String, nullable=True)

    # Health metrics at time of event
    health_score = Column(Float, nullable=True)
    consecutive_failures = Column(Integer, default=0)
    requests_total = Column(Integer, default=0)
    requests_failed = Column(Integer, default=0)

    # Error information
    error_message = Column(Text, nullable=True)
    recovery_attempted = Column(Boolean, default=False)
    recovery_successful = Column(Boolean, nullable=True)

    # Timing
    occurred_at = Column(DateTime, nullable=False, index=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_session_event_time", "session_id", "event_type", "occurred_at"),
    )

    def __repr__(self):
        return f"<SessionLog {self.session_id} {self.event_type}>"


class BrowserHealth(Base):
    """Browser instance health metrics."""

    __tablename__ = "browser_health"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # Browser identification
    browser_id = Column(String, nullable=False, index=True)

    # Resource usage
    memory_mb = Column(Float, nullable=True)
    cpu_percent = Column(Float, nullable=True)
    context_count = Column(Integer, default=0)
    page_count = Column(Integer, default=0)

    # Health status
    is_healthy = Column(Boolean, default=True)
    crash_count = Column(Integer, default=0)
    uptime_seconds = Column(Integer, default=0)

    # Additional metrics
    metrics = Column(JSON, nullable=True)

    recorded_at = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (Index("idx_browser_time", "browser_id", "recorded_at"),)

    def __repr__(self):
        return f"<BrowserHealth {self.browser_id} healthy={self.is_healthy}>"


class IngestionMetrics(Base):
    """Aggregated ingestion metrics for monitoring."""

    __tablename__ = "ingestion_metrics"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # Time bucket (e.g., per minute)
    bucket_start = Column(DateTime, nullable=False, index=True)
    bucket_end = Column(DateTime, nullable=False)

    # Source identification
    sportsbook = Column(String, nullable=False, index=True)

    # Counts
    ticks_ingested = Column(Integer, default=0)
    fixtures_tracked = Column(Integer, default=0)
    websocket_messages = Column(Integer, default=0)
    http_requests = Column(Integer, default=0)

    # Success/failure
    successes = Column(Integer, default=0)
    failures = Column(Integer, default=0)
    timeouts = Column(Integer, default=0)

    # Latency (milliseconds)
    avg_latency_ms = Column(Float, nullable=True)
    p95_latency_ms = Column(Float, nullable=True)
    p99_latency_ms = Column(Float, nullable=True)

    # WebSocket specific
    websocket_uptime_pct = Column(Float, nullable=True)
    reconnect_count = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (Index("idx_bucket_sportsbook", "bucket_start", "sportsbook"),)

    def __repr__(self):
        return f"<IngestionMetrics {self.sportsbook} @{self.bucket_start}>"


# Existing models (kept for backward compatibility)


class Odds(Base):
    """Legacy odds data from sportsbooks (snapshot-based)."""

    __tablename__ = "odds"

    id = Column(Integer, primary_key=True)
    fixture_id = Column(Integer, ForeignKey("fixtures.id"), nullable=False)
    sportsbook = Column(String, nullable=False)
    market_type = Column(String, nullable=False)

    # Odds values stored as JSON for flexibility
    odds_data = Column(JSON, nullable=False)

    # Snapshot timestamp
    collected_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    fixture = relationship("Fixture", back_populates="odds")

    __table_args__ = (
        Index("idx_fixture_sportsbook", "fixture_id", "sportsbook"),
        Index("idx_collected_at", "collected_at"),
    )

    def __repr__(self):
        return f"<Odds {self.sportsbook} - {self.market_type}>"


class Prediction(Base):
    """Model predictions for fixtures."""

    __tablename__ = "predictions"

    id = Column(Integer, primary_key=True)
    fixture_id = Column(Integer, ForeignKey("fixtures.id"), nullable=False)
    model_name = Column(String, nullable=False)
    model_version = Column(String, nullable=False)

    # Prediction details
    predicted_outcome = Column(String, nullable=False)
    confidence = Column(Float, nullable=False)
    probability_home = Column(Float)
    probability_draw = Column(Float)
    probability_away = Column(Float)

    # Recommended bet
    recommended_market = Column(String)
    recommended_selection = Column(String)
    fair_odds = Column(Float)
    kelly_stake = Column(Float)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    fixture = relationship("Fixture", back_populates="predictions")

    __table_args__ = (Index("idx_fixture_model", "fixture_id", "model_name"),)

    def __repr__(self):
        return f"<Prediction {self.model_name} - {self.predicted_outcome}>"


class Bet(Base):
    """Placed bets tracking."""

    __tablename__ = "bets"

    id = Column(Integer, primary_key=True)
    fixture_id = Column(Integer, ForeignKey("fixtures.id"), nullable=False)
    prediction_id = Column(Integer, ForeignKey("predictions.id"), nullable=True)

    sportsbook = Column(String, nullable=False)
    market_type = Column(String, nullable=False)
    selection = Column(String, nullable=False)

    stake = Column(Float, nullable=False)
    odds = Column(Float, nullable=False)
    potential_return = Column(Float, nullable=False)

    status = Column(String, default="pending")  # pending, won, lost, void, cashed_out
    result = Column(Float, nullable=True)  # Actual return amount

    placed_at = Column(DateTime, default=datetime.utcnow)
    settled_at = Column(DateTime, nullable=True)

    # Relationships
    fixture = relationship("Fixture", back_populates="bets")

    __table_args__ = (
        Index("idx_status", "status"),
        Index("idx_placed_at", "placed_at"),
    )

    def __repr__(self):
        return f"<Bet {self.selection} @ {self.odds}>"


class BankrollSnapshot(Base):
    """Bankroll tracking over time."""

    __tablename__ = "bankroll_snapshots"

    id = Column(Integer, primary_key=True)
    total_bankroll = Column(Float, nullable=False)
    available_bankroll = Column(Float, nullable=False)
    exposed_bankroll = Column(Float, nullable=False)

    total_profit_loss = Column(Float, default=0.0)
    bets_count = Column(Integer, default=0)
    winning_bets = Column(Integer, default=0)
    losing_bets = Column(Integer, default=0)

    recorded_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (Index("idx_recorded_at", "recorded_at"),)

    def __repr__(self):
        return f"<BankrollSnapshot {self.total_bankroll}>"

