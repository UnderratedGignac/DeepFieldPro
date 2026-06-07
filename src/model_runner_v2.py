# -*- coding: utf-8 -*-
"""
model_runner.py — DeepFieldPro Model Execution Engine
=====================================================
Loads LightGBM models, queries player DB, applies international normalization,
and routes to correct model based on competition_type.

NAMING CONVENTIONS:
- Parameters: ProperCase suffix _P  (e.g. FallbackLeague_P)
- Variables:  ProperCase suffix _V  (e.g. LamSot_V)
- SQL table/column names: lowercase
- SQL keywords: UPPERCASE
- Comments: single line, human-readable, max 1 line
"""

import os
import sqlite3
import time
import math
import pickle
import pandas as pd
from datetime import datetime, timezone
from dotenv import load_dotenv

from execution_engine import place_bet

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

# ─────────────────────────────────────────────────────────
# PATH CONSTANTS
# ─────────────────────────────────────────────────────────
BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
MODEL_DIR = os.path.join(BASE_DIR, "models")
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_ODDS = os.path.join(DATA_DIR, "odds_stream.db")
DB_OPP = os.path.join(DATA_DIR, "opponent_profiles.db")
DB_LINEUPS = os.path.join(DATA_DIR, "parsed_lineups.db")
PLAYER_CSV = os.path.join(DATA_DIR, "world_cup_players_match_logs.csv")
MISSING_PLAYERS_LOG = os.path.join(DATA_DIR, "missing_players.log")

# ─────────────────────────────────────────────────────────
# INTERNATIONAL NORMALIZATION PARAMETERS
# ─────────────────────────────────────────────────────────
ClubPpdaBaseline_P = 12.0
IntlPpdaBaseline_P = 9.5
ClubMinutesAvg_P = 82
IntlMinutesAvg_P = 72
IntlMinutesFactor_P = IntlMinutesAvg_P / ClubMinutesAvg_P  # 0.878 ≈ 0.88


def load_models_international():
    """Load both club and international models."""
    models_V = {}

    club_model_path = f"{MODEL_DIR}/lgbm_sot_club_v1.pkl"
    intl_model_path = f"{MODEL_DIR}/lgbm_sot_international_v2.pkl"

    if os.path.exists(club_model_path):
        with open(club_model_path, "rb") as f:
            models_V["sot_club"] = pickle.load(f)
        print(f"[OK] Loaded club SoT model: {club_model_path}")
    else:
        print(f"[WARN] Club SoT model not found: {club_model_path}")

    if os.path.exists(intl_model_path):
        with open(intl_model_path, "rb") as f:
            models_V["sot_international"] = pickle.load(f)
        print(f"[OK] Loaded international SoT model: {intl_model_path}")
    else:
        print(f"[WARN] International SoT model not found: {intl_model_path}")

    return models_V


def get_player_historical_stats(player_name, competition_type=0):
    """
    Get player historical stats from CSV.
    Returns None if player not found (triggers fallback).
    """
    if not os.path.exists(PLAYER_CSV):
        log_missing_player(player_name)
        return None

    df = pd.read_csv(PLAYER_CSV)
    from unidecode import unidecode

    df["name_clean"] = df["player_"].apply(lambda x: unidecode(str(x)).lower().strip())
    name_clean = unidecode(str(player_name)).lower().strip()

    matches = df[df["name_clean"] == name_clean]
    if matches.empty:
        matches = df[df["name_clean"].str.contains(name_clean[:10], na=False)]

    if matches.empty:
        log_missing_player(player_name)
        return None

    return matches.sort_values("season_", ascending=False).iloc[0]


def log_missing_player(player_name):
    """Log missing player to missing_players.log."""
    timestamp = datetime.now(timezone.utc).isoformat()
    with open(MISSING_PLAYERS_LOG, "a", encoding="utf-8") as f:
        f.write(f"{timestamp} | {player_name}\n")
    print(f"[MISSING] Player '{player_name}' logged to missing_players.log")


