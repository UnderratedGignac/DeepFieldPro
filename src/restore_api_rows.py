"""
Fix the 44 API-Football rows that have no game_ date.
These are season-aggregate rows from the scrape_api_football.py run.
We assign them a synthetic game_ date of '2024-07-01 SeasonAggregate'
so they parse correctly and can be used as a season baseline.
"""

import pandas as pd
import sys
import io
import os

sys.stdout = io.TextIOWrapper(
    sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLEAN_CSV = os.path.join(ROOT, "data", "world_cup_players_match_logs_global.csv")
BACKUP_CSV = os.path.join(ROOT, "data", "world_cup_players_match_logs_global.bak.csv")

# Load backup (which still has the API rows)
bak = pd.read_csv(BACKUP_CSV)
api_rows = bak[bak["game_id_"].str.startswith("api_", na=False)].copy()

print(f"API aggregate rows found: {len(api_rows)}")
print(f"Columns: {list(api_rows.columns)}")
print(api_rows[["player_", "game_id_"]].head(5).to_string())

# Assign a valid placeholder date for the season aggregate
# Date format matches the rest of the dataset: 'YYYY-MM-DD TeamA-TeamB'
api_rows["game_"] = "2024-07-01 SeasonAggregate"

# Load the clean CSV (without api rows)
clean = pd.read_csv(CLEAN_CSV)
print(f"\nClean CSV rows: {len(clean)}")

# Make column schemas match
for col in clean.columns:
    if col not in api_rows.columns:
        api_rows[col] = None
api_rows = api_rows[[c for c in clean.columns if c in api_rows.columns]]

# Append
combined = pd.concat([clean, api_rows], ignore_index=True)
combined = combined.drop_duplicates(subset=["game_id_", "player_"], keep="first")
combined.to_csv(CLEAN_CSV, index=False)

print(f"Final dataset: {len(combined):,} rows")
print(f"API rows restored: {len(api_rows)}")
print("Done!")
