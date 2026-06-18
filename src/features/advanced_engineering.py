import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)


def calculate_player_ewma(
    df: pd.DataFrame, columns: list, span: int = 5
) -> pd.DataFrame:
    """
    Calculates Exponentially Weighted Moving Averages for player stats.
    Ensures no data leakage by shifting the results match-by-match.

    df must contain: ['player_id', 'match_date']
    """
    df = df.sort_values(["player_id", "match_date"])

    for col in columns:
        col_name = f"{col}_ewma_{span}"
        # Calculate EWMA per player
        df[col_name] = df.groupby("player_id")[col].transform(
            lambda x: x.ewm(span=span, adjust=False).mean()
        )
        # SHIFT: Use stats from previous matches ONLY for the current match prediction
        df[col_name] = df.groupby("player_id")[col_name].shift(1)

    return df


def calculate_team_elo(df: pd.DataFrame, k_factor: int = 32) -> pd.DataFrame:
    """
    Calculates rolling Elo ratings for teams match-by-match.

    df must contain: ['match_id', 'match_date', 'home_team', 'away_team', 'home_score', 'away_score']
    """
    # Unique matches sorted by date
    matches = (
        df[
            [
                "match_id",
                "match_date",
                "home_team",
                "away_team",
                "home_score",
                "away_score",
            ]
        ]
        .drop_duplicates()
        .sort_values("match_date")
    )

    elo_ratings = {}  # team -> rating
    results = []

    for _, row in matches.iterrows():
        home, away = row["home_team"], row["away_team"]
        h_score, a_score = row["home_score"], row["away_score"]

        # Initial Elo: 1500
        r_h = elo_ratings.get(home, 1500.0)
        r_a = elo_ratings.get(away, 1500.0)

        # Expected scores
        e_h = 1 / (1 + 10 ** ((r_a - r_h) / 400))
        e_a = 1 / (1 + 10 ** ((r_h - r_a) / 400))

        # Actual scores (1 for win, 0.5 for draw, 0 for loss)
        if h_score > a_score:
            s_h, s_a = 1.0, 0.0
        elif h_score < a_score:
            s_h, s_a = 0.0, 1.0
        else:
            s_h, s_a = 0.5, 0.5

        # Update ratings
        new_r_h = r_h + k_factor * (s_h - e_h)
        new_r_a = r_a + k_factor * (s_a - e_a)

        # Store for next match
        elo_ratings[home] = new_r_h
        elo_ratings[away] = new_r_a

        results.append(
            {
                "match_id": row["match_id"],
                "home_elo_pre": r_h,
                "away_elo_pre": r_a,
                "home_elo_post": new_r_h,
                "away_elo_post": new_r_a,
            }
        )

    elo_df = pd.DataFrame(results)
    return df.merge(elo_df, on="match_id", how="left")


def adjust_stats_by_opponent(df: pd.DataFrame) -> pd.DataFrame:
    """
    Scales player EWMA stats based on the opposing team's Elo rating.
    A performance against a strong team is worth more.
    """
    # Assuming calculate_team_elo has been run and we have 'away_elo_pre' for home players
    # and 'home_elo_pre' for away players.

    # Define weight: (OpponentElo / 1500)
    # If I'm home player, opponent is away team
    df["opponent_elo"] = np.where(
        df["is_home"] == 1, df["away_elo_pre"], df["home_elo_pre"]
    )

    # Adjustment factor (capped to avoid extremes)
    df["elo_adj_factor"] = (df["opponent_elo"] / 1500.0).clip(0.8, 1.2)

    # Apply to EWMA columns
    ewma_cols = [c for c in df.columns if "_ewma_" in c]
    for col in ewma_cols:
        df[f"{col}_adj"] = df[col] * df["elo_adj_factor"]

    return df
