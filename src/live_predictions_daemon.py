import sys
import os

# Ensure src is in path to allow 'src' package imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
import joblib
import requests
import datetime
import time
import math
import threading
from src.execution_engine import place_bet # TASK 1: Import place_bet
from src import sharp_edge  # Pinnacle sharp-line steam + Betarabia lagging-value engine

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

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
MODELS_DIR = os.path.join(BASE_DIR, "models")

# Import new DeepFieldPro modules - only the specific classes/functions we actually use
from src.free_scraper_module import (  # noqa: E402
    get_todays_fixtures_free as get_todays_fixtures,
)
from src.models.calibration_engine import ProbabilityCalibrator  # noqa: E402
from src.risk_engine.no_bet_filter import create_no_bet_filter  # noqa: E402
from src.telemetry_warehouse.clv_tracker import create_clv_tracker  # noqa: E402
from src.dfp_config import settings as dfp_settings # institutional risk gates

PLAYER_STATS_CACHE = {}
TEAM_PLAYERS_CACHE = {}

# Global instances for new modules
_xmin_model = None
_xmin_features = None
_probability_calibrator = None
_no_bet_filter = None
_clv_tracker = None

# ── 1X2 probability calibration (Platt) ───────────────────────────────
# Corrects the model's favourite-overconfidence (says 60-70%, wins ~39%).
# Trained by tools/train_1x2_calibrator.py -> models/calibrator_1x2.json.
_CAL_1X2 = None


def _load_1x2_calibrator():
    global _CAL_1X2
    if _CAL_1X2 is not None:
        return _CAL_1X2
    try:
        path = os.path.join(os.path.dirname(__file__), "..", "models", "calibrator_1x2.json")
        with open(path, encoding="utf-8") as f:
            _CAL_1X2 = json.load(f)
            print(f"[+] 1X2 calibrator loaded (Platt a={_CAL_1X2.get('a'):.3f} "
                  f"b={_CAL_1X2.get('b'):.3f}, n={_CAL_1X2.get('n_train')})")
    except Exception:
        _CAL_1X2 = {}     # absent => identity (raw probs)
    return _CAL_1X2


def _calibrate_1x2(prob_pct):
    """Map a raw 1X2 win prob (%) to a calibrated marginal win prob (%).
    Returns the input unchanged if no calibrator is present."""
    c = _load_1x2_calibrator()
    if not c or c.get("type") != "platt":
        return prob_pct
    p = min(0.999999, max(1e-6, prob_pct / 100.0))
    z = math.log(p / (1 - p))
    cal = 1.0 / (1.0 + math.exp(-(c["a"] + c["b"] * z)))
    return round(cal * 100.0, 1)


# ── O/U 2.5 probability calibration (Platt) ───────────────────────────────
# The DC-derived O/U under-estimates total goals (~0.2 low) so it under-calls
# "over". This calibrator (tools/train_ou_calibrator.py -> calibrator_ou25.json)
# removes that bias so the DISPLAYED O/U numbers are honest. NOTE: O/U is still
# OFF the betting whitelist (validated -EV into the close); this is display-only.
_CAL_OU = None


def _load_ou_calibrator():
    global _CAL_OU
    if _CAL_OU is not None:
        return _CAL_OU
    try:
        path = os.path.join(os.path.dirname(__file__), "..", "models", "calibrator_ou25.json")
        with open(path, encoding="utf-8") as f:
            _CAL_OU = json.load(f)
            print(f"[+] O/U 2.5 calibrator loaded (Platt a={_CAL_OU.get('a'):.3f} "
                  f"b={_CAL_OU.get('b'):.3f}, n={_CAL_OU.get('n_train')})")
    except Exception:
        _CAL_OU = {}      # absent => identity (raw probs)
    return _CAL_OU


def _calibrate_over25(prob_pct):
    """Map a raw P(over 2.5) (%) to a bias-corrected P(over 2.5) (%).
    Returns the input unchanged if no calibrator is present."""
    c = _load_ou_calibrator()
    if not c or c.get("type") != "platt":
        return prob_pct
    p = min(0.999999, max(1e-6, prob_pct / 100.0))
    z = math.log(p / (1 - p))
    cal = 1.0 / (1.0 + math.exp(-(c["a"] + c["b"] * z)))
    return round(cal * 100.0, 1)


# ── Real-time STEAM detector (line-movement signal) ────────────────────────
# tools/backtest_market_signals.py showed the side a line moves TOWARD (earliest
# -> latest de-vigged prob) is genuinely predictive — ROI rises with move size
# (+8.8% at >=3% moves, +20% at >=5%), the OPPOSITE of the model. This reads the
# odds_history ledger the daemon already writes (fixture_id, market, selection,
# odds, timestamp) and returns the de-vigged probability move per selection.
def _devig_map(odds_by_sel):
    inv = {s: 1.0 / o for s, o in odds_by_sel.items() if o and o > 0}
    tot = sum(inv.values())
    if tot <= 0 or len(inv) < 2:
        return None
    return {s: v / tot for s, v in inv.items()}


def _odds_history_db():
    return os.path.join(DATA_DIR, "deepfield_browser_data", "completed_fixtures.db")


def _purge_odds_history(days=3):
    """Bound odds_history growth. Steam detection needs only same-day pre-kickoff
    history and CLV settles within a day, so anything older than `days` is dead weight
    (the table was at 31k rows and climbing every scrape)."""
    try:
        con = sqlite3.connect(_odds_history_db())
        con.execute("DELETE FROM odds_history WHERE timestamp < datetime('now', ?)",
                    (f"-{int(days)} days",))
        con.commit()
        con.close()
    except Exception:
        pass


def _steam_moves(fid, m_type):
    """Return {selection: latest_prob - earliest_prob} for a fixture+market, or {}.
    Both snapshots come from the odds_history ledger (latest = most recent logged
    price per selection, which the sniper writes just before this gate runs)."""
    try:
        conn = sqlite3.connect(_odds_history_db())
        rows = conn.execute(
            "SELECT selection, odds, timestamp FROM odds_history "
            "WHERE fixture_id=? AND market=? ORDER BY timestamp ASC",
            (str(fid), m_type)).fetchall()
        conn.close()
    except Exception:
        return {}
    if len({ts for _, _, ts in rows}) < 2:     # need an actual move over time
        return {}
    earliest, latest = {}, {}
    for sel, o, _ts in rows:
        if o and o > 0:
            earliest.setdefault(sel, o)         # first (oldest) price per selection
            latest[sel] = o                     # overwritten -> ends at newest
    early, late = _devig_map(earliest), _devig_map(latest)
    if not early or not late:
        return {}
    return {s: late[s] - early.get(s, late[s]) for s in late}


def _record_steam_signal(fid, league, match, m_type, sel_name, odds, move, kickoff):
    """Append a fired steam pick to the steam_signals research ledger (one row per
    fixture/market/selection — first detection's price sticks). Settled offline by
    tools/steam_report.py. Independent of the model bet path / staking."""
    try:
        conn = sqlite3.connect(_odds_history_db())
        conn.execute(
            """CREATE TABLE IF NOT EXISTS steam_signals (
                   fixture_id TEXT, league TEXT, match TEXT, market TEXT, selection TEXT,
                   entry_odds REAL, steam_move REAL, kickoff TEXT,
                   detected_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                   UNIQUE(fixture_id, market, selection))""")
        conn.execute(
            """INSERT OR IGNORE INTO steam_signals
                   (fixture_id, league, match, market, selection, entry_odds, steam_move, kickoff)
               VALUES (?,?,?,?,?,?,?,?)""",
            (str(fid), league, match, m_type, sel_name, odds, move, kickoff))
        conn.commit()
        conn.close()
    except Exception:
        pass


# ── Dixon-Coles team-strength model (continuous expected goals) ────────────
# Trained by tools/train_dixon_coles.py on 13k historical matches; replaces the
# 3-bucket exp_h/exp_a heuristic for known leagues/teams.
_DC_MODEL = "unloaded"
_DC_TEAM_CACHE = {}
# Map the daemon's live league names -> football-data.co.uk league codes.
_DC_LEAGUE_MAP = {
    "premier league": "E0", "epl": "E0", "england 1": "E0",
    "championship": "E1", "england 2": "E1",
    "laliga": "SP1", "la liga": "SP1", "primera division": "SP1", "spain 1": "SP1",
    "serie a": "I1", "italy 1": "I1",
    "bundesliga": "D1", "germany 1": "D1",
    "ligue 1": "F1", "france 1": "F1",
    "eredivisie": "N1", "netherlands 1": "N1",
    "primeira liga": "P1", "liga portugal": "P1", "portugal 1": "P1",
    "jupiler pro league": "B1", "belgium 1": "B1", "pro league": "B1",
    "premiership": "SC0", "scottish premiership": "SC0", "scotland 1": "SC0",
}


def _load_dc_model():
    global _DC_MODEL
    if _DC_MODEL == "unloaded":
        try:
            from src.models.dixon_coles import DixonColes
            _DC_MODEL = DixonColes.load()
            n = sum(len(lg["teams"]) for lg in _DC_MODEL.leagues.values())
            print(f"[+] Dixon-Coles model loaded ({len(_DC_MODEL.leagues)} leagues, {n} teams)")
        except Exception:
            _DC_MODEL = None
    return _DC_MODEL


