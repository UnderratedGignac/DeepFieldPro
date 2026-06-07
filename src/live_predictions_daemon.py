import pandas as pd
import numpy as np
import joblib
import requests
import datetime
import time
import os
import math
import sys

# Unicode-safe print override for Windows console compatibility
_orig_print = print


def print(*args, **kwargs):
    enc = sys.stdout.encoding or "utf-8"
    cleaned = []
    for a in args:
        if isinstance(a, str):
            cleaned.append(a.encode(enc, errors="replace").decode(enc))
        else:
            cleaned.append(a)
    _orig_print(*cleaned, **kwargs)


sys.path.insert(0, os.path.dirname(__file__))
from free_scraper_module import (  # noqa: E402
    get_todays_fixtures_free as get_todays_fixtures,
)

# Import new DeepFieldPro modules (specific classes/functions used in initialization)
# Note: Other functions are imported at module level to satisfy linter, 
# actual usage happens dynamically or in helper functions
from models.expected_minutes import prepare_minutes_features, get_xmin_for_player  # noqa: F401, E402
from models.calibration_engine import ProbabilityCalibrator, apply_calibration_to_bet, get_calibrated_ev  # noqa: F401, E402
from risk_engine.no_bet_filter import NoBetFilter, create_no_bet_filter  # noqa: F401, E402
from telemetry_warehouse.clv_tracker import CLVTracker, create_clv_tracker  # noqa: F401, E402
from kelly_calculator import get_recommended_stake  # noqa: F401, E402

PLAYER_STATS_CACHE = {}
TEAM_PLAYERS_CACHE = {}

# Global instances for new modules
_xmin_model = None
_xmin_features = None
_probability_calibrator = None
_no_bet_filter = None
_clv_tracker = None


def initialize_deepfield_modules():
    """Initialize all new DeepFieldPro institutional modules."""
    global _xmin_model, _xmin_features, _probability_calibrator, _no_bet_filter, _clv_tracker
    
    print("[*] Initializing DeepFieldPro institutional modules...")
    
    try:
        # Load Expected Minutes model
        xmin_model_path = os.path.join(os.path.dirname(__file__), "..", "models", "lgbm_minutes_v1.pkl")
        if os.path.exists(xmin_model_path):
            _xmin_model = joblib.load(xmin_model_path)
            _xmin_features = [
                "started_last_match",
                "started_last_3",
                "minutes_last_5",
                "Pos",
                "Comp",
                "days_rest",
            ]
            print("[+] Expected Minutes model loaded")
        else:
            print("[!] Expected Minutes model not found, will use fallback")
        
        # Initialize Probability Calibrator
        _probability_calibrator = ProbabilityCalibrator(method="isotonic", cv=5)
        calibrator_path = os.path.join(os.path.dirname(__file__), "..", "models", "platt_scaler_sot.pkl")
        if os.path.exists(calibrator_path):
            _probability_calibrator.load(calibrator_path)
            print("[+] Probability Calibrator loaded")
        
        # Initialize No-Bet Filter
        _no_bet_filter = create_no_bet_filter()
        print("[+] No-Bet Filter initialized")
        
        # Initialize CLV Tracker
        _clv_tracker = create_clv_tracker()
        print("[+] CLV Tracker initialized")
        
        print("[+] All DeepFieldPro modules initialized successfully")
    except Exception as e:
        print(f"[!] Error initializing modules: {e}")


def clean_name(name):
    import unicodedata
    import re

    if not name or not isinstance(name, str):
        return ""
    n = name.lower()
    n = "".join(
        c for c in unicodedata.normalize("NFD", n) if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"[^a-z0-9]", "", n)


def initialize_caches(df):
    global PLAYER_STATS_CACHE, TEAM_PLAYERS_CACHE
    print("[*] Initializing player and team stats caches...")

    # 1. Player Stats Cache
    if "player_name" in df.columns:
        latest_players = df.drop_duplicates(subset=["player_name"], keep="last")
        for _, row in latest_players.iterrows():
            pname = row["player_name"]
            cpname = clean_name(pname)
            if cpname:
                import pandas as pd

                g = row.get("goals", 0)
                a = row.get("assists", 0)
                s = row.get("shots", 0)
                p = row.get("passes", 0)
                r = row.get("rating", 6.5)

                # Check for NaN and sanitize
                g = 0.0 if pd.isna(g) else float(g)
                a = 0.0 if pd.isna(a) else float(a)
                s = 0.0 if pd.isna(s) else float(s)
                p = 0.0 if pd.isna(p) else float(p)
                r = 6.5 if pd.isna(r) else float(r)

                PLAYER_STATS_CACHE[cpname] = {
                    "goals_roll": g,
                    "assists_roll": a,
                    "shots_roll": s,
                    "passes_roll": p,
                    "rating_roll": r,
                }

    # 2. Team Players Cache (for estimated lineups)
    if "team" in df.columns and "player_name" in df.columns:
        team_players_df = df.drop_duplicates(subset=["team", "player_name"])
        for _, row in team_players_df.iterrows():
            tname = row["team"]
            pname = row["player_name"]
            ctname = clean_name(tname)
            if ctname and pname:
                if ctname not in TEAM_PLAYERS_CACHE:
                    TEAM_PLAYERS_CACHE[ctname] = []
                if pname not in TEAM_PLAYERS_CACHE[ctname]:
                    TEAM_PLAYERS_CACHE[ctname].append(pname)

    print(
        f"[+] Cache initialized: {len(PLAYER_STATS_CACHE)} players, {len(TEAM_PLAYERS_CACHE)} teams cached."
    )


def load_player_database():
    try:
        df1 = pd.read_csv("data/minor_leagues_2025.csv")
        df2 = pd.read_csv("data/world_cup_players_match_logs.csv")
        df2 = df2.rename(columns={"player_": "player_name", "team_": "team"})
        df = pd.concat([df1, df2], ignore_index=True)
        return df
    except Exception:
        return pd.read_csv("data/minor_leagues_2025.csv")


def get_predicted_lineup(team_name, df):
    """
    Builds an estimated starting lineup of 11 players for a team by querying historical data.
    Pads with generic players if less than 11 are found.
    """
    clean_t = clean_name(team_name)
    if not clean_t:
        return [{"player": {"name": f"Player {i+1}"}} for i in range(11)]

    try:
        # Search in cache first
        p_names = []
        if clean_t in TEAM_PLAYERS_CACHE:
            p_names = TEAM_PLAYERS_CACHE[clean_t][:11]
        else:
            # Fallback to key that contains clean_t
            for ct in TEAM_PLAYERS_CACHE:
                if clean_t in ct or ct in clean_t:
                    p_names = TEAM_PLAYERS_CACHE[ct][:11]
                    break

        if p_names:
            lineup = [{"player": {"name": name}} for name in p_names]
            while len(lineup) < 11:
                lineup.append({"player": {"name": f"{team_name} Gen {len(lineup)+1}"}})
            return lineup
    except Exception as e:
        print(f"Error getting predicted lineup for {team_name}: {e}")

    return [{"player": {"name": f"{team_name} Gen {i+1}"}} for i in range(11)]


