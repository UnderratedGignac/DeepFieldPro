"""
clv_tracker_v2.py — Complete CLV tracking system.
==================================================
Records the full lifecycle of every bet's odds:
  1. Opening odds (first price seen from the book)
  2. Bet odds (the price we actually got)
  3. Closing odds (final price at kickoff)
  4. CLV calculation: (closing_odds - bet_odds) / bet_odds * 100

Produces weekly reports with:
  - Average CLV across all bets
  - CLV by market type
  - CLV by league
  - CLV by bet source (strategy)
  - Win rate, ROI, calibration error

All data stored in SQLite (data/clv_tracking.db).
No SQLAlchemy dependency — uses raw sqlite3 like the rest of the system.
"""

import os
import sqlite3
import json
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
CLV_DB = os.path.join(DATA_DIR, "clv_tracking.db")


def _conn():
    """Get a connection to the CLV tracking database."""
    conn = sqlite3.connect(CLV_DB, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = _conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS clv_bets (
                bet_id TEXT PRIMARY KEY,
                fixture_id TEXT,
                match_name TEXT,
                league TEXT,
                market_type TEXT DEFAULT '1X2',
                selection TEXT,
                bet_source TEXT,

                -- Odds lifecycle
                opening_odds REAL,
                bet_odds REAL,
                closing_odds REAL,
                pinnacle_opening_odds REAL,
                pinnacle_bet_odds REAL,
                pinnacle_closing_odds REAL,

                -- Probabilities
                pinnacle_devig_prob REAL,
                implied_prob REAL,

                -- CLV metrics
                clv_pct REAL,
                weighted_clv REAL,
                clv_vs_pinnacle REAL,

                -- Outcome
                stake REAL DEFAULT 0.0,
                result TEXT DEFAULT 'OPEN',
                pnl REAL DEFAULT 0.0,
                actual_prob REAL,

                -- Timestamps
                opening_seen_at REAL,
                bet_placed_at REAL,
                closing_captured_at REAL,
                settled_at REAL,

                -- Metadata
                edge_at_placement REAL,
                ev_at_placement REAL,
                week_number TEXT,
                notes TEXT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS clv_weekly_reports (
                week_number TEXT PRIMARY KEY,
                week_start TEXT,
                week_end TEXT,
                total_bets INTEGER,
                settled_bets INTEGER,
                wins INTEGER,
                losses INTEGER,
                total_staked REAL,
                total_pnl REAL,
                roi_pct REAL,
                avg_clv_pct REAL,
                median_clv_pct REAL,
                positive_clv_count INTEGER,
                positive_clv_rate REAL,
                avg_clv_by_market TEXT,
                avg_clv_by_league TEXT,
                avg_clv_by_source TEXT,
                calibration_error REAL,
                generated_at TEXT
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_clv_week ON clv_bets(week_number)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_clv_league ON clv_bets(league)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_clv_source ON clv_bets(bet_source)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_clv_market ON clv_bets(market_type)
        """)

        conn.commit()
    finally:
        conn.close()


def _week_number(dt: Optional[datetime] = None) -> str:
    """ISO week number as YYYY-Www."""
    if dt is None:
        dt = datetime.now(timezone.utc)
    return dt.strftime("%Y-W%W")


def record_bet(
    bet_id: str,
    fixture_id: Optional[str],
    match_name: str,
    league: str,
    selection: str,
    bet_source: str,
    opening_odds: float,
    bet_odds: float,
    pinnacle_devig_prob: float = 0.0,
    pinnacle_opening_odds: float = 0.0,
    pinnacle_bet_odds: float = 0.0,
    edge: float = 0.0,
    ev: float = 0.0,
    stake: float = 0.0,
    market_type: str = "1X2",
):
    """Record a new bet with opening and bet odds."""
    conn = _conn()
    try:
        now = time.time()
        implied_prob = 1.0 / bet_odds if bet_odds > 1.0 else 0.0

        conn.execute(
            """INSERT OR REPLACE INTO clv_bets
               (bet_id, fixture_id, match_name, league, market_type, selection,
                bet_source, opening_odds, bet_odds, pinnacle_opening_odds,
                pinnacle_bet_odds, pinnacle_devig_prob, implied_prob,
                edge_at_placement, ev_at_placement, stake,
                bet_placed_at, opening_seen_at, week_number)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                bet_id,
                str(fixture_id) if fixture_id else None,
                match_name,
                league,
                market_type,
                selection,
                bet_source,
                opening_odds,
                bet_odds,
                pinnacle_opening_odds,
                pinnacle_bet_odds,
                pinnacle_devig_prob,
                implied_prob,
                edge,
                ev,
                stake,
                now,
                now,
                _week_number(),
            ),
        )
        conn.commit()
        logger.debug(f"[CLV] Recorded bet {bet_id}: {match_name} ({selection}) @ {bet_odds}")
    finally:
        conn.close()


def record_closing_odds(
    bet_id: str,
    closing_odds: float,
    pinnacle_closing_odds: float = 0.0,
):
    """Record the closing odds for a bet (captured at kickoff)."""
    conn = _conn()
    try:
        now = time.time()

        # Calculate CLV
        clv_pct = 0.0
        clv_vs_pinnacle = 0.0

        row = conn.execute(
            "SELECT bet_odds, pinnacle_bet_odds FROM clv_bets WHERE bet_id=?",
            (bet_id,),
        ).fetchone()

        if row:
            bet_odds = row["bet_odds"]
            if bet_odds and bet_odds > 0 and closing_odds and closing_odds > 0:
                # CLV = how much better our odds were vs the close
                # Positive = we got better odds than the closing line
                clv_pct = (closing_odds - bet_odds) / bet_odds * 100.0

            pin_bet = row["pinnacle_bet_odds"]
            if pin_bet and pin_bet > 0 and pinnacle_closing_odds and pinnacle_closing_odds > 0:
                clv_vs_pinnacle = (pinnacle_closing_odds - pin_bet) / pin_bet * 100.0

        conn.execute(
            """UPDATE clv_bets SET closing_odds=?, pinnacle_closing_odds=?,
               clv_pct=?, clv_vs_pinnacle=?, closing_captured_at=?
               WHERE bet_id=?""",
            (closing_odds, pinnacle_closing_odds, clv_pct, clv_vs_pinnacle, now, bet_id),
        )
        conn.commit()
        logger.debug(f"[CLV] Closing odds for {bet_id}: {closing_odds} (CLV={clv_pct:.2f}%)")
    finally:
        conn.close()


def settle_bet(bet_id: str, result: str, pnl: float, actual_prob: float = 0.0):
    """Settle a bet with final result (WIN/LOSS/VOID)."""
    conn = _conn()
    try:
        now = time.time()
        conn.execute(
            """UPDATE clv_bets SET result=?, pnl=?, actual_prob=?, settled_at=?
               WHERE bet_id=?""",
            (result, pnl, actual_prob, now, bet_id),
        )
        conn.commit()
        logger.debug(f"[CLV] Settled {bet_id}: {result} PnL={pnl:.2f}")
    finally:
        conn.close()


def get_clv_summary(min_bets: int = 1) -> dict:
    """
    Get overall CLV summary statistics.

    Returns dict with: total_bets, avg_clv, median_clv, positive_clv_rate,
    roi, win_rate, calibration_error, by_market, by_league, by_source.
    """
    conn = _conn()
    try:
        # Overall stats
        row = conn.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN result != 'OPEN' THEN 1 ELSE 0 END) as settled,
                SUM(CASE WHEN result = 'WIN' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN result = 'LOSS' THEN 1 ELSE 0 END) as losses,
                SUM(stake) as total_staked,
                SUM(pnl) as total_pnl,
                AVG(clv_pct) as avg_clv,
                AVG(CASE WHEN clv_pct > 0 THEN 1.0 ELSE 0.0 END) * 100 as pos_clv_rate
            FROM clv_bets
            WHERE bet_id IS NOT NULL
        """).fetchone()

        if not row or row["total"] < min_bets:
            return {"total_bets": 0, "error": f"Need {min_bets}+ bets, have {row['total'] if row else 0}"}

        total = row["total"]
        settled = row["settled"] or 0
        wins = row["wins"] or 0
        losses = row["losses"] or 0
        total_staked = row["total_staked"] or 0
        total_pnl = row["total_pnl"] or 0
        avg_clv = row["avg_clv"] or 0
        pos_clv_rate = row["pos_clv_rate"] or 0

        roi = (total_pnl / total_staked * 100) if total_staked > 0 else 0
        win_rate = (wins / settled * 100) if settled > 0 else 0

        # Median CLV
        median_row = conn.execute("""
            SELECT clv_pct FROM clv_bets
            WHERE clv_pct IS NOT NULL AND clv_pct != 0
            ORDER BY clv_pct LIMIT 1 OFFSET ?
        """, (total // 2,)).fetchone()
        median_clv = median_row["clv_pct"] if median_row else 0

        # By market
        by_market = {}
        for r in conn.execute("""
            SELECT market_type, COUNT(*) as cnt, AVG(clv_pct) as avg_clv,
                   SUM(stake) as staked, SUM(pnl) as pnl
            FROM clv_bets GROUP BY market_type
        """).fetchall():
            by_market[r["market_type"]] = {
                "bets": r["cnt"],
                "avg_clv": round(r["avg_clv"] or 0, 2),
                "roi": round((r["pnl"] / r["staked"] * 100) if r["staked"] else 0, 2),
            }

        # By league
        by_league = {}
        for r in conn.execute("""
            SELECT league, COUNT(*) as cnt, AVG(clv_pct) as avg_clv,
                   SUM(stake) as staked, SUM(pnl) as pnl
            FROM clv_bets WHERE league IS NOT NULL GROUP BY league
        """).fetchall():
            by_league[r["league"]] = {
                "bets": r["cnt"],
                "avg_clv": round(r["avg_clv"] or 0, 2),
                "roi": round((r["pnl"] / r["staked"] * 100) if r["staked"] else 0, 2),
            }

        # By source (strategy)
        by_source = {}
        for r in conn.execute("""
            SELECT bet_source, COUNT(*) as cnt, AVG(clv_pct) as avg_clv,
                   SUM(stake) as staked, SUM(pnl) as pnl
            FROM clv_bets WHERE bet_source IS NOT NULL GROUP BY bet_source
        """).fetchall():
            by_source[r["bet_source"]] = {
                "bets": r["cnt"],
                "avg_clv": round(r["avg_clv"] or 0, 2),
                "roi": round((r["pnl"] / r["staked"] * 100) if r["staked"] else 0, 2),
            }

        # Calibration error: |predicted_prob - actual_prob| averaged
        cal_row = conn.execute("""
            SELECT AVG(ABS(implied_prob - actual_prob)) as cal_err
            FROM clv_bets
            WHERE actual_prob > 0 AND implied_prob > 0
        """).fetchone()
        cal_error = cal_row["cal_err"] if cal_row and cal_row["cal_err"] else 0

        return {
            "total_bets": total,
            "settled_bets": settled,
            "wins": wins,
            "losses": losses,
            "total_staked": round(total_staked, 2),
            "total_pnl": round(total_pnl, 2),
            "roi_pct": round(roi, 2),
            "win_rate_pct": round(win_rate, 2),
            "avg_clv_pct": round(avg_clv, 2),
            "median_clv_pct": round(median_clv, 2),
            "positive_clv_rate_pct": round(pos_clv_rate, 2),
            "calibration_error": round(cal_error, 4),
            "by_market": by_market,
            "by_league": by_league,
            "by_source": by_source,
        }
    finally:
        conn.close()


def generate_weekly_report() -> dict:
    """Generate and store a weekly CLV report."""
    conn = _conn()
    try:
        now = datetime.now(timezone.utc)
        week_start = now - timedelta(days=7)
        week_num = _week_number(now)

        summary = get_clv_summary()
        if summary.get("total_bets", 0) == 0:
            return {"error": "No bets to report"}

        report = {
            "week_number": week_num,
            "week_start": week_start.isoformat(),
            "week_end": now.isoformat(),
            **summary,
            "generated_at": now.isoformat(),
        }

        # Store report
        conn.execute(
            """INSERT OR REPLACE INTO clv_weekly_reports
               (week_number, week_start, week_end, total_bets, settled_bets,
                wins, losses, total_staked, total_pnl, roi_pct, avg_clv_pct,
                median_clv_pct, positive_clv_count, positive_clv_rate,
                avg_clv_by_market, avg_clv_by_league, avg_clv_by_source,
                calibration_error, generated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                week_num,
                report["week_start"],
                report["week_end"],
                summary["total_bets"],
                summary["settled_bets"],
                summary["wins"],
                summary["losses"],
                summary["total_staked"],
                summary["total_pnl"],
                summary["roi_pct"],
                summary["avg_clv_pct"],
                summary["median_clv_pct"],
                int(summary["positive_clv_rate_pct"] * summary["total_bets"] / 100),
                summary["positive_clv_rate_pct"],
                json.dumps(summary["by_market"]),
                json.dumps(summary["by_league"]),
                json.dumps(summary["by_source"]),
                summary["calibration_error"],
                report["generated_at"],
            ),
        )
        conn.commit()

        logger.info(
            f"[CLV] Weekly report {week_num}: {summary['total_bets']} bets, "
            f"CLV={summary['avg_clv_pct']:.2f}%, ROI={summary['roi_pct']:.2f}%"
        )
        return report
    finally:
        conn.close()


def capture_closing_odds_from_pinnacle(fixture_id: str):
    """
    Capture closing odds from the latest Pinnacle snapshot for all bets
    on a given fixture. Called at kickoff time.
    """
    try:
        from tools.pinnacle_value import get_pinnacle_latest

        conn = _conn()
        try:
            bets = conn.execute(
                "SELECT bet_id, match_name, selection FROM clv_bets "
                "WHERE fixture_id=? AND closing_odds IS NULL",
                (str(fixture_id),),
            ).fetchall()

            for bet in bets:
                match_parts = bet["match_name"].split(" vs ")
                if len(match_parts) != 2:
                    continue
                home, away = match_parts[0].strip(), match_parts[1].strip()
                pin = get_pinnacle_latest(home, away, bet["selection"])
                if pin:
                    record_closing_odds(
                        bet["bet_id"],
                        closing_odds=0,  # We don't have soft-book closing odds directly
                        pinnacle_closing_odds=pin["decimal_odds"],
                    )
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"[CLV] Error capturing closing odds: {e}")


# Initialize on import
init_db()
