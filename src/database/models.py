"""
Database Models

SQLAlchemy models for the DeepField betting system.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, JSON, ForeignKey, Index
from sqlalchemy.orm import relationship, declarative_base


Base = declarative_base()


class Fixture(Base):
    """Football fixture/match model."""
    
    __tablename__ = 'fixtures'
    
    id = Column(Integer, primary_key=True)
    api_id = Column(String, unique=True, nullable=False)  # External API ID
    home_team = Column(String, nullable=False)
    away_team = Column(String, nullable=False)
    league = Column(String, nullable=False)
    country = Column(String, nullable=False)
    kickoff_time = Column(DateTime, nullable=False)
    status = Column(String, default='scheduled')  # scheduled, live, finished, cancelled
    
    home_score = Column(Integer, nullable=True)
    away_score = Column(Integer, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    odds = relationship('Odds', back_populates='fixture', lazy='dynamic')
    predictions = relationship('Prediction', back_populates='fixture', lazy='dynamic')
    bets = relationship('Bet', back_populates='fixture', lazy='dynamic')
    
    __table_args__ = (
        Index('idx_kickoff_time', 'kickoff_time'),
        Index('idx_status', 'status'),
    )
    
    def __repr__(self):
        return f"<Fixture {self.home_team} vs {self.away_team}>"


class Odds(Base):
    """Odds data from sportsbooks."""
    
    __tablename__ = 'odds'
    
    id = Column(Integer, primary_key=True)
    fixture_id = Column(Integer, ForeignKey('fixtures.id'), nullable=False)
    sportsbook = Column(String, nullable=False)
    market_type = Column(String, nullable=False)  # 1x2, over_under, etc.
    
    # Odds values stored as JSON for flexibility
    odds_data = Column(JSON, nullable=False)
    
    # Snapshot timestamp
    collected_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    fixture = relationship('Fixture', back_populates='odds')
    
    __table_args__ = (
        Index('idx_fixture_sportsbook', 'fixture_id', 'sportsbook'),
        Index('idx_collected_at', 'collected_at'),
    )
    
    def __repr__(self):
        return f"<Odds {self.sportsbook} - {self.market_type}>"


class Prediction(Base):
    """Model predictions for fixtures."""
    
    __tablename__ = 'predictions'
    
    id = Column(Integer, primary_key=True)
    fixture_id = Column(Integer, ForeignKey('fixtures.id'), nullable=False)
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
    fixture = relationship('Fixture', back_populates='predictions')
    
    __table_args__ = (
        Index('idx_fixture_model', 'fixture_id', 'model_name'),
    )
    
    def __repr__(self):
        return f"<Prediction {self.model_name} - {self.predicted_outcome}>"


class Bet(Base):
    """Placed bets tracking."""
    
    __tablename__ = 'bets'
    
    id = Column(Integer, primary_key=True)
    fixture_id = Column(Integer, ForeignKey('fixtures.id'), nullable=False)
    prediction_id = Column(Integer, ForeignKey('predictions.id'), nullable=True)
    
    sportsbook = Column(String, nullable=False)
    market_type = Column(String, nullable=False)
    selection = Column(String, nullable=False)
    
    stake = Column(Float, nullable=False)
    odds = Column(Float, nullable=False)
    potential_return = Column(Float, nullable=False)
    
    status = Column(String, default='pending')  # pending, won, lost, void, cashed_out
    result = Column(Float, nullable=True)  # Actual return amount
    
    placed_at = Column(DateTime, default=datetime.utcnow)
    settled_at = Column(DateTime, nullable=True)
    
    # Relationships
    fixture = relationship('Fixture', back_populates='bets')
    
    __table_args__ = (
        Index('idx_status', 'status'),
        Index('idx_placed_at', 'placed_at'),
    )
    
    def __repr__(self):
        return f"<Bet {self.selection} @ {self.odds}>"


class BankrollSnapshot(Base):
    """Bankroll tracking over time."""
    
    __tablename__ = 'bankroll_snapshots'
    
    id = Column(Integer, primary_key=True)
    total_bankroll = Column(Float, nullable=False)
    available_bankroll = Column(Float, nullable=False)
    exposed_bankroll = Column(Float, nullable=False)
    
    total_profit_loss = Column(Float, default=0.0)
    bets_count = Column(Integer, default=0)
    winning_bets = Column(Integer, default=0)
    losing_bets = Column(Integer, default=0)
    
    recorded_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_recorded_at', 'recorded_at'),
    )
    
    def __repr__(self):
        return f"<BankrollSnapshot {self.total_bankroll}>"
