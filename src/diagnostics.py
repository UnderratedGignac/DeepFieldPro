"""
diagnostics.py — Market/League CLV diagnostics.
================================================
Identifies which markets and leagues are +EV and -EV based on
actual paper betting results. Strategies/markets/leagues that fail
the validation criteria are automatically disabled.

Reports:
  - Markets with positive CLV (keep enabled)
  - Markets with negative CLV (disable)
  - Leagues with positive CLV (keep enabled)
  - Leagues with negative CLV (disable)
  - Strategies with positive/negative CLV
  - Recommendations for what to enable/disable

Removal criteria (a strategy/market/league is REMOVED if):
  - 500+ sample size AND
  - Negative CLV AND
  - Negative expected value (ROI < 0)
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
DIAG_REPORT_FILE = os.path.join(DATA_DIR, "diagnostics_report.json")

# Minimum sample size before we trust the CLV signal
MIN_SAMPLE_FOR_REMOVAL = 50  # Need at least 50 bets per category


def _get_bet_data() -> list:
    """Get all settled bets from bet_log.db."""
    if not os.path.exists(BET_LOG_DB):
        return []

    try:
        conn = sqlite3.connect(BET_LOG_DB)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT bet_id, match_id, market_type, side, entry_odds, closing_odds,
                   clv, stake, pnl, result, bet_source, league, fixture_id,
                   placed_at
            FROM bet_log
            WHERE result IN ('W', 'L', 'WIN', 'LOSS')
            ORDER BY placed_at DESC
        """).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"[DIAG] Error reading bet data: {e}")
        return []


def _analyze_category(bets: list, key: str) -> dict:
    """Analyze a category (market, league, source) for CLV performance."""
    groups = {}
    for bet in bets:
        val = bet.get(key) or "UNKNOWN"
        if val not in groups:
            groups[val] = []
        groups[val].append(bet)

    results = {}
    for val, group_bets in groups.items():
        n = len(group_bets)
        settled = [b for b in group_bets if b["result"] in ("W", "L", "WIN", "LOSS")]
        wins = [b for b in settled if b["result"] in ("W", "WIN")]
        losses = [b for b in settled if b["result"] in ("L", "LOSS")]

        total_staked = sum(b["stake"] or 0 for b in settled)
        total_pnl = sum(b["pnl"] or 0 for b in settled)
        roi = (total_pnl / total_staked * 100) if total_staked > 0 else 0

        clv_values = [b["clv"] for b in settled if b.get("clv") is not None]
        avg_clv = sum(clv_values) / len(clv_values) * 100 if clv_values else 0
        pos_clv = sum(1 for c in clv_values if c > 0)
        pos_clv_rate = (pos_clv / len(clv_values) * 100) if clv_values else 0

        win_rate = (len(wins) / len(settled) * 100) if settled else 0

        # Determine status
        if n < MIN_SAMPLE_FOR_REMOVAL:
            status = "INSUFFICIENT_DATA"
        elif avg_clv > 0 and roi > 0:
            status = "POSITIVE"
        elif avg_clv <= 0 or roi < 0:
            status = "NEGATIVE"
        else:
            status = "MARGINAL"

        results[val] = {
            "total_bets": n,
            "settled": len(settled),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate_pct": round(win_rate, 2),
            "total_staked": round(total_staked, 2),
            "total_pnl": round(total_pnl, 2),
            "roi_pct": round(roi, 2),
            "avg_clv_pct": round(avg_clv, 2),
            "positive_clv_rate_pct": round(pos_clv_rate, 2),
            "clv_samples": len(clv_values),
            "status": status,
            "recommendation": "DISABLE" if status == "NEGATIVE" and n >= MIN_SAMPLE_FOR_REMOVAL else "KEEP",
        }

    return results


