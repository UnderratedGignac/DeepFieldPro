import json
import os

PARLAYS_FILE = "data/smart_parlays.json"


def get_bankroll_status():
    return {"current_balance": 15420.50, "total_pnl": 1240.25, "roi": 8.1}


def get_active_parlays():
    if os.path.exists(PARLAYS_FILE):
        with open(PARLAYS_FILE, "r") as f:
            data = json.load(f)
            return data.get("top_parlays", [])
    return []
