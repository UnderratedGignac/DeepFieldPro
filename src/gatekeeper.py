"""
gatekeeper.py — Real-money bet gatekeeper.
============================================
The SINGLE chokepoint that ALL real-money bet paths must pass through.
Refuses to place real-money bets until the shadow validation criteria are met.

This module wraps the shadow_framework validation and adds additional checks:
  1. Shadow validation (500+ bets, positive CLV, positive ROI, calibration)
  2. Diagnostics check (market/league not disabled)
  3. Daily exposure limits
  4. Bankroll sanity checks

Usage:
    from src.gatekeeper import check_real_money_gate

    refusal = check_real_money_gate(
        market="1X2",
        league="Premier League",
        strategy="PINNACLE_VALUE",
        stake=25.0,
    )
    if refusal:
        # Real money refused — log the refusal and skip
        print(f"Real money refused: {refusal['reason']}")
    else:
        # Gate passed — proceed with real money
        place_real_bet(...)
"""

import os
import json
import sqlite3
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")


def load_settings() -> dict:
    try:
        with open(SETTINGS_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def check_real_money_gate(
    market: str = "1X2",
    league: str = "",
    strategy: str = "",
    stake: float = 0.0,
) -> Optional[dict]:
    """
    Check if a real-money bet is allowed.

    Returns None if the bet is allowed, or a refusal dict if refused.
    """
    settings = load_settings()

    # ── Check 1: Global kill switch ──────────────────────────────────────
    # DEEPFIELD_ARENA_LIVE env var must be set to "1" for ANY real money
    arena_live = os.getenv("DEEPFIELD_ARENA_LIVE", "0").strip() == "1"
    if not arena_live:
        return {
            "refused": True,
            "reason": "DEEPFIELD_ARENA_LIVE != 1",
            "level": "HARD_GATE",
        }

    # ── Check 2: Shadow validation ───────────────────────────────────────
    try:
        from src.shadow_framework import validate_readiness
        validation = validate_readiness()
        if not validation["ready"]:
            return {
                "refused": True,
                "reason": "Shadow validation criteria not met",
                "level": "SHADOW_VALIDATION",
                "criteria_failures": validation["reasons"],
                "current_metrics": validation["metrics"],
            }
    except Exception as e:
        logger.error(f"[GATEKEEPER] Shadow validation error: {e}")
        return {
            "refused": True,
            "reason": f"Shadow validation error: {e}",
            "level": "VALIDATION_ERROR",
        }

    # ── Check 3: Diagnostics — is this market/league/strategy disabled? ──
    try:
        from src.diagnostics import should_disable
        if should_disable(market=market, league=league, strategy=strategy):
            return {
                "refused": True,
                "reason": f"Market/league/strategy disabled by diagnostics: "
                          f"market={market}, league={league}, strategy={strategy}",
                "level": "DIAGNOSTICS",
            }
    except Exception as e:
        logger.warning(f"[GATEKEEPER] Diagnostics check error: {e}")
        # Don't block on diagnostics errors — they're advisory

    # ── Check 4: Bankroll sanity ─────────────────────────────────────────
    try:
        br_conn = sqlite3.connect(os.path.join(DATA_DIR, "bankroll.db"))
        balance = br_conn.execute(
            "SELECT current_balance FROM bankroll ORDER BY date DESC LIMIT 1"
        ).fetchone()[0]
        br_conn.close()

        if stake > balance:
            return {
                "refused": True,
                "reason": f"Stake ${stake:.2f} exceeds balance ${balance:.2f}",
                "level": "BANKROLL",
            }

        # Don't bet more than 2% of bankroll on a single bet
        max_single = balance * 0.02
        if stake > max_single:
            return {
                "refused": True,
                "reason": f"Stake ${stake:.2f} exceeds 2% of bankroll (${max_single:.2f})",
                "level": "BANKROLL",
            }
    except Exception as e:
        logger.warning(f"[GATEKEEPER] Bankroll check error: {e}")

    # ── Check 5: Daily exposure limit ────────────────────────────────────
    try:
        max_daily_exposure_pct = settings.get("max_daily_exposure_pct", 0.10)
        br_conn = sqlite3.connect(os.path.join(DATA_DIR, "bankroll.db"))
        row = br_conn.execute(
            "SELECT starting_balance, daily_exposure FROM bankroll WHERE date = ?",
            (datetime.now(timezone.utc).date().isoformat(),),
        ).fetchone()
        br_conn.close()

        if row:
            starting_balance, daily_exposure = row
            exposure_cap = starting_balance * max_daily_exposure_pct
            if daily_exposure + stake > exposure_cap:
                return {
                    "refused": True,
                    "reason": f"Daily exposure ${daily_exposure + stake:.2f} would exceed "
                              f"cap ${exposure_cap:.2f} ({max_daily_exposure_pct:.0%} of "
                              f"${starting_balance:.2f})",
                    "level": "DAILY_EXPOSURE",
                }
    except Exception as e:
        logger.warning(f"[GATEKEEPER] Daily exposure check error: {e}")

    # ── All checks passed ────────────────────────────────────────────────
    logger.info(
        f"[GATEKEEPER] Real-money bet APPROVED: {market} {league} "
        f"{strategy} stake=${stake:.2f}"
    )
    return None


def get_gate_status() -> dict:
    """Get the current status of all gate checks for dashboard display."""
    try:
        from src.shadow_framework import get_shadow_status
        shadow_status = get_shadow_status()
    except Exception:
        shadow_status = {"mode": "ERROR", "ready_for_real_money": False}

    arena_live = os.getenv("DEEPFIELD_ARENA_LIVE", "0").strip() == "1"

    return {
        "arena_live_gate": arena_live,
        "shadow_validation": shadow_status,
        "overall_status": "LIVE" if (arena_live and shadow_status.get("ready_for_real_money")) else "SHADOW",
    }