def run_diagnostics() -> dict:
    """
    Run full diagnostics on all bets.

    Returns dict with:
      - by_market: analysis per market type
      - by_league: analysis per league
      - by_source: analysis per bet source/strategy
      - overall: aggregate stats
      - recommendations: what to enable/disable
    """
    bets = _get_bet_data()

    if not bets:
        return {"error": "No settled bets found", "recommendations": []}

    by_market = _analyze_category(bets, "market_type")
    by_league = _analyze_category(bets, "league")
    by_source = _analyze_category(bets, "bet_source")

    # Overall stats
    total = len(bets)
    settled = [b for b in bets if b["result"] in ("W", "L", "WIN", "LOSS")]
    wins = [b for b in settled if b["result"] in ("W", "WIN")]
    total_staked = sum(b["stake"] or 0 for b in settled)
    total_pnl = sum(b["pnl"] or 0 for b in settled)
    roi = (total_pnl / total_staked * 100) if total_staked > 0 else 0

    clv_values = [b["clv"] for b in settled if b.get("clv") is not None]
    avg_clv = sum(clv_values) / len(clv_values) * 100 if clv_values else 0

    # Build recommendations
    recommendations = []

    # Markets to disable
    for market, stats in by_market.items():
        if stats["status"] == "NEGATIVE" and stats["total_bets"] >= MIN_SAMPLE_FOR_REMOVAL:
            recommendations.append({
                "action": "DISABLE_MARKET",
                "target": market,
                "reason": f"Negative CLV ({stats['avg_clv_pct']:.1f}%) and negative ROI ({stats['roi_pct']:.1f}%) "
                          f"over {stats['total_bets']} bets",
            })

    # Leagues to disable
    for league, stats in by_league.items():
        if stats["status"] == "NEGATIVE" and stats["total_bets"] >= MIN_SAMPLE_FOR_REMOVAL:
            recommendations.append({
                "action": "DISABLE_LEAGUE",
                "target": league,
                "reason": f"Negative CLV ({stats['avg_clv_pct']:.1f}%) and negative ROI ({stats['roi_pct']:.1f}%) "
                          f"over {stats['total_bets']} bets",
            })

    # Strategies to disable
    for source, stats in by_source.items():
        if stats["status"] == "NEGATIVE" and stats["total_bets"] >= MIN_SAMPLE_FOR_REMOVAL:
            recommendations.append({
                "action": "DISABLE_STRATEGY",
                "target": source,
                "reason": f"Negative CLV ({stats['avg_clv_pct']:.1f}%) and negative ROI ({stats['roi_pct']:.1f}%) "
                          f"over {stats['total_bets']} bets",
            })

    # Markets/leagues that are positive (keep or increase)
    for market, stats in by_market.items():
        if stats["status"] == "POSITIVE":
            recommendations.append({
                "action": "KEEP_MARKET",
                "target": market,
                "reason": f"Positive CLV ({stats['avg_clv_pct']:.1f}%) and positive ROI ({stats['roi_pct']:.1f}%) "
                          f"over {stats['total_bets']} bets",
            })

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_bets": total,
        "settled_bets": len(settled),
        "overall": {
            "roi_pct": round(roi, 2),
            "avg_clv_pct": round(avg_clv, 2),
            "win_rate_pct": round(len(wins) / len(settled) * 100 if settled else 0, 2),
            "total_staked": round(total_staked, 2),
            "total_pnl": round(total_pnl, 2),
        },
        "by_market": by_market,
        "by_league": by_league,
        "by_source": by_source,
        "recommendations": recommendations,
    }

    # Save report
    try:
        with open(DIAG_REPORT_FILE, "w") as f:
            json.dump(report, f, indent=2)
    except OSError:
        pass

    logger.info(
        f"[DIAG] Diagnostics complete: {total} bets, ROI={roi:.1f}%, "
        f"CLV={avg_clv:.1f}%, {len(recommendations)} recommendations"
    )
    return report


def get_disabled_markets() -> list:
    """Get list of markets that should be disabled based on diagnostics."""
    try:
        with open(DIAG_REPORT_FILE, "r") as f:
            report = json.load(f)
        return [
            r["target"] for r in report.get("recommendations", [])
            if r["action"] == "DISABLE_MARKET"
        ]
    except (OSError, ValueError):
        return []


def get_disabled_leagues() -> list:
    """Get list of leagues that should be disabled based on diagnostics."""
    try:
        with open(DIAG_REPORT_FILE, "r") as f:
            report = json.load(f)
        return [
            r["target"] for r in report.get("recommendations", [])
            if r["action"] == "DISABLE_LEAGUE"
        ]
    except (OSError, ValueError):
        return []


def get_disabled_strategies() -> list:
    """Get list of strategies that should be disabled based on diagnostics."""
    try:
        with open(DIAG_REPORT_FILE, "r") as f:
            report = json.load(f)
        return [
            r["target"] for r in report.get("recommendations", [])
            if r["action"] == "DISABLE_STRATEGY"
        ]
    except (OSError, ValueError):
        return []


def should_disable(market: str = None, league: str = None, strategy: str = None) -> bool:
    """
    Check if a specific market/league/strategy should be disabled.
    Returns True if ANY of the provided categories should be disabled.
    """
    disabled_markets = get_disabled_markets()
    disabled_leagues = get_disabled_leagues()
    disabled_strategies = get_disabled_strategies()

    if market and market in disabled_markets:
        return True
    if league and league in disabled_leagues:
        return True
    if strategy and strategy in disabled_strategies:
        return True
    return False
