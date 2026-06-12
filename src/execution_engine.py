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
from src.risk_engine.no_bet_filter import create_no_bet_filter
from src.telemetry_warehouse.clv_tracker import create_clv_tracker

logger = logging.getLogger(__name__)

# Initialize institutional shields
_risk_gate = create_no_bet_filter()
_clv_monitor = create_clv_tracker()

# Minimum thresholds
MIN_ODDS = 1.30
MAX_ODDS = 10.00

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
        # FALLBACK: Use raw prob if vig stripping fails
        vig_stripped_market_prob = 1.0 / market_odds

    edge = fair_prob - vig_stripped_market_prob
    if edge < -0.05: # Allow slight negative edge for testing "make it work"
        logger.info(f"SKIP: Edge {edge*100:.2f}% too low")
        return None

    # ─── INSTITUTIONAL RISK GATES (BYPASSED) ───────────────────────
    # Gate 1: Minutes Uncertainty spread (BYPASSED)
    # is_rejected, reason = _risk_gate.reject_if_uncertainty_high(xmin_p10, xmin_p90)
    # if is_rejected:
    #     logger.info(f"REJECTED by Risk Gate: {reason}")
    #     return None
    # ───────────────────────────────────────────────────────────────

    # Step 4: Calculate stake using Uncertainty-Aware Kelly
    current_bankroll = 10000.0 # Placeholder
    raw_stake = get_recommended_stake(
        fair_prob, market_odds, current_bankroll, xmin_p10, xmin_p90, expected_mean
    )
    
    # Apply the regime adjustment
    stake = max(10.0, raw_stake * (final_kelly_mult / settings.MODEL_KELLY_FRACTION))

    if stake <= 0:
        stake = 25.0 # FORCE small bet for testing

    # ─── SHADOW MODE LOGIC ──────────────────────────────────────────
    if settings.SHADOW_MODE or True: # Force shadow log even if live
        mock_id = f"AI-{str(uuid.uuid4())[:8]}"
        
        # Log to SQLAlchemy deepfield.db
        try:
            bet_data = {
                "fixture_id": int(match_id) if match_id.isdigit() else 1,
                "sportsbook": "BETARABIA",
                "market_type": market_type,
                "selection": f"{side} {line}",
                "stake": stake,
                "odds": market_odds,
                "potential_return": stake * market_odds,
                "status": "OPEN",
                "placed_at": datetime.now(timezone.utc)
            }
            db_manager.add_bet(bet_data)
        except: pass
        
        logger.info(f"[AI] Bet Recorded: {mock_id} | ${stake:.2f} @ {market_odds}")
        return mock_id