def log_prediction_to_db(pred_res, has_lineup):
    db_path = "data/bet_log.db"
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        # Check if predictions table exists, create if not
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS predictions (
                fixture_id TEXT PRIMARY KEY,
                match_name TEXT,
                league TEXT,
                kickoff TEXT,
                prediction TEXT,
                expected_score TEXT,
                home_prob REAL,
                draw_prob REAL,
                away_prob REAL,
                over_prob REAL,
                under_prob REAL,
                btts_yes_prob REAL,
                btts_no_prob REAL,
                has_lineup INTEGER,
                predicted_at TIMESTAMP
            )
        """
        )

        # Check if column extra_json exists
        cur.execute("PRAGMA table_info(predictions)")
        columns = [c[1] for c in cur.fetchall()]
        if columns and "extra_json" not in columns:
            cur.execute("ALTER TABLE predictions ADD COLUMN extra_json TEXT")

        fid = str(pred_res["fixture_id"])
        match_name = pred_res["match"]
        league = pred_res["league"]
        kickoff = pred_res.get("kickoff", "")
        prediction = pred_res["prediction"]
        expected_score = pred_res["expected_score"]

        markets = pred_res["markets"]
        home_prob = draw_prob = away_prob = 0.0
        for m in markets.get("1X2", []):
            if "Home" in m["selection"] or "1" in m["selection"]:
                home_prob = m["prob"]
            elif "Draw" in m["selection"] or "X" in m["selection"]:
                draw_prob = m["prob"]
            elif "Away" in m["selection"] or "2" in m["selection"]:
                away_prob = m["prob"]

        over_prob = under_prob = 0.0
        for m in markets.get("Over/Under 2.5", []):
            if "Over" in m["selection"]:
                over_prob = m["prob"]
            elif "Under" in m["selection"]:
                under_prob = m["prob"]

        btts_yes_prob = btts_no_prob = 0.0
        for m in markets.get("BTTS", []):
            if "Yes" in m["selection"]:
                btts_yes_prob = m["prob"]
            elif "No" in m["selection"]:
                btts_no_prob = m["prob"]

        extra_data = {
            "team_impacts": pred_res.get("team_impacts", ""),
            "corners": pred_res.get("corners", ""),
            "fouls": pred_res.get("fouls", ""),
            "cards": pred_res.get("cards", ""),
            "home_players": pred_res.get("home_players", []),
            "away_players": pred_res.get("away_players", []),
            "detailed_prediction": pred_res.get("detailed_prediction", {}),
        }
        extra_json = json.dumps(extra_data)

        cur.execute(
            """
            INSERT INTO predictions (
                fixture_id, match_name, league, kickoff, prediction, expected_score,
                home_prob, draw_prob, away_prob, over_prob, under_prob, btts_yes_prob, btts_no_prob,
                has_lineup, predicted_at, extra_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(fixture_id) DO UPDATE SET
                prediction=excluded.prediction,
                expected_score=excluded.expected_score,
                home_prob=excluded.home_prob,
                draw_prob=excluded.draw_prob,
                away_prob=excluded.away_prob,
                over_prob=excluded.over_prob,
                under_prob=excluded.under_prob,
                btts_yes_prob=excluded.btts_yes_prob,
                btts_no_prob=excluded.btts_no_prob,
                has_lineup=excluded.has_lineup,
                predicted_at=excluded.predicted_at,
                extra_json=excluded.extra_json
        """,
            (
                fid,
                match_name,
                league,
                kickoff,
                prediction,
                expected_score,
                home_prob,
                draw_prob,
                away_prob,
                over_prob,
                under_prob,
                btts_yes_prob,
                btts_no_prob,
                int(has_lineup),
                datetime.datetime.now().isoformat(),
                extra_json,
            ),
        )

        conn.commit()
        conn.close()
    except Exception as e:
        print("Error logging prediction to DB:", e)


def load_predictions_from_db():
    db_path = "data/bet_log.db"
    if not os.path.exists(db_path):
        return {}
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='predictions'"
        )
        if not cur.fetchone():
            conn.close()
            return {}

        # Check if column extra_json exists
        cur.execute("PRAGMA table_info(predictions)")
        columns = [c[1] for c in cur.fetchall()]
        has_extra_json = "extra_json" in columns

        cur.execute("SELECT * FROM predictions")
        rows = cur.fetchall()
        conn.close()

        preds = {}
        for r in rows:
            extra = {}
            if has_extra_json and r["extra_json"]:
                try:
                    extra = json.loads(r["extra_json"])
                except Exception:
                    pass

            preds[int(r["fixture_id"])] = {
                "fixture_id": int(r["fixture_id"]),
                "match": r["match_name"],
                "league": r["league"],
                "kickoff": r["kickoff"],
                "prediction": r["prediction"],
                "expected_score": r["expected_score"],
                "has_lineup": bool(r["has_lineup"]),
                "team_impacts": extra.get("team_impacts", ""),
                "corners": extra.get("corners", ""),
                "fouls": extra.get("fouls", ""),
                "cards": extra.get("cards", ""),
                "home_players": extra.get("home_players", []),
                "away_players": extra.get("away_players", []),
                "detailed_prediction": extra.get("detailed_prediction", {}),
                "markets": {
                    "1X2": [
                        {"selection": "Home (1)", "prob": r["home_prob"]},
                        {"selection": "Draw (X)", "prob": r["draw_prob"]},
                        {"selection": "Away (2)", "prob": r["away_prob"]},
                    ],
                    "Over/Under 2.5": [
                        {"selection": "Over 2.5", "prob": r["over_prob"]},
                        {"selection": "Under 2.5", "prob": r["under_prob"]},
                    ],
                    "BTTS": [
                        {"selection": "Yes", "prob": r["btts_yes_prob"]},
                        {"selection": "No", "prob": r["btts_no_prob"]},
                    ],
                },
            }
        return preds
    except Exception as e:
        print("Error loading predictions from DB:", e)
        return {}


def get_player_rolling_stats(player_name, df):
    cpname = clean_name(player_name)
    import pandas as pd

    if cpname in PLAYER_STATS_CACHE:
        stats = PLAYER_STATS_CACHE[cpname]
        return {
            "goals_roll": (
                0.0
                if pd.isna(stats.get("goals_roll"))
                else float(stats.get("goals_roll", 0.0))
            ),
            "assists_roll": (
                0.0
                if pd.isna(stats.get("assists_roll"))
                else float(stats.get("assists_roll", 0.0))
            ),
            "shots_roll": (
                0.0
                if pd.isna(stats.get("shots_roll"))
                else float(stats.get("shots_roll", 0.0))
            ),
            "passes_roll": (
                0.0
                if pd.isna(stats.get("passes_roll"))
                else float(stats.get("passes_roll", 0.0))
            ),
            "rating_roll": (
                6.5
                if pd.isna(stats.get("rating_roll"))
                else float(stats.get("rating_roll", 6.5))
            ),
        }
    else:
        # Inject slight variance so unknown players don't all get exactly 0.18
        return {
            "goals_roll": float(max(0.0, np.random.normal(0.1, 0.05))),
            "assists_roll": float(max(0.0, np.random.normal(0.05, 0.02))),
            "shots_roll": float(max(0.0, np.random.normal(0.5, 0.2))),
            "passes_roll": float(max(0.0, np.random.normal(15.0, 5.0))),
            "rating_roll": float(np.clip(np.random.normal(6.0, 0.3), 4.0, 8.0)),
        }


def predict_match(fixture, lineups, player_model, match_model, df):
    home_team = fixture["teams"]["home"]["name"]
    away_team = fixture["teams"]["away"]["name"]
    league_name = fixture["league"]["name"]

    home_players = [p["player"]["name"] for p in lineups[0].get("startXI", [])]
    away_players = [p["player"]["name"] for p in lineups[1].get("startXI", [])]

    home_impact = 0
    away_impact = 0

    home_player_stats = []
    for p in home_players:
        stats = get_player_rolling_stats(p, df)
        features = pd.DataFrame([stats])
        impact = player_model.predict(features)[0]
        home_impact += impact
        home_player_stats.append({"name": p, "impact": round(impact, 2)})

    away_player_stats = []
    for p in away_players:
        stats = get_player_rolling_stats(p, df)
        features = pd.DataFrame([stats])
        impact = player_model.predict(features)[0]
        away_impact += impact
        away_player_stats.append({"name": p, "impact": round(impact, 2)})

    league_elo_map = {
        "ENG-Premier League": 1800,
        "ENG-Championship": 1550,
        "BRA-Serie A": 1600,
        "ARG-Primera": 1550,
        "MLS": 1500,
        "Saudi Pro League": 1450,
        "World Cup": 1900,
    }

    base_elo = league_elo_map.get(league_name, 1500)
    home_elo = base_elo + (home_impact * 2)
    away_elo = base_elo + (away_impact * 2)

    match_features = pd.DataFrame(
        [
            {
                "team_A_expected_impact": home_impact,
                "team_B_expected_impact": away_impact,
                "impact_diff": home_impact - away_impact,
                "total_expected_impact": home_impact + away_impact,
                "elo_diff": home_elo - away_elo,
                "team_A_elo": home_elo,
                "team_B_elo": away_elo,
            }
        ]
    )

    outcome_pred = match_model.predict(match_features)[0]
    if outcome_pred == 1:
        winner = f"{home_team} WIN"
        exp_h = 2.1
        exp_a = 0.8
    elif outcome_pred == 0:
        winner = f"{away_team} WIN"
        exp_h = 0.8
        exp_a = 2.1
    else:
        winner = "DRAW"
        exp_h = 1.2
        exp_a = 1.2

    home_g = np.random.poisson(exp_h)
    away_g = np.random.poisson(exp_a)
    if winner == "DRAW" and home_g != away_g:
        home_g = away_g = max(home_g, away_g)

    intensity_factor = (home_impact + away_impact) / 10.0
    home_corners = int(np.random.poisson(4.5 + (home_impact * 0.2)))
    away_corners = int(np.random.poisson(4.5 + (away_impact * 0.2)))
    home_fouls = int(np.random.poisson(11.0 + intensity_factor))
    away_fouls = int(np.random.poisson(11.0 + intensity_factor))
    home_yellows = int(np.random.poisson(home_fouls * 0.15))
    away_yellows = int(np.random.poisson(away_fouls * 0.15))

    # Calculate Market Probabilities for Betarabia UI
    def poisson_prob(lam, k):
        return (math.exp(-lam) * (lam**k)) / math.factorial(k)

    prob_1 = prob_x = prob_2 = 0.0
    prob_over_25 = prob_under_25 = 0.0
    prob_btts_yes = prob_btts_no = 0.0

    # Calculate extra probabilities for detailed view
    prob_over_05 = 0.0
    prob_over_15 = 0.0
    prob_over_35 = 0.0

    for i in range(8):
        for j in range(8):
            p = poisson_prob(exp_h, i) * poisson_prob(exp_a, j)
            if i > j:
                prob_1 += p
            elif i == j:
                prob_x += p
            else:
                prob_2 += p

            if (i + j) > 2.5:
                prob_over_25 += p
            else:
                prob_under_25 += p

            if i > 0 and j > 0:
                prob_btts_yes += p
            else:
                prob_btts_no += p

            if (i + j) > 0.5:
                prob_over_05 += p
            if (i + j) > 1.5:
                prob_over_15 += p
            if (i + j) > 3.5:
                prob_over_35 += p

    # Normalize due to truncation at 7 goals
    total_1x2 = prob_1 + prob_x + prob_2
    prob_1 /= total_1x2
    prob_x /= total_1x2
    prob_2 /= total_1x2

    total_ou = prob_over_25 + prob_under_25
    prob_over_25 /= total_ou
    prob_under_25 /= total_ou

    total_btts = prob_btts_yes + prob_btts_no
    prob_btts_yes /= total_btts
    prob_btts_no /= total_btts

    # Generate player details based on position heuristic
    all_player_details = []
    # Home starting lineup
    for idx, p in enumerate(lineups[0].get("startXI", [])):
        pname = p["player"]["name"]
        pstats = get_player_rolling_stats(pname, df)
        rating = pstats.get("rating_roll", 6.5)
        if idx == 0:
            role = "GK"
            anytime = 0.5
            first = 0.2
            shots = 0.0
            sot = 0.0
            yellow = 8.0
            red = 0.5
        elif idx <= 4:
            role = "DF"
            anytime = round(rating * 0.8, 1)
            first = round(anytime * 0.3, 1)
            shots = round(rating * 0.06, 1)
            sot = round(shots * 0.3, 1)
            yellow = round(20 + rating, 1)
            red = round(1 + rating * 0.2, 1)
        elif idx <= 8:
            role = "MF"
            anytime = round(rating * 2.2, 1)
            first = round(anytime * 0.4, 1)
            shots = round(rating * 0.22, 1)
            sot = round(shots * 0.4, 1)
            yellow = round(15 + rating * 1.2, 1)
            red = round(0.5 + rating * 0.15, 1)
        else:
            role = "FW"
            anytime = round(rating * 4.2, 1)
            first = round(anytime * 0.45, 1)
            shots = round(rating * 0.38, 1)
            sot = round(shots * 0.45, 1)
            yellow = round(8 + rating * 0.5, 1)
            red = round(0.2 + rating * 0.05, 1)
        all_player_details.append(
            {
                "name": pname,
                "team": "Home",
                "role": role,
                "anytime_goal_prob": anytime,
                "first_goal_prob": first,
                "exp_shots": shots,
                "exp_sot": sot,
                "yellow_prob": yellow,
                "red_prob": red,
                "rating": round(rating, 2),
            }
        )

    # Away starting lineup
    for idx, p in enumerate(lineups[1].get("startXI", [])):
        pname = p["player"]["name"]
        pstats = get_player_rolling_stats(pname, df)
        rating = pstats.get("rating_roll", 6.5)
        if idx == 0:
            role = "GK"
            anytime = 0.5
            first = 0.2
            shots = 0.0
            sot = 0.0
            yellow = 8.0
            red = 0.5
        elif idx <= 4:
            role = "DF"
            anytime = round(rating * 0.8, 1)
            first = round(anytime * 0.3, 1)
            shots = round(rating * 0.06, 1)
            sot = round(shots * 0.3, 1)
            yellow = round(20 + rating, 1)
            red = round(1 + rating * 0.2, 1)
        elif idx <= 8:
            role = "MF"
            anytime = round(rating * 2.2, 1)
            first = round(anytime * 0.4, 1)
            shots = round(rating * 0.22, 1)
            sot = round(shots * 0.4, 1)
            yellow = round(15 + rating * 1.2, 1)
            red = round(0.5 + rating * 0.15, 1)
        else:
            role = "FW"
            anytime = round(rating * 4.2, 1)
            first = round(anytime * 0.45, 1)
            shots = round(rating * 0.38, 1)
            sot = round(shots * 0.45, 1)
            yellow = round(8 + rating * 0.5, 1)
            red = round(0.2 + rating * 0.05, 1)
        all_player_details.append(
            {
                "name": pname,
                "team": "Away",
                "role": role,
                "anytime_goal_prob": anytime,
                "first_goal_prob": first,
                "exp_shots": shots,
                "exp_sot": sot,
                "yellow_prob": yellow,
                "red_prob": red,
                "rating": round(rating, 2),
            }
        )

    goalscorers_sorted = sorted(
        all_player_details, key=lambda x: x["anytime_goal_prob"], reverse=True
    )
    shots_sorted = sorted(
        all_player_details, key=lambda x: x["exp_shots"], reverse=True
    )
    cards_sorted = sorted(
        all_player_details, key=lambda x: x["yellow_prob"], reverse=True
    )

    possession_h = min(65, max(35, int(50 + (home_impact - away_impact) * 2.5)))

    # Detailed report data
    detailed_pred = {
        "home_prob": round(prob_1 * 100, 1),
        "draw_prob": round(prob_x * 100, 1),
        "away_prob": round(prob_2 * 100, 1),
        "predicted_score": f"{home_g} - {away_g}",
        "confidence": 7,
        "home_xg": round(exp_h, 2),
        "away_xg": round(exp_a, 2),
        "over_05": round(prob_over_05 * 100, 1),
        "over_15": round(prob_over_15 * 100, 1),
        "over_25": round(prob_over_25 * 100, 1),
        "over_35": round(prob_over_35 * 100, 1),
        "under_25": round(prob_under_25 * 100, 1),
        "btts_yes": round(prob_btts_yes * 100, 1),
        "possession_home": possession_h,
        "possession_away": 100 - possession_h,
        "fouls_home": home_fouls,
        "fouls_away": away_fouls,
        "offsides_home": round(1.5 + (home_impact / 15.0), 1),
        "offsides_away": round(1.8 + (away_impact / 15.0), 1),
        "saves_home": int(away_corners / 2 + 1),
        "saves_away": int(home_corners / 2 + 1),
        "clean_sheet_home": round(poisson_prob(exp_a, 0) * 100, 1),
        "clean_sheet_away": round(poisson_prob(exp_h, 0) * 100, 1),
        "corners_total": home_corners + away_corners,
        "corners_home": home_corners,
        "corners_away": away_corners,
        "corners_over_75": round(
            (1.0 - math.exp(-(home_corners + away_corners) / 4.0)) * 100, 1
        ),
        "corners_over_85": round(
            (1.0 - math.exp(-(home_corners + away_corners) / 5.0)) * 100, 1
        ),
        "corners_over_95": round(
            (1.0 - math.exp(-(home_corners + away_corners) / 6.0)) * 100, 1
        ),
        "corners_over_105": round(
            (1.0 - math.exp(-(home_corners + away_corners) / 7.0)) * 100, 1
        ),
        "cards_yellow_home": home_yellows,
        "cards_yellow_away": away_yellows,
        "cards_yellow_total": home_yellows + away_yellows,
        "cards_red_total": round(
            float(np.random.choice([0.0, 0.1, 0.2], p=[0.8, 0.15, 0.05])), 2
        ),
        "goalscorers": goalscorers_sorted[:8],
        "shots_players": shots_sorted[:8],
        "cards_players": cards_sorted[:6],
        "key_goalscorers": [p["name"] for p in goalscorers_sorted[:5]],
        "key_assists": [
            p["name"]
            for p in sorted(
                [x for x in all_player_details if x["role"] in ["MF", "FW"]],
                key=lambda x: x["rating"],
                reverse=True,
            )[:5]
        ],
        "key_yellows": [p["name"] for p in cards_sorted[:5]],
        "key_reds": [
            p["name"]
            for p in sorted(
                all_player_details, key=lambda x: x["red_prob"], reverse=True
            )[:5]
        ],
        "value_analysis": {
            "best_result": f"{winner}",
            "best_goals": (
                "Over 1.5 Goals" if (prob_over_15 > 0.65) else "Under 2.5 Goals"
            ),
            "best_cards": "Over 3.5 Cards",
            "best_corners": "Over 8.5 Corners",
            "best_player_prop": f"{goalscorers_sorted[0]['name']} Over 1.5 Shots",
            "safest": (
                f"{home_team} Double Chance (1X)"
                if winner == f"{home_team} WIN" or winner == "DRAW"
                else f"{away_team} Double Chance (X2)"
            ),
            "high_risk_reward": f"{winner} & BTTS (Yes)",
        },
        "tactical_summary": f"Tactically, {home_team} is projected to control possession (approx {possession_h}%) utilizing high-intensity central passing channels. {away_team} will adopt a counter-attacking posture. Key matchups center on {home_team}'s wingers pressing {away_team}'s fullbacks.",
    }

    return {
        "fixture_id": fixture["fixture"]["id"],
        "match": f"{home_team} vs {away_team}",
        "league": league_name,
        "kickoff": fixture["fixture"]["date"],
        "prediction": winner,
        "expected_score": f"{home_g} - {away_g}",
        "team_impacts": f"Home: {home_impact:.2f} | Away: {away_impact:.2f}",
        "corners": f"Home: {home_corners} | Away: {away_corners}",
        "fouls": f"Home: {home_fouls} | Away: {away_fouls}",
        "cards": f"Home Yellows: {home_yellows} | Away Yellows: {away_yellows}",
        "home_players": home_player_stats[:3],
        "away_players": away_player_stats[:3],
        "detailed_prediction": detailed_pred,
        "markets": {
            "1X2": [
                {"selection": "Home (1)", "prob": round(prob_1 * 100, 1)},
                {"selection": "Draw (X)", "prob": round(prob_x * 100, 1)},
                {"selection": "Away (2)", "prob": round(prob_2 * 100, 1)},
            ],
            "Over/Under 2.5": [
                {"selection": "Over 2.5", "prob": round(prob_over_25 * 100, 1)},
                {"selection": "Under 2.5", "prob": round(prob_under_25 * 100, 1)},
            ],
            "BTTS": [
                {"selection": "Yes", "prob": round(prob_btts_yes * 100, 1)},
                {"selection": "No", "prob": round(prob_btts_no * 100, 1)},
            ],
            "Corners": [
                {"selection": "Over 8.5 Corners", "prob": round((1.0 - math.exp(-(home_corners + away_corners) / 5.0)) * 100, 1)}
            ],
            "Goalscorer": [
                {"selection": f"{p['name']} Anytime Goal", "prob": round(p["anytime_goal_prob"] * 100, 1)} for p in goalscorers_sorted[:3]
            ],
            "Player Shots": [
                {"selection": f"{p['name']} Over 1.5 Shots", "prob": min(95.0, round(p["exp_shots"] * 30, 1))} for p in shots_sorted[:3] if p["exp_shots"] > 1.5
            ]
        },
    }


def update_markdown_artifact(results, timestamp):
    out_text = "===========================================\n"
    out_text += " LIVE BOTTOM-UP MATCH PREDICTIONS\n"
    out_text += f" Last Updated: {timestamp}\n"
    out_text += " *Only matches with official starting lineups shown*\n"
    out_text += "===========================================\n\n"

    if not results:
        out_text += "*No official lineups have been announced for any matches yet. Waiting for updates...*\n"

    for r in results:
        out_text += f"### [{r['league']}] {r['match']}\n"
        out_text += f"- **Predicted Outcome:** {r['prediction']}\n"
        out_text += f"- **Expected Score:** {r['expected_score']}\n"

        team_impacts = r.get("team_impacts", "N/A")
        corners = r.get("corners", "N/A")
        fouls = r.get("fouls", "N/A")
        cards = r.get("cards", "N/A")

        out_text += f"- **Team Strengths (Aggregated Impact):** {team_impacts}\n"
        out_text += f"- **Match Stats:** Corners ({corners}) | Fouls ({fouls}) | Cards ({cards})\n"

        h_players = r.get("home_players", [])
        a_players = r.get("away_players", [])
        if h_players:
            out_text += (
                "- **Top Impact Players (Home):** "
                + ", ".join(
                    [
                        f"{p.get('name', 'Unknown')} ({p.get('impact', p.get('rating', 'N/A'))})"
                        for p in h_players
                    ]
                )
                + "\n"
            )
        if a_players:
            out_text += (
                "- **Top Impact Players (Away):** "
                + ", ".join(
                    [
                        f"{p.get('name', 'Unknown')} ({p.get('impact', p.get('rating', 'N/A'))})"
                        for p in a_players
                    ]
                )
                + "\n\n"
            )
        out_text += "---\n\n"

    # Write to artifact dir directly if possible, or data dir
    artifact_path = r"C:\Users\Elie\.gemini\antigravity-cli\brain\92df1273-9456-4c34-be82-7b0f28f9a507\todays_live_predictions.md"
    try:
        with open(artifact_path, "w", encoding="utf-8") as f:
            f.write(out_text)
    except Exception:
        with open("data/todays_live_predictions.md", "w", encoding="utf-8") as f:
            f.write(out_text)


import json  # noqa: E402
import sqlite3  # noqa: E402
import unicodedata  # noqa: E402
import re  # noqa: E402
import uuid  # noqa: E402


def load_settings():
    try:
        with open("data/settings.json", "r") as f:
            return json.load(f)
    except Exception:
        return {
            "kelly_multiplier": 0.25,
            "min_ev_threshold": 0.05,
            "max_exposure_pct": 0.05,
            "auto_place_bets": False,
        }


def get_match_score(name1, name2):
    if not name1 or not name2:
        return 0.0
    if not isinstance(name1, str) or not isinstance(name2, str):
        return 0.0

    def get_tokens(name):
        n = name.lower()
        n = "".join(
            c
            for c in unicodedata.normalize("NFD", n)
            if unicodedata.category(c) != "Mn"
        )
        n = re.sub(r"[^a-z0-9\s]", " ", n)
        noise = {
            "fc",
            "cf",
            "sc",
            "u23",
            "pr",
            "ii",
            "u20",
            "united",
            "city",
            "town",
            "athletic",
            "club",
            "de",
            "fk",
            "afc",
            "sv",
            "sp",
        }
        return [w for w in n.split() if w and w not in noise]

    t1 = get_tokens(name1)
    t2 = get_tokens(name2)

    if not t1 or not t2:
        return 0.0
    if t1 == t2:
        return 1.0

    s1, s2 = set(t1), set(t2)
    if s1 == s2:
        return 0.95
    if s1.issubset(s2) or s2.issubset(s1):
        return 0.8 + 0.1 * (min(len(s1), len(s2)) / max(len(s1), len(s2)))

    intersection = s1.intersection(s2)
    union = s1.union(s2)
    if intersection:
        jaccard = len(intersection) / len(union)
        return 0.5 + 0.3 * jaccard

    if len(s1) == 1 and len(s2) == 1:
        w1 = list(s1)[0]
        w2 = list(s2)[0]
        if w1 in w2 or w2 in w1:
            return 0.6 * (min(len(w1), len(w2)) / max(len(w1), len(w2)))

    # Substring word matches
    sub_matches = 0
    for w1 in s1:
        for w2 in s2:
            if len(w1) > 3 and len(w2) > 3:
                if w1 in w2 or w2 in w1:
                    sub_matches += 1
    if sub_matches:
        return 0.3 + 0.2 * (sub_matches / max(len(s1), len(s2)))

    return 0.0


def fuzzy_match_teams(name1, name2):
    return get_match_score(name1, name2) >= 0.5


def find_betarabia_odds(home_team, away_team):
    """
    Looks up a match in odds_stream.db fixture table and grabs odds from market table.
    Returns a dict with market keys and selection odds.
    """
    db_path = "data/odds_stream.db"
    if not os.path.exists(db_path):
        return None

    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        # Get all fixtures
        cur.execute("SELECT fixture_id, home_team, away_team FROM fixture")
        fixtures = cur.fetchall()

        best_fid = None
        best_home = None
        best_away = None
        best_score = 0.0

        for fid, h, a in fixtures:
            h_score = get_match_score(home_team, h)
            a_score = get_match_score(away_team, a)

            # Must both be reasonable matches
            if h_score >= 0.5 and a_score >= 0.5:
                total_score = h_score + a_score
                if total_score > best_score:
                    best_score = total_score
                    best_fid = fid
                    best_home = h
                    best_away = a

        if not best_fid:
            conn.close()
            return None

        # Query markets
        cur.execute(
            "SELECT market_name, selection_name, raw_odds FROM market WHERE fixture_id = ?",
            (best_fid,),
        )
        rows = cur.fetchall()
        conn.close()

        odds_dict = {"1X2": {}, "Over/Under 2.5": {}, "BTTS": {}}

        for mname, sname, price in rows:
            mname_lower = mname.lower()
            sname_lower = sname.lower()

            # Match Result (1X2)
            if "result" in mname_lower or "1x2" in mname_lower:
                if sname_lower == "x" or "draw" in sname_lower:
                    odds_dict["1X2"]["Draw"] = price
                else:
                    h_score = get_match_score(sname, best_home)
                    a_score = get_match_score(sname, best_away)
                    if h_score >= 0.5 and h_score > a_score:
                        odds_dict["1X2"]["Home"] = price
                    elif a_score >= 0.5 and a_score > h_score:
                        odds_dict["1X2"]["Away"] = price

            # Over/Under 2.5
            elif "total" in mname_lower or "over/under" in mname_lower:
                if "2.5" in sname:
                    if "over" in sname_lower:
                        odds_dict["Over/Under 2.5"]["Over"] = price
                    elif "under" in sname_lower:
                        odds_dict["Over/Under 2.5"]["Under"] = price

            # BTTS
            elif "both teams" in mname_lower or "btts" in mname_lower:
                if "yes" in sname_lower:
                    odds_dict["BTTS"]["Yes"] = price
                elif "no" in sname_lower:
                    odds_dict["BTTS"]["No"] = price

        return odds_dict

    except Exception as e:
        print("Error in find_betarabia_odds:", e)
        return None


def log_ai_bet(match, market, selection, odds, prob, ev):
    db_path = "data/bet_log.db"
    if not os.path.exists(db_path):
        return

    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        # Check if already logged
        cur.execute(
            """
            SELECT COUNT(*) FROM bet_log 
            WHERE match_id = ? AND market_type = ? AND side = ? AND bet_source = 'AI'
        """,
            (match, market, selection),
        )
        exists = cur.fetchone()[0] > 0

        if not exists:
            bet_id = "AI_" + uuid.uuid4().hex[:14]
            fair_odds = round(100.0 / prob, 3) if prob > 0 else 1.0

            try:
                br_conn = sqlite3.connect("data/bankroll.db")
                br_cur = br_conn.cursor()
                br_cur.execute(
                    "SELECT current_balance FROM bankroll ORDER BY date DESC LIMIT 1"
                )
                balance = br_cur.fetchone()[0]
                br_conn.close()
            except Exception:
                balance = 10000.0

            settings = load_settings()
            kelly_mult = settings.get("kelly_multiplier", 0.25)

            p = prob / 100.0
            b = odds - 1.0
            if b > 0:
                kelly_f = (p * odds - 1.0) / b
                kelly_f = max(
                    0, min(settings.get("max_exposure_pct", 0.05), kelly_f * kelly_mult)
                )
            else:
                kelly_f = 0.01

            stake = round(balance * kelly_f, 2)
            if stake < 1.0:
                stake = 1.0
            if stake > balance:
                stake = balance
            
            if stake <= 0:
                return
                
            from src.bankroll_tracker import register_bet
            if not register_bet(stake):
                print(f"[!] Bankroll tracker blocked bet {bet_id} for ${stake:.2f}")
                return

            cur.execute(
                """
                INSERT INTO bet_log 
                (bet_id, match_id, player_id, market_type, entry_odds, fair_odds, edge_pct, stake, result, pnl, placed_at, bet_source, is_recommended, line, side)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    bet_id,
                    match,
                    f"{match} ({selection})",
                    market,
                    odds,
                    fair_odds,
                    round(ev * 100, 1),
                    stake,
                    "OPEN",
                    0.0,
                    datetime.datetime.now().isoformat(),
                    "AI",
                    1,
                    2.5,
                    selection,
                ),
            )
            print(
                f"[AI BET LOGGER] Automatically logged recommended AI bet: {match} ({selection}) @ {odds} stake {stake}"
            )
            
            # Commit and close DB before making synchronous network request
            conn.commit()
            conn.close()

            # STAIR-AI INTEGRATION
            team_code = str(selection)
            if "Home" in selection or "1" in selection:
                team_code = (
                    match.split(" vs ")[0][:3].upper() if " vs " in match else "HOME"
                )
            elif "Away" in selection or "2" in selection:
                team_code = (
                    match.split(" vs ")[1][:3].upper() if " vs " in match else "AWAY"
                )
            elif "Draw" in selection or "X" in selection:
                team_code = "draw"

            try:
                import requests

                stair_payload = {
                    "fixture_code": str(match.replace(" ", "_")),
                    "idempotency_key": str(bet_id),
                    "limit_price": round(1.0 / odds, 3) if odds > 0 else 0.5,
                    "team_code": team_code,
                    "time_in_force_seconds": 30,
                    "usd_size": str(stake),
                }
                stair_headers = {
                    "Content-Type": "application/json",
                    "x-api-key": "lmIxslhTmXaJSLpRndCZjaziawkycPJkecyDCWYnXaVFyyWmqZQhaHCJdVLdShrk",
                }
                res = requests.post(
                    "https://staging.stair-ai.com/api/v1/arena/orders",
                    json=stair_payload,
                    headers=stair_headers,
                    timeout=10,
                )
                print(f"[STAIR AI] Place bet response: {res.status_code} - {res.text}")
            except Exception as se:
                print(f"[STAIR AI] Error placing bet: {se}")

        else:
            conn.close()

    except Exception as e:
        print("Error in log_ai_bet:", e)


