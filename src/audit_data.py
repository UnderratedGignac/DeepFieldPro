import os
from app_config import config
import pandas as pd

# Your main database
df = pd.read_csv(os.path.join(config.DATA_DIR, "csv/FULL_PLAYER_DATABASE_2026.csv"))
print(f"Total rows: {len(df)}")
print(f"Seasons: {df['season'].unique()}")
print(f"Leagues: {df['league'].unique()}")
print(f"Null counts:\n{df.isnull().sum()}")

# Key columns we need for passes model:
passes_cols = [
    "Player Name",
    "Position",
    "Minutes Played",
    "Starts",
    "Matches Played",
    "Percentage of Minutes Played",
    "Mn/MP",
    "Crs",
    "Interceptions",
    "Tackles Won",
]

print("\nChecking for expected columns:")
for col in passes_cols:
    if col in df.columns:
        print(f"[OK] Found column: {col}")
    else:
        print(f"[MISSING] Column: {col}")
