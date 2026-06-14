"""
Single-league scraper template for parallel execution.
Usage: python scrape_league_worker.py <league> <season> <output_file>
"""

import soccerdata as sd
import pandas as pd
import unicodedata
import re
import os
import sys
import io
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Args
LEAGUE = sys.argv[1]
SEASON = sys.argv[2]
OUT_FILE = sys.argv[3]
MISSING_CSV = os.path.join(
    os.path.dirname(__file__), "../data/wc_player_name_mapping.csv"
)


def normalize_name(name):
    if not isinstance(name, str):
        return ""
    name = name.lower().strip()
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    name = re.sub(r"[^a-z\s]", "", name)
    return re.sub(r"\s+", " ", name).strip()


# Load missing WC players
mapping = pd.read_csv(MISSING_CSV)
missing_legal = mapping[mapping["fbref_name"].isna()]["legal_name"].tolist()
missing_norm = set(normalize_name(n) for n in missing_legal)
missing_tokens_list = [set(normalize_name(n).split()) for n in missing_legal]


def is_wc_player(name):
    norm = normalize_name(name)
    if not norm:
        return False
    if norm in missing_norm:
        return True
    tokens = set(norm.split())
    if not tokens:
        return False
    for wc_toks in missing_tokens_list:
        if not wc_toks:
            continue
        if len(tokens) >= 2 and tokens.issubset(wc_toks):
            return True
        if len(wc_toks) >= 2 and wc_toks.issubset(tokens):
            return True
        if len(tokens & wc_toks) >= 2:
            return True
    return False


print(f"[{LEAGUE}] Starting scrape (season={SEASON})")
print(f"[{LEAGUE}] Targeting {len(missing_legal)} missing WC players")

MAX_RETRIES = 3
for attempt in range(1, MAX_RETRIES + 1):
    try:
        fbref = sd.FBref(leagues=LEAGUE, seasons=SEASON)
        stats = fbref.read_player_match_stats(stat_type="summary")

        if stats is None or len(stats) == 0:
            print(f"[{LEAGUE}] ERROR: No data returned")
            sys.exit(1)

        stats = stats.reset_index()

        # Flatten MultiIndex columns
        if hasattr(stats.columns, "levels"):
            stats.columns = [
                "_".join(filter(None, map(str, col))).strip("_")
                for col in stats.columns
            ]

        print(f"[{LEAGUE}] Raw rows: {len(stats):,}")

        # Find player column
        player_col = next(
            (c for c in ["player", "Player", "player_"] if c in stats.columns), None
        )
        if not player_col:
            print(
                f"[{LEAGUE}] ERROR: No player column. Cols: {stats.columns.tolist()[:10]}"
            )
            sys.exit(1)

        # Print sample players
        sample = list(stats[player_col].dropna().unique()[:8])
        print(f"[{LEAGUE}] Sample players: {sample}")

        # Filter to WC players
        stats["_is_wc"] = stats[player_col].apply(is_wc_player)
        wc_rows = stats[stats["_is_wc"]].copy()
        wc_rows = wc_rows.drop(columns=["_is_wc"], errors="ignore")

        if len(wc_rows) == 0:
            print(f"[{LEAGUE}] No WC players found in this league")
            # Save empty file as signal that scrape completed
            pd.DataFrame().to_csv(OUT_FILE, index=False)
            sys.exit(0)

        wc_rows["league_"] = LEAGUE
        wc_rows["season_scraped"] = SEASON

        wc_rows.to_csv(OUT_FILE, index=False)

        found = wc_rows[player_col].unique()
        print(f"[{LEAGUE}] SUCCESS: {len(found)} WC players, {len(wc_rows):,} rows")
        for p in found:
            print(f"[{LEAGUE}]   + {p}")
        sys.exit(0)

    except Exception as e:
        err = str(e)
        print(f"[{LEAGUE}] Attempt {attempt}/{MAX_RETRIES} failed: {err[:120]}")
        if attempt < MAX_RETRIES:
            wait = 30 * attempt
            print(f"[{LEAGUE}] Waiting {wait}s before retry...")
            time.sleep(wait)
        else:
            print(f"[{LEAGUE}] All retries exhausted. Giving up.")
            sys.exit(1)
