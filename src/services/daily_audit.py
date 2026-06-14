import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import sqlite3
import logging
from datetime import datetime, timedelta, timezone
from src.dfp_config import settings
from src.services.alerting import notifier

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BET_LOG_DB = os.path.join(BASE_DIR, "data", "bet_log.db")

def run_daily_audit():
    """
    Analyzes performance for the last 24 hours and sends a WhatsApp report.
    """
    if not os.path.exists(BET_LOG_DB):
        logger.error(f"Bet log DB not found at {BET_LOG_DB}")
        return

    try:
        conn = sqlite3.connect(BET_LOG_DB)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Time range: Last 24 hours
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")

        # 1. Total Staked & Settled Count
        cur.execute("SELECT COUNT(*), SUM(stake) FROM bet_log WHERE placed_at >= ?", (yesterday,))
        total_bets, total_staked = cur.fetchone()
        total_staked = total_staked or 0.0

        # 2. Results & PnL
        cur.execute("SELECT COUNT(*) FROM bet_log WHERE placed_at >= ? AND result = 'W'", (yesterday,))
        wins = cur.fetchone()[0] or 0
        
        cur.execute("SELECT COUNT(*) FROM bet_log WHERE placed_at >= ? AND result = 'L'", (yesterday,))
        losses = cur.fetchone()[0] or 0
        
        cur.execute("SELECT SUM(pnl) FROM bet_log WHERE placed_at >= ? AND result != 'OPEN'", (yesterday,))
        daily_pnl = cur.fetchone()[0] or 0.0

        # 3. Average CLV (Closing Line Value)
        cur.execute("SELECT AVG(clv) FROM bet_log WHERE placed_at >= ? AND clv IS NOT NULL", (yesterday,))
        avg_clv = cur.fetchone()[0] or 0.0

        # 4. Top Win & Worst Loss
        cur.execute("SELECT match_id, pnl FROM bet_log WHERE placed_at >= ? ORDER BY pnl DESC LIMIT 1", (yesterday,))
        top_win = cur.fetchone()
        
        cur.execute("SELECT match_id, pnl FROM bet_log WHERE placed_at >= ? ORDER BY pnl ASC LIMIT 1", (yesterday,))
        worst_loss = cur.fetchone()

        conn.close()

        # Calculation
        win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
        roi = (daily_pnl / total_staked * 100) if total_staked > 0 else 0

        # Format Message
        report = (
            f"*📊 DeepField Daily Institutional Audit*\n"
            f"_{datetime.now().strftime('%d %b %Y')}_\n\n"
            f"*Performance Summary:*\n"
            f"• Net PnL: {'+' if daily_pnl >= 0 else ''}${daily_pnl:.2f}\n"
            f"• daily ROI: {roi:+.1f}%\n"
            f"• Win Rate: {win_rate:.1f}% ({wins}W / {losses}L)\n"
            f"• Total Staked: ${total_staked:.2f}\n\n"
            f"*Alpha Tracking:*\n"
            f"• Avg CLV: {avg_clv*100:+.2f}% {'✅ Beat Market' if avg_clv > 0 else '❌ Lagging'}\n"
            f"• Active Regime: {'Safety' if roi < -10 else 'Growth'}\n\n"
            f"*Highlights:*\n"
            f"🏆 Best: {top_win['match_id'] if top_win else 'N/A'} (${top_win['pnl'] if top_win else 0:+.2f})\n"
            f"⚠️ Worst: {worst_loss['match_id'] if worst_loss else 'N/A'} (${worst_loss['pnl'] if worst_loss else 0:+.2f})\n\n"
            f"_Audit Complete. Capital Engine Secure._"
        )

        notifier.send_general_alert("Daily Performance Audit", report)
        logger.info("Daily audit report sent successfully.")

    except Exception as e:
        logger.error(f"Daily audit failed: {e}")

if __name__ == "__main__":
    run_daily_audit()