def detect_competition_type(league_name):
    """
    Detect if match is international or domestic club.
    Returns: 1 = international, 0 = domestic club
    """
    international_keywords = [
        "world cup",
        "nations league",
        "euro",
        "copa america",
        "afcon",
        "asian cup",
        "gold cup",
        "friendly",
        "international",
        "wc-",
        "uefa-",
        "conmebol-",
        "concacaf-",
    ]

    league_lower = str(league_name).lower()
    for keyword in international_keywords:
        if keyword in league_lower:
            return 1
    return 0


def get_opponent_profile(opponent_team_name, competition_type=0):
    """
    Get opponent defensive profile from DB.
    Applies international PPDA normalization.
    """
    if not os.path.exists(DB_OPP):
        baseline = IntlPpdaBaseline_P if competition_type == 1 else ClubPpdaBaseline_P
        return {"ppda": baseline, "opp_possession_allowed": 50.0}

    conn = sqlite3.connect(DB_OPP)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT ppda, opp_possession_allowed FROM opponent_profiles 
        WHERE team_name LIKE ? ORDER BY match_week DESC LIMIT 1
    """,
        (f"%{opponent_team_name}%",),
    )
    row = cursor.fetchone()
    conn.close()

    if row:
        return {"ppda": row[0], "opp_possession_allowed": row[1]}

    baseline = IntlPpdaBaseline_P if competition_type == 1 else ClubPpdaBaseline_P
    return {"ppda": baseline, "opp_possession_allowed": 50.0}


def compute_intl_ppda_norm(opp_ppda, competition_type=0):
    """
    Compute international-normalized PPDA.
    Club baseline: 12.0, International baseline: 9.5
    """
    if competition_type == 1:
        IntlPpdaNorm_V = opp_ppda / IntlPpdaBaseline_P
    else:
        IntlPpdaNorm_V = opp_ppda / ClubPpdaBaseline_P
    return IntlPpdaNorm_V


def compute_intl_minutes_factor(competition_type=0):
    """
    Compute minutes adjustment factor for international matches.
    International starters average 72 min vs 82 for club.
    """
    if competition_type == 1:
        IntlMinutesFactor_V = IntlMinutesFactor_P
    else:
        IntlMinutesFactor_V = 1.0
    return IntlMinutesFactor_V


def safe_float(val, default):
    """Safely convert value to float."""
    try:
        if isinstance(val, str) and "-" in val:
            return float(val.split("-")[0])
        return float(val)
    except:  # noqa: E722
        return float(default)


def build_feature_vector(stats, opp_profile, competition_type=0):
    """Build feature vector for model prediction with international adjustments."""
    position_map = {"MF": 3, "DF": 2, "FW": 1, "GK": 0, "MF,FW": 2, "DF,MF": 2}
    pos_encoded = position_map.get(str(stats.get("pos_", "MF")), 2)

    opp_ppda = opp_profile.get("ppda", ClubPpdaBaseline_P)
    IntlPpdaNorm_V = compute_intl_ppda_norm(opp_ppda, competition_type)

    return {
        "Age": safe_float(stats.get("age_", 25), 25),
        "Position_encoded": pos_encoded,
        "Minutes Played": safe_float(stats.get("min_", 900), 900),
        "Starts": safe_float(stats.get("game_id_", 10), 10),
        "Percentage of Minutes Played": safe_float(stats.get("Min%", 0.7), 0.7),
        "Mn/Start": safe_float(stats.get("Mn/Start", 75), 75),
        "Mn/MP": safe_float(stats.get("Mn/MP", 70), 70),
        "PPM": safe_float(stats.get("PPM", 1.5), 1.5),
        "Crs": safe_float(stats.get("Performance_Crs", 1.0), 1.0),
        "Interceptions": safe_float(stats.get("Performance_Int", 1.0), 1.0),
        "Tackles Won": safe_float(stats.get("Performance_TklW", 1.0), 1.0),
        "ppda": IntlPpdaNorm_V,
        "opp_possession_allowed": safe_float(
            opp_profile.get("opp_possession_allowed", 50.0), 50.0
        ),
        "competition_type": competition_type,
        "sample_weight": 1.0,
        # New features for retrained LightGBM models
        "age_": safe_float(stats.get("age_", 25), 25),
        "min_": safe_float(stats.get("min_", 90), 90),
        "pos_encoded": pos_encoded,
        "Performance_Sh": safe_float(stats.get("Shots per 90", 1.0), 1.0),
        "Performance_Crs": safe_float(stats.get("Crs", 1.0), 1.0),
        "Performance_Int": safe_float(stats.get("Interceptions", 1.0), 1.0),
        "Performance_TklW": safe_float(stats.get("Tackles Won", 1.0), 1.0),
    }


def poisson_prob_ge(lam, k):
    """Probability of Poisson variable being >= k."""
    if lam <= 0:
        return 0.0
    prob_lt_k = 0.0
    for i in range(k):
        prob_lt_k += (lam**i) * math.exp(-lam) / math.factorial(i)
    return max(0.0, min(1.0, 1.0 - prob_lt_k))


def compute_pearson_lambda(
    p10, p50, p90, expected_minutes, opp_ppda, competition_type=0
):
    """
    Compute Poisson lambda using Pearson mean formula.
    Lambda = (p10 + 4*p50 + p90) / 6 * (expected_minutes / 90) * (1 / IntlPpdaNorm_V)
    """
    PearsonMean_V = (p10 + 4 * p50 + p90) / 6.0

    IntlMinutesFactor_V = compute_intl_minutes_factor(competition_type)
    adjusted_minutes = expected_minutes * IntlMinutesFactor_V

    IntlPpdaNorm_V = compute_intl_ppda_norm(opp_ppda, competition_type)

    Lam_V = PearsonMean_V * (adjusted_minutes / 90.0) * (1.0 / max(IntlPpdaNorm_V, 0.1))
    return max(0.001, Lam_V)


def get_sot_model(competition_type=0):
    """Route to correct SoT model based on competition type."""
    if competition_type == 1:
        model_path = f"{MODEL_DIR}/lgbm_sot_international_v2.pkl"
    else:
        model_path = f"{MODEL_DIR}/lgbm_sot_club_v1.pkl"

    if os.path.exists(model_path):
        with open(model_path, "rb") as f:
            return pickle.load(f)
    return None


def run_for_match(
    fixture_id,
    opponent_team,
    lineup_drop_at,
    latency_ms,
    role_shifts,
    regime="lineup_adjustment_window",
    competition_type=0,
    league_name="",
):
    """
    Main prediction engine for a fixture.
    Auto-selects club vs international model and applies proper normalization.
    """
    print(f"\n=== MODEL RUNNER STARTING | Fixture: {fixture_id} ===")
    print(
        f"Competition Type: {'International' if competition_type == 1 else 'Domestic Club'}"
    )
    print(f"League: {league_name}")

    start_time = time.time()

    models_V = load_models_international()  # noqa: F841
    opp_profile = get_opponent_profile(opponent_team, competition_type)

    IntlPpdaNorm_V = compute_intl_ppda_norm(opp_profile["ppda"], competition_type)
    print(
        f"Opponent: {opponent_team} | PPDA: {opp_profile['ppda']} | "
        f"Normalized PPDA: {IntlPpdaNorm_V:.3f}"
    )

    if not os.path.exists(DB_LINEUPS):
        print("ERROR: Lineups DB not found. Did lineup_parser run?")
        return []

    conn = sqlite3.connect(DB_LINEUPS)
    starters_df = pd.read_sql_query(
        """
        SELECT player_id, player_name, expected_role FROM parsed_lineups 
        WHERE match_id = ? AND is_starter = 1
    """,
        conn,
        params=(str(fixture_id),),
    )
    conn.close()

    if starters_df.empty:
        print("ERROR: No starters found in DB.")
        return []

    shift_lookup = {s["player_id"]: s for s in role_shifts}  # noqa: F841
    bets_placed = []

    for _, player_row in starters_df.iterrows():
        player_name = player_row["player_name"]
        player_id = player_row["player_id"]
        role = player_row["expected_role"]

        if role == "goalkeeper":
            continue

        stats = get_player_historical_stats(player_name, competition_type)
        if stats is None:
            print(f"[SKIP] {player_name}: No historical data found")
            continue

        features = build_feature_vector(stats, opp_profile, competition_type)

        MINUTES_FEATURES = [
            "Age",
            "Starts",
            "Percentage of Minutes Played",
            "Mn/Start",
            "Mn/MP",
            "PPM",
            "ppda",
            "opp_possession_allowed",
            "sample_weight",
        ]
        PASSES_FEATURES = [
            "Age",
            "Position_encoded",
            "Minutes Played",
            "Mn/Start",
            "Percentage of Minutes Played",
            "Crs",
            "Interceptions",
            "Tackles Won",
            "ppda",
            "opp_possession_allowed",
            "sample_weight",
        ]
        NEW_SOT_FEATURES = [
            "age_",
            "competition_type",
            "min_",
            "pos_encoded",
            "Performance_Sh",
            "Performance_Crs",
            "Performance_Int",
            "Performance_TklW",
            "sample_weight",
        ]

        X_minutes = pd.DataFrame([features], columns=MINUTES_FEATURES)  # noqa: F841
        X_passes = pd.DataFrame([features], columns=PASSES_FEATURES)  # noqa: F841
        X_sot_new = pd.DataFrame([features], columns=NEW_SOT_FEATURES)

        sot_model = get_sot_model(competition_type)
        if sot_model is None:
            print(f"[SKIP] {player_name}: No SoT model available")
            continue

            sot_prob = float(sot_model.predict(X_sot_new)[0])
        sot_p10 = sot_prob
        sot_p50 = sot_prob
        sot_p90 = sot_prob

        IntlMinutesFactor_V = compute_intl_minutes_factor(competition_type)
        expected_minutes = 75 * IntlMinutesFactor_V

        LamSot_V = compute_pearson_lambda(
            p10=sot_p10,
            p50=sot_p50,
            p90=sot_p90,
            expected_minutes=expected_minutes,
            opp_ppda=opp_profile["ppda"],
            competition_type=competition_type,
        )

        prob_sot_over_0_5 = poisson_prob_ge(LamSot_V, 1)

        print(f"\n  {player_name} | Role: {role}")
        print(
            f"    SoT Lambda (Pearson): {LamSot_V:.3f} | P(SoT>=1): {prob_sot_over_0_5:.3f}"
        )

        fair_prob = prob_sot_over_0_5

        over_odds, under_odds = get_current_odds(
            str(fixture_id), player_name, "sot_total", 0.5
        )

        if over_odds is None:
            print("    [WAITING] No odds available for SoT market")
            continue

        all_outcome_odds = [over_odds, under_odds] if under_odds else [over_odds]

        bet_id = place_bet(
            fair_prob=fair_prob,
            market_odds=over_odds,
            all_outcome_odds=all_outcome_odds,
            match_id=str(fixture_id),
            player_id=player_id,
            market_type="sot_total",
            line=0.5,
            side="over",
            lineup_drop_at=lineup_drop_at,
            latency_ms=latency_ms,
            regime=regime,
            role_shift_flag=False,
        )

        if bet_id:
            bets_placed.append(bet_id)

    elapsed = int((time.time() - start_time) * 1000)
    print(f"\n=== MODEL RUNNER DONE | {len(bets_placed)} bets placed | {elapsed}ms ===")
    return bets_placed


def get_current_odds(match_id, player_name, market_type, line):
    """Fetch current odds from odds_stream.db."""
    if not os.path.exists(DB_ODDS):
        return None, None

    conn = sqlite3.connect(DB_ODDS)
    cursor = conn.cursor()

    line_str = f"%{line}%" if line is not None else "%%"
    cursor.execute(
        """
        SELECT price FROM odds_feed
        WHERE match_id = ?
          AND market_type = ?
          AND (selection_name LIKE ? AND selection_name LIKE ?)
        ORDER BY timestamp DESC LIMIT 2
    """,
        (match_id, market_type, line_str, f"%{player_name}%"),
    )

    rows = cursor.fetchall()
    conn.close()

    if len(rows) >= 2:
        return rows[0][0], rows[1][0]
    elif len(rows) == 1:
        return rows[0][0], None
    return None, None


if __name__ == "__main__":
    print("Model Runner Test Mode")
    print("=" * 50)

    test_leagues = [
        ("ENG-Premier League", 0),
        ("World Cup 2026", 1),
        ("UEFA Nations League", 1),
        ("Serie A", 0),
    ]

    for league, expected_type in test_leagues:
        detected = detect_competition_type(league)
        status = "✓" if detected == expected_type else "✗"
        print(f"{status} {league}: detected={detected}, expected={expected_type}")