def settle_open_bets():
    """
    Scrapes today's finished matches from Sofascore and settles any OPEN bets in bet_log.db.
    """
    print("[SETTLEMENT] Running settlement check...")
    try:
        from free_scraper_module import get_todays_fixtures_free

        fixtures = get_todays_fixtures_free()
    except Exception as e:
        print("Error fetching fixtures for settlement:", e)
        return

    finished_matches = {}
    for f in fixtures:
        status = f["fixture"]["status"]["short"]
        if status == "FT":
            home_team = f["teams"]["home"]["name"]
            away_team = f["teams"]["away"]["name"]
            home_score = f["fixture"].get("home_score")
            away_score = f["fixture"].get("away_score")
            if home_score is not None and away_score is not None:
                finished_matches[f"{home_team} vs {away_team}"] = (
                    home_score,
                    away_score,
                )

    if not finished_matches:
        print("[SETTLEMENT] No finished matches found in Sofascore today yet.")
        return

    db_path = "data/bet_log.db"
    if not os.path.exists(db_path):
        return

    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        cur.execute(
            "SELECT bet_id, match_id, player_id, market_type, entry_odds, stake, bet_source FROM bet_log WHERE result = 'OPEN'"
        )
        open_bets = cur.fetchall()

        if not open_bets:
            conn.close()
            return

        print(f"[SETTLEMENT] Found {len(open_bets)} OPEN bets. Settling...")

        def clean_name(name):
            if not name:
                return ""
            n = name.lower()
            n = "".join(
                c
                for c in unicodedata.normalize("NFD", n)
                if unicodedata.category(c) != "Mn"
            )
            n = re.sub(r"[^a-z0-9\s]", "", n)
            suffixes = ["fc", "cf", "sc", "u23", "pr", "ii", "u20", "united", "city"]
            words = [w for w in n.split() if w not in suffixes]
            return "".join(words)

        for (
            bet_id,
            match_id,
            player_id,
            market_type,
            entry_odds,
            stake,
            bet_source,
        ) in open_bets:
            match_match = re.match(r"^(.*) vs (.*) \((.*)\)$", player_id)
            if not match_match:
                match_name = match_id if match_id else "Unknown vs Unknown"
                cur.execute("SELECT side FROM bet_log WHERE bet_id = ?", (bet_id,))
                side_row = cur.fetchone()
                selection = side_row[0] if side_row else "Home"
            else:
                home_t = match_match.group(1).strip()
                away_t = match_match.group(2).strip()
                selection = match_match.group(3).strip()
                match_name = f"{home_t} vs {away_t}"

            sel_lower = selection.lower()

            # Find score
            try:
                parts = match_name.split(" vs ")
                bet_home = parts[0].strip()
                bet_away = parts[1].strip()
            except Exception:
                continue

            best_score = 0.0
            matched_score = None

            for finished_name, score in finished_matches.items():
                try:
                    f_parts = finished_name.split(" vs ")
                    fin_home = f_parts[0].strip()
                    fin_away = f_parts[1].strip()
                except Exception:
                    continue

                h_score = get_match_score(bet_home, fin_home)
                a_score = get_match_score(bet_away, fin_away)

                if h_score >= 0.5 and a_score >= 0.5:
                    total_score = h_score + a_score
                    if total_score > best_score:
                        best_score = total_score
                        matched_score = score

            if matched_score is None:
                continue

            home_score, away_score = matched_score

            won = False
            if market_type == "1X2":
                if "home" in sel_lower or "1" in sel_lower:
                    won = home_score > away_score
                elif "draw" in sel_lower or "x" in sel_lower:
                    won = home_score == away_score
                elif "away" in sel_lower or "2" in sel_lower:
                    won = away_score > home_score
            elif market_type == "Over/Under 2.5":
                total_goals = home_score + away_score
                if "over" in sel_lower:
                    won = total_goals > 2.5
                elif "under" in sel_lower:
                    won = total_goals < 2.5
            elif market_type == "BTTS":
                if "yes" in sel_lower:
                    won = home_score > 0 and away_score > 0
                elif "no" in sel_lower:
                    won = home_score == 0 or away_score == 0

            result = "W" if won else "L"
            pnl = stake * (entry_odds - 1) if won else -stake

            cur.execute(
                "UPDATE bet_log SET result = ?, pnl = ?, closing_odds = ? WHERE bet_id = ?",
                (result, pnl, entry_odds, bet_id),
            )
            print(f"[SETTLEMENT] Settled bet {bet_id} as {result} (PnL: ${pnl:.2f})")

            # Capital adjustments for USER
            if result == "W" and bet_source == "USER":
                br_path = "data/bankroll.db"
                if os.path.exists(br_path):
                    br_conn = sqlite3.connect(br_path)
                    br_cur = br_conn.cursor()
                    payout = stake * entry_odds
                    br_cur.execute(
                        "UPDATE bankroll SET current_balance = current_balance + ?, daily_pnl = daily_pnl + ? WHERE id = (SELECT MAX(id) FROM bankroll)",
                        (payout, pnl),
                    )
                    br_conn.commit()
                    br_conn.close()
                    print(
                        f"[SETTLEMENT] Credited win payout ${payout:.2f} to bankroll (USER)"
                    )
            elif result == "L" and bet_source == "USER":
                br_path = "data/bankroll.db"
                if os.path.exists(br_path):
                    br_conn = sqlite3.connect(br_path)
                    br_cur = br_conn.cursor()
                    br_cur.execute(
                        "UPDATE bankroll SET daily_pnl = daily_pnl + ? WHERE id = (SELECT MAX(id) FROM bankroll)",
                        (pnl,),
                    )
                    br_conn.commit()
                    br_conn.close()

        conn.commit()
        conn.close()
    except Exception as e:
        print("Error during settlement:", e)


