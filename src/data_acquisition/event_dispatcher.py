import asyncio
import logging
from dataclasses import dataclass
from typing import Dict, Any

from .validation_engine import validation_engine
from .db_writer import db_writer
from .normalization_engine import normalize_engine
from .betarabia_scraper import betarabia_scraper

# New Lineup Architecture Modules
from .lineup_confidence_engine import confidence_engine
from .player_position_normalizer import position_normalizer
from .lineup_change_detector import change_detector

logger = logging.getLogger(__name__)

@dataclass
class LineupConfirmedEvent:
    fixture_id: str
    confidence_score: float
    source: str
    has_changes: bool
    changes_summary: Dict[str, Any]
    timestamp: str

class EventDispatcher:
    def __init__(self):
        pass

    async def trigger_pricing_pipeline(self, fixture_id: str):
        """
        Calls the main model_runner pipeline.
        """
        logger.info(f"Triggering downstream pricing engine for {fixture_id}...")
        # TODO: Import and call model_runner.py's run_for_match async or via subprocess
        pass

    async def handle_lineups_confirmed(self, lineup_payload: Dict[str, Any], source: str = "unknown"):
        """
        Fired when a lineup payload is retrieved (probabilistic, expected, or official).
        Validates, normalizes, detects changes, writes snapshot, and emits event.
        """
        fixture_id = lineup_payload.get('fixture_id')
        logger.info(f"Received lineup payload for {fixture_id} from {source}")
        
        # 1. Validate
        if not validation_engine.validate_lineup(lineup_payload):
            logger.error("Lineup payload validation failed. Aborting pipeline.")
            return
            
        players = lineup_payload.get('players', [])
            
        # 2. Normalize Names & Positions
        for player in players:
            raw_name = player.get('player_name')
            player['normalized_name'] = normalize_engine.normalize_name(raw_name)
            
            raw_pos = player.get('position')
            player['canonical_position'] = position_normalizer.normalize(raw_pos)
            
        # 3. Calculate Confidence Score
        confidence = confidence_engine.compute_confidence(fixture_id, source, players)
        # Inject confidence into players for DB write
        for p in players:
            p['confidence_score'] = confidence
            p['source'] = source
            
        # 4. Detect Tactical/Personnel Changes
        changes = change_detector.detect_changes(fixture_id, players)
            
        # 5. Versioning: Save Snapshot to DB
        await db_writer.insert_lineups(fixture_id, source, players)
        
        from datetime import datetime, timezone
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # 6. Emit Event-Driven Integration Payload
        event = LineupConfirmedEvent(
            fixture_id=fixture_id,
            confidence_score=confidence,
            source=source,
            has_changes=changes["has_changes"],
            changes_summary=changes,
            timestamp=timestamp
        )
        
        logger.info(f"EMITTING EVENT: {event}")
        
        # 7. Trigger Downstream (Only if confidence is high enough or it's a significant expected update)
        if confidence > 0.6:
            # Trigger odds scraper
            confirmed_starters = [p for p in players if p.get('starter')]
            try:
                # In the new architecture, the odds scraper is continuous via websockets, 
                # but we can optionally trigger a fresh navigation here if needed.
                pass
            except Exception as e:
                logger.error(f"Failed during odds dispatch: {e}")
                
            # Trigger Pricing Pipeline Recalculation
            await self.trigger_pricing_pipeline(fixture_id)

event_dispatcher = EventDispatcher()
