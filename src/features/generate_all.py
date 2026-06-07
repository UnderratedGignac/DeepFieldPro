import pandas as pd
import os
import sys

# Import our custom modules
from opponent_features import calculate_opponent_features
from player_rolling_form import calculate_player_rolling_form
from venue_effects import calculate_venue_effects
from team_tactics import calculate_team_tactics
from availability import calculate_availability_features
from market_intelligence import calculate_market_intelligence
from fatigue import calculate_fatigue_features
from referee import calculate_referee_features
from weather import integrate_weather_features


def main():
    data_path = os.path.join(
        os.path.dirname(__file__), "../../data/world_cup_players_match_logs_global.csv"
    )
    output_path = os.path.join(
        os.path.dirname(__file__), "../../data/model_ready_features.csv"
    )

    print(f"Loading raw data from: {data_path}")
    if not os.path.exists(data_path):
        print("ERROR: Raw data not found. The scraper must finish first.")
        sys.exit(1)

    df = pd.read_csv(data_path)

    # 1. Clean Column Names (soccerdata outputs MultiIndex flattened to Tuples or strings like "('Performance', 'Sh')")
    # We will rename common columns to match our scripts' expectations
    rename_map = {
        "game_": "Date",  # We will extract date from this string later
        "league_": "Comp",
        "team_": "Squad",
        "pos_": "Pos",
        "min_": "Min",
        "Performance_Sh": "Sh",
        "Performance_SoT": "SoT",
        "Performance_Gls": "Gls",
        "Performance_Ast": "Ast",
        "Performance_CrdY": "CrdY",
        "Performance_CrdR": "CrdR",
        "Performance_PKatt": "PKatt",
        "game_id_": "Match_ID",
        "player_": "Player",
    }

    # Check current columns and rename if necessary
    for col in df.columns:
        if col in rename_map:
            df.rename(columns={col: rename_map[col]}, inplace=True)

    # Ensure Date is datetime (extracting from 'YYYY-MM-DD Match_Name')
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"].str[:10], errors="coerce")

    # Mock Opponent and Venue since they are missing in this view
    if "Opponent" not in df.columns:
        df["Opponent"] = "Unknown"
    if "Venue" not in df.columns:
        df["Venue"] = "Home"

    # Drop rows without dates
    df = df.dropna(subset=["Date"])

    # Drop rows where Min is 0 or NaN
    df["Min"] = pd.to_numeric(df["Min"], errors="coerce").fillna(0)
    df = df[df["Min"] > 0]

    # Fill NA for stats
    stat_cols = ["Sh", "SoT", "Gls", "Ast", "xG", "xAG", "CrdY", "CrdR", "PKatt"]
    for c in stat_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
        else:
            df[c] = 0.0

    if "Possession" not in df.columns:
        df["Possession"] = 50.0  # Mock team possession

    print("Executing Phase 2: Opponent Features...")
    try:
        df = calculate_opponent_features(df)
    except Exception as e:
        print(f"Skipping Phase 2 due to error: {e}")

    print("Executing Phase 3: Player Rolling Form...")
    try:
        df = calculate_player_rolling_form(df)
    except Exception as e:
        print(f"Skipping Phase 3 due to error: {e}")

    print("Executing Phase 4: Venue Effects...")
    try:
        df = calculate_venue_effects(df)
    except Exception as e:
        print(f"Skipping Phase 4 due to error: {e}")

    print("Executing Phase 5: Team Tactics...")
    try:
        df = calculate_team_tactics(df)
    except Exception as e:
        print(f"Skipping Phase 5 due to error: {e}")

    print("Executing Phase 7: Availability Features...")
    try:
        df = calculate_availability_features(df)
    except Exception as e:
        print(f"Skipping Phase 7 due to error: {e}")

    print("Executing Phase 8: Market Intelligence...")
    try:
        df = calculate_market_intelligence(df)
    except Exception as e:
        print(f"Skipping Phase 8 due to error: {e}")

    print("Executing Phase 9: Fatigue Features...")
    try:
        df = calculate_fatigue_features(df)
    except Exception as e:
        print(f"Skipping Phase 9 due to error: {e}")

    print("Executing Phase 10: Referee Features...")
    try:
        df = calculate_referee_features(df)
    except Exception as e:
        print(f"Skipping Phase 10 due to error: {e}")

    print("Executing Phase 11: Weather Features...")
    try:
        # Mocking venue coordinates
        df = integrate_weather_features(df, venue_coordinates={})
    except Exception as e:
        print(f"Skipping Phase 11 due to error: {e}")

    print(f"Saving final modeling dataset to {output_path}...")
    df.to_csv(output_path, index=False)
    print("Feature generation pipeline complete!")


if __name__ == "__main__":
    main()
