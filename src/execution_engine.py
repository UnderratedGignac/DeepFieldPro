import os
import time
import uuid
from datetime import datetime, timezone
import logging

from src.dfp_config import settings
from src.data.database_manager import db_manager
from src.services.alerting import notifier
from src.kelly_calculator import get_recommended_stake
from src.utils import remove_vig

logger = logging.getLogger(__name__)

# Minimum thresholds
MIN_ODDS = 1.30
MAX_ODDS = 5.00

def place_bet(
    fair_prob: float,
    market_odds: float,
    all_outcome_odds: list,
    match_id: str,
    player_id: str,
    market_type: str,
    line: float,
    side: str,
    lineup_drop_at: str,
    latency_ms: int,
    regime: str,
    role_shift_flag: bool,
    confidence: str = 'HIGH',
    has_lineup: int = 0,
    expected_mean: float = 0.0,
    xmin_p10: float = 0.0,
    xmin_p90: float = 0.0
):
    """
    Institutional Execution Engine.
    Handles risk gates, sizing, and the Shadow vs Live toggle.
    """
    execution_start = time.time()

    # Guard 1: Odds range filter
    if not (MIN_ODDS <= market_odds <= MAX_ODDS):
        logger.info(f"SKIP: Odds {market_odds} outside range")
        return None

    # Guard 2: Vig strip + edge check
    try:
        fair_probs, overround = remove_vig(all_outcome_odds)
        side_index = 0 # Expecting the target side to be first
        vig_stripped_market_prob = fair_probs[side_index]
    except Exception as e:
        logger.error(f"SKIP: Vig stripping failed - {e}")
        return None

    edge = fair_prob - vig_stripped_market_prob
    if edge < settings.MODEL_THRESHOLD_MIN_EDGE:
        logger.info(f"SKIP: Edge {edge*100:.2f}% below threshold")
        return None

    # Step 4: Calculate stake using Uncertainty-Aware Kelly (from Phase 4)
    # Note: In a real implementation, we'd fetch actual bankroll here
    current_bankroll = 10000.0 # Placeholder
    stake = get_recommended_stake(
        fair_prob, market_odds, current_bankroll, xmin_p10, xmin_p90, expected_mean
    )

    if stake <= 0:
        logger.info("SKIP: Kelly sizing returned $0 stake.")
        return None

    # ─── SHADOW MODE LOGIC ──────────────────────────────────────────
    if settings.SHADOW_MODE:
        mock_id = f"SHADOW-{str(uuid.uuid4())[:8]}"
        
        # Log to SQLAlchemy deepfield.db
        bet_data = {
            "fixture_id": int(match_id) if match_id.isdigit() else 1,
            "sportsbook": "SHADOW_BOOK",
            "market_type": market_type,
            "selection": f"{side} {line}",
            "stake": stake,
            "odds": market_odds,
            "potential_return": stake * market_odds,
            "status": "SHADOW",
            "placed_at": datetime.now(timezone.utc)
        }
        db_manager.add_bet(bet_data)
        
        # Fire Alert
        notifier.send_execution_alert({
            "match": match_id,
            "market": market_type,
            "side": side,
            "odds": market_odds,
            "stake": stake,
            "edge": edge,
            "status": "SHADOW",
            "bet_id": mock_id
        })
        
        logger.info(f"[SHADOW] Bet Recorded: {mock_id} | ${stake:.2f} @ {market_odds}")
        return mock_id
    # ───────────────────────────────────────────────────────────────

    # LIVE EXECUTION (Placeholder for actual browser automation/API calls)
    logger.warning("[LIVE] Real capital execution not yet fully linked in this patch.")
    return None
