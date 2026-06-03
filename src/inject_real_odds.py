import json
import sqlite3


def run():
    db = sqlite3.connect("data/odds_stream.db")
    cursor = db.cursor()

    with open("data/betarabia_api_responses.json", "r", encoding="utf-8") as f:
        responses = json.load(f)

    for r in responses:
        if "prematch-event-odds.json" in r.get("url", ""):
            data = r.get("data", {})
            odds_dict = data.get("odds", {})

            for odd_id, odd_data in odds_dict.items():
                event_id = str(odd_data.get("event_id"))
                raw_odds = float(odd_data.get("odd_value", 0.0))
                selection = odd_data.get("name", "Unknown")
                market_name = odd_data.get("marketName", "Match Result")

                market_id = f"{event_id}_{odd_id}"

                if raw_odds > 0:
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO market 
                        (market_id, fixture_id, market_name, selection_name, raw_odds, prop_player, prop_type, prop_line, scraped_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            market_id,
                            event_id,
                            market_name,
                            selection,
                            raw_odds,
                            None,
                            None,
                            None,
                            "2026-06-03",
                        ),
                    )

    db.commit()
    db.close()
    print("Injected real odds successfully!")


if __name__ == "__main__":
    run()
