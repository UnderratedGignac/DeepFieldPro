"""
feature_store.py
----------------
Feature store for CalibBet v1.0.
Calculates lagged stats, ELO dynamics, rest/travel factors, and market features
from the matches database. Ensures strict chronological order to avoid look-ahead bias.
"""

import sqlite3
import pandas as pd
import numpy as np
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("feature_store")

def load_data(db_path="data/history.db"):
    """
    Loads raw matches data from history.db.
    """
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database not found at {db_path}")
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query("SELECT * FROM matches", conn)
    conn.close()
    return df

def build_features(df, k_factor=32, rolling_window=5):
    """
    Extracts features chronologically to enforce the Leakage Shield.
    Only matches with valid odds will be used for training, but ELO and rolling stats
    are tracked over all matches to maintain history continuity.
    """
    logger.info("Parsing match dates...")
    df = df.copy()
    df["date_parsed"] = pd.to_datetime(df["date"], dayfirst=True, errors="coerce")
    
    # Drop rows without dates
    df = df.dropna(subset=["date_parsed"])
    
    # Sort chronologically to prevent look-ahead bias
    df = df.sort_values("date_parsed").reset_index(drop=True)
    
    logger.info(f"Computing ELO dynamics and rolling stats over {len(df)} matches...")
    
    # ELO and rolling trackers
    elo_dict = {}  # team -> elo
    team_history = {}  # team -> list of (goals_scored, goals_conceded)
    team_last_date = {}  # team -> last match date
    
    home_elo = []
    away_elo = []
    
    home_recent_g_scored = []
    home_recent_g_conceded = []
    away_recent_g_scored = []
    away_recent_g_conceded = []
    
    rest_days_home = []
    rest_days_away = []
    
    for idx, row in df.iterrows():
        home, away = row["home"], row["away"]
        h_goals, a_goals = row["home_goals"], row["away_goals"]
        match_date = row["date_parsed"]
        
        # 1. Fetch current ELO ratings (pre-match)
        r_h = elo_dict.get(home, 1500.0)
        r_a = elo_dict.get(away, 1500.0)
        home_elo.append(r_h)
        away_elo.append(r_a)
        
        # 2. Fetch rolling stats (pre-match)
        home_hist = team_history.get(home, [])
        if len(home_hist) > 0:
            avg_scored_h = np.mean([x[0] for x in home_hist[-rolling_window:]])
            avg_conceded_h = np.mean([x[1] for x in home_hist[-rolling_window:]])
        else:
            avg_scored_h = 1.3
            avg_conceded_h = 1.3
        home_recent_g_scored.append(avg_scored_h)
        home_recent_g_conceded.append(avg_conceded_h)
        
        away_hist = team_history.get(away, [])
        if len(away_hist) > 0:
            avg_scored_a = np.mean([x[0] for x in away_hist[-rolling_window:]])
            avg_conceded_a = np.mean([x[1] for x in away_hist[-rolling_window:]])
        else:
            avg_scored_a = 1.1
            avg_conceded_a = 1.5
        away_recent_g_scored.append(avg_scored_a)
        away_recent_g_conceded.append(avg_conceded_a)
        
        # 3. Compute rest days
        last_date_h = team_last_date.get(home, None)
        if last_date_h is not None:
            days_h = (match_date - last_date_h).days
        else:
            days_h = 10  # default
        days_h = min(max(days_h, 0), 30)
        rest_days_home.append(days_h)
        
        last_date_a = team_last_date.get(away, None)
        if last_date_a is not None:
            days_a = (match_date - last_date_a).days
        else:
            days_a = 10  # default
        days_a = min(max(days_a, 0), 30)
        rest_days_away.append(days_a)
        
        # 4. Update ELO and stats trackers post-match
        # ELO Update
        if h_goals > a_goals:
            s_h, s_a = 1.0, 0.0
        elif h_goals < a_goals:
            s_h, s_a = 0.0, 1.0
        else:
            s_h, s_a = 0.5, 0.5
            
        e_h = 1.0 / (1.0 + 10.0 ** ((r_a - r_h) / 400.0))
        e_a = 1.0 / (1.0 + 10.0 ** ((r_h - r_a) / 400.0))
        
        elo_dict[home] = r_h + k_factor * (s_h - e_h)
        elo_dict[away] = r_a + k_factor * (s_a - e_a)
        
        # Stats updates
        if home not in team_history:
            team_history[home] = []
        team_history[home].append((h_goals, a_goals))
        
        if away not in team_history:
            team_history[away] = []
        team_history[away].append((a_goals, h_goals))
        
        team_last_date[home] = match_date
        team_last_date[away] = match_date
        
    df["home_elo"] = home_elo
    df["away_elo"] = away_elo
    df["elo_diff"] = df["home_elo"] - df["away_elo"]
    
    df["home_recent_goals_scored"] = home_recent_g_scored
    df["home_recent_goals_conceded"] = home_recent_g_conceded
    df["away_recent_goals_scored"] = away_recent_g_scored
    df["away_recent_goals_conceded"] = away_recent_g_conceded
    
    # Calculate recent xG difference (goals scored - conceded proxy)
    df["recent_xg_diff"] = (df["home_recent_goals_scored"] - df["away_recent_goals_conceded"]) - \
                           (df["away_recent_goals_scored"] - df["home_recent_goals_conceded"])
                           
    df["rest_days_home"] = rest_days_home
    df["rest_days_away"] = rest_days_away
    df["home_advantage"] = 1.0
    
    # Rest/Travel factors
    # Home team rest advantage
    df["rest_diff"] = df["rest_days_home"] - df["rest_days_away"]
    df["home_fatigue"] = (df["rest_days_home"] < 4).astype(float)
    df["away_fatigue"] = (df["rest_days_away"] < 4).astype(float)
    
    logger.info("Computing market features...")
    # Market features (odds & implied probabilities)
    # First, handle missing odds by backfilling or forward filling
    df["odds_h"] = df["odds_h"].fillna(df["odds_ch"])
    df["odds_d"] = df["odds_d"].fillna(df["odds_cd"])
    df["odds_a"] = df["odds_a"].fillna(df["odds_ca"])
    
    df["odds_ch"] = df["odds_ch"].fillna(df["odds_h"])
    df["odds_cd"] = df["odds_cd"].fillna(df["odds_d"])
    df["odds_ca"] = df["odds_ca"].fillna(df["odds_a"])
    
    # Calculate implied probabilities
    df["implied_prob_h"] = 1.0 / df["odds_h"]
    df["implied_prob_d"] = 1.0 / df["odds_d"]
    df["implied_prob_a"] = 1.0 / df["odds_a"]
    
    df["implied_prob_ch"] = 1.0 / df["odds_ch"]
    df["implied_prob_cd"] = 1.0 / df["odds_cd"]
    df["implied_prob_ca"] = 1.0 / df["odds_ca"]
    
    # Handle NaNs and infinite values in odds features
    for col in ["implied_prob_h", "implied_prob_d", "implied_prob_a", 
                "implied_prob_ch", "implied_prob_cd", "implied_prob_ca"]:
        df[col] = df[col].replace([np.inf, -np.inf], np.nan)
        
    # Drop rows where we cannot compute implied probabilities
    df = df.dropna(subset=["implied_prob_h", "implied_prob_d", "implied_prob_a",
                           "implied_prob_ch", "implied_prob_cd", "implied_prob_ca"])
    
    # Normalized opening implied probabilities
    sum_prob_open = df["implied_prob_h"] + df["implied_prob_d"] + df["implied_prob_a"]
    df["implied_prob_h_norm"] = df["implied_prob_h"] / sum_prob_open
    df["implied_prob_d_norm"] = df["implied_prob_d"] / sum_prob_open
    df["implied_prob_a_norm"] = df["implied_prob_a"] / sum_prob_open
    df["margin_open"] = sum_prob_open - 1.0
    
    # Normalized closing implied probabilities
    sum_prob_close = df["implied_prob_ch"] + df["implied_prob_cd"] + df["implied_prob_ca"]
    df["implied_prob_ch_norm"] = df["implied_prob_ch"] / sum_prob_close
    df["implied_prob_cd_norm"] = df["implied_prob_cd"] / sum_prob_close
    df["implied_prob_ca_norm"] = df["implied_prob_ca"] / sum_prob_close
    df["margin_close"] = sum_prob_close - 1.0
    
    # Market odds movements
    df["odds_change_h"] = (df["odds_ch"] - df["odds_h"]) / df["odds_h"]
    df["odds_change_d"] = (df["odds_cd"] - df["odds_d"]) / df["odds_d"]
    df["odds_change_a"] = (df["odds_ca"] - df["odds_a"]) / df["odds_a"]
    
    # Outcomes
    df["home_win"] = (df["home_goals"] > df["away_goals"]).astype(int)
    df["draw"] = (df["home_goals"] == df["away_goals"]).astype(int)
    df["away_win"] = (df["home_goals"] < df["away_goals"]).astype(int)
    
    # Clean up any potential NaNs in engineered features
    engineered_cols = ["elo_diff", "recent_xg_diff", "rest_days_home", "rest_days_away", 
                       "rest_diff", "home_fatigue", "away_fatigue", "home_advantage",
                       "odds_change_h", "odds_change_d", "odds_change_a",
                       "implied_prob_h_norm", "implied_prob_d_norm", "implied_prob_a_norm",
                       "implied_prob_ch_norm", "implied_prob_cd_norm", "implied_prob_ca_norm"]
    df[engineered_cols] = df[engineered_cols].fillna(0)
    
    logger.info(f"Feature construction complete. Kept {len(df)} matches with valid odds.")
    return df

if __name__ == "__main__":
    df = load_data()
    features_df = build_features(df)
    print("Features preview:")
    print(features_df[["date", "home", "away", "elo_diff", "recent_xg_diff", "implied_prob_ch_norm"]].head())
