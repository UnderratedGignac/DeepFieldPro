"""
seed_opponent_profiles.py
--------------------------
Computes per-team PPDA proxy and possession-allowed proxy
directly from the scraped World Cup match logs.

PPDA proxy: We don't have true PPDA (passes allowed / defensive actions)
from summary logs, so we use passes conceded per game as a proxy
by grouping from the opponent's perspective.

Possession-allowed proxy: We estimate it from passes completed per game
relative to the overall average.
"""

import os
import sqlite3
import pandas as pd
from app_config import config

print("Seeding opponent profiles from World Cup match logs...")

df = pd.read_csv(os.path.join(config.DATA_DIR, "world_cup_players_match_logs.csv"))

df["min_"] = pd.to_numeric(df["min_"], errors="coerce").fillna(0)
df["Performance_Crs"] = pd.to_numeric(
    df["Performance_Crs"] if "Performance_Crs" in df.columns else 0, errors="coerce"
).fillna(0)
df["Performance_Int"] = pd.to_numeric(
    df["Performance_Int"] if "Performance_Int" in df.columns else 0, errors="coerce"
).fillna(0)
df["Performance_TklW"] = pd.to_numeric(
    df["Performance_TklW"] if "Performance_TklW" in df.columns else 0, errors="coerce"
).fillna(0)

# Only outfield players who played
df = df[
    (df["min_"] > 0) & (~df["pos_"].astype(str).str.contains("GK", na=False))
].copy()

# Group by team and game to get per-match totals
team_game = (
    df.groupby(["team_", "game_"])
    .agg(
        total_crosses=("Performance_Crs", "sum"),
        total_int=("Performance_Int", "sum"),
        total_tkl=("Performance_TklW", "sum"),
        players=("player_", "count"),
    )
    .reset_index()
)

# Compute per-team averages across all their games
team_avg = (
    team_game.groupby("team_")
    .agg(
        avg_crosses_per_game=("total_crosses", "mean"),
        avg_int_per_game=("total_int", "mean"),
        avg_tkl_per_game=("total_tkl", "mean"),
        num_games=("game_", "count"),
    )
    .reset_index()
)

# PPDA proxy: defensive actions (int + tkl) per opponent pass
# Higher PPDA = more passive defense (allows more passes)
# Lower PPDA  = high pressing (fewer passes allowed)
# We estimate it from the overall league average baseline
league_avg_passes = team_avg["avg_crosses_per_game"].mean()
league_avg_def = (team_avg["avg_int_per_game"] + team_avg["avg_tkl_per_game"]).mean()
baseline_ppda = league_avg_passes / max(league_avg_def, 1.0)

team_avg["defensive_actions"] = (
    team_avg["avg_int_per_game"] + team_avg["avg_tkl_per_game"]
)
# PPDA from crosses perspective: high crosses allowed = passive defense = high PPDA
team_avg["ppda"] = (
    team_avg["avg_crosses_per_game"] / team_avg["defensive_actions"].clip(lower=0.1)
) * 3.0
team_avg["ppda"] = team_avg["ppda"].clip(5.0, 20.0)

# Possession-allowed proxy: teams with more crosses against allow more possession
team_avg["opp_possession_allowed"] = (
    (team_avg["avg_crosses_per_game"] / team_avg["avg_crosses_per_game"].mean()) * 50.0
).clip(30.0, 70.0)

print(f"\nComputed opponent profiles for {len(team_avg)} teams")
print(f"PPDA range: {team_avg['ppda'].min():.1f} – {team_avg['ppda'].max():.1f}")
print(
    f"Possession allowed range: {team_avg['opp_possession_allowed'].min():.1f}% – {team_avg['opp_possession_allowed'].max():.1f}%"
)
print("\nSample (best pressing teams = lowest PPDA):")
print(
    team_avg.nsmallest(10, "ppda")[
        ["team_", "ppda", "opp_possession_allowed", "num_games"]
    ].to_string(index=False)
)

# Write to opponent_profiles.db
DB_OPP = os.path.join(config.DATA_DIR, "opponent_profiles.db")
conn = sqlite3.connect(DB_OPP)
cursor = conn.cursor()

cursor.execute(
    """CREATE TABLE IF NOT EXISTS opponent_profiles (
    team_name TEXT PRIMARY KEY,
    ppda REAL,
    opp_possession_allowed REAL,
    avg_crosses_per_game REAL,
    num_games INTEGER,
    match_week INTEGER
)"""
)

# Clear existing data
cursor.execute("DELETE FROM opponent_profiles")

for _, row in team_avg.iterrows():
    cursor.execute(
        """
        INSERT OR REPLACE INTO opponent_profiles
        (team_name, ppda, opp_possession_allowed, avg_crosses_per_game, num_games, match_week)
        VALUES (?, ?, ?, ?, ?, ?)
    """,
        (
            row["team_"],
            round(row["ppda"], 3),
            round(row["opp_possession_allowed"], 2),
            round(row["avg_crosses_per_game"], 1),
            int(row["num_games"]),
            1,
        ),
    )

conn.commit()
conn.close()

print(f"\n[OK] {len(team_avg)} team opponent profiles saved to opponent_profiles.db")
