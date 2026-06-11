import sqlite3
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import logging
from datetime import datetime, timedelta
from src.services.alerting import notifier

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ODDS_DB = os.path.join(BASE_DIR, "data", "deepfield_browser_data", "completed_fixtures.db")

def detect_steam_moves():
    """
    Scans recent odds history for rapid price drops (Steam) that indicate sharp money.
    """
    if not os.path.exists(ODDS_DB):
        return []

    try:
        conn = sqlite3.connect(ODDS_DB)
        cur = conn.cursor()

        # 1. Get unique active fixtures from the last 15 mins
        time_limit = (datetime.now() - timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("SELECT DISTINCT fixture_id, market, selection FROM odds_history WHERE timestamp >= ?", (time_limit,))
        targets = cur.fetchall()

        steam_alerts = []

        for fid, market, selection in targets:
            # 2. Get history for this specific selection
            cur.execute(
                "SELECT odds, timestamp FROM odds_history WHERE fixture_id = ? AND market = ? AND selection = ? ORDER BY timestamp DESC LIMIT 20",
                (fid, market, selection)
            )
            rows = cur.fetchall()
            if len(rows) < 5: continue

            latest_odds = rows[0][0]
            # Look back ~10 mins
            old_odds = rows[-1][0]

            if latest_odds < old_odds * 0.90: # 10% drop
                drop_pct = ((old_odds - latest_odds) / old_odds) * 100
                
                alert_msg = (
                    f"🚀 *MARKET MOMENTUM DETECTED*\n\n"
                    f"*Match ID:* {fid}\n"
                    f"*Selection:* {market} - {selection}\n"
                    f"*Move:* {old_odds:.2f} ➔ {latest_odds:.2f} ({drop_pct:.1f}% Drop)\n\n"
                    f"⚠️ _Sharp money detected. Odds are steaming._"
                )
                
                # Deduplication: Check if we already alerted on this in the last hour
                # (Simplified for now: just return it)
                steam_alerts.append(alert_msg)

        conn.close()
        return steam_alerts

    except Exception as e:
        logger.error(f"Momentum detection failed: {e}")
        return []

if __name__ == "__main__":
    alerts = detect_steam_moves()
    for a in alerts:
        notifier.send_general_alert("Steam Move Alert", a)
