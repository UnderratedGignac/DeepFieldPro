import soccerdata as sd
import pandas as pd
import os

print("Initializing World Cup 2026 Scraper...")

# The 48 countries qualified for the 2026 World Cup (FBref Nationality Codes)
# We map the standard FIFA country codes that FBref uses.
WC_NATIONS = [
    "ARG",
    "BRA",
    "FRA",
    "ENG",
    "ESP",
    "GER",
    "POR",
    "NED",
    "ITA",
    "BEL",
    "CRO",
    "URU",
    "COL",
    "USA",
    "MEX",
    "CAN",
    "JPN",
    "KOR",
    "SEN",
    "MAR",
    "USA",
    "MEX",
    "CAN",
    "CRC",
    "PAN",
    "JAM",
    "HON",
    "SLV",
    "GUA",
    "HAI",
    "CMR",
    "GHA",
    "NGA",
    "ALG",
    "TUN",
    "MLI",
    "CIV",
    "BFA",
    "EGY",
    "KSA",
    "IRN",
    "AUS",
    "QAT",
    "ECU",
    "PER",
    "CHI",
    "VEN",
    "PAR",
    "BOL",
    "SRB",
    "SUI",
    "DEN",
    "SWE",
    "POL",
    "WAL",
    "SCO",
    "UKR",
    "AUT",
    "CZE",
    "HUN",
]

# Initialize FBref scraper for the most recent completed club season (25/26)
print(
    "Connecting to FBref to scrape match-by-match logs for Top 5 Leagues (25/26 season)..."
)
try:
    fbref = sd.FBref(leagues=["Big 5 European Leagues Combined"], seasons=["2526"])
except Exception as e:
    print(f"Error initializing FBref: {e}")
    exit(1)

# Scrape Match Logs
print(
    "Fetching Match Logs (Summary)... This will take a few minutes to respect rate limits."
)
merged_logs = fbref.read_player_match_stats(stat_type="summary")

print("Cleaning data...")
merged_logs = merged_logs.reset_index()

# Clean up column names (FBref often uses multi-index columns like ('Performance', 'Min'))
# Flatten columns
merged_logs.columns = [
    "_".join(col).strip() if isinstance(col, tuple) else col
    for col in merged_logs.columns
]

# Filter 1: Only players from World Cup nations
print("Filtering for players participating in the World Cup...")


# FBref nationality usually looks like "ar ARG" or "fr FRA"
def extract_nation(nat_string):
    if pd.isna(nat_string):
        return "UNK"
    parts = str(nat_string).split()
    return parts[-1].upper() if parts else "UNK"


if "nationality_std" in merged_logs.columns:
    merged_logs["Nation"] = merged_logs["nationality_std"].apply(extract_nation)
elif "nationality" in merged_logs.columns:
    merged_logs["Nation"] = merged_logs["nationality"].apply(extract_nation)
else:
    # If nationality isn't in match logs, we must merge it from season stats
    print(
        "Nationality not in match logs, fetching player season stats to get nationalities..."
    )
    season_stats = fbref.read_player_season_stats(stat_type="standard").reset_index()
    season_stats.columns = [
        "_".join(col).strip() if isinstance(col, tuple) else col
        for col in season_stats.columns
    ]

    # Create a mapping of player -> nationality
    def get_col_name(df, possible_names):
        for name in possible_names:
            for c in df.columns:
                if name.lower() == c.lower() or name.lower() in c.lower():
                    return c
        return None

    player_col = get_col_name(season_stats, ["player", "Player"])
    nat_col = get_col_name(season_stats, ["nationality", "nation", "nat"])

    if player_col and nat_col:
        nat_map = season_stats.set_index(player_col)[nat_col].to_dict()

        # We also need to know the name of the player column in merged_logs
        log_player_col = get_col_name(merged_logs, ["player", "Player"])
        merged_logs["Nation"] = (
            merged_logs[log_player_col].map(nat_map).apply(extract_nation)
        )
    else:
        print(f"Could not find player/nat columns. Columns are: {season_stats.columns}")
        merged_logs["Nation"] = "UNK"

# Apply the filter
wc_players_logs = merged_logs[merged_logs["Nation"].isin(WC_NATIONS)].copy()

# Filter 2: Remove matches where they didn't play (0 minutes)
# Find the minutes column
min_col = next((c for c in wc_players_logs.columns if "Min" in c), None)
if min_col:
    wc_players_logs[min_col] = pd.to_numeric(wc_players_logs[min_col], errors="coerce")
    wc_players_logs = wc_players_logs[wc_players_logs[min_col] > 0]

# Ensure output directory exists
out_dir = "C:/Users/Elie/DeepFieldPro/data"
os.makedirs(out_dir, exist_ok=True)

out_file = os.path.join(out_dir, "world_cup_players_match_logs.csv")
wc_players_logs.to_csv(out_file, index=False)

print("\n" + "=" * 50)
print(f"SUCCESS: Scraped {len(wc_players_logs)} match logs for World Cup players.")
print(f"Data saved to: {out_file}")
print("You can now use this match-by-match data to retrain your models accurately!")
print("=" * 50)