def _norm_team(s):
    import re
    import unicodedata
    s = unicodedata.normalize("NFD", str(s).lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    drop = {"fc", "cf", "sc", "afc", "ac", "as", "ss", "ssc", "rc", "cd", "ud",
            "club", "calcio", "the"}
    return " ".join(w for w in s.split() if w not in drop)


def _match_team(league_code, name):
    """Fuzzy-map a live team name to a model team in this league (cached)."""
    import difflib
    key = (league_code, name)
    if key in _DC_TEAM_CACHE:
        return _DC_TEAM_CACHE[key]
    model = _load_dc_model()
    result = None
    if model and league_code in model.leagues:
        teams = list(model.leagues[league_code]["teams"].keys())
        norm_map = {_norm_team(t): t for t in teams}
        target = _norm_team(name)
        if target in norm_map:
            result = norm_map[target]
        else:
            # token-overlap then difflib similarity
            best, best_score = None, 0.0
            tset = set(target.split())
            for nt, orig in norm_map.items():
                ov = len(tset & set(nt.split())) / max(1, len(tset | set(nt.split())))
                sim = difflib.SequenceMatcher(None, target, nt).ratio()
                score = max(ov, sim)
                if score > best_score:
                    best, best_score = orig, score
            if best_score >= 0.6:
                result = best
    _DC_TEAM_CACHE[key] = result
    return result


def _dc_expected_goals(home_team, away_team, league_name):
    """Return (exp_home, exp_away) from Dixon-Coles, or None if not covered."""
    model = _load_dc_model()
    if not model:
        return None
    code = _DC_LEAGUE_MAP.get(str(league_name).strip().lower())
    if not code or code not in model.leagues:
        return None
    h = _match_team(code, home_team)
    a = _match_team(code, away_team)
    if not h or not a:
        return None
    return model.expected_goals(code, h, a)


def initialize_deepfield_modules():
    """Initialize all new DeepFieldPro institutional modules."""
    global _xmin_model, _xmin_features, _probability_calibrator, _no_bet_filter, _clv_tracker

    print("[*] Initializing DeepFieldPro institutional modules...")

    try:
        # Load Expected Minutes model
        xmin_model_path = os.path.join(
            os.path.dirname(__file__), "..", "models", "lgbm_minutes_v1.pkl"
        )
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
        calibrator_path = os.path.join(
            os.path.dirname(__file__), "..", "models", "platt_scaler_sot.pkl"
        )
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
        df1 = pd.read_csv(os.path.join(DATA_DIR, "minor_leagues_2025.csv"))
        df2 = pd.read_csv(os.path.join(DATA_DIR, "world_cup_players_match_logs.csv"))
        df2 = df2.rename(columns={"player_": "player_name", "team_": "team"})
        df = pd.concat([df1, df2], ignore_index=True)
        return df
    except Exception:
        return pd.read_csv(os.path.join(DATA_DIR, "minor_leagues_2025.csv"))


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
    db_path = os.path.join(DATA_DIR, "bet_log.db")
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
            "markets": pred_res.get("markets", {}),
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
    db_path = os.path.join(DATA_DIR, "bet_log.db")
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

            db_markets = extra.get("markets")
            if not db_markets:
                db_markets = {
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
                }

            dp = extra.get("detailed_prediction", {})
            if dp:
                # Reconstruct Corners
                if "Corners" not in db_markets and "corners_over_85" in dp:
                    db_markets["Corners"] = [
                        {"selection": "Over 8.5 Corners", "prob": dp["corners_over_85"]}
                    ]
                # Reconstruct Total Cards
                if "Total Cards" not in db_markets and "cards_yellow_total" in dp:
                    db_markets["Total Cards"] = [
                        {
                            "selection": "Over 3.5 Cards",
                            "prob": round(
                                (1.0 - math.exp(-dp["cards_yellow_total"] / 2.5)) * 100,
                                1,
                            ),
                        }
                    ]
                # Reconstruct Goalscorer
                if "Goalscorer" not in db_markets and "goalscorers" in dp:
                    db_markets["Goalscorer"] = [
                        {
                            "selection": f"{p['name']} Anytime Goal",
                            "prob": (
                                round(p["anytime_goal_prob"], 1)
                                if p["anytime_goal_prob"] > 1.0
                                else round(p["anytime_goal_prob"] * 100, 1)
                            ),
                        }
                        for p in dp["goalscorers"][:3]
                    ]
                # Reconstruct Player Shots
                if "Player Shots" not in db_markets and "shots_players" in dp:
                    db_markets["Player Shots"] = [
                        {
                            "selection": f"{p['name']} Over 1.5 Shots",
                            "prob": min(95.0, round(p["exp_shots"] * 30, 1)),
                        }
                        for p in dp["shots_players"][:3]
                        if p.get("exp_shots", 0) > 1.5
                    ]

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
                "markets": db_markets,
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

    # Continuous team-strength override (Dixon-Coles). When we have ratings for
    # this league + both teams, replace the crude 3-bucket expected goals with
    # model-derived ones so probabilities reflect HOW strong each side is. Falls
    # back to the heuristic above for unknown leagues/teams (e.g. World Cup).
    _dc_eg = _dc_expected_goals(home_team, away_team, league_name)
    if _dc_eg:
        exp_h, exp_a = _dc_eg
        if exp_h > exp_a:
            winner = f"{home_team} WIN"
        elif exp_a > exp_h:
            winner = f"{away_team} WIN"
        else:
            winner = "DRAW"

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
                {"selection": "Home (1)", "prob": _calibrate_1x2(round(prob_1 * 100, 1))},
                {"selection": "Draw (X)", "prob": _calibrate_1x2(round(prob_x * 100, 1))},
                {"selection": "Away (2)", "prob": _calibrate_1x2(round(prob_2 * 100, 1))},
            ],
            "Over/Under 2.5": [
                # Calibrated for honest display; O/U stays off the betting whitelist.
                {"selection": "Over 2.5", "prob": _calibrate_over25(round(prob_over_25 * 100, 1))},
                {"selection": "Under 2.5",
                 "prob": round(100.0 - _calibrate_over25(round(prob_over_25 * 100, 1)), 1)},
            ],
            "BTTS": [
                {"selection": "Yes", "prob": round(prob_btts_yes * 100, 1)},
                {"selection": "No", "prob": round(prob_btts_no * 100, 1)},
            ],
            "Corners": [
                {
                    "selection": "Over 8.5 Corners",
                    "prob": round(
                        (1.0 - math.exp(-(home_corners + away_corners) / 5.0)) * 100, 1
                    ),
                }
            ],
            "Total Cards": [
                {
                    "selection": "Over 3.5 Cards",
                    "prob": round(
                        (1.0 - math.exp(-(home_yellows + away_yellows) / 2.5)) * 100, 1
                    ),
                }
            ],
            "Goalscorer": [
                {
                    "selection": f"{p['name']} Anytime Goal",
                    "prob": round(p["anytime_goal_prob"], 1),
                }
                for p in goalscorers_sorted[:3]
            ],
            "Player Shots": [
                {
                    "selection": f"{p['name']} Over 1.5 Shots",
                    "prob": min(95.0, round(p["exp_shots"] * 30, 1)),
                }
                for p in shots_sorted[:3]
                if p["exp_shots"] > 1.5
            ],
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

    # Write to data dir
    try:
        with open(
            os.path.join(DATA_DIR, "todays_live_predictions.md"), "w", encoding="utf-8"
        ) as f:
            f.write(out_text)
    except Exception as e:
        print(f"Error writing markdown artifact: {e}")


import json  # noqa: E402
import sqlite3  # noqa: E402
import unicodedata  # noqa: E402
import re  # noqa: E402
import uuid  # noqa: E402


def load_settings():
    try:
        with open(os.path.join(DATA_DIR, "settings.json"), "r") as f:
            return json.load(f)
    except Exception:
        return {
            "kelly_multiplier": 0.25,
            "min_ev_threshold": 0.05,
            "max_exposure_pct": 0.05,
            "auto_place_bets": False,
        }


# Canonical team/country aliases. Different feeds name the same team differently:
# our odds feed uses native/French names (Cote d'Ivoire), ESPN uses English (Ivory Coast).
# These have ZERO string overlap, so fuzzy matching fails and the bet never settles.
# Map every known variant to ONE canonical token-phrase, applied before tokenizing.
# Keys/values are already lowercased + accent-stripped (matches get_tokens' pipeline).
_TEAM_ALIASES = {
    "cote d ivoire": "ivory coast",
    "cote divoire": "ivory coast",
    "korea republic": "south korea",
    "korea dpr": "north korea",
    "ir iran": "iran",
    "china pr": "china",
    "usa": "united states",
    "czechia": "czech republic",
    "turkiye": "turkey",
    "cabo verde": "cape verde",
    "the gambia": "gambia",
    "congo dr": "dr congo",
    "dr congo": "dr congo",
    "viet nam": "vietnam",
}


def _apply_aliases(n):
    # n is lowercased, accent-stripped, non-alnum collapsed to spaces, single-spaced.
    n = f" {n} "
    for variant, canon in _TEAM_ALIASES.items():
        n = n.replace(f" {variant} ", f" {canon} ")
    return n.strip()


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
        n = _apply_aliases(re.sub(r"\s+", " ", n).strip())
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


def fetch_betarabia_odds():
    """
    Returns (matches, raw) where `matches` is a dict keyed by "Home vs Away".
    Each value carries the real fixture metadata scraped into odds_stream.db
    so the fixture fallback can show the correct kickoff time / league / status
    instead of stamping "now". Per-match odds are resolved later via
    find_betarabia_odds(home, away).
    """
    db_path = os.path.join(DATA_DIR, "odds_stream.db")
    matches = {}
    if not os.path.exists(db_path):
        return matches, None
    try:
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(
            "SELECT home_team, away_team, kickoff_time, tournament_name FROM fixture"
        )
        for home, away, kickoff_time, tournament in cur.fetchall():
            if not (home and away):
                continue
            # Normalise the scraped ISO kickoff (e.g. 2026-06-09T00:00:00.000Z)
            kickoff_iso = None
            status_short = "NS"
            if kickoff_time:
                try:
                    ko = datetime.datetime.fromisoformat(
                        kickoff_time.replace("Z", "+00:00")
                    )
                    if ko.tzinfo is None:
                        ko = ko.replace(tzinfo=datetime.timezone.utc)
                    kickoff_iso = ko.isoformat()
                    # Mark already-played fixtures as finished so the dashboard
                    # buckets them correctly instead of showing them as upcoming.
                    if ko < now_utc:
                        status_short = "FT"
                except Exception:
                    kickoff_iso = None
            matches[f"{home} vs {away}"] = {
                "kickoff": kickoff_iso,
                "league": tournament or "Betarabia",
                "status": status_short,
            }
        conn.close()
    except Exception as e:
        print(f"[!] fetch_betarabia_odds error: {e}")
    return matches, None


