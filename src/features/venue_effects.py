import pandas as pd
import numpy as np


def calculate_venue_effects(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculates venue-specific player averages and international context.
    Crucially, features are calculated using ONLY data available BEFORE kickoff.

    Expected Input DataFrame `df`:
    Must contain player-level match aggregates:
    ['Date', 'Player', 'Venue', 'Sh', 'xG', 'Ast', 'Comp']
    Venue is expected to be 'Home', 'Away', or 'Neutral'.
    """
    # 1. Sort chronologically by Player, then Date to prevent future leakage
    df = df.sort_values(by=["Player", "Date"]).reset_index(drop=True)

    # 2. International Football Indicators
    # Check if the competition is the World Cup, Euros, Copa America, etc.
    intl_comps = [
        "World Cup",
        "European Championship",
        "Copa America",
        "Friendlies (M)",
    ]
    df["is_international"] = df["Comp"].apply(
        lambda x: 1 if any(c in str(x) for c in intl_comps) else 0
    )

    # Define neutral venue explicitly
    # For World Cups, almost all games are Neutral unless playing the host nation
    df["neutral_venue"] = np.where(df["Venue"] == "Neutral", 1, 0)

    # Host countries for World Cup 2026
    host_nations = ["USA", "Canada", "Mexico"]

    # Check if the player's Squad matches one of the host nations
    df["home_country"] = np.where(
        (df["is_international"] == 1) & (df["Squad"].isin(host_nations)), 1, 0
    )

    # If it's an international match, and the opponent is the host nation, you are the away country
    df["away_country"] = np.where(
        (df["is_international"] == 1) & (df["Opponent"].isin(host_nations)), 1, 0
    )

    # 3. Calculate Venue-Split Averages (Home vs. Away)
    # We want to know a player's historical average AT HOME vs. AWAY.
    # We use expanding means but grouped by Player AND Venue, heavily shifted to avoid leakage.

    metrics = ["Sh", "xG", "Ast"]
    for metric in metrics:
        feature_name = metric.lower()

        # We group by Player and Venue.
        # .expanding().mean().shift(1) ensures we take the average of all prior Home (or Away) matches.
        df[f"venue_{feature_name}_avg"] = df.groupby(["Player", "Venue"])[
            metric
        ].transform(lambda x: x.shift(1).expanding().mean())

    # Pivot the venue averages so they are available regardless of where the current match is played.
    # For a model, we want: what is their home avg? what is their away avg?
    # To do this safely without leakage, we forward-fill the last known Home/Away average.

    for metric in metrics:
        feature_name = metric.lower()

        # Create isolated series for Home and Away
        df[f"home_{feature_name}_avg"] = np.where(
            df["Venue"] == "Home", df[f"venue_{feature_name}_avg"], np.nan
        )
        df[f"away_{feature_name}_avg"] = np.where(
            df["Venue"] == "Away", df[f"venue_{feature_name}_avg"], np.nan
        )

        # Group by Player and forward-fill the last known values
        df[f"home_{feature_name}_avg"] = df.groupby("Player")[
            f"home_{feature_name}_avg"
        ].ffill()
        df[f"away_{feature_name}_avg"] = df.groupby("Player")[
            f"away_{feature_name}_avg"
        ].ffill()

        # For Neutral venues, we can create a blended average
        df[f"neutral_{feature_name}_avg"] = (
            df[f"home_{feature_name}_avg"].fillna(0)
            + df[f"away_{feature_name}_avg"].fillna(0)
        ) / 2

    # Drop the temporary column
    drop_cols = [c for c in df.columns if c.startswith("venue_") and c.endswith("_avg")]
    df.drop(columns=drop_cols, inplace=True, errors="ignore")

    # Handle early season NaN values
    fill_cols = [c for c in df.columns if c.endswith("_avg")]
    df[fill_cols] = df.groupby("Player")[fill_cols].bfill().fillna(0)

    return df


if __name__ == "__main__":
    print("Venue Effects Module Loaded.")
