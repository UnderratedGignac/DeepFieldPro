"""
shadow_framework.py — Shadow-mode paper betting validation framework.
=====================================================================
Enforces that NO real-money bets are placed until the system has:
  1. Generated 500+ paper bets
  2. Demonstrated positive CLV (avg CLV > 0)
  3. Demonstrated positive ROI
  4. Acceptable calibration error (< 5%)

This is the SINGLE source of truth for whether the system is "ready" for
real money. The arena_betting.py and execution_engine.py both check this
before placing any real-money order.

Shadow bets are logged to bet_log.db (same as existing paper bets) AND
to clv_tracking.db (new CLV tracking system) for dual validation.

Metrics tracked:
  - CLV (closing line value)
  - ROI (return on investment)
  - Win rate
  - Calibration (predicted prob vs actual outcome frequency)
  - Performance by market type
  - Performance by league
  - Performance by strategy/bet_source
"""

import os
import sqlite3
import json
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
BET_LOG_DB = os.path.join(DATA_DIR, "bet_log.db")
SHADOW_STATE_FILE = os.path.join(DATA_DIR, "shadow_validation_state.json")

# ── Validation thresholds ─────────────────────────────────────────────────
MIN_PAPER_BETS = 500         # Need 500+ settled paper bets
MIN_AVG_CLV_PCT = 0.0        # Average CLV must be > 0%
MIN_ROI_PCT = 0.0            # ROI must be > 0%
MAX_CALIBRATION_ERROR = 0.05  # Calibration error must be < 5%


def load_state() -> dict:
    """Load shadow validation state from disk."""
    try:
        with open(SHADOW_STATE_FILE, "r") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {
            "status": "SHADOW_MODE",
            "total_paper_bets": 0,
            "settled_paper_bets": 0,
            "avg_clv_pct": 0.0,
            "roi_pct": 0.0,
            "win_rate_pct": 0.0,
            "calibration_error": 0.0,
            "ready_for_real_money": False,
            "last_check_at": None,
            "failure_reasons": [],
        }