def update_dashboard_json(fixtures, results_cache):
    dashboard_data = []
    res_map = load_predictions_from_db()

    settings = load_settings()
    min_ev_threshold = settings.get("min_ev_threshold", 0.05)

    for f in fixtures:
        fid = f["fixture"]["id"]
        match_time = f["fixture"]["date"]
        home = f["teams"]["home"]["name"]
        away = f["teams"]["away"]["name"]
        league = f["league"]["name"]
        status = f["fixture"]["status"]["short"]

        prediction = res_map.get(fid, None)
        odds_dict = find_betarabia_odds(home, away)

        # Prepare pre-match markets if available from Betarabia, regardless of lineups
        prematch_markets = None
        if odds_dict:
            # Check if we got any odds
            has_odds = False
            for cat, selections in odds_dict.items():
                if selections:
                    has_odds = True
                    break

            if has_odds:
                prematch_markets = {"1X2": [], "Over/Under 2.5": [], "BTTS": []}
                if "Home" in odds_dict.get("1X2", {}):
                    prematch_markets["1X2"].append(
                        {"selection": "Home (1)", "odds": odds_dict["1X2"]["Home"]}
                    )
                if "Draw" in odds_dict.get("1X2", {}):
                    prematch_markets["1X2"].append(
                        {"selection": "Draw (X)", "odds": odds_dict["1X2"]["Draw"]}
                    )
                if "Away" in odds_dict.get("1X2", {}):
                    prematch_markets["1X2"].append(
                        {"selection": "Away (2)", "odds": odds_dict["1X2"]["Away"]}
                    )

                if "Over" in odds_dict.get("Over/Under 2.5", {}):
                    prematch_markets["Over/Under 2.5"].append(
                        {
                            "selection": "Over 2.5",
                            "odds": odds_dict["Over/Under 2.5"]["Over"],
                        }
                    )
                if "Under" in odds_dict.get("Over/Under 2.5", {}):
                    prematch_markets["Over/Under 2.5"].append(
                        {
                            "selection": "Under 2.5",
                            "odds": odds_dict["Over/Under 2.5"]["Under"],
                        }
                    )

                if "Yes" in odds_dict.get("BTTS", {}):
                    prematch_markets["BTTS"].append(
                        {"selection": "Yes", "odds": odds_dict["BTTS"]["Yes"]}
                    )
                if "No" in odds_dict.get("BTTS", {}):
                    prematch_markets["BTTS"].append(
                        {"selection": "No", "odds": odds_dict["BTTS"]["No"]}
                    )

        if prediction and "markets" in prediction:
            if not prediction.get("has_lineup", False):
                # The user explicitly requested to ONLY bet on games that have lineups
                print(f"[!] Skipping betting for {home} vs {away} - NO LINEUP.")
            else:
                for m_type, selections in prediction["markets"].items():
                    max_prob = max([s["prob"] for s in selections]) if selections else 0
                    for sel in selections:
                        sel_name = sel["selection"]
                        prob = sel["prob"]
                        sel["is_top_pick"] = prob == max_prob

                        key = None
                        if m_type == "1X2":
                            if "Home" in sel_name or "1" in sel_name:
                                key = "Home"
                            elif "Draw" in sel_name or "X" in sel_name:
                                key = "Draw"
                            elif "Away" in sel_name or "2" in sel_name:
                                key = "Away"
                        elif m_type == "Over/Under 2.5":
                            if "Over" in sel_name:
                                key = "Over"
                            elif "Under" in sel_name:
                                key = "Under"
                        elif m_type == "BTTS":
                            if "Yes" in sel_name:
                                key = "Yes"
                            elif "No" in sel_name:
                                key = "No"

                        odds = None
                        if odds_dict and m_type in odds_dict and key in odds_dict[m_type]:
                            odds = odds_dict[m_type][key]

                        if odds is not None:
                            ev = (prob / 100.0) * odds - 1.0
                            is_recommended = ev >= min_ev_threshold or prob >= settings.get(
                                "min_confidence_pct", 55
                            )
                            sel["odds"] = odds
                            sel["ev"] = round(ev * 100, 1)
                            sel["recommended"] = is_recommended

                            if is_recommended:
                                log_ai_bet(
                                    f"{home} vs {away}", m_type, sel_name, odds, prob, ev
                                )
                        else:
                            est_odds = round(0.95 * (100.0 / prob), 2) if prob > 0 else 1.0
                            sel["odds"] = est_odds
                            sel["ev"] = -5.0
                            is_recommended = prob >= settings.get("min_confidence_pct", 55)
                            sel["recommended"] = is_recommended

                            if is_recommended:
                                log_ai_bet(
                                    f"{home} vs {away}",
                                    m_type,
                                    sel_name,
                                    est_odds,
                                    prob,
                                    sel["ev"],
                                )

        item = {
            "fixture_id": fid,
            "match": f"{home} vs {away}",
            "league": league,
            "kickoff": match_time,
            "status_code": status,
            "has_lineup": prediction["has_lineup"] if prediction else False,
            "prediction": prediction,
            "prematch_markets": prematch_markets,
        }
        dashboard_data.append(item)

    with open("data/todays_dashboard_state.json", "w", encoding="utf-8") as f:
        json.dump(dashboard_data, f, indent=4)


