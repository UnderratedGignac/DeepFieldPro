"""
get_real_pass_data.py
-----------------------
STEP 1: Get REAL per-match pass data from StatsBomb open data.
Uses FIFA World Cup 2022 + 2018 match event data to extract
actual completed passes per player per match.

This replaces the formula proxy with ground truth training data.
"""

import os
import pandas as pd
from statsbombpy import sb
from app_config import config

print("=" * 60)
print("STEP 1: Fetching real pass data from StatsBomb Open Data")
print("=" * 60)

WC_COMPETITIONS = [
    {"competition_id": 43, "season_id": 106, "name": "World Cup 2022"},
    {"competition_id": 43, "season_id": 3, "name": "World Cup 2018"},
    {"competition_id": 43, "season_id": 55, "name": "World Cup 1990"},
]

all_player_match_rows = []

for comp in WC_COMPETITIONS:
    print(f"\nFetching {comp['name']}...")
    try:
        matches = sb.matches(
            competition_id=comp["competition_id"], season_id=comp["season_id"]
        )
        print(f"  Found {len(matches)} matches")
    except Exception as e:
        print(f"  Skipping {comp['name']}: {e}")
        continue

    for _, match in matches.iterrows():
        match_id = match["match_id"]
        home_team = match["home_team"]
        away_team = match["away_team"]
        match_date = match.get("match_date", "")

        try:
            # Get full event stream for this match
            events = sb.events(match_id=match_id)

            # --- Passes ---
            passes = events[
                (events["type"] == "Pass")
                & (events["pass_outcome"].isna())  # NaN = successful pass
            ].copy()

            # --- Minutes played per player ---
            # Starting XI
            lineups_raw = sb.lineups(match_id=match_id)

            for team_name, lineup in lineups_raw.items():
                opp_team = away_team if team_name == home_team else home_team

                for _, player in lineup.iterrows():
                    player_id = player["player_id"]
                    player_name = player["player_name"]
                    position = player.get("positions", [{}])
                    pos_name = (
                        position[0].get("position", "Unknown")
                        if isinstance(position, list) and len(position) > 0
                        else "Unknown"
                    )
                    nationality = (
                        player.get("country", {}).get("name", "Unknown")
                        if isinstance(player.get("country"), dict)
                        else "Unknown"
                    )

                    # Minutes: from substitution events or default 90
                    player_events = events[events["player_id"] == player_id]
                    if player_events.empty:
                        continue  # Didn't play

                    # Estimate minutes played
                    sub_off = events[
                        (events["type"] == "Substitution")
                        & (events["player_id"] == player_id)
                    ]
                    sub_on = (
                        events[
                            (events["type"] == "Substitution")
                            & (
                                events.get("substitution_replacement_id", pd.Series())
                                == player_id
                            )
                        ]
                        if "substitution_replacement_id" in events.columns
                        else pd.DataFrame()
                    )

                    start_min = int(sub_on["minute"].min()) if not sub_on.empty else 0
                    end_min = int(sub_off["minute"].min()) if not sub_off.empty else 90
                    minutes_played = max(end_min - start_min, 1)

                    # Completed passes for this player this match
                    player_passes = passes[passes["player_id"] == player_id]
                    completed_passes = len(player_passes)

                    # Only include outfield players who played > 10 minutes
                    if minutes_played < 10 or pos_name == "Goalkeeper":
                        continue

                    passes_per_90 = (completed_passes / minutes_played) * 90

                    all_player_match_rows.append(
                        {
                            "player_id": player_id,
                            "player_name": player_name,
                            "nationality": nationality,
                            "position": pos_name,
                            "match_id": match_id,
                            "match_date": match_date,
                            "team": team_name,
                            "opponent": opp_team,
                            "competition": comp["name"],
                            "minutes_played": minutes_played,
                            "completed_passes": completed_passes,
                            "passes_per_90": round(passes_per_90, 2),
                        }
                    )

        except Exception as e:
            print(f"  Error on match {match_id}: {e}")
            continue

    print(f"  Collected {len(all_player_match_rows)} player-match rows so far")

# ── Save ──────────────────────────────────────────────────
df = pd.DataFrame(all_player_match_rows)
print(f"\nTotal rows collected: {len(df)}")
print(f"\npasses_per_90 stats:\n{df['passes_per_90'].describe()}")
print(
    f"\nTop positions by avg passes:\n{df.groupby('position')['passes_per_90'].mean().sort_values(ascending=False).head(10)}"
)

os.makedirs(config.DATA_DIR, exist_ok=True)
df.to_csv(os.path.join(config.DATA_DIR, "statsbomb_real_passes.csv"), index=False)
print(
    "\n[OK] Real pass data saved: config.DATA_DIR/statsbomb_real_passes.csv"
)
print("Now run: python build_training_dataset_v2.py")
