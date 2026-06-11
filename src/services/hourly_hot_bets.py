import os
import sys
import json
import sqlite3
import logging
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from src.dfp_config import settings
from src.services.alerting import notifier

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BET_LOG_DB = os.path.join(BASE_DIR, "data", "bet_log.db")
BANKROLL_DB = os.path.join(BASE_DIR, "data", "bankroll.db")
PARLAYS_FILE = os.path.join(BASE_DIR, "data", "smart_parlays.json")

def get_current_bankroll():
    if os.path.exists(BANKROLL_DB):
        try:
            conn = sqlite3.connect(BANKROLL_DB)
            cursor = conn.cursor()
            cursor.execute("SELECT current_balance FROM bankroll ORDER BY date DESC LIMIT 1")
            row = cursor.fetchone()
            conn.close()
            if row and row[0] > 0: return row[0]
        except: pass
    return 1000.0

def run_hourly_hot_bets():
    if not os.path.exists(BET_LOG_DB):
        logger.error(f"Bet log DB not found at {BET_LOG_DB}")
        return

    try:
        conn = sqlite3.connect(BET_LOG_DB)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Check for hot bets in the last hour
        one_hour_ago = (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
        
        cur.execute("""
            SELECT match_id, market_type, side, entry_odds, edge_pct 
            FROM bet_log 
            WHERE placed_at >= ? AND result = 'OPEN' AND edge_pct > 0
            ORDER BY edge_pct DESC 
            LIMIT 10
        """, (one_hour_ago,))
        
        hot_bets = cur.fetchall()

        # Load Parlays
        top_parlays = []
        if os.path.exists(PARLAYS_FILE):
            try:
                with open(PARLAYS_FILE, "r") as f:
                    data = json.load(f)
                    top_parlays = data.get("top_parlays", [])[:3] # Get top 3
            except: pass

        if not hot_bets and not top_parlays:
            logger.info("No new hot bets or parlays in the last hour. Skipping notification.")
            conn.close()
            return

        # Calculate PnL and Record
        cur.execute("SELECT SUM(pnl) as total_pnl FROM bet_log WHERE result IN ('W', 'L', 'HALF_WON', 'HALF_LOST')")
        row = cur.fetchone()
        total_pnl = row['total_pnl'] if row and row['total_pnl'] is not None else 0.0

        cur.execute("SELECT COUNT(*) as cnt FROM bet_log WHERE result = 'W'")
        wins = cur.fetchone()['cnt']
        
        cur.execute("SELECT COUNT(*) as cnt FROM bet_log WHERE result = 'L'")
        losses = cur.fetchone()['cnt']

        conn.close()

        bankroll = get_current_bankroll()
        pnl_str = f"+${total_pnl:.2f}" if total_pnl >= 0 else f"-${abs(total_pnl):.2f}"

        # Format Message
        report = (
            f"*🔥 DeepField Hot Bets & Status*\n\n"
            f"*Current Balance:* ${bankroll:.2f}\n"
            f"*Models PnL:* {pnl_str}\n"
            f"*Record:* {wins}W - {losses}L\n\n"
        )

        if hot_bets:
            report += f"*🔥 Top Hottest Bets (Last Hour):*\n"
            for i, bet in enumerate(hot_bets, 1):
                edge = bet['edge_pct']
                edge_str = f"+{edge:.1f}%" if edge > 0 else f"{edge:.1f}%"
                report += f"{i}. {bet['match_id']} | {bet['side']} @ {bet['entry_odds']} (Edge: {edge_str})\n"
            report += "\n"

        if top_parlays:
            report += f"*🎯 Recommended Parlays:*\n"
            for i, p in enumerate(top_parlays, 1):
                report += f"*{i}. Parlay ({p['combined_odds']:.2f})*\n"
                for leg in p['legs']:
                    report += f" - {leg['match']}: {leg['selection']}\n"
                report += "\n"

        if hasattr(notifier, '_send_whatsapp'):
            notifier._send_whatsapp(report)
            logger.info("WhatsApp hot bets report sent successfully.")
        else:
            notifier.send_general_alert("Hourly Hot Bets", report)

    except Exception as e:
        logger.error(f"Hourly hot bets script failed: {e}")

if __name__ == "__main__":
    run_hourly_hot_bets()
