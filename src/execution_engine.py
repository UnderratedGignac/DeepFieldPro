import os
import sqlite3
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
    confidence: str = "HIGH",
    has_lineup: int = 0,
    expected_mean: float = 0.0,
    xmin_p10: float = 0.0,
    xmin_p90: float = 0.0,
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
        side_index = 0  # Expecting the target side to be first
        vig_stripped_market_prob = fair_probs[side_index]
    except Exception as e:
        logger.error(f"SKIP: Vig stripping failed - {e}")
        return None

    edge = fair_prob - vig_stripped_market_prob
    if edge < settings.MODEL_THRESHOLD_MIN_EDGE:
        logger.info(f"SKIP: Edge {edge*100:.2f}% below threshold")
        return None

    # ─── INSTITUTIONAL RISK GATES ──────────────────────────────────
    # Gate 1: Minutes Uncertainty spread
    is_rejected, reason = _risk_gate.reject_if_uncertainty_high(xmin_p10, xmin_p90)
    if is_rejected:
        logger.info(f"REJECTED by Risk Gate: {reason}")
        return None

    # Gate 2: Team/Player Correlation (Exposure check)
    # player_id passed from daemon is often just first name, but better than nothing
    is_rejected, reason = _risk_gate.reject_if_correlated(
        player_id, match_id, market_type
    )
    if is_rejected:
        logger.info(f"REJECTED by Risk Gate: {reason}")
        return None
    # ───────────────────────────────────────────────────────────────

    # ─── DYNAMIC REGIME SWITCHER ──────────────────────────────────
    # Check recent ROI to determine if we should be aggressive or safe
    try:
        conn_roi = sqlite3.connect(
            os.path.join(os.path.dirname(__file__), "..", "data", "bet_log.db")
        )
        cur_roi = conn_roi.cursor()
        # Look at last 10 settled bets
        cur_roi.execute(
            "SELECT SUM(pnl), SUM(stake) FROM (SELECT pnl, stake FROM bet_log WHERE result != 'OPEN' ORDER BY placed_at DESC LIMIT 10)"
        )
        recent_pnl, recent_staked = cur_roi.fetchone()
        conn_roi.close()

        recent_roi = (
            (recent_pnl / recent_staked)
            if (recent_staked and recent_staked > 0)
            else 0.0
        )

        if recent_roi < -0.20:
            logger.warning(
                f"REGIME SHIFT: Detected losing streak (ROI: {recent_roi*100:.1f}%). Switching to SAFETY MODE."
            )
            # Reduce Kelly multiplier by 75% for safety
            final_kelly_mult = settings.MODEL_KELLY_FRACTION * 0.25
        else:
            final_kelly_mult = settings.MODEL_KELLY_FRACTION
    except:
        final_kelly_mult = settings.MODEL_KELLY_FRACTION
    # ───────────────────────────────────────────────────────────────

    # Step 4: Calculate stake using Uncertainty-Aware Kelly (from Phase 4)
    # Note: In a real implementation, we'd fetch actual bankroll here
    current_bankroll = 10000.0  # Placeholder
    # Use the dynamic kelly multiplier
    raw_stake = get_recommended_stake(
        fair_prob, market_odds, current_bankroll, xmin_p10, xmin_p90, expected_mean
    )

    # Apply the regime adjustment
    stake = raw_stake * (final_kelly_mult / settings.MODEL_KELLY_FRACTION)

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
            "placed_at": datetime.now(timezone.utc),
        }
        db_manager.add_bet(bet_data)

        logger.info(f"[SHADOW] Bet Recorded: {mock_id} | ${stake:.2f} @ {market_odds}")

        # ─── REAL-TIME NOTIFICATION ────────────────────────────────────
        notifier.send_execution_alert(
            {
                "match": match_id,
                "market": market_type,
                "side": side,
                "odds": market_odds,
                "stake": stake,
                "edge": edge,
                "status": "SHADOW",
                "bet_id": mock_id,
            }
        )
        # ───────────────────────────────────────────────────────────────

        # ─── TELEMETRY TRACKING ────────────────────────────────────────
        # Schedule CLV capture for 60s before kickoff
        try:
            # Parse kickoff time (assuming ISO format from daemon)
            k_time = datetime.fromisoformat(lineup_drop_at)
            _clv_monitor.schedule_clv_capture(
                bet_id=mock_id,
                kickoff_time=k_time,
                entry_odds=market_odds,
                player_name=player_id,
                team=match_id,  # Simplified mapping
                market=market_type,
                uncertainty_spread=(xmin_p90 - xmin_p10),
            )
        except Exception as e:
            logger.error(f"CLV Scheduling failed: {e}")
        # ───────────────────────────────────────────────────────────────

        return mock_id
    # ───────────────────────────────────────────────────────────────

    # LIVE EXECUTION (Placeholder for actual browser automation/API calls)
    logger.warning("[LIVE] Real capital execution not yet fully linked in this patch.")
    return None