def save_state(state: dict):
    """Persist shadow validation state."""
    try:
        with open(SHADOW_STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except OSError as e:
        logger.error(f"[SHADOW] Failed to save state: {e}")


def count_paper_bets() -> dict:
    """
    Count paper bets from bet_log.db.

    Returns dict with total, settled, wins, losses, total_staked, total_pnl.
    """
    if not os.path.exists(BET_LOG_DB):
        return {"total": 0, "settled": 0, "wins": 0, "losses": 0,
                "total_staked": 0, "total_pnl": 0}

    try:
        conn = sqlite3.connect(BET_LOG_DB)
        conn.row_factory = sqlite3.Row
        row = conn.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN result IN ('W', 'L', 'WIN', 'LOSS') THEN 1 ELSE 0 END) as settled,
                SUM(CASE WHEN result IN ('W', 'WIN') THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN result IN ('L', 'LOSS') THEN 1 ELSE 0 END) as losses,
                COALESCE(SUM(stake), 0) as total_staked,
                COALESCE(SUM(pnl), 0) as total_pnl
            FROM bet_log
            WHERE bet_id IS NOT NULL
        """).fetchone()
        conn.close()

        return {
            "total": row["total"] or 0,
            "settled": row["settled"] or 0,
            "wins": row["wins"] or 0,
            "losses": row["losses"] or 0,
            "total_staked": row["total_staked"] or 0,
            "total_pnl": row["total_pnl"] or 0,
        }
    except Exception as e:
        logger.error(f"[SHADOW] Error counting bets: {e}")
        return {"total": 0, "settled": 0, "wins": 0, "losses": 0,
                "total_staked": 0, "total_pnl": 0}


def get_avg_clv() -> float:
    """Get average CLV from clv_tracking.db."""
    try:
        from src.clv_tracker_v2 import get_clv_summary
        summary = get_clv_summary()
        return summary.get("avg_clv_pct", 0.0)
    except Exception:
        # Fallback: compute from bet_log.db
        if not os.path.exists(BET_LOG_DB):
            return 0.0
        try:
            conn = sqlite3.connect(BET_LOG_DB)
            row = conn.execute(
                "SELECT AVG(clv) FROM bet_log WHERE clv IS NOT NULL AND clv != 0"
            ).fetchone()
            conn.close()
            return (row[0] or 0) * 100  # Convert to percentage
        except Exception:
            return 0.0


def get_calibration_error() -> float:
    """
    Get calibration error from clv_tracking.db.

    Calibration error = average |predicted_prob - actual_outcome|
    where actual_outcome is 1 for WIN, 0 for LOSS.
    """
    try:
        from src.clv_tracker_v2 import get_clv_summary
        summary = get_clv_summary()
        return summary.get("calibration_error", 0.0)
    except Exception:
        return 0.0


def validate_readiness() -> dict:
    """
    Check if the system is ready for real-money betting.

    Returns dict with:
      - ready: bool
      - reasons: list of failure reasons (empty if ready)
      - metrics: current performance metrics
    """
    state = load_state()
    bet_counts = count_paper_bets()
    avg_clv = get_avg_clv()
    cal_error = get_calibration_error()

    settled = bet_counts["settled"]
    total_staked = bet_counts["total_staked"]
    total_pnl = bet_counts["total_pnl"]
    wins = bet_counts["wins"]
    losses = bet_counts["losses"]

    roi = (total_pnl / total_staked * 100) if total_staked > 0 else 0
    win_rate = (wins / settled * 100) if settled > 0 else 0

    reasons = []

    # Check 1: Minimum paper bets
    if settled < MIN_PAPER_BETS:
        reasons.append(
            f"Need {MIN_PAPER_BETS}+ settled paper bets, have {settled}"
        )

    # Check 2: Positive CLV
    if avg_clv <= MIN_AVG_CLV_PCT:
        reasons.append(
            f"Average CLV must be > {MIN_AVG_CLV_PCT}%, currently {avg_clv:.2f}%"
        )

    # Check 3: Positive ROI
    if roi <= MIN_ROI_PCT:
        reasons.append(
            f"ROI must be > {MIN_ROI_PCT}%, currently {roi:.2f}%"
        )

    # Check 4: Acceptable calibration
    if cal_error > MAX_CALIBRATION_ERROR and settled >= 50:
        reasons.append(
            f"Calibration error must be < {MAX_CALIBRATION_ERROR*100:.1f}%, "
            f"currently {cal_error*100:.2f}%"
        )

    ready = len(reasons) == 0

    # Update state
    state.update({
        "status": "READY_FOR_LIVE" if ready else "SHADOW_MODE",
        "total_paper_bets": bet_counts["total"],
        "settled_paper_bets": settled,
        "avg_clv_pct": round(avg_clv, 2),
        "roi_pct": round(roi, 2),
        "win_rate_pct": round(win_rate, 2),
        "calibration_error": round(cal_error, 4),
        "ready_for_real_money": ready,
        "last_check_at": datetime.now(timezone.utc).isoformat(),
        "failure_reasons": reasons,
    })
    save_state(state)

    return {
        "ready": ready,
        "reasons": reasons,
        "metrics": {
            "settled_bets": settled,
            "avg_clv_pct": round(avg_clv, 2),
            "roi_pct": round(roi, 2),
            "win_rate_pct": round(win_rate, 2),
            "calibration_error": round(cal_error, 4),
            "total_staked": round(total_staked, 2),
            "total_pnl": round(total_pnl, 2),
        },
    }


def is_ready_for_real_money() -> bool:
    """Quick check: is the system ready for real money?"""
    result = validate_readiness()
    return result["ready"]


def refuse_real_money_if_not_ready() -> Optional[dict]:
    """
    Call this before any real-money bet. Returns None if ready,
    or a refusal dict with reasons if not ready.
    """
    result = validate_readiness()
    if result["ready"]:
        return None

    logger.warning(
        f"[SHADOW] REAL MONEY REFUSED: {len(result['reasons'])} criteria not met. "
        f"Metrics: {result['metrics']}"
    )
    return {
        "refused": True,
        "reason": "Shadow validation criteria not met",
        "criteria_failures": result["reasons"],
        "current_metrics": result["metrics"],
    }


def get_shadow_status() -> dict:
    """Get full shadow validation status for dashboard display."""
    validation = validate_readiness()
    state = load_state()

    return {
        "mode": "SHADOW" if not validation["ready"] else "LIVE_READY",
        "ready_for_real_money": validation["ready"],
        "criteria": {
            "min_500_settled_bets": {
                "required": MIN_PAPER_BETS,
                "current": validation["metrics"]["settled_bets"],
                "met": validation["metrics"]["settled_bets"] >= MIN_PAPER_BETS,
            },
            "positive_clv": {
                "required": f">{MIN_AVG_CLV_PCT}%",
                "current": f"{validation['metrics']['avg_clv_pct']:.2f}%",
                "met": validation["metrics"]["avg_clv_pct"] > MIN_AVG_CLV_PCT,
            },
            "positive_roi": {
                "required": f">{MIN_ROI_PCT}%",
                "current": f"{validation['metrics']['roi_pct']:.2f}%",
                "met": validation["metrics"]["roi_pct"] > MIN_ROI_PCT,
            },
            "calibration_acceptable": {
                "required": f"<{MAX_CALIBRATION_ERROR*100:.1f}%",
                "current": f"{validation['metrics']['calibration_error']*100:.2f}%",
                "met": validation["metrics"]["calibration_error"] <= MAX_CALIBRATION_ERROR,
            },
        },
        "failure_reasons": validation["reasons"],
        "metrics": validation["metrics"],
        "last_check": state.get("last_check_at"),
    }
