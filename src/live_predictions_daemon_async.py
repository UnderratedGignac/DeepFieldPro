import asyncio
import datetime
import logging
import os
import sys
import json
import joblib
import pandas as pd
from typing import Dict, List, Any

# Ensure src is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models.registry_manager import registry_manager
from src.execution_engine import place_bet
from src.data.database_manager import db_manager
from src.free_scraper_module import get_todays_fixtures_free as get_todays_fixtures

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Global production pipeline (Target Variable -> SafeModelLoader)
PRODUCTION_PIPELINE = registry_manager.load_production_pipeline()

async def odds_producer(queue: asyncio.Queue):
    """
    Producer: Continuously fetches live odds and fixtures.
    Puts discovery items into the prediction_queue.
    """
    logger.info("[PRODUCER] Starting Odds Producer coroutine...")
    
    while True:
        try:
            # 1. Fetch current fixtures and odds
            # In production, this would be a high-frequency WebSocket or API call
            fixtures = await asyncio.to_thread(get_todays_fixtures)
            
            # 2. Filter for actionable matches (e.g., T-45m or Live)
            for fixture in fixtures:
                # Mockup: In reality, we'd fetch real-time odds for each fixture here
                item = {
                    "fixture": fixture,
                    "timestamp": datetime.datetime.now(datetime.timezone.utc),
                    "raw_odds": {"1X2": {"Home": 2.10, "Draw": 3.40, "Away": 3.20}} 
                }
                
                # 3. Put into queue for inference
                await queue.put(item)
            
            logger.info(f"[PRODUCER] Ingested {len(fixtures)} fixtures into queue.")
            
            # Wait for next sweep (e.g., every 60 seconds)
            await asyncio.sleep(60)
            
        except Exception as e:
            logger.error(f"[PRODUCER] Error in odds fetch: {e}")
            await asyncio.sleep(10)

async def inference_consumer(queue: asyncio.Queue):
    """
    Consumer: Reads items from the queue and executes model inference.
    Uses the strict Model Registry and SafeModelLoader.
    """
    logger.info("[CONSUMER] Starting Inference Consumer coroutine...")
    
    while True:
        # Get work item from queue
        item = await queue.get()
        
        try:
            fixture = item["fixture"]
            match_id = fixture["fixture"]["id"]
            
            # 1. Build prediction context (Dataframe)
            # Mockup: In reality, this would fetch player stats and lineup data
            input_df = pd.DataFrame([{
                "started_last_match": 1,
                "started_last_3": 3,
                "minutes_last_5": 400,
                "Pos": "FW",
                "Comp": "Premier League",
                "days_rest": 4
            }])
            
            # 2. Execute all production models for this fixture
            for target_var, model_wrapper in PRODUCTION_PIPELINE.items():
                prediction = model_wrapper.predict_safe(input_df)
                
                if prediction is not None:
                    # 3. Logic to convert prediction to fair probability/odds
                    fair_prob = 0.52 # Mock result
                    market_odds = item["raw_odds"]["1X2"]["Home"]
                    
                    # 4. Call Execution Engine if edge exists
                    if market_odds > (1.0 / fair_prob):
                        await asyncio.to_thread(
                            place_bet,
                            fair_prob=fair_prob,
                            market_odds=market_odds,
                            all_outcome_odds=[market_odds],
                            match_id=str(match_id),
                            player_id="PLAYER_001",
                            market_type=target_var,
                            line=0.5,
                            side="over",
                            lineup_drop_at=fixture["fixture"]["date"],
                            latency_ms=0,
                            regime="async_daemon",
                            role_shift_flag=False,
                            has_lineup=1,
                            xmin_p10=60.0,
                            xmin_p90=90.0,
                            expected_mean=75.0
                        )
            
        except Exception as e:
            logger.error(f"[CONSUMER] Error in inference/execution: {e}")
        finally:
            # Mark task as done
            queue.task_done()

async def main():
    """
    Entry point for the Async Live Predictions Daemon.
    Orchestrates the producer-consumer pipeline.
    """
    # Initialize DB (Consolidated in Phase 2)
    db_manager.init_db()
    
    # Create the shared queue
    prediction_queue = asyncio.Queue(maxsize=100)
    
    # Run producer and consumer concurrently
    logger.info("[MAIN] Launching DeepFieldPro Async Infrastructure...")
    await asyncio.gather(
        odds_producer(prediction_queue),
        inference_consumer(prediction_queue),
        inference_consumer(prediction_queue) # Run 2 consumers for parallel inference
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("[MAIN] Daemon stopped by user.")
