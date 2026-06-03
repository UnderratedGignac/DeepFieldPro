"""
build_training_dataset_v2.py
------------------------------
Builds a clean training dataset using REAL pass data from StatsBomb.
Merges with the FBref match logs to add opponent context features.
"""

import pandas as pd
import numpy as np
import sqlite3
import os
from datetime import datetime

print("Building v2 training dataset from real StatsBomb pass data...")

# 1. Load real pass data
try:
    passes_df = pd.read_csv("C:/Users/Elie/DeepFieldPro/data/statsbomb_real_passes.csv")
    print(f"Real pass data: {passes_df.shape}")
    print(f"passes_per_90 stats:\n{passes_df['passes_per_90'].describe()}\n")
except FileNotFoundError:
    print(
        "Error: statsbomb_real_passes.csv not found. Run get_real_pass_data.py first."
    )
    exit(1)

# 2. Load FBref match logs for additional features (crosses, tackles, interceptions)
try:
    fbref_df = pd.read_csv(
        "C:/Users/Elie/DeepFieldPro/data/world_cup_players_match_logs.csv"
    )
    for col in [
        "Performance_Crs",
        "Performance_TklW",
        "Performance_Int",
        "Performance_Sh",
    ]:
        if col in fbref_df.columns:
            fbref_df[col] = pd.to_numeric(fbref_df[col], errors="coerce").fillna(0)
    fbref_df["min_"] = pd.to_numeric(fbref_df["min_"], errors="coerce").fillna(0)
    fbref_player_avg = (
        fbref_df[fbref_df["min_"] > 0]
        .groupby("player_")
        .agg(
            avg_crs=("Performance_Crs", "mean"),
            avg_tkl=("Performance_TklW", "mean"),
            avg_int=("Performance_Int", "mean"),
            avg_sh=("Performance_Sh", "mean"),
            avg_min=("min_", "mean"),
        )
        .reset_index()
        .rename(columns={"player_": "player_name"})
    )
    print(f"FBref player averages: {fbref_player_avg.shape}")
except FileNotFoundError:
    fbref_player_avg = pd.DataFrame()
    print("Warning: FBref match logs not found. Using StatsBomb data only.")

# 3. Compute per-player career averages from StatsBomb data
player_career = (
    passes_df.groupby("player_name")
    .agg(
        career_avg_passes=("passes_per_90", "mean"),
        career_min=("minutes_played", "mean"),
        num_matches=("match_id", "count"),
        nationality=("nationality", "first"),
        position=("position", "first"),
    )
    .reset_index()
)

# 4. Merge all features
df = passes_df.copy()

# Add career averages
df = df.merge(
    player_career[["player_name", "career_avg_passes", "career_min", "num_matches"]],
    on="player_name",
    how="left",
)

# Add FBref features if available
if not fbref_player_avg.empty:
    df = df.merge(fbref_player_avg, on="player_name", how="left")
    df["Crs"] = df["avg_crs"].fillna(1.0)
    df["Interceptions"] = df["avg_int"].fillna(1.0)
    df["Tackles Won"] = df["avg_tkl"].fillna(1.0)
else:
    df["Crs"] = 1.0
    df["Interceptions"] = 1.0
    df["Tackles Won"] = 1.0

# 5. Build features
pos_map = {
    "Center Midfield": 3,
    "Defensive Midfield": 3,
    "Attacking Midfield": 3,
    "Left Midfield": 3,
    "Right Midfield": 3,
    "Center Back": 2,
    "Left Back": 2,
    "Right Back": 2,
    "Left Wing": 1,
    "Right Wing": 1,
    "Center Forward": 1,
    "Left Wing Back": 2,
    "Right Wing Back": 2,
    "Unknown": 2,
}
df["Position_encoded"] = df["position"].map(pos_map).fillna(2).astype(int)
df["Age"] = 26.0  # StatsBomb open data doesn't expose ages easily; use league average
df["Starts"] = (df["minutes_played"] >= 60).astype(int)
df["Min%"] = (df["minutes_played"] / 90.0).clip(0.1, 1.1)
df["Mn/Start"] = df["career_min"]
df["Mn/MP"] = df["career_min"]
df["PPM"] = df["career_avg_passes"] / 90.0

# 6. Opponent context
DB_OPP = "C:/Users/Elie/DeepFieldPro/data/opponent_profiles.db"
df["ppda"] = 12.0
df["opp_possession_allowed"] = 50.0

if os.path.exists(DB_OPP):
    conn = sqlite3.connect(DB_OPP)
    try:
        opp = pd.read_sql_query(
            "SELECT team_name, ppda, opp_possession_allowed FROM opponent_profiles",
            conn,
        )
        df = df.merge(
            opp.rename(columns={"team_name": "opponent"}),
            on="opponent",
            how="left",
            suffixes=("", "_opp"),
        )
        df["ppda"] = df["ppda_opp"].fillna(12.0)
        df["opp_possession_allowed"] = df["opp_possession_allowed_opp"].fillna(50.0)
    except Exception as e:
        print(f"Warning: Opponent DB merge failed: {e}")
    conn.close()

# 7. Recency weighting
df["match_date"] = pd.to_datetime(df["match_date"], errors="coerce")
today = pd.Timestamp(datetime.now())
df["weeks_ago"] = ((today - df["match_date"]).dt.days / 7).fillna(100.0)
df["sample_weight"] = np.exp(-0.07 * df["weeks_ago"])

# 8. Rename and clean
df = df.rename(
    columns={
        "minutes_played": "Minutes Played",
        "completed_passes": "Cmp",
        "position": "Position",
    }
)
df["Goals Scored While on Pitch"] = 0.0  # Not available in this dataset

df = df.dropna(subset=["passes_per_90", "Minutes Played"]).copy()
df = df[df["Minutes Played"] > 10].copy()

# Save
os.makedirs("C:/Users/Elie/DeepFieldPro/data", exist_ok=True)
df.to_csv("C:/Users/Elie/DeepFieldPro/data/training_dataset.csv", index=False)

print(f"\n[OK] Training dataset v2 saved: {df.shape[0]} rows x {df.shape[1]} cols")
print(f"\nFinal passes_per_90 distribution:\n{df['passes_per_90'].describe()}")
print(
    f"\nSample by position:\n{df.groupby('Position')['passes_per_90'].agg(['mean','count']).sort_values('mean', ascending=False).head(8)}"
)
print("\nReady to run train_minutes_model.py and train_passes_model.py!")