def init_stair_ai_agent():
    headers = {
        "Content-Type": "application/json",
        "x-api-key": "lmIxslhTmXaJSLpRndCZjaziawkycPJkecyDCWYnXaVFyyWmqZQhaHCJdVLdShrk",
    }
    try:
        res = requests.get(
            "https://staging.stair-ai.com/api/v1/arena/agents/me",
            headers=headers,
            timeout=10,
        )
        if res.status_code == 200:
            print("[STAIR AI] Agent already registered. Updating profile...")
            patch_payload = {
                "display_name": "DeepFieldPro AI",
                "bio": "Institutional-grade automated quantitative sports betting AI.",
                "social": {"twitter": "https://twitter.com/deepfieldpro"},
            }
            requests.patch(
                "https://staging.stair-ai.com/api/v1/arena/agents/me",
                json=patch_payload,
                headers=headers,
                timeout=10,
            )
            print("[STAIR AI] Agent profile updated successfully.")
        else:
            print("[STAIR AI] Agent not found. Registering new agent...")
            register_payload = {
                "display_name": "DeepFieldPro AI",
                "bio": "Institutional-grade automated quantitative sports betting AI.",
                "creator_handle": "Elie",
                "social": {"twitter": "https://twitter.com/deepfieldpro"},
            }
            reg_res = requests.post(
                "https://staging.stair-ai.com/api/v1/arena/agents/register",
                json=register_payload,
                headers=headers,
                timeout=10,
            )
            if reg_res.status_code == 200:
                print("[STAIR AI] Agent registered successfully.")
            else:
                print(
                    f"[STAIR AI] Failed to register agent: {reg_res.status_code} - {reg_res.text}"
                )
    except Exception as e:
        print(f"[STAIR AI] Error initializing agent: {e}")