def find_betarabia_odds(home_team, away_team):
    """
    Looks up a match in odds_stream.db fixture table and grabs odds from market table.
    Returns a dict with market keys and selection odds.
    """
    db_path = os.path.join(DATA_DIR, "odds_stream.db")
    if not os.path.exists(db_path):
        return None

    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        # Get all fixtures
        cur.execute("SELECT fixture_id, home_team, away_team, scraped_at FROM fixture")
        fixtures = cur.fetchall()

        best_fid = None
        best_home = None
        best_away = None
        best_score = 0.0
        best_scraped_at = None

        for fid, h, a, sat in fixtures:
            h_score = get_match_score(home_team, h)
            a_score = get_match_score(away_team, a)

            # Must both be reasonable matches
            if h_score >= 0.5 and a_score >= 0.5:
                total_score = h_score + a_score
                # Prefer the best name match; on a tie prefer the FRESHER fixture so a
                # stale lingering duplicate never wins over today's odds (ISO timestamps
                # sort lexically, so newer string == newer time).
                fresher_tie = (total_score == best_score and sat and best_scraped_at
                               and str(sat) > str(best_scraped_at))
                if total_score > best_score or fresher_tie:
                    best_score = total_score
                    best_fid = fid
                    best_home = h
                    best_away = a
                    best_scraped_at = sat

        # Expose how stale the matched fixture's odds are (for the bet-gate guard).
        global _betarabia_odds_age_min
        _betarabia_odds_age_min = None
        if best_scraped_at:
            try:
                _ts = datetime.datetime.fromisoformat(
                    str(best_scraped_at).replace("Z", "+00:00")).timestamp()
                _betarabia_odds_age_min = (time.time() - _ts) / 60.0
            except Exception:
                _betarabia_odds_age_min = None

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

        odds_dict = {
            "1X2": {},
            "Over/Under 2.5": {},
            "BTTS": {},
            "Corners": {},
            "Cards": {},
        }

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
                if "corner" in mname_lower:
                    # Capture corner lines (e.g. Over 8.5 Corners)
                    if "over" in sname_lower:
                        odds_dict["Corners"][sname] = price
                    elif "under" in sname_lower:
                        odds_dict["Corners"][sname] = price
                elif "card" in mname_lower or "booking" in mname_lower:
                    if "over" in sname_lower:
                        odds_dict["Cards"][sname] = price
                    elif "under" in sname_lower:
                        odds_dict["Cards"][sname] = price
                elif "2.5" in sname:
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


# ---------------------------------------------------------------------------
# Closing-line capture
# ---------------------------------------------------------------------------
# CLV (did we beat the close?) is only trustworthy if "closing_odds" is a price
# taken JUST before kickoff. Settlement reads the LAST odds_history row for a
# bet, but the main prediction sweep stops snapshotting a fixture once it drops
# out of today's predictions — so the "close" could be a stale afternoon scrape.
# A dedicated thread fixes that: every CLOSING_CAPTURE_INTERVAL seconds it logs
# the current Betarabia 1X2 price for every OPEN bet whose kickoff is imminent,
# so the final pre-kickoff snapshot is a genuine closing line. Paper-safe — it
# only appends to odds_history; it never places, settles, or sizes anything.
CLOSING_WINDOW_MIN = 30          # snapshot when kickoff is within this many minutes
CLOSING_CAPTURE_INTERVAL = 90    # seconds between capture passes (decoupled from the slow main loop)
_closing_started = False
# Handle to the running Betarabia scraper subprocess. The scraper takes ~3 min
# (it scouts each event's markets one-by-one); spawning a fresh one every cycle
# stacks Chromium instances that exhaust memory and die before writing -> stale
# odds. We keep this handle and only launch a new scrape once the prior finished.
_scraper_proc = None
# Age (minutes) of the Betarabia odds for the fixture most recently looked up by
# find_betarabia_odds(). The bet gate reads this to REFUSE betting on stale odds —
# defence-in-depth so a future scraper failure can never silently bet old prices.
_betarabia_odds_age_min = None


def _kickoff_map():
    """fid(str) -> timezone-aware kickoff datetime, from the dashboard state file."""
    out = {}
    try:
        path = os.path.join(DATA_DIR, "todays_dashboard_state.json")
        with open(path, encoding="utf-8") as f:
            for item in json.load(f):
                fid, ko = item.get("fixture_id"), item.get("kickoff")
                if fid is None or not ko:
                    continue
                try:
                    dt = datetime.datetime.fromisoformat(str(ko).replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=datetime.timezone.utc)
                    out[str(fid)] = dt
                except Exception:
                    continue
    except Exception:
        pass
    return out


def capture_closing_lines():
    """Append the current Betarabia 1X2 price to odds_history for each OPEN bet
    whose kickoff is within CLOSING_WINDOW_MIN. The last such snapshot before
    kickoff becomes the bet's true closing line at settlement."""
    db_path = os.path.join(DATA_DIR, "bet_log.db")
    if not os.path.exists(db_path):
        return 0
    try:
        conn = sqlite3.connect(db_path)
        open_bets = conn.execute(
            "SELECT fixture_id, match_id, side FROM bet_log "
            "WHERE result = 'OPEN' AND market_type = '1X2' "
            "AND fixture_id IS NOT NULL AND fixture_id != ''"
        ).fetchall()
        conn.close()
    except Exception:
        return 0
    if not open_bets:
        return 0

    kickoffs = _kickoff_map()
    now = datetime.datetime.now(datetime.timezone.utc)
    window = datetime.timedelta(minutes=CLOSING_WINDOW_MIN)
    captured = 0
    for fid, match, side in open_bets:
        ko = kickoffs.get(str(fid))
        # Only snapshot in the pre-kickoff window. Unknown/started/far-off -> skip
        # (keeps odds_history from filling with non-closing rows).
        if not ko or not (now <= ko <= now + window):
            continue
        if not match or " vs " not in match:
            continue
        home, away = match.split(" vs ", 1)
        try:
            odds_dict = find_betarabia_odds(home, away)
        except Exception:
            odds_dict = None
        if not odds_dict:
            continue
        key = str(side).split(" (")[0]          # "Home (1)" -> "Home"
        price = (odds_dict.get("1X2") or {}).get(key)
        if not price or price <= 0:
            continue
        try:
            snap = sqlite3.connect(_odds_history_db())
            # Write the bet's EXACT side string so settlement's CLV lookup
            # (which matches odds_history.selection to bet_log.side) finds it.
            snap.execute(
                "INSERT INTO odds_history (fixture_id, market, selection, odds) "
                "VALUES (?, ?, ?, ?)",
                (str(fid), "1X2", side, float(price)),
            )
            snap.commit()
            snap.close()
            captured += 1
        except Exception:
            continue
    if captured:
        print(f"[CLOSING] Captured {captured} pre-kickoff closing line(s) for open bets.")
    return captured


def _closing_capture_loop():
    while True:
        try:
            capture_closing_lines()
        except Exception as e:
            print(f"[CLOSING] capture pass error: {e}")
        time.sleep(CLOSING_CAPTURE_INTERVAL)


def start_closing_capture():
    """Launch the closing-line capture thread once (idempotent)."""
    global _closing_started
    if _closing_started:
        return
    _closing_started = True
    threading.Thread(target=_closing_capture_loop, daemon=True,
                     name="closing-capture").start()
    print("[*] Closing-line capture thread started "
          f"(every {CLOSING_CAPTURE_INTERVAL}s, kickoff window {CLOSING_WINDOW_MIN}m).")


# Sane decimal-odds bands per market. A price outside its band is almost always a STALE
# or GARBLED scrape (e.g. the phantom "Tindastoll vs Augnablik Under 2.5 @ 4.10" that no
# results source could ever settle because the match didn't exist). Reject such bets at
# logging time so they never enter the ledger as forever-OPEN "awaiting result" rows.
_ODDS_BANDS = {
    "1X2": (1.01, 34.0),            # big underdogs exist; >34 or <1.01 is impossible
    "Over/Under 2.5": (1.20, 5.00),  # totals lines live in a tight range
    "BTTS": (1.20, 5.00),
    "Corners": (1.15, 7.00),
    "Total Cards": (1.15, 7.00),
}


def _implausible_odds(market, odds):
    """True if `odds` is outside a sane band for `market` (i.e. stale/garbled)."""
    try:
        o = float(odds)
    except (TypeError, ValueError):
        return True
    lo, hi = _ODDS_BANDS.get(market, (1.01, 51.0))
    return o < lo or o > hi


def log_steam_bet(match, market, selection, odds, steam_move_pct, fixture_id=None, league=None):
    """Shadow flat-stake bet for a fired STEAM (line-movement) signal.

    A SEPARATE strategy from the model: bet_source='STEAM', a FLAT stake (the edge is the
    move itself, not a model probability, so Kelly doesn't apply), settled by settle_open_bets
    like any other 1X2 bet. Paper only — never touches real money. Gated by
    settings.steam_betting_enabled (default True) and deduped per fixture/market/selection."""
    settings = load_settings()
    if not settings.get("steam_betting_enabled", True):
        return
    if _implausible_odds(market, odds):
        print(f"[GUARD] Skipped STEAM bet on implausible {market} odds {odds}: "
              f"{match} ({selection}) — stale/garbled price.")
        return
    db_path = os.path.join(DATA_DIR, "bet_log.db")
    if not os.path.exists(db_path):
        return
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM bet_log WHERE match_id=? AND market_type=? AND side=? "
            "AND bet_source='STEAM'", (match, market, selection))
        if cur.fetchone()[0] > 0:
            conn.close()
            return

        try:
            br_conn = sqlite3.connect(os.path.join(DATA_DIR, "bankroll.db"))
            balance = br_conn.execute(
                "SELECT current_balance FROM bankroll ORDER BY date DESC LIMIT 1").fetchone()[0]
            br_conn.close()
        except Exception:
            balance = 10000.0

        stake = float(settings.get("steam_flat_stake", 25.0))
        if stake > balance:
            stake = balance
        if stake <= 0:
            conn.close()
            return

        from src.bankroll_tracker import register_bet
        if not register_bet(stake):
            conn.close()
            return

        bet_id = "STEAM_" + uuid.uuid4().hex[:12]
        cur.execute(
            """INSERT INTO bet_log
               (bet_id, match_id, player_id, market_type, entry_odds, fair_odds, edge_pct, stake,
                result, pnl, placed_at, bet_source, is_recommended, line, side, fixture_id, league)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (bet_id, match, f"{match} ({selection})", market, odds, odds,
             round(steam_move_pct, 1), stake, "OPEN", 0.0,
             datetime.datetime.now().isoformat(), "STEAM", 1, 2.5, selection,
             str(fixture_id) if fixture_id is not None else None, league))
        conn.commit()
        conn.close()
        print(f"[STEAM BET] Shadow flat-stake bet: {match} ({selection}) @ {odds} "
              f"move +{steam_move_pct:.1f}% stake {stake}")
    except Exception as e:
        print(f"[STEAM BET] error: {e}")


def log_sharp_bet(match, market, selection, odds, sharp_move_pct, fixture_id=None,
                  league=None, source="SHARP"):
    """Shadow flat-stake bet for a sharp-reference signal vs Betarabia. Two sub-strategies,
    each its own bet_source so they're judged separately:
      'SHARP'  - Pinnacle line steamed toward this side AND Betarabia still pays more.
      'SHARPV' - Betarabia is +EV vs Pinnacle's de-vigged fair price (capped band).
    Paper only; gated by settings.sharp_betting_enabled; deduped per pick/source."""
    settings = load_settings()
    if not settings.get("sharp_betting_enabled", True):
        return
    if _implausible_odds(market, odds):
        print(f"[GUARD] Skipped {source} bet on implausible {market} odds {odds}: "
              f"{match} ({selection}) — stale/garbled price.")
        return
    db_path = os.path.join(DATA_DIR, "bet_log.db")
    if not os.path.exists(db_path):
        return
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM bet_log WHERE match_id=? AND market_type=? AND side=? "
            "AND bet_source=?", (match, market, selection, source))
        if cur.fetchone()[0] > 0:
            conn.close()
            return

        try:
            br_conn = sqlite3.connect(os.path.join(DATA_DIR, "bankroll.db"))
            balance = br_conn.execute(
                "SELECT current_balance FROM bankroll ORDER BY date DESC LIMIT 1").fetchone()[0]
            br_conn.close()
        except Exception:
            balance = 10000.0

        stake = float(settings.get("sharp_flat_stake", 25.0))
        if stake > balance:
            stake = balance
        if stake <= 0:
            conn.close()
            return

        from src.bankroll_tracker import register_bet
        if not register_bet(stake):
            conn.close()
            return

        bet_id = f"{source}_" + uuid.uuid4().hex[:12]
        cur.execute(
            """INSERT INTO bet_log
               (bet_id, match_id, player_id, market_type, entry_odds, fair_odds, edge_pct, stake,
                result, pnl, placed_at, bet_source, is_recommended, line, side, fixture_id, league)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (bet_id, match, f"{match} ({selection})", market, odds, odds,
             round(sharp_move_pct, 1), stake, "OPEN", 0.0,
             datetime.datetime.now().isoformat(), source, 1, 2.5, selection,
             str(fixture_id) if fixture_id is not None else None, league))
        conn.commit()
        conn.close()
        _tag = "sharp move" if source == "SHARP" else "value EV"
        print(f"[{source} BET] Shadow flat-stake bet: {match} ({selection}) @ {odds} "
              f"{_tag} +{sharp_move_pct:.1f}% stake {stake}")
    except Exception as e:
        print(f"[{source} BET] error: {e}")


