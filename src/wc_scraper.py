from app_config import config
import soccerdata as sd
import pandas as pd
import os

print("Initializing Global World Cup 2026 Scraper...")

# The 48 countries qualified for the 2026 World Cup (FBref Nationality Codes)
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

LEAGUES_2526 = [
    "Big 5 European Leagues Combined",
    "KSA-Saudi Pro League",
    "NED-Eredivisie",
    "POR-Primeira Liga",
    "ENG-Championship",
    "MEX-Liga MX",
    "TUR-Super Lig",
    "BEL-Pro League",
]

LEAGUES_2025 = ["USA-MLS", "BRA-Brasileirao", "ARG-Primera Division"]

all_wc_logs = []


def scrape_and_filter(leagues, season_str):
    print(f"\n--- Scraping {season_str} Season for {len(leagues)} Leagues ---")
    try:
        fbref = sd.FBref(leagues=leagues, seasons=[season_str])
    except Exception as e:
        print(f"Error initializing FBref for {season_str}: {e}")
        return pd.DataFrame()

    print("Fetching Match Logs (Summary)... This will take a while.")
    try:
        merged_logs = fbref.read_player_match_stats(stat_type="summary")
    except Exception as e:
        print(f"Error fetching match stats: {e}")
        return pd.DataFrame()

    merged_logs = merged_logs.reset_index()
    merged_logs.columns = [
        "_".join(col).strip() if isinstance(col, tuple) else col
        for col in merged_logs.columns
    ]

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
        print("Nationality not in match logs, fetching season stats...")
        try:
            season_stats = fbref.read_player_season_stats(
                stat_type="standard"
            ).reset_index()
            season_stats.columns = [
                "_".join(col).strip() if isinstance(col, tuple) else col
                for col in season_stats.columns
            ]

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
                log_player_col = get_col_name(merged_logs, ["player", "Player"])
                merged_logs["Nation"] = (
                    merged_logs[log_player_col].map(nat_map).apply(extract_nation)
                )
            else:
                merged_logs["Nation"] = "UNK"
        except Exception as e:
            print(f"Error fetching season stats: {e}")
            merged_logs["Nation"] = "UNK"

    wc_players_logs = merged_logs[merged_logs["Nation"].isin(WC_NATIONS)].copy()

    min_col = next((c for c in wc_players_logs.columns if "Min" in c), None)
    if min_col:
        wc_players_logs[min_col] = pd.to_numeric(
            wc_players_logs[min_col], errors="coerce"
        )
        wc_players_logs = wc_players_logs[wc_players_logs[min_col] > 0]

    print(f"Found {len(wc_players_logs)} match logs for WC players in {season_str}.")
    return wc_players_logs


df_2526 = scrape_and_filter(LEAGUES_2526, "2526")
df_2025 = scrape_and_filter(LEAGUES_2025, "2025")

final_df = pd.concat([df_2526, df_2025], ignore_index=True)

out_dir = config.DATA_DIR
os.makedirs(out_dir, exist_ok=True)
out_file = os.path.join(out_dir, "world_cup_players_match_logs_global.csv")

final_df.to_csv(out_file, index=False)

print("\n" + "=" * 50)
print(
    f"SUCCESS: Scraped {len(final_df)} match logs for World Cup players across ALL global leagues."
)
print(f"Data saved to: {out_file}")
print("You can now use this match-by-match data to retrain your models accurately!")
print("=" * 50)