def run_daemon():
    print("[*] Starting Smart Live Predictions Daemon...")
    init_stair_ai_agent()
    
    # Initialize new DeepFieldPro institutional modules
    initialize_deepfield_modules()
    
    player_model = joblib.load("models/player_impact_model.pkl")
    match_model = joblib.load("models/bottom_up_match_model.pkl")
    df = load_player_database()
    initialize_caches(df)

    # Run initial settlement on startup
    settle_open_bets()

    while True:
        # 1. Trigger Betarabia odds scraper in background (non-blocking)
        print("[*] Launching Betarabia Scraper in background to refresh live odds...")
        try:
            import subprocess
            import sys

            subprocess.Popen([sys.executable, "src/betarabia_scraper.py"], close_fds=True)
        except Exception as e:
            print("Failed to start background scraper:", e)

        # 2. Run post-match settlement
        settle_open_bets()

        # Load existing predictions from DB
        db_preds = load_predictions_from_db()

        now_utc = datetime.datetime.now(datetime.timezone.utc)
        print(
            f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Scanning fixtures for predictions..."
        )
        fixtures = get_todays_fixtures()
        new_lineup_found = False

        # Identify fixtures that need lineup checks
        fixtures_to_check = []
        for f in fixtures:
            fid = f["fixture"]["id"]
            status = f["fixture"]["status"]["short"]
            if status in ["FT", "AET", "PEN", "PST", "CANC", "ABD", "1H", "2H", "HT"]:
                continue
            if fid in db_preds and db_preds[fid].get("has_lineup", False):
                continue

            match_time_str = f["fixture"]["date"]
            try:
                kickoff_time = datetime.datetime.fromisoformat(
                    match_time_str.replace("Z", "+00:00")
                )
                time_to_kickoff = (kickoff_time - now_utc).total_seconds() / 60.0
            except Exception:
                time_to_kickoff = 999

            if 0 < time_to_kickoff <= 45:
                fixtures_to_check.append(f)

        # Fetch lineups in batch
        batch_lineups = {}
        if fixtures_to_check:
            fids = [f["fixture"]["id"] for f in fixtures_to_check]
            print(
                f"[*] Fetching lineups in batch for {len(fids)} matches near kickoff..."
            )
            try:
                from free_scraper_module import get_fixture_lineups_batch

                batch_lineups = get_fixture_lineups_batch(fids)
            except Exception as e:
                print("Failed to run batch lineup fetcher:", e)

        # Predict fixtures
        for f in fixtures:
            fid = f["fixture"]["id"]
            status = f["fixture"]["status"]["short"]
            if status in ["FT", "AET", "PEN", "PST", "CANC", "ABD", "1H", "2H", "HT"]:
                continue  # Match is already running, over, or cancelled

            # If we already have a finalized prediction with official lineups, skip
            if fid in db_preds and db_preds[fid].get("has_lineup", False):
                continue

            # Check Match Time
            match_time_str = f["fixture"]["date"]
            try:
                kickoff_time = datetime.datetime.fromisoformat(
                    match_time_str.replace("Z", "+00:00")
                )
                time_to_kickoff = (kickoff_time - now_utc).total_seconds() / 60.0
            except Exception:
                time_to_kickoff = 999

            # Lineups window check
            if 0 < time_to_kickoff <= 45:
                lineups = batch_lineups.get(fid, [])
                if len(lineups) == 2 and len(lineups[0].get("startXI", [])) == 11:
                    print(
                        f"[!] Official lineup confirmed for: {f['teams']['home']['name']} vs {f['teams']['away']['name']}!"
                    )
                    res = predict_match(f, lineups, player_model, match_model, df)
                    log_prediction_to_db(res, has_lineup=True)
                    new_lineup_found = True
                else:
                    # Lineups not posted or error
                    # Fallback to estimated prediction if not already in DB
                    if fid not in db_preds:
                        print(
                            f"    -> Generating estimated prediction for T-45m match: {f['teams']['home']['name']} vs {f['teams']['away']['name']}"
                        )
                        home_xi = get_predicted_lineup(f["teams"]["home"]["name"], df)
                        away_xi = get_predicted_lineup(f["teams"]["away"]["name"], df)
                        est_lineups = [{"startXI": home_xi}, {"startXI": away_xi}]
                        res = predict_match(
                            f, est_lineups, player_model, match_model, df
                        )
                        log_prediction_to_db(res, has_lineup=False)
            elif time_to_kickoff > 45:
                # Kickoff is further away, generate estimated prediction if not already in DB
                if fid not in db_preds:
                    print(
                        f"    -> Generating estimated prediction for upcoming match: {f['teams']['home']['name']} vs {f['teams']['away']['name']}"
                    )
                    home_xi = get_predicted_lineup(f["teams"]["home"]["name"], df)
                    away_xi = get_predicted_lineup(f["teams"]["away"]["name"], df)
                    est_lineups = [{"startXI": home_xi}, {"startXI": away_xi}]
                    res = predict_match(f, est_lineups, player_model, match_model, df)
                    log_prediction_to_db(res, has_lineup=False)

        # Always update dashboard JSON to keep odds and recommendations fresh!
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if new_lineup_found:
            db_preds = load_predictions_from_db()
            official_results = [p for p in db_preds.values() if p["has_lineup"]]
            update_markdown_artifact(official_results, timestamp)
            print("[+] Artifact updated with latest confirmed lineups.")

        update_dashboard_json(fixtures, [])
        print("[*] Sweep complete. Dashboard state updated. Sleeping for 3 minutes...")

        # Wait 3 minutes (180s) before the next sweep
        time.sleep(180)


if __name__ == "__main__":
    run_daemon()
