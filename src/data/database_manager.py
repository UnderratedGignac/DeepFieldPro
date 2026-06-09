import logging
import asyncio
from typing import List, Optional, Any, Dict
from sqlalchemy import create_engine, insert
from sqlalchemy.orm import sessionmaker, Session
from src.database.models import Base, Bet, Prediction, Fixture, OddsTick
from src.dfp_config import settings

logger = logging.getLogger(__name__)

class DatabaseManager:
    """
    Centralized database manager for DeepFieldPro.
    Ensures all operations go through SQLAlchemy and the deepfield.db source of truth.
    """
    
    def __init__(self, database_url: str = settings.DATABASE_URL):
        self.engine = create_engine(
            database_url,
            pool_size=20,
            max_overflow=0,
            pool_pre_ping=True
        )
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        
    def init_db(self):
        """Create all tables if they don't exist."""
        Base.metadata.create_all(bind=self.engine)
        logger.info("Database initialized (SQLAlchemy)")

    def get_session(self) -> Session:
        """Provide a database session."""
        return self.SessionLocal()

    # --- High-Frequency Odds Operations ---

    async def async_bulk_insert_ticks(self, ticks_list: List[Dict[str, Any]]):
        """
        High-performance bulk insert for odds ticks.
        Uses SQLAlchemy core insert().values() for maximum throughput.
        """
        if not ticks_list:
            return

        def _bulk_insert():
            with self.engine.begin() as conn:
                # Optimized bulk insert using executemany execution style
                conn.execute(
                    insert(OddsTick).values(ticks_list)
                )
        
        try:
            # Offload blocking IO to a thread pool to avoid stalling the event loop
            await asyncio.to_thread(_bulk_insert)
            logger.debug(f"[DB] Bulk inserted {len(ticks_list)} odds ticks.")
        except Exception as e:
            logger.error(f"[DB] Bulk insert failed: {e}")

    # --- Bet Operations ---
    
    def add_bet(self, bet_data: Dict[str, Any]) -> Bet:
        """Add a new bet to the database."""
        session = self.get_session()
        try:
            # First, ensure fixture exists or link it
            fixture_id = bet_data.get("fixture_id")
            # In a real scenario, we'd verify fixture_id here
            
            new_bet = Bet(
                fixture_id=fixture_id,
                sportsbook=bet_data.get("sportsbook"),
                market_type=bet_data.get("market_type"),
                selection=bet_data.get("selection"),
                stake=bet_data.get("stake"),
                odds=bet_data.get("odds"),
                potential_return=bet_data.get("potential_return", 0.0),
                status=bet_data.get("status", "pending"),
                placed_at=bet_data.get("placed_at")
            )
            session.add(new_bet)
            session.commit()
            session.refresh(new_bet)
            return new_bet
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to add bet: {e}")
            raise
        finally:
            session.close()

    def update_bet_status(self, bet_id: int, status: str, result: float = None):
        """Update the status and result of a bet."""
        session = self.get_session()
        try:
            bet = session.query(Bet).filter(Bet.id == bet_id).first()
            if bet:
                bet.status = status
                if result is not None:
                    bet.result = result
                session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to update bet {bet_id}: {e}")
        finally:
            session.close()

    # --- Prediction Operations ---
    
    def add_prediction(self, pred_data: Dict[str, Any]) -> Prediction:
        """Add a model prediction to the database."""
        session = self.get_session()
        try:
            new_pred = Prediction(
                fixture_id=pred_data.get("fixture_id"),
                model_name=pred_data.get("model_name"),
                model_version=pred_data.get("model_version", "v1.0"),
                predicted_outcome=pred_data.get("predicted_outcome"),
                confidence=pred_data.get("confidence"),
                probability_home=pred_data.get("probability_home"),
                probability_draw=pred_data.get("probability_draw"),
                probability_away=pred_data.get("probability_away"),
                recommended_market=pred_data.get("recommended_market"),
                recommended_selection=pred_data.get("recommended_selection"),
                fair_odds=pred_data.get("fair_odds"),
                kelly_stake=pred_data.get("kelly_stake")
            )
            session.add(new_pred)
            session.commit()
            session.refresh(new_pred)
            return new_pred
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to add prediction: {e}")
            raise
        finally:
            session.close()

db_manager = DatabaseManager()
