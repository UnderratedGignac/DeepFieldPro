import os
import pandas as pd
import sqlite3
import matplotlib.pyplot as plt

LOG_FILE = os.path.join(
    os.path.dirname(__file__), "..", "data", "lineup_latency_log.csv"
)
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "odds_stream.db")
PLOTS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "plots")


def analyze_survival_windows():
    if not os.path.exists(LOG_FILE):
        print(f"Error: {LOG_FILE} not found. Please run lineup_monitor.py first.")
        return

    if not os.path.exists(DB_PATH):
        print(f"Error: {DB_PATH} not found. Please run odds_feed.py first.")
        return

    if not os.path.exists(PLOTS_DIR):
        os.makedirs(PLOTS_DIR)

    # 1. Load Lineup Times
    lineup_df = pd.read_csv(LOG_FILE, parse_dates=["lineup_received_at"])
    lineup_df = lineup_df[lineup_df["status"] == "success"]

    if lineup_df.empty:
        print("No successful lineup data found to analyze.")
        return

    # 2. Load Odds Data
    conn = sqlite3.connect(DB_PATH)
    odds_df = pd.read_sql_query(
        "SELECT * FROM odds_feed", conn, parse_dates=["timestamp"]
    )
    conn.close()

    if odds_df.empty:
        print("No odds data found to analyze.")
        return

    # 3. Merge and Calculate Window
    # For simplicity, we loop through each lineup event
    results = []

    for _, row in lineup_df.iterrows():
        match_id = str(row["match_id"])
        drop_time = row["lineup_received_at"]

        # Filter odds for this match after the lineup drop
        match_odds = odds_df[
            (odds_df["match_id"] == match_id) & (odds_df["timestamp"] >= drop_time)
        ].copy()

        if match_odds.empty:
            continue

        # Group by selection to see price movements
        for selection, group in match_odds.groupby("selection_name"):
            group = group.sort_values("timestamp")
            initial_price = group.iloc[0]["price"]

            for _, odd_row in group.iterrows():
                time_diff = (odd_row["timestamp"] - drop_time).total_seconds()
                movement_pct = (
                    abs((odd_row["price"] - initial_price) / initial_price) * 100
                )

                results.append(
                    {
                        "match_id": match_id,
                        "selection": selection,
                        "seconds_since_drop": time_diff,
                        "movement_pct": movement_pct,
                    }
                )

    if not results:
        print("No intersecting lineup and odds data found.")
        return

    res_df = pd.DataFrame(results)

    # 4. Plot
    plt.figure(figsize=(10, 6))
    plt.scatter(res_df["seconds_since_drop"], res_df["movement_pct"], alpha=0.5)
    plt.title("Odds Movement % vs Time Since Lineup Drop (Survival Window)")
    plt.xlabel("Seconds Since Lineup Drop")
    plt.ylabel("Odds Movement %")
    plt.grid(True)

    plot_path = os.path.join(PLOTS_DIR, "survival_window.png")
    plt.savefig(plot_path)
    print(f"Survival window analysis complete. Plot saved to: {plot_path}")


if __name__ == "__main__":
    analyze_survival_windows()