def log_ai_bet(match, market, selection, odds, prob, ev, fixture_id=None, league=None):
    db_path = os.path.join(DATA_DIR, "bet_log.db")
    if not os.path.exists(db_path):
        return
    if _implausible_odds(market, odds):
        print(f"[GUARD] Skipped AI bet on implausible {market} odds {odds}: "
              f"{match} ({selection}) — stale/garbled price.")
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
                br_conn = sqlite3.connect(os.path.join(DATA_DIR, "bankroll.db"))
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
                (bet_id, match_id, player_id, market_type, entry_odds, fair_odds, edge_pct, stake, result, pnl, placed_at, bet_source, is_recommended, line, side, fixture_id, league)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    str(fixture_id) if fixture_id is not None else None,
                    league,
                ),
            )
            print(
                f"[AI BET LOGGER] Automatically logged recommended AI bet: {match} ({selection}) @ {odds} stake {stake}"
            )

            # Commit and close DB before making synchronous network request
            conn.commit()
            conn.close()

            # Massive Edge Alert — best-effort only. WhatsApp is an EXTERNAL, keyed
            # dependency; it must never break or stall the bet path, so isolate it fully.
            if ev >= 1.0:
                try:
                    from src.services.alerting import notifier
                    edge_pct_val = round(ev * 100, 1)
                    alert_msg = (
                        f"🚨 *MASSIVE EDGE ALERT (+{edge_pct_val}%)* 🚨\n\n"
                        f"*Match:* {match}\n"
                        f"*Selection:* {selection}\n"
                        f"*Odds:* {odds}\n"
                        f"*Stake:* ${stake:.2f}\n\n"
                        f"_The AI just sniped this mispriced line!_"
                    )
                    if hasattr(notifier, '_send_whatsapp'):
                        notifier._send_whatsapp(alert_msg)
                    else:
                        notifier.send_general_alert("Massive Edge Alert", alert_msg)
                except Exception as alert_err:
                    print(f"[ALERT] WhatsApp alert skipped (non-fatal): {alert_err}")

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

                # SAFETY GATE — the paper daemon places bets across ALL markets, and the
                # realized track record shows most are heavily -EV (Goalscorer, Player Shots,
                # Over/Under, BTTS all lose money). It must NEVER spend real USDC. Real money
                # flows ONLY through the disciplined 1X2-only Arena path (src/arena_betting.py).
                # Override only with eyes open: set DEEPFIELD_DAEMON_LIVE_ORDERS=1.
                live_orders = os.getenv("DEEPFIELD_DAEMON_LIVE_ORDERS") == "1"
                order_id = None
                if live_orders:
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
                        "x-api-key": _stair_api_key(),
                    }
                    res = requests.post(
                        "https://stair-ai.com/api/v1/arena/orders",
                        json=stair_payload,
                        headers=stair_headers,
                        timeout=10,
                    )
                    print(f"[STAIR AI] Place bet response: {res.status_code} - {res.text}")
                    if res.status_code in [200, 201]:
                        try:
                            res_data = res.json()
                            if "order_id" in res_data:
                                order_id = res_data["order_id"]
                            elif "orderId" in res_data:
                                order_id = res_data["orderId"]
                            elif "data" in res_data and isinstance(res_data["data"], dict):
                                order_id = (
                                    res_data["data"].get("orderId")
                                    or res_data["data"].get("order_id")
                                    or res_data["data"].get("id")
                                )
                            elif "id" in res_data:
                                order_id = res_data["id"]
                        except Exception as json_err:
                            print("[STAIR AI] Error parsing response JSON:", json_err)
                    if not order_id:
                        order_id = f"STAIR_ERR_{bet_id[-8:]}"
                else:
                    # Shadow: record the intent, place no real order.
                    order_id = f"SHADOW_{bet_id[-8:]}"

                # Write to stair_orders
                try:
                    conn2 = sqlite3.connect(db_path)
                    cur2 = conn2.cursor()
                    cur2.execute(
                        "INSERT OR IGNORE INTO stair_orders (bet_id, order_id) VALUES (?, ?)",
                        (bet_id, order_id),
                    )
                    conn2.commit()
                    conn2.close()
                    print(
                        f"[STAIR AI] Order logged to database: {bet_id} -> {order_id}"
                    )
                except Exception as db_err:
                    print("[STAIR AI] Error saving order to database:", db_err)
            except Exception as se:
                print(f"[STAIR AI] Error placing bet: {se}")

        else:
            conn.close()

    except Exception as e:
        print("Error in log_ai_bet:", e)


# API-Football is a FREE tier: 100 requests/day. The settlement loop runs every cycle,
# so calling it uncached burned the whole daily quota in ~25 min — which is why it was
# always "limit reached" and never actually settled anything. Cache per-date with a long
# TTL so we spend only ~48 calls/day (2 dates x hourly), leaving the free source usable
# all day. It has deep league coverage (often incl. Brazilian Serie C) that ESPN lacks.
_apifootball_cache = {}          # date_str -> (epoch_fetched, {match: (hs, as)})
_APIFOOTBALL_TTL = 3600          # 1 hour


def fetch_api_football_results():
    """
    Finished results (today + yesterday UTC) from API-Football, keyed by 'Home vs Away'
    -> (home_score, away_score). Cached (1h TTL) to protect the free 100/day quota.
    Coverage depends on API-Football including the league that was bet on.
    """
    key = os.getenv("API_FOOTBALL_KEY")
    if not key:
        try:
            with open(os.path.join(DATA_DIR, "..", ".env"), encoding="utf-8") as fh:
                for line in fh:
                    if line.startswith("API_FOOTBALL_KEY="):
                        key = line.split("=", 1)[1].strip()
                        break
        except OSError:
            pass
    if not key:
        return {}

    headers = {"x-apisports-key": key}
    results = {}
    now = datetime.datetime.now(datetime.timezone.utc)
    for delta in (0, 1):
        day = (now - datetime.timedelta(days=delta)).strftime("%Y-%m-%d")
        cached = _apifootball_cache.get(day)
        if cached and (time.time() - cached[0]) < _APIFOOTBALL_TTL:
            results.update(cached[1])
            continue
        day_results = {}
        try:
            r = requests.get(
                "https://v3.football.api-sports.io/fixtures",
                headers=headers, params={"date": day}, timeout=20,
            )
            payload = r.json()
            if payload.get("errors"):
                # Quota exhausted or auth error — don't cache an empty (so it retries
                # next hour after the daily reset), just skip this date for now.
                print(f"[SETTLEMENT] API-Football skipped for {day}: {payload['errors']}")
                continue
            data = payload.get("response", [])
        except Exception as e:
            print(f"[SETTLEMENT] API-Football fetch failed for {day}: {e}")
            continue
        for fx in data:
            st = ((fx.get("fixture") or {}).get("status") or {}).get("short")
            if st not in ("FT", "AET", "PEN"):
                continue
            teams = fx.get("teams") or {}
            goals = fx.get("goals") or {}
            home = (teams.get("home") or {}).get("name")
            away = (teams.get("away") or {}).get("name")
            hs, as_ = goals.get("home"), goals.get("away")
            if home and away and hs is not None and as_ is not None:
                day_results[f"{home} vs {away}"] = (hs, as_)
        _apifootball_cache[day] = (time.time(), day_results)
        results.update(day_results)
    if results:
        print(f"[SETTLEMENT] API-Football provided {len(results)} finished results.")
    return results


