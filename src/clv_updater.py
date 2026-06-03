"""
clv_updater.py
--------------
Fetches closing odds post-match and calculates Realized CLV for every bet.

CLV Convention:
  Positive CLV = you beat the closing line = long-run profitable signal.
  Formula: clv = (1 / closing_odds) - (1 / entry_odds)

  Example:
    Entry odds:   2.10  → implied prob = 0.476
    Closing odds: 1.90  → implied prob = 0.526
    CLV = 0.526 - 0.476 = +0.050  → You were RIGHT, market moved to agree with you.

  Anti-example (the OLD broken formula was reversed):
    OLD (wrong): clv = (1/entry) - (1/closing) = 0.476 - 0.526 = -0.050  ← WRONG SIGN
"""

import os
import sqlite3
import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))
ODDS_API_KEY = os.getenv("ODDS_API_KEY")

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "bet_log.db")


def fetch_closing_odds_from_api(match_id, sport_key="soccer_epl"):
    """
    Fetch closing odds from The Odds API for a given match.
    Requires a paid plan for historical data.
    Returns None if not available.
    """
    if not ODDS_API_KEY:
        return None

    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/events/{match_id}/odds"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "uk,eu",
        "markets": "h2h",
        "dateFormat": "iso",
        "oddsFormat": "decimal",
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            # Return the first available price from a sharp book (Pinnacle preferred)
            preferred_books = ["Pinnacle", "Betfair Exchange", "Matchbook"]
            for book_name in preferred_books:
                for bookmaker in data.get("bookmakers", []):
                    if bookmaker["title"] in preferred_books:
                        for market in bookmaker["markets"]:
                            if market["key"] == "h2h":
                                # Return first outcome price as proxy
                                return market["outcomes"][0]["price"]
    except Exception as e:
        print(f"Error fetching closing odds for {match_id}: {e}")

    return None


def update_clv():
    """
    For all bets with no closing_odds yet, attempt to fetch closing odds
    and calculate Realized CLV.

    CLV formula: clv = (1 / closing_odds) - (1 / entry_odds)
    Positive = beat the closing line = good.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    df = pd.read_sql_query("SELECT * FROM bet_log WHERE closing_odds IS NULL", conn)

    if df.empty:
        print("No pending bets to update for CLV.")
        conn.close()
        return

    print(f"Updating CLV for {len(df)} unsettled bets...")

    for _, row in df.iterrows():
        match_id = row["match_id"]
        entry_odds = float(row["entry_odds"])
        bet_id = row["bet_id"]

        # Try to get real closing odds from API
        closing_odds = fetch_closing_odds_from_api(match_id)

        if closing_odds is None:
            # No real data available yet — skip (do not mock in production)
            print(
                f"Bet {bet_id}: Closing odds not available yet for match {match_id}. Skipping."
            )
            continue

        # CORRECT CLV formula: positive = beat the closing line
        clv = (1.0 / closing_odds) - (1.0 / entry_odds)

        cursor.execute(
            """
            UPDATE bet_log
            SET closing_odds = ?, clv = ?
            WHERE bet_id = ?
        """,
            (closing_odds, clv, bet_id),
        )

        direction = "✅ BEAT" if clv > 0 else "❌ MISSED"
        print(
            f"Bet {bet_id}: Entry {entry_odds:.3f} → Close {closing_odds:.3f} | "
            f"CLV: {clv:+.4f} ({direction} closing line)"
        )

    conn.commit()
    conn.close()
    print("CLV Update Complete.")


if __name__ == "__main__":
    update_clv()
