import json
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import time
import logging
from datetime import datetime
from seleniumbase import SB
from src.services.alerting import notifier

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DASHBOARD_FILE = os.path.join(BASE_DIR, "data", "todays_dashboard_state.json")

def scan_breaking_news():
    """
    Scans football news aggregators for 'Breaking' injury or lineup news 
    related to today's high-value matches.
    """
    if not os.path.exists(DASHBOARD_FILE): return
    
    try:
        with open(DASHBOARD_FILE, "r") as f: matches = json.load(f)
    except: return

    # Focus on top 5 matches (by time) to keep scan fast
    active_matches = [m for m in matches if m.get("status_code") == "NS"][:5]
    if not active_matches: return

    keywords = ["injury", "injured", "out of", "starting", "lineup", "misses"]
    found_news = []

    with SB(uc=True, headless=True) as sb:
        for m in active_matches:
            match_name = m["match"]
            teams = match_name.split(" vs ")
            
            # Use NewsNow or similar search
            search_query = f"{match_name} lineup injury news"
            url = f"https://www.google.com/search?q={search_query.replace(' ', '+')}&tbm=nws"
            
            try:
                sb.open(url)
                time.sleep(2)
                
                # Get article titles
                titles = sb.find_elements("div[role='heading']")
                for t_el in titles[:5]: # Top 5 news items
                    text = t_el.text.lower()
                    if any(kw in text for kw in keywords):
                        # Potential breaking news
                        news_alert = (
                            f"📰 *BREAKING NEWS SNIPER*\n\n"
                            f"*Target Match:* {match_name}\n"
                            f"*Headline:* {t_el.text}\n\n"
                            f"⚠️ _Check odds immediately. Market may not have adjusted._"
                        )
                        found_news.append(news_alert)
                        break # Only one alert per match
            except Exception as e:
                logger.error(f"Error scanning news for {match_name}: {e}")

    return found_news

if __name__ == "__main__":
    alerts = scan_breaking_news()
    if alerts:
        for a in alerts:
            notifier.send_general_alert("Lineup Sniper Alert", a)