def settle_open_bets():
    """
    Settles OPEN bets in bet_log.db using finished-match scores. Tries Sofascore first
    (often empty) then augments with API-Football finished results.
    """
    print("[SETTLEMENT] Running settlement check...")

    # Load completed comparisons for minor market results
    completed_path = os.path.join(DATA_DIR, "completed_comparisons.json")
    completed_data = {}
    if os.path.exists(completed_path):
        try:
            import json

            with open(completed_path, "r", encoding="utf-8") as f:
                completed_data = json.load(f)
        except Exception as e:
            print("Error loading completed_comparisons:", e)

    try:
        fixtures = get_todays_fixtures()
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

    # Sofascore is bot-blocked/empty — use the free, key-less results scraper
    # (ESPN + TheSportsDB) as the primary settlement feed.
    try:
        from src.free_results_scraper import get_finished_results
        free_results = get_finished_results()
        finished_matches.update(free_results)
        print(f"[SETTLEMENT] Free results scraper provided {len(free_results)} finished matches.")
    except Exception as e:
        print("[SETTLEMENT] free results scraper failed:", e)

    # Flashscore (keyless, deep coverage down to Brazilian Serie D) — catches the obscure
    # lower-division matches ESPN/TheSportsDB miss. Plain requests, cached, no browser.
    try:
        from src.flashscore_scraper import get_finished_results as fs_results
        flash = fs_results()
        finished_matches.update(flash)
        print(f"[SETTLEMENT] Flashscore provided {len(flash)} finished matches.")
    except Exception as e:
        print("[SETTLEMENT] Flashscore scraper failed:", e)

    # API-Football as an extra source when its daily quota still allows.
    try:
        finished_matches.update(fetch_api_football_results())
    except Exception as e:
        print("[SETTLEMENT] API-Football merge failed:", e)

    if not finished_matches:
        print("[SETTLEMENT] No finished matches found from any source yet.")
        return

    db_path = os.path.join(DATA_DIR, "bet_log.db")
    if not os.path.exists(db_path):
        return

    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        cur.execute(
            "SELECT bet_id, match_id, player_id, market_type, entry_odds, stake, bet_source, fixture_id, side FROM bet_log WHERE result = 'OPEN'"
        )
        open_bets = cur.fetchall()

        if not open_bets:
            conn.close()
            return

        print(f"[SETTLEMENT] Found {len(open_bets)} OPEN bets. Settling...")

        # REAL prop stats (corners/cards) from Flashscore — only for matches that actually
        # have an open Corners/Total Cards bet (keeps it cheap). Replaces the old hash()
        # fabrication: a prop bet settles only from a real stat, else it stays OPEN.
        prop_stats = {}
        prop_match_ids = {mid for (_, mid, _, mt, *_ ) in open_bets
                          if mt in ("Corners", "Total Cards") and mid}
        if prop_match_ids:
            try:
                from src.flashscore_stats import stats_for_matches
                prop_stats = stats_for_matches(prop_match_ids)
                print(f"[SETTLEMENT] Flashscore stats for {len(prop_stats)}/{len(prop_match_ids)} "
                      f"prop match(es).")
            except Exception as e:
                print("[SETTLEMENT] Flashscore stats fetch failed:", e)

        # Kickoff map (fixture_id -> kickoff dt) so CLV uses the last PRE-KICKOFF price.
        # Without this, CLV picks the absolute-last odds_history row, which can be an
        # IN-PLAY price (favourite scores -> odds crash), producing a fake +CLV mirage.
        try:
            ko_map = _kickoff_map()
        except Exception:
            ko_map = {}

        # Load existing predictions mapping to lookup detailed stats
        res_map = load_predictions_from_db()

        def clean_name(name):
            if not name:
                return ""
            import re
            import unicodedata

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
            bet_fixture_id,
            bet_side,
        ) in open_bets:
            import re

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

            candidates = []   # (total_name_score, result_score, finished_name)
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
                    candidates.append((h_score + a_score, score, finished_name))

            if not candidates:
                continue

            candidates.sort(key=lambda c: c[0], reverse=True)
            best_total, matched_score, best_name = candidates[0]

            # AMBIGUITY GUARD: if a DIFFERENT finished match is nearly as good a name
            # match AND reports a DIFFERENT score, refuse to settle this cycle rather
            # than grade the bet against possibly the wrong game. (Loose 0.5 name
            # matching with no date check can otherwise settle on the wrong fixture —
            # the same false-match class as the sharp engine's Iraq->Iran bug.) The bet
            # stays OPEN and retries next cycle; a wrong settlement would corrupt ROI/CLV.
            if len(candidates) > 1:
                second_total, second_score, second_name = candidates[1]
                if (best_total - second_total) < 0.30 and second_score != matched_score:
                    print(f"[SETTLEMENT] Ambiguous result match for '{match_name}': "
                          f"'{best_name}'{matched_score} vs '{second_name}'{second_score} "
                          f"— skipping to avoid wrong settlement.")
                    continue

            home_score, away_score = matched_score

            # Check if match is in completed_comparisons.json
            match_in_completed = False
            act_corners = None
            act_cards = None
            scored_players = []
            player_shots_val = {}

            fixture_id_str = None
            for fid, pred in res_map.items():
                if pred.get("match") == match_name or clean_name(
                    pred.get("match")
                ) == clean_name(match_name):
                    fixture_id_str = str(fid)
                    break

            if fixture_id_str and fixture_id_str in completed_data:
                match_in_completed = True
                comp_match = completed_data[fixture_id_str]
                act_corners = comp_match.get("corners_total")
                act_cards = comp_match.get("cards_yellow_total")
                scored_players = [
                    g.get("player", "").lower() for g in comp_match.get("goals", [])
                ]
                for p_stat in comp_match.get("player_stats", []):
                    player_shots_val[p_stat.get("name", "").lower()] = p_stat.get(
                        "shots", 0
                    )

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
            elif market_type == "Corners":
                if act_corners is None:
                    # Fall back to REAL Flashscore corner stats; never fabricate.
                    ps = prop_stats.get(match_id)
                    if ps and ps.get("corners_total") is not None:
                        act_corners = ps["corners_total"]
                    else:
                        continue  # no real corner data yet → leave OPEN

                line_match = re.search(r"(\d+\.\d+|\d+)", sel_lower)
                line_val = float(line_match.group(1)) if line_match else 8.5
                if "over" in sel_lower:
                    won = act_corners > line_val
                else:
                    won = act_corners < line_val
            elif market_type == "Total Cards":
                if act_cards is None:
                    # Fall back to REAL Flashscore card stats; never fabricate.
                    ps = prop_stats.get(match_id)
                    if ps and ps.get("cards_total") is not None:
                        act_cards = ps["cards_total"]
                    else:
                        continue  # no real card data yet → leave OPEN

                line_match = re.search(r"(\d+\.\d+|\d+)", sel_lower)
                line_val = float(line_match.group(1)) if line_match else 3.5
                if "over" in sel_lower:
                    won = act_cards > line_val
                else:
                    won = act_cards < line_val
            elif market_type == "Goalscorer":
                player_name_extracted = (
                    selection.replace("Anytime Goal", "")
                    .replace("Anytime", "")
                    .replace("Goal", "")
                    .strip()
                )
                p_name_lower = player_name_extracted.lower()

                if match_in_completed:
                    won = any(
                        p_name_lower in sp or sp in p_name_lower
                        for sp in scored_players
                    )
                else:
                    player_team = "Home"
                    if fixture_id_str and fixture_id_str in res_map:
                        dp = res_map[int(fixture_id_str)].get("detailed_prediction", {})
                        for pl in dp.get("goalscorers", []):
                            if (
                                p_name_lower in pl["name"].lower()
                                or pl["name"].lower() in p_name_lower
                            ):
                                player_team = pl.get("team", "Home")
                                break

                    team_scored = (
                        home_score > 0 if player_team == "Home" else away_score > 0
                    )
                    if team_scored:
                        # Team scored but we lack per-player goal data → genuinely unknown.
                        # Leave OPEN rather than fabricate a win from hash(bet_id).
                        continue
                    else:
                        # Team scored 0 → the player provably did not score. Real settle.
                        won = False
            elif market_type == "Player Shots":
                player_name_extracted = selection.split(" Over ")[0].strip()
                p_name_lower = player_name_extracted.lower()

                line_match = re.search(r"(\d+\.\d+|\d+)", sel_lower)
                line_val = float(line_match.group(1)) if line_match else 1.5

                if match_in_completed:
                    shots_val = 0
                    for name, val in player_shots_val.items():
                        if p_name_lower in name or name in p_name_lower:
                            shots_val = val
                            break
                    won = shots_val > line_val
                else:
                    # No real per-player shot data → leave OPEN, never fabricate from hash.
                    continue

            result = "W" if won else "L"
            pnl = stake * (entry_odds - 1) if won else -stake
            payout = stake * entry_odds if won else 0.0

            # CLV (Closing Line Value): compare our entry price to the LAST price we
            # observed for this exact fixture/market/selection in odds_history. CLV>0
            # means we beat the close — the strongest leading indicator of a real edge,
            # and it validates in far fewer bets than waiting on win/loss.
            closing_odds = entry_odds
            clv = None
            try:
                if bet_fixture_id:
                    # Use the last snapshot taken BEFORE kickoff (odds_history.timestamp is
                    # UTC). This excludes in-play prices that would fake a huge CLV.
                    ko = ko_map.get(str(bet_fixture_id))
                    snap = sqlite3.connect(
                        os.path.join(DATA_DIR, "deepfield_browser_data", "completed_fixtures.db")
                    )
                    sc = snap.cursor()
                    if ko is not None:
                        ko_utc = ko.astimezone(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                        sc.execute(
                            "SELECT odds FROM odds_history WHERE fixture_id = ? AND market = ? "
                            "AND selection = ? AND timestamp <= ? ORDER BY timestamp DESC LIMIT 1",
                            (str(bet_fixture_id), market_type, bet_side, ko_utc),
                        )
                        row = sc.fetchone()
                    else:
                        row = None
                    if not row:  # no kickoff or no pre-kickoff snapshot -> best available
                        sc.execute(
                            "SELECT odds FROM odds_history WHERE fixture_id = ? AND market = ? "
                            "AND selection = ? ORDER BY rowid DESC LIMIT 1",
                            (str(bet_fixture_id), market_type, bet_side),
                        )
                        row = sc.fetchone()
                    snap.close()
                    if row and row[0] and float(row[0]) > 0:
                        c_odds = float(row[0])
                        c_clv = round(entry_odds / c_odds - 1.0, 4)
                        # Sanity guard: real CLV is rarely beyond +-40%. A larger value means a
                        # stale/garbled/in-play close, not edge — record price but drop the CLV.
                        if abs(c_clv) <= 0.40:
                            closing_odds = c_odds
                            clv = c_clv
                        else:
                            closing_odds = c_odds  # keep the observed close for the record
            except Exception:
                pass

            cur.execute(
                "UPDATE bet_log SET result = ?, pnl = ?, closing_odds = ?, clv = ? WHERE bet_id = ?",
                (result, pnl, closing_odds, clv, bet_id),
            )
            _clv_str = f" CLV {clv*100:+.1f}%" if clv is not None else ""
            print(f"[SETTLEMENT] Settled bet {bet_id} as {result} (PnL: ${pnl:.2f}){_clv_str}")

            # Capital adjustments via Central Tracker
            from src.bankroll_tracker import register_settlement
            register_settlement(payout, pnl)

        # PARLAY SETTLEMENT
        cur.execute("SELECT parlay_id, legs_json, stake, total_odds FROM parlay_log WHERE result = 'OPEN'")
        open_parlays = cur.fetchall()
        
        for p_id, legs_json, p_stake, p_odds in open_parlays:
            import json
            legs = json.loads(legs_json)
            parlay_finished = True
            parlay_won = True
            any_leg_lost = False
            legs_updated = False
            
            for leg in legs:
                if leg.get('result') in ['W', 'L']:
                    if leg['result'] == 'L':
                        any_leg_lost = True
                    continue
                
                # Try to settle this leg
                leg_match_name = leg['match']
                leg_market = leg['market']
                leg_selection = leg['selection'].lower()
                
                # Find score
                best_s = 0.0
                m_score = None
                for fin_name, score in finished_matches.items():
                    h_s = get_match_score(leg_match_name.split(' vs ')[0], fin_name.split(' vs ')[0])
                    a_s = get_match_score(leg_match_name.split(' vs ')[1], fin_name.split(' vs ')[1])
                    if h_s >= 0.5 and a_s >= 0.5:
                        if (h_s + a_s) > best_s:
                            best_s = h_s + a_s
                            m_score = score
                
                if m_score:
                    h_score, a_score = m_score
                    # Basic 1X2 / OU settlement for parlay legs
                    leg_won = False
                    if leg_market == 'Match Result':
                        if '1' in leg_selection or 'home' in leg_selection: leg_won = h_score > a_score
                        elif 'x' in leg_selection or 'draw' in leg_selection: leg_won = h_score == a_score
                        else: leg_won = a_score > h_score
                    elif 'Total Goals' in leg_market:
                        line = 2.5 # Default
                        if 'over' in leg_selection: leg_won = (h_score + a_score) > line
                        else: leg_won = (h_score + a_score) < line
                    else:
                        # No real data for this leg's market → leave the parlay OPEN rather
                        # than fabricate a leg result from hash (the old "random for demo").
                        parlay_finished = False
                        continue

                    leg['result'] = 'W' if leg_won else 'L'
                    if not leg_won: any_leg_lost = True
                    legs_updated = True
                else:
                    parlay_finished = False # Still waiting for some legs
            
            if any_leg_lost:
                res = 'L'
                pnl = -p_stake
                cur.execute("UPDATE parlay_log SET result = ?, pnl = ?, legs_json = ? WHERE parlay_id = ?", (res, pnl, json.dumps(legs), p_id))
                from src.bankroll_tracker import register_settlement
                register_settlement(0.0, pnl)
                print(f"[SETTLEMENT] Parlay {p_id} LOST.")
            elif parlay_finished:
                res = 'W'
                pnl = p_stake * (p_odds - 1)
                payout = p_stake * p_odds
                cur.execute("UPDATE parlay_log SET result = ?, pnl = ?, legs_json = ? WHERE parlay_id = ?", (res, pnl, json.dumps(legs), p_id))
                from src.bankroll_tracker import register_settlement
                register_settlement(payout, pnl)
                print(f"[SETTLEMENT] Parlay {p_id} WON! (PnL: ${pnl:.2f})")
            elif legs_updated:
                # Update legs even if parlay is still open
                cur.execute("UPDATE parlay_log SET legs_json = ? WHERE parlay_id = ?", (json.dumps(legs), p_id))

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
        status = f["fixture"]["status"]["short"]

        # Filter out finished matches that are more than 12 hours old
        if status in ["FT", "AET", "PEN"]:
            try:
                # Handle ISO format with or without Z
                ts = match_time.replace("Z", "+00:00")
                kickoff_dt = datetime.datetime.fromisoformat(ts)
                now_utc = datetime.datetime.now(datetime.timezone.utc)
                if (now_utc - kickoff_dt).total_seconds() > 12 * 3600:
                    continue
            except Exception:
                pass

        home = f["teams"]["home"]["name"]
        away = f["teams"]["away"]["name"]
        league = f["league"]["name"]

        prediction = res_map.get(fid, None)
        odds_dict = find_betarabia_odds(home, away)
        # Freshness guard: refuse to bet on STALE Betarabia odds (defence-in-depth so a
        # future scraper regression can never silently bet old prices). Age was set by
        # the find_betarabia_odds call just above for this exact fixture.
        _max_stale_min = load_settings().get("max_odds_staleness_min", 60)
        odds_fresh = (_betarabia_odds_age_min is None
                      or _betarabia_odds_age_min <= _max_stale_min)

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
            # Always attach the real Betarabia price to each market selection so the
            # dashboard shows actual odds (not "@ 0.00"), even for estimated XI.
            # BUT only place a bet when OFFICIAL lineups are confirmed (has_lineup).
            bet_allowed = bool(prediction.get("has_lineup", False))
            if True:
                match_bet_candidates = []
                for m_type, selections in prediction["markets"].items():
                    for sel in selections:
                        sel_name = sel["selection"]
                        prob = sel["prob"]

                        # Determine Key for odds lookup
                        key = None
                        if m_type == "1X2":
                            if "Home" in sel_name or "1" in sel_name: key = "Home"
                            elif "Draw" in sel_name or "X" in sel_name: key = "Draw"
                            elif "Away" in sel_name or "2" in sel_name: key = "Away"
                        elif m_type == "Over/Under 2.5":
                            if "Over" in sel_name: key = "Over"
                            elif "Under" in sel_name: key = "Under"
                        elif m_type == "BTTS":
                            if "Yes" in sel_name: key = "Yes"
                            elif "No" in sel_name: key = "No"
                        elif m_type == "Corners": key = sel_name
                        elif m_type == "Total Cards": key = sel_name

                        odds = None
                        all_market_odds = []
                        if odds_dict:
                            if m_type in odds_dict and key in odds_dict[m_type]:
                                odds = odds_dict[m_type][key]
                                all_market_odds = list(odds_dict[m_type].values())
                            elif m_type == "Corners" and "Corners" in odds_dict:
                                for o_name, o_price in odds_dict["Corners"].items():
                                    if "8.5" in o_name and "over" in o_name.lower(): 
                                        odds = o_price
                                        all_market_odds = [o_price, 1.05] # Dummy under odds if missing
                                        break
                            elif m_type == "Total Cards" and "Cards" in odds_dict:
                                for o_name, o_price in odds_dict["Cards"].items():
                                    if "3.5" in o_name and "over" in o_name.lower(): 
                                        odds = o_price
                                        all_market_odds = [o_price, 1.05]
                                        break

                        if odds is not None:
                            # Sniper / Peak Logic
                            try:
                                conn_sniper = sqlite3.connect(os.path.join(DATA_DIR, "deepfield_browser_data", "completed_fixtures.db"))
                                cur_sniper = conn_sniper.cursor()
                                cur_sniper.execute("INSERT INTO odds_history (fixture_id, market, selection, odds) VALUES (?, ?, ?, ?)", (str(fid), m_type, sel_name, odds))
                                conn_sniper.commit()
                                cur_sniper.execute("SELECT MAX(odds) FROM odds_history WHERE fixture_id = ? AND market = ? AND selection = ?", (str(fid), m_type, sel_name))
                                max_seen_odds = cur_sniper.fetchone()[0] or odds
                                conn_sniper.close()
                            except: max_seen_odds = odds

                            # MARKET BLENDING: shade the model probability toward the
                            # de-vigged market consensus. The market is the single best
                            # predictor; blending cuts variance and stops us betting on
                            # pure model error. Only bets where the model still disagrees
                            # after blending survive. Weight via settings (0=all market,
                            # 1=all model). Needs >=2 outcome odds to de-vig.
                            prob_used = prob / 100.0
                            # De-vigged market prob for THIS selection (single book's
                            # H/D/A prices). Computed unconditionally so the conviction
                            # cap below works regardless of the blend weight.
                            mkt_prob = None
                            if all_market_odds and len(all_market_odds) >= 2 and odds and odds > 0:
                                inv = [1.0 / o for o in all_market_odds if o and o > 0]
                                if inv:
                                    mkt_prob = (1.0 / odds) / sum(inv)
                            blend_w = settings.get("market_blend_weight", 0.5)
                            if blend_w < 1.0 and mkt_prob is not None:
                                prob_used = blend_w * prob_used + (1.0 - blend_w) * mkt_prob

                            ev = prob_used * odds - 1.0
                            prob = round(prob_used * 100.0, 1)   # downstream gates use blended prob
                            is_at_peak = (odds >= max_seen_odds * 0.98)

                            # CONVICTION CAP (tools/backtest_1x2_lines.py finding): the model's
                            # BIGGEST disagreements with the market are where it is most WRONG —
                            # raising the edge bar made out-of-sample ROI worse, not better. So
                            # bet only MODEST, market-adjacent value and skip "too good to be
                            # true" gaps (model error). edge = blended prob - market prob.
                            edge_cap_pct = settings.get("edge_cap_pct", 10.0)
                            model_edge_pct = ((prob_used - mkt_prob) * 100.0) if mkt_prob is not None else 0.0
                            conviction_ok = (mkt_prob is None) or (model_edge_pct <= edge_cap_pct)
                            
                            # VALUE CHASER LOGIC: Chase high EV even if prob is lower.
                            # If EV > 15%, we allow prob down to 30%. Otherwise need 55%.
                            conf_threshold = settings.get("min_confidence_pct", 55)
                            if ev >= 0.15: conf_threshold = 30.0

                            # MARKET WHITELIST: only bet markets with a proven edge. The
                            # realized record shows ONLY 1X2 is +EV; all props lose 40-80%.
                            # Configurable via settings["allowed_markets"] (default 1X2 only).
                            allowed_markets = settings.get("allowed_markets", ["1X2"])
                            market_allowed = (not allowed_markets) or (m_type in allowed_markets)

                            # LEAGUE BLOCKLIST: skip competitions that have shown no edge
                            # (populate from tools/league_report.py once CLV/ROI data exists).
                            league_blocked = league in (settings.get("league_blocklist") or [])

                            # 1X2 DRAWS excluded: realized record is 0/9 (-100% ROI) and the
                            # model shows no skill on draws (its draw probs sit in the
                            # overconfident long-tail). The 1X2 profit is entirely Home/Away.
                            exclude_draws = settings.get("exclude_draws", True)
                            draw_excluded = exclude_draws and (m_type == "1X2" and key == "Draw")

                            # STEAM signal (line movement) — validated as genuinely
                            # predictive (tools/backtest_market_signals.py), unlike the
                            # model. Detect the de-vigged move toward this selection from
                            # the odds_history ledger, capture fired picks to the research
                            # ledger, and (opt-in) use it to confirm model picks. 1X2 only.
                            steam_min = settings.get("steam_min_move_pct", 3.0) / 100.0
                            steam_move = _steam_moves(fid, m_type).get(sel_name, 0.0) if market_allowed else 0.0
                            sel["steam_move"] = round(steam_move * 100.0, 2)
                            steam_fired = (
                                steam_move >= steam_min
                                and odds and odds >= dfp_settings.MODEL_MIN_ODDS
                                and market_allowed and not league_blocked and not draw_excluded
                                and odds_fresh
                            )
                            if steam_fired:
                                _record_steam_signal(fid, league, f"{home} vs {away}",
                                                     m_type, sel_name, odds, steam_move, match_time)
                                # Flat-stake shadow bet for the steam signal (separate
                                # strategy from the model; paper only; deduped internally).
                                log_steam_bet(f"{home} vs {away}", m_type, sel_name, odds,
                                              steam_move * 100.0, fid, league)
                            # SHARP EDGE (Pinnacle): the strongest validated play — bet
                            # Betarabia when the SHARP line steamed toward this side AND
                            # Betarabia still offers a better price than Pinnacle (lagging
                            # value). Separate strategy (bet_source='SHARP'); paper only.
                            if (market_allowed and not league_blocked and not draw_excluded
                                    and odds and odds_fresh):
                                try:
                                    _ko = None
                                    try:
                                        _dt = datetime.datetime.fromisoformat(
                                            str(match_time).replace("Z", "+00:00"))
                                        if _dt.tzinfo is None:
                                            _dt = _dt.replace(tzinfo=datetime.timezone.utc)
                                        _ko = _dt.timestamp()
                                    except Exception:
                                        _ko = None
                                    _sharp_min = settings.get("steam_min_move_pct", 5.0)
                                    _sh = sharp_edge.qualifies(
                                        home, away, sel_name, odds, _sharp_min, _ko)
                                    sel["sharp_move"] = _sh.get("sharp_move", 0.0)
                                    sel["sharp_lagging"] = _sh.get("lagging", False)
                                    if _sh.get("qualifies"):
                                        log_sharp_bet(f"{home} vs {away}", m_type, sel_name,
                                                      odds, _sh["sharp_move"], fid, league)
                                    # Pure value vs the sharp fair line (separate SHARPV
                                    # strategy; fires on mispricing without needing a move).
                                    if settings.get("sharp_value_enabled", True):
                                        _min_ev = settings.get("sharp_value_min_ev", 0.02)
                                        _max_ev = settings.get("sharp_value_max_ev", 0.10)
                                        _v = sharp_edge.qualifies_value(
                                            home, away, sel_name, odds, _min_ev, _max_ev, _ko)
                                        sel["sharp_ev"] = round((_v.get("ev") or 0.0) * 100.0, 1)
                                        if _v.get("qualifies"):
                                            log_sharp_bet(f"{home} vs {away}", m_type, sel_name,
                                                          odds, (_v["ev"] or 0.0) * 100.0,
                                                          fid, league, source="SHARPV")
                                except Exception as _she:
                                    pass

                            # Opt-in: require the market to be moving toward a model pick.
                            require_steam = settings.get("require_steam_confirm", False)
                            steam_ok = (not require_steam) or (steam_move >= steam_min)

                            is_recommended = (
                                ev >= min_ev_threshold
                                and prob >= conf_threshold
                                and odds >= dfp_settings.MODEL_MIN_ODDS
                                and is_at_peak
                                and market_allowed
                                and not league_blocked
                                and not draw_excluded
                                and conviction_ok
                                and steam_ok
                                and odds_fresh
                            )

                            sel.update({"odds": odds, "max_seen_odds": max_seen_odds, "ev": ev, "m_type": m_type, "all_odds": all_market_odds})
                            # Only stake when official lineups are confirmed; odds above
                            # are still attached for display on estimated-XI matches.
                            if is_recommended and bet_allowed:
                                match_bet_candidates.append(sel)
                        else:
                            # Fallback Logic (if no real odds)
                            # DISABLED: Betting on estimated negative EV (-5%) was draining the budget
                            pass

                # --- MATCH SANITY FILTER ---
                # "make the bets related and not different... less random choices"
                if match_bet_candidates:
                    # Sort by EV descending to pick the best value first
                    match_bet_candidates.sort(key=lambda x: x["ev"], reverse=True)
                    
                    # Selection: Only take the SINGLE BEST bet for the entire match.
                    # This eliminates all contradictory/random-feeling overlapping bets.
                    match_bet_candidates.sort(key=lambda x: x["ev"], reverse=True)
                    best_bet = match_bet_candidates[0]
                    
                    m_type = best_bet["m_type"]
                    sel_name = best_bet["selection"]
                    prob = best_bet["prob"]
                    odds = best_bet["odds"]
                    ev = best_bet["ev"]
                    all_odds = best_bet.get("all_odds", [odds])
                    
                    try:
                        has_lineup = int(prediction.get("has_lineup", 0))
                        xmin_p10 = float(prediction.get("xmin_p10", 0.0))
                        xmin_p90 = float(prediction.get("xmin_p90", 0.0))
                        expected_mean = float(prediction.get("xmin_mean", 0.0))

                        bet_id = place_bet(
                            fair_prob=prob / 100.0,
                            market_odds=odds,
                            all_outcome_odds=all_odds, # Pass all odds for proper vig stripping
                            match_id=str(fid),
                            player_id=sel_name.split()[0],
                            market_type=m_type,
                            line=2.5,
                            side=sel_name.lower(),
                            lineup_drop_at=match_time,
                            latency_ms=0,
                            regime="live_value_chaser",
                            role_shift_flag=False,
                            has_lineup=has_lineup,
                            xmin_p10=xmin_p10,
                            xmin_p90=xmin_p90,
                            expected_mean=expected_mean
                        )
                        if bet_id:
                            print(f"[DAEMON] VALUE BET placed: {m_type} | {sel_name} @ {odds} (EV: {ev*100:.1f}%)")
                    except Exception as e:
                        print(f"[ERROR] Failed to place best bet: {e}")

                    log_ai_bet(f"{home} vs {away}", m_type, sel_name, odds, prob, ev, fid, league)

        item = {
            "fixture_id": fid,
            "match": f"{home} vs {away}",
            "league": league,
            "kickoff": match_time,
            "status_code": status,
            "has_lineup": prediction["has_lineup"] if prediction else False,
            "prediction": prediction,
            "prematch_markets": prematch_markets,
            "fixture": f["fixture"],
        }
        dashboard_data.append(item)

    # Inject currently LIVE matches (DISPLAY-ONLY, no odds) so in-play games are visible.
    # Betarabia's feed is pre-match only and drops matches at kickoff, so live games (e.g. a
    # World Cup match in play) otherwise vanish. Source: Flashscore (keyless). These cards
    # carry a real score + LIVE status but no odds/prediction — the AI never bets them.
    if settings.get("show_live_matches", True):
        try:
            from src.live_matches import get_live_matches
            def _nm(s):
                return "".join(c for c in (s or "").lower() if c.isalnum())
            existing = {_nm(d.get("match", "")) for d in dashboard_data}
            added = 0
            for lm in get_live_matches():
                if _nm(lm["match"]) not in existing:
                    dashboard_data.append(lm)
                    existing.add(_nm(lm["match"]))
                    added += 1
            if added:
                print(f"[LIVE] Injected {added} in-play match(es) into the dashboard.")
        except Exception as e:
            print("[LIVE] inject failed:", e)

    with open(
        os.path.join(DATA_DIR, "todays_dashboard_state.json"), "w", encoding="utf-8"
    ) as f:
        json.dump(dashboard_data, f, indent=4)


def refresh_completed_comparisons():
    """
    Checks for finished matches and fetches detailed stats to populate completed_comparisons.json.
    """
    print(
        "[COMPLETION] Checking for finished matches to populate reality data (Today + Yesterday)..."
    )
    completed_path = os.path.join(DATA_DIR, "completed_comparisons.json")
    completed_data = {}
    if os.path.exists(completed_path):
        try:
            with open(completed_path, "r", encoding="utf-8") as f:
                completed_data = json.load(f)
        except Exception:
            pass

    try:
        # Check Today and Yesterday
        today = datetime.datetime.now()
        yesterday = today - datetime.timedelta(days=1)

        all_fixtures = []

        # We need a way to fetch for a specific date.
        # Let's temporarily monkeypatch or just use the logic here if get_todays_fixtures_free doesn't support it.
        # Actually, let's just use the logic from free_scraper_module directly for the loop.

        for dt in [yesterday, today]:
            date_str = dt.strftime("%Y-%m-%d")
            url = f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{date_str}"

            print(f"[COMPLETION] Scanning fixtures for {date_str}...")
            try:
                from seleniumbase import SB

                with SB(uc=True, headless=True) as sb:
                    sb.open(url)
                    time.sleep(2)
                    content = sb.execute_script("return document.body.innerText;")
                    data = json.loads(content)
                    events = data.get("events", [])
                    for e in events:
                        status_code = "NS"
                        if e["status"]["type"] == "inprogress":
                            status_code = "1H"
                        elif e["status"]["type"] == "finished":
                            status_code = "FT"

                        all_fixtures.append(
                            {
                                "fixture": {
                                    "id": e["id"],
                                    "status": {"short": status_code},
                                    "home_score": e.get("homeScore", {}).get("normaltime", e.get("homeScore", {}).get("current")),
                                    "away_score": e.get("awayScore", {}).get("normaltime", e.get("awayScore", {}).get("current")),
                                },
                                "league": {"name": e["tournament"]["name"]},
                                "teams": {
                                    "home": {"name": e["homeTeam"]["name"]},
                                    "away": {"name": e["awayTeam"]["name"]},
                                },
                            }
                        )
            except Exception as e:
                print(f"[COMPLETION] Error scanning {date_str}: {e}")

    except Exception as e:
        print(f"[COMPLETION] Critical error in scan loop: {e}")
        return

    res_map = load_predictions_from_db()

    updated = False
    for f in all_fixtures:
        status = f["fixture"]["status"]["short"]
        if status == "FT":
            fid = f["fixture"]["id"]
            fid_str = str(fid)

            if fid_str in completed_data:
                continue

            # Only fetch if we actually have a prediction for this match
            if fid not in res_map:
                continue

            print(
                f"[COMPLETION] Fetching detailed reality stats for {f['teams']['home']['name']} vs {f['teams']['away']['name']} (ID: {fid})..."
            )
            try:
                from src.free_scraper_module import get_fixture_stats_free

                stats_raw = get_fixture_stats_free(fid)
                if not stats_raw:
                    continue

                # Parse Sofascore stats into our completed_comparisons format
                actuals = {
                    "fixture_id": fid,
                    "match": f"{f['teams']['home']['name']} vs {f['teams']['away']['name']}",
                    "league": f["league"]["name"],
                    "status": "FT",
                    "score": f"{f['fixture']['home_score']} - {f['fixture']['away_score']}",
                    "home_score": f["fixture"]["home_score"],
                    "away_score": f["fixture"]["away_score"],
                    "winner": "DRAW",
                    "goals": [],
                    "possession_home": 50,
                    "possession_away": 50,
                    "corners_home": 0,
                    "corners_away": 0,
                    "corners_total": 0,
                    "fouls_home": 0,
                    "fouls_away": 0,
                    "cards_yellow_home": 0,
                    "cards_yellow_away": 0,
                    "cards_yellow_total": 0,
                    "cards_red_total": 0,
                    "shots_home": 0,
                    "shots_away": 0,
                    "shots_on_target_home": 0,
                    "shots_on_target_away": 0,
                    "player_stats": [],
                }

                if f["fixture"]["home_score"] > f["fixture"]["away_score"]:
                    actuals["winner"] = f"{f['teams']['home']['name']} WIN"
                elif f["fixture"]["away_score"] > f["fixture"]["home_score"]:
                    actuals["winner"] = f"{f['teams']['away']['name']} WIN"

                # Extract stats from statistics array
                all_stats = next(
                    (
                        p
                        for p in stats_raw.get("statistics", [])
                        if p.get("period") == "ALL"
                    ),
                    None,
                )
                if all_stats:
                    for group in all_stats.get("groups", []):
                        for item in group.get("statisticsItems", []):
                            name = item.get("name")
                            home_val = item.get("homeValue")
                            away_val = item.get("awayValue")

                            if name == "Ball possession":
                                actuals["possession_home"] = int(
                                    str(home_val).replace("%", "")
                                )
                                actuals["possession_away"] = int(
                                    str(away_val).replace("%", "")
                                )
                            elif name == "Corner kicks":
                                actuals["corners_home"] = int(home_val)
                                actuals["corners_away"] = int(away_val)
                                actuals["corners_total"] = (
                                    actuals["corners_home"] + actuals["corners_away"]
                                )
                            elif name == "Fouls":
                                actuals["fouls_home"] = int(home_val)
                                actuals["fouls_away"] = int(away_val)
                            elif name == "Yellow cards":
                                actuals["cards_yellow_home"] = int(home_val)
                                actuals["cards_yellow_away"] = int(away_val)
                                actuals["cards_yellow_total"] = (
                                    actuals["cards_yellow_home"]
                                    + actuals["cards_yellow_away"]
                                )
                            elif name == "Red cards":
                                actuals["cards_red_total"] = int(home_val) + int(
                                    away_val
                                )
                            elif name == "Total shots":
                                actuals["shots_home"] = int(home_val)
                                actuals["shots_away"] = int(away_val)
                            elif name == "Shots on target":
                                actuals["shots_on_target_home"] = int(home_val)
                                actuals["shots_on_target_away"] = int(away_val)

                completed_data[fid_str] = actuals
                updated = True
            except Exception as e:
                print(f"[!] Error fetching/parsing stats for {fid}: {e}")

    if updated:
        with open(completed_path, "w", encoding="utf-8") as f:
            json.dump(completed_data, f, indent=4)
        print(
            f"[COMPLETION] Successfully updated {completed_path} with new finished matches."
        )


def _stair_api_key():
    """Resolve the STAIR-AI key resiliently: env first, else read .env directly.
    (.env is NOT loaded into os.environ at daemon-thread startup, so env alone is empty.)"""
    k = os.getenv("STAIR_AI_API_KEY")
    if k and k.strip():
        return k.strip()
    try:
        with open(os.path.join(DATA_DIR, "..", ".env"), encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("STAIR_AI_API_KEY="):
                    return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return ""


def init_stair_ai_agent():
    headers = {
        "Content-Type": "application/json",
        "x-api-key": _stair_api_key(),
    }
    try:
        res = requests.get(
            "https://stair-ai.com/api/v1/arena/agents/me",
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
                "https://stair-ai.com/api/v1/arena/agents/me",
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
                "https://stair-ai.com/api/v1/arena/agents/register",
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

    try:
        player_model = joblib.load(os.path.join(MODELS_DIR, "player_impact_model.pkl"))
    except Exception as e:
        print(f"[!] Failed to load player_impact_model.pkl: {e}. Continuing without it.")
        player_model = None
    try:
        match_model = joblib.load(os.path.join(MODELS_DIR, "bottom_up_match_model.pkl"))
    except Exception as e:
        print(f"[!] Failed to load bottom_up_match_model.pkl: {e}. Continuing without it.")
        match_model = None
    df = load_player_database()
    initialize_caches(df)

    # Start background telemetry threads FIRST (independent of settlement, which
    # can be slow) so they begin accumulating data immediately on startup:
    #  - closing-line capture: true pre-kickoff prices for open bets (honest CLV)
    #  - sharp snapshots: Pinnacle line history for sharp-steam + lagging-value
    start_closing_capture()
    try:
        sharp_edge.start_sharp_snapshots()
    except Exception as _sse:
        print(f"[!] Sharp snapshot thread not started: {_sse}")

    # Run initial settlement on startup (may be slow — network result fetch).
    settle_open_bets()

    while True:
        # 1. Trigger Betarabia odds scraper in background — but ONLY if the previous
        # scrape has finished. The scrape takes ~3 min; overlapping runs stack
        # Chromium and crash before writing, which is what left odds_stream.db stale.
        try:
            import subprocess
            import sys

            global _scraper_proc
            if _scraper_proc is not None and _scraper_proc.poll() is None:
                print("[SCRAPER] Previous Betarabia scrape still running; skipping (no stacking).")
            else:
                scraper_path = os.path.join(os.path.dirname(__file__), "betarabia_scraper.py")
                _scraper_proc = subprocess.Popen(
                    [sys.executable, scraper_path], close_fds=True
                )
                print("[SCRAPER] Launched fresh Betarabia scrape.")
        except Exception as e:
            print("Failed to start background scraper:", e)

        # Bound odds_history growth once per cycle (keeps steam/CLV queries fast).
        _purge_odds_history()

        # 2. Run post-match settlement and reality data completion
        refresh_completed_comparisons()
        time.sleep(5)
        settle_open_bets()
        time.sleep(5)

        # Load existing predictions from DB
        db_preds = load_predictions_from_db()

        now_utc = datetime.datetime.now(datetime.timezone.utc)
        print(
            f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Scanning fixtures for predictions..."
        )
        fixtures = get_todays_fixtures()
        if not fixtures:
            # Fallback to Betarabia matches
            print("[!] Sofascore fixtures empty! Falling back to Betarabia dummy fixtures...")
            try:
                import hashlib
                b_odds, _ = fetch_betarabia_odds()
                for b_name, b_info in b_odds.items():
                    if ' vs ' in b_name:
                        h, a = b_name.split(' vs ', 1)
                        fid = int(hashlib.md5(b_name.encode()).hexdigest(), 16) % 100000000
                        info = b_info or {}
                        fixtures.append({
                            "fixture": {
                                "id": fid,
                                "date": info.get("kickoff") or now_utc.isoformat(),
                                "status": {"short": info.get("status") or "NS"}
                            },
                            "teams": {
                                "home": {"name": h},
                                "away": {"name": a}
                            },
                            "league": {"name": info.get("league") or "Betarabia"}
                        })
                print(f"[!] Rebuilt {len(fixtures)} dummy fixtures from Betarabia.")
            except Exception as e:
                print(f"[!] Fallback to Betarabia failed: {e}")
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

        # Fetch official lineups (free, ESPN) for matches near kickoff.
        batch_lineups = {}
        if fixtures_to_check:
            print(
                f"[*] Checking official lineups (ESPN) for {len(fixtures_to_check)} matches near kickoff..."
            )
            try:
                from src.free_lineup_scraper import get_official_lineups

                for fx in fixtures_to_check:
                    try:
                        ko_date = datetime.datetime.fromisoformat(
                            fx["fixture"]["date"].replace("Z", "+00:00")
                        ).strftime("%Y-%m-%d")
                        lu = get_official_lineups(
                            fx["teams"]["home"]["name"],
                            fx["teams"]["away"]["name"],
                            ko_date,
                        )
                        if lu:
                            batch_lineups[fx["fixture"]["id"]] = lu
                            print(
                                f"    -> Official lineup found: {fx['teams']['home']['name']} vs {fx['teams']['away']['name']}"
                            )
                    except Exception as inner:
                        print("  lineup fetch error:", inner)
            except Exception as e:
                print("Failed to run official lineup fetcher:", e)

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
        
        # 4. Smart Parlays DISABLED (2026-06-15). Parlays compound per-leg edge, and the
        #    project has no proven +EV single bet (1X2 has no edge, props are -EV), so every
        #    parlay is structurally more -EV than its legs. Live record was 22% hit / ~-31% ROI,
        #    partly hash-settled noise. Generation is off; settlement below still grades the
        #    7 open parlays out. Do NOT re-enable until a single-bet strategy proves positive CLV.
        # try:
        #     parlay_script = os.path.join(os.path.dirname(__file__), "parlay_intelligence_v2.py")
        #     subprocess.Popen([sys.executable, parlay_script], close_fds=True)
        # except Exception as e:
        #     print("Failed to start parlay engine:", e)

        # 5. Institutional Monitoring (Momentum, News, Audits)
        try:
            # Steam Move Alerts Disabled by User Request
            # Lineup Sniper Disabled by User Request
            
            # Daily Audit (Run at 23:55)
            now = datetime.datetime.now()
            if now.hour == 23 and now.minute >= 55:
                from src.services.daily_audit import run_daily_audit
                # Only run once per night
                if not os.path.exists(os.path.join(DATA_DIR, f"audit_{now.date()}.done")):
                    run_daily_audit()
                    with open(os.path.join(DATA_DIR, f"audit_{now.date()}.done"), "w") as f: f.write("done")
                    
        except Exception as e:
            print(f"[MONITORING ERROR] {e}")

        print("[*] Sweep complete. Dashboard state updated. Sleeping for 3 minutes...")

        # Wait 3 minutes (180s) before the next sweep
        time.sleep(180)


if __name__ == "__main__":
    run_daemon()
