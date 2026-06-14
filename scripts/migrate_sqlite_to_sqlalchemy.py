import sqlite3
import os
import sys
import logging
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.data.database_manager import db_manager
from src.database.models import Bet, Prediction, Fixture

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("migration")

LEGACY_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "src", "data", "bet_log.db")

def migrate():
    if not os.path.exists(LEGACY_DB_PATH):
        logger.error(f"Legacy database not found at {LEGACY_DB_PATH}")
        return

    logger.info("Starting migration from legacy bet_log.db to deepfield.db...")
    
    # Ensure tables exist
    db_manager.init_db()
    
    conn_legacy = sqlite3.connect(LEGACY_DB_PATH)
    cursor_legacy = conn_legacy.cursor()
    
    session = db_manager.get_session()
    
    try:
        # --- Migrate Bets ---
        logger.info("Migrating bets...")
        cursor_legacy.execute("SELECT * FROM bets")
        legacy_bets = cursor_legacy.fetchall()
        
        # Get column names to handle indices correctly
        column_names = [description[0] for description in cursor_legacy.description]
        
        for lb in legacy_bets:
            bet_dict = dict(zip(column_names, lb))
            bet_id = bet_dict.get("bet_id")
            
            # Check if bet already exists (using selection/timestamp as proxy if no bet_id in target)
            # Actually, the target 'Bet' model doesn't have a string 'bet_id' field, it has an auto-inc 'id'.
            # We'll use a unique constraint check or just skip if we think it's a dupe.
            # For simplicity, we'll assume bet_id is unique and map it to a JSON field or ignore if it's just a log.
            
            # Find or create fixture
            match_name = f"{bet_dict.get('team', 'Unknown')}" # Simplified
            fixture = session.query(Fixture).filter(Fixture.home_team == match_name).first()
            if not fixture:
                fixture = Fixture(
                    api_id=f"legacy_{bet_id}",
                    home_team=match_name,
                    away_team="Unknown",
                    league="Legacy",
                    country="Unknown",
                    kickoff_time=datetime.now() # Fallback
                )
                session.add(fixture)
                session.flush()
            
            new_bet = Bet(
                fixture_id=fixture.id,
                sportsbook="Legacy",
                market_type=bet_dict.get("market"),
                selection=bet_dict.get("selection"),
                stake=bet_dict.get("stake"),
                odds=bet_dict.get("entry_odds"),
                potential_return=bet_dict.get("profit_loss", 0.0) + (bet_dict.get("stake", 0.0) if bet_dict.get("status") == "won" else 0.0),
                status=bet_dict.get("status"),
                placed_at=datetime.fromisoformat(bet_dict.get("timestamp")) if bet_dict.get("timestamp") else datetime.now()
            )
            session.add(new_bet)
            
        # --- Migrate Predictions ---
        logger.info("Migrating predictions...")
        # Check if predictions table exists in legacy
        cursor_legacy.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='predictions'")
        if cursor_legacy.fetchone():
            cursor_legacy.execute("SELECT * FROM predictions")
            legacy_preds = cursor_legacy.fetchall()
            col_names_preds = [description[0] for description in cursor_legacy.description]
            
            for lp in legacy_preds:
                pred_dict = dict(zip(col_names_preds, lp))
                fid = pred_dict.get("fixture_id")
                
                # Try to find fixture by API ID
                fixture = session.query(Fixture).filter(Fixture.api_id == str(fid)).first()
                if not fixture:
                    fixture = Fixture(
                        api_id=str(fid),
                        home_team=pred_dict.get("match_name", "Unknown").split(" vs ")[0],
                        away_team=pred_dict.get("match_name", "Unknown").split(" vs ")[-1],
                        league=pred_dict.get("league", "Unknown"),
                        country="Unknown",
                        kickoff_time=datetime.fromisoformat(pred_dict.get("kickoff")) if pred_dict.get("kickoff") else datetime.now()
                    )
                    session.add(fixture)
                    session.flush()

                new_pred = Prediction(
                    fixture_id=fixture.id,
                    model_name="LegacyModel",
                    model_version="v0",
                    predicted_outcome=pred_dict.get("prediction"),
                    confidence=pred_dict.get("confidence", 0.0),
                    probability_home=pred_dict.get("home_prob"),
                    probability_draw=pred_dict.get("draw_prob"),
                    probability_away=pred_dict.get("away_prob"),
                    fair_odds=pred_dict.get("fair_odds", 0.0)
                )
                session.add(new_pred)

        session.commit()
        logger.info("Migration completed successfully.")
        
    except Exception as e:
        session.rollback()
        logger.error(f"Migration failed: {e}")
    finally:
        conn_legacy.close()
        session.close()

if __name__ == "__main__":
    migrate()
