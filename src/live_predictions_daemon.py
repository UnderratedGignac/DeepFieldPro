import sys
import os

# Ensure src is in path to allow 'src' package imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
import joblib
import requests
import datetime
import json
import time
import math
import threading

# LightGBM ensemble + form cache (best-practice upgrades)
try:
    from src.models.lgbm_predictor import predict_1x2 as _lgbm_predict_1x2
    from src.models.form_cache import (
        get_form as _get_form,
        get_h2h as _get_h2h,
        build_cache as _build_form_cache,
    )

    _LGBM_AVAILABLE = True
except Exception:
    _lgbm_predict_1x2 = None
    _get_form = None
    _get_h2h = None
    _build_form_cache = None
    _LGBM_AVAILABLE = False

# Multi-book odds aggregator: Pinnacle probs → LightGBM features + line-shopping display
try:
    from src.odds_aggregator import get_pinnacle_probs as _get_pinnacle_probs
    from src.odds_aggregator import get_best_price as _get_best_price

    _ODDS_AGG = True
except Exception:
    _get_pinnacle_probs = None
    _get_best_price = None
    _ODDS_AGG = False

# Fatigue, weather, referee, and arb signal modules
try:
    from src.fatigue_detector import xg_multipliers as _fatigue_xg_mult
    from src.fatigue_detector import congestion_summary as _congestion_summary

    _FATIGUE_OK = True
except Exception:
    _fatigue_xg_mult = None
    _congestion_summary = None
    _FATIGUE_OK = False

try:
    from src.weather_adjuster import get_weather_adjustments as _weather_adj

    _WEATHER_OK = True
except Exception:
    _weather_adj = None
    _WEATHER_OK = False

try:
    from src.referee_data import get_referee_signal as _referee_signal

    _REFEREE_OK = True
except Exception:
    _referee_signal = None
    _REFEREE_OK = False

try:
    from src.arb_detector import check_arb as _check_arb

    _ARB_OK = True
except Exception:
    _check_arb = None
    _ARB_OK = False
from src.execution_engine import place_bet  # TASK 1: Import place_bet

# ── NEW ARCHITECTURE: Pinnacle-value strategy + CLV tracking + shadow gate ──
try:
    from src.pinnacle_value_engine import (
        find_value_bets as _pv_find_value,
        log_value_bet as _pv_log_bet,
        is_liquid_league as _pv_liquid_league,
        normalize_league as _pv_normalize_league,
        resolve_league_country as _pv_resolve_league,
        LIQUID_LEAGUES as _PV_LIQUID_LEAGUES,
    )

    _PV_ENGINE_OK = True
except Exception as _pv_exc:
    _pv_find_value = None
    _pv_log_bet = None
    _pv_liquid_league = None
    _pv_normalize_league = None
    _pv_resolve_league = None
    _PV_LIQUID_LEAGUES = set()
    _PV_ENGINE_OK = False

try:
    from src.clv_tracker_v2 import (
        record_bet as _clv_record_bet,
        record_closing_odds as _clv_record_closing,
        settle_bet as _clv_settle_bet,
        generate_weekly_report as _clv_weekly_report,
    )

    _CLV_TRACKER_OK = True
except Exception as _clv_exc:
    _clv_record_bet = None
    _clv_record_closing = None
    _clv_settle_bet = None
    _clv_weekly_report = None
    _CLV_TRACKER_OK = False

try:
    from src.shadow_framework import (
        refuse_real_money_if_not_ready as _shadow_refuse,
        get_shadow_status as _shadow_status,
    )

    _SHADOW_OK = True
except Exception:
    _shadow_refuse = None
    _shadow_status = None
    _SHADOW_OK = False

try:
    from src.gatekeeper import check_real_money_gate as _gatekeeper_check

    _GATEKEEPER_OK = True
except Exception:
    _gatekeeper_check = None
    _GATEKEEPER_OK = False

# Unicode-safe print override for Windows console compatibility
_orig_print = print


def print(*args, **kwargs):
    enc = (sys.stdout.encoding if sys.stdout else None) or "utf-8"
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

# ---------------------------------------------------------------------------
# Calibrated league corner/card base rates (measured from football-data.co.uk)
# ---------------------------------------------------------------------------
_CORNER_BASE_RATES = {
    "premier league": 10.57,
    "eng-premier league": 10.57,
    "e0": 10.57,
    "championship": 11.0,
    "eng-championship": 11.0,
    "la liga": 9.44,
    "esp-la liga": 9.44,
    "sp1": 9.44,
    "serie a": 9.47,
    "ita-serie a": 9.47,
    "i1": 9.47,
    "bundesliga": 9.77,
    "ger-bundesliga": 9.77,
    "d1": 9.77,
    "ligue 1": 9.37,
    "fra-ligue 1": 9.37,
    "f1": 9.37,
    "eredivisie": 10.4,
    "ned-eredivisie": 10.4,
    "primeira liga": 9.9,
    "por-primeira liga": 9.9,
    "world cup": 9.5,
    "copa america": 9.3,
    "euros": 9.6,
    "euro": 9.6,
    "champions league": 9.7,
    "europa league": 10.0,
    "mls": 10.2,
    "brasileirao": 9.6,
}

# Trained corner model (loaded lazily from models/corner_model.json)
_corner_model: dict = {}


def _load_corner_model():
    global _corner_model
    if _corner_model:
        return _corner_model
    path = os.path.join(MODELS_DIR, "corner_model.json")
    if os.path.exists(path):
        try:
            with open(path) as _f:
                _corner_model = json.load(_f)
        except Exception:
            _corner_model = {}
    return _corner_model


_CARD_BASE_RATES = {
    "premier league": 3.2,
    "eng-premier league": 3.2,
    "championship": 3.8,
    "eng-championship": 3.8,
    "la liga": 4.0,
    "esp-la liga": 4.0,
    "serie a": 4.5,
    "ita-serie a": 4.5,
    "bundesliga": 3.0,
    "ger-bundesliga": 3.0,
    "ligue 1": 4.0,
    "fra-ligue 1": 4.0,
    "eredivisie": 3.5,
    "ned-eredivisie": 3.5,
    "world cup": 3.8,
    "copa america": 3.5,
    "euro": 3.0,
    "champions league": 2.8,
    "europa league": 3.3,
    "mls": 3.4,
    "brasileirao": 4.2,
}


def _corner_base(league_name: str) -> float:
    # Check trained model's league_base first
    mdl = _load_corner_model()
    if mdl:
        lb = mdl.get("league_base", {})
        ln = (league_name or "").lower()
        for k, v in lb.items():
            if k.lower() in ln or ln in k.lower():
                return float(v)
    # Fall back to hardcoded calibrated rates
    ln = (league_name or "").lower()
    for k, v in _CORNER_BASE_RATES.items():
        if k in ln:
            return v
    return 9.74  # global mean from 3503-match training set


def _team_corner_rate(team_name: str, side: str) -> float:
    """Per-team historical corner rate. Returns None if not in model."""
    mdl = _load_corner_model()
    if not mdl:
        return None
    key = "home_corner_rate" if side == "home" else "away_corner_rate"
    rate_map = mdl.get(key, {})
    if team_name in rate_map:
        return float(rate_map[team_name])
    # Fuzzy: try case-insensitive match
    tl = team_name.lower()
    for k, v in rate_map.items():
        if k.lower() == tl:
            return float(v)
    return None


def _card_base(league_name: str) -> float:
    ln = (league_name or "").lower()
    for k, v in _CARD_BASE_RATES.items():
        if k in ln:
            return v
    return 3.5


def _poisson_sf(threshold: float, lam: float) -> float:
    """P(X > threshold) for Poisson(lam) — exact via series summation."""
    if lam <= 0:
        return 0.0
    k = int(math.floor(threshold))
    p = math.exp(-lam)
    cdf = p
    for i in range(1, k + 1):
        p = p * lam / i
        cdf += p
    return max(0.0, min(1.0, 1.0 - cdf))


# Import new DeepFieldPro modules - only the specific classes/functions we actually use
try:
    from src.sofascore_patchright_scraper import get_sofascore_fixtures_today as get_todays_fixtures  # noqa: E402
    import logging as _log
    _log.getLogger(__name__).info("[DAEMON] Using Sofascore Patchright scraper as fixture source")
except ImportError:
    from src.free_scraper_module import get_todays_fixtures_free as get_todays_fixtures  # noqa: E402
from src.models.calibration_engine import ProbabilityCalibrator  # noqa: E402
from src.risk_engine.no_bet_filter import create_no_bet_filter  # noqa: E402
from src.telemetry_warehouse.clv_tracker import create_clv_tracker  # noqa: E402
from src.dfp_config import settings as dfp_settings  # institutional risk gates

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
        path = os.path.join(
            os.path.dirname(__file__), "..", "models", "calibrator_1x2.json"
        )
        with open(path, encoding="utf-8") as f:
            _CAL_1X2 = json.load(f)
            print(
                f"[+] 1X2 calibrator loaded (Platt a={_CAL_1X2.get('a'):.3f} "
                f"b={_CAL_1X2.get('b'):.3f}, n={_CAL_1X2.get('n_train')})"
            )
    except Exception:
        _CAL_1X2 = {}  # absent => identity (raw probs)
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
# removes that bias so the DISPLAYED O/U numbers are honest.
# NOTE (2026-06): Paper bet data shows O/U 2.5 is our BEST market (+51% ROI on
# 13 settled bets). This calibrator is essential for honest O/U probabilities.
_CAL_OU = None


def _load_ou_calibrator():
    global _CAL_OU
    if _CAL_OU is not None:
        return _CAL_OU
    try:
        path = os.path.join(
            os.path.dirname(__file__), "..", "models", "calibrator_ou25.json"
        )
        with open(path, encoding="utf-8") as f:
            _CAL_OU = json.load(f)
            print(
                f"[+] O/U 2.5 calibrator loaded (Platt a={_CAL_OU.get('a'):.3f} "
                f"b={_CAL_OU.get('b'):.3f}, n={_CAL_OU.get('n_train')})"
            )
    except Exception:
        _CAL_OU = {}  # absent => identity (raw probs)
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

_LEAGUE_NATION = {
    # Top European leagues
    "premier league": "England",
    "championship": "England",
    "league one": "England",
    "league two": "England",
    "fa cup": "England",
    "la liga": "Spain",
    "segunda división": "Spain",
    "copa del rey": "Spain",
    "bundesliga": "Germany",
    "2. bundesliga": "Germany",
    "serie a": "Italy",
    "serie b": "Italy",
    "coppa italia": "Italy",
    "ligue 1": "France",
    "ligue 2": "France",
    "eredivisie": "Netherlands",
    "primeira liga": "Portugal",
    "super lig": "Turkey",
    "premier league ukraine": "Ukraine",
    "scottish premiership": "Scotland",
    "belgian pro league": "Belgium",
    # International / multi-nation
    "champions league": "Europe",
    "europa league": "Europe",
    "conference league": "Europe",
    "nations league": "International",
    "world cup": "International",
    "copa america": "South America",
    "gold cup": "CONCACAF",
    "afcon": "Africa",
    "euro": "Europe",
    "u21": "International",
    "u20": "International",
    "u17": "International",
    "club friendlies": "International",
}


def _nation_from_league(league: str) -> str:
    """Extract the nation/region for a league string.

    Priority:
    1. Country in parentheses, e.g. 'National Premier League 2 (Australia)' → 'Australia'
    2. Hardcoded lookup on lowercased league name substring.
    3. 'International' as fallback.
    """
    import re

    m = re.search(r"\(([^)]+)\)$", league.strip())
    if m:
        return m.group(1).strip()
    low = league.lower()
    for key, nation in _LEAGUE_NATION.items():
        if key in low:
            return nation
    return "International"


def _devig_map(odds_by_sel):
    inv = {s: 1.0 / o for s, o in odds_by_sel.items() if o and o > 0}
    tot = sum(inv.values())
    if tot <= 0 or len(inv) < 2:
        return None
    return {s: v / tot for s, v in inv.items()}


def _odds_history_db():
    return os.path.join(DATA_DIR, "deepfield_browser_data", "completed_fixtures.db")


_SIGNAL_REGISTRY_DEFAULTS = {
    "STEAM_FWD": {"enabled": 1, "promoted": 0, "min_samples": 100},
    "STEAM_REV": {"enabled": 0, "promoted": 0, "min_samples": 100},
    "DOG_DRIFT": {"enabled": 0, "promoted": 0, "min_samples": 100},
    "FAV_DRIFT": {"enabled": 0, "promoted": 0, "min_samples": 100},
    "EARLY_STEAM": {"enabled": 0, "promoted": 0, "min_samples": 100},
    "LATE_STEAM": {"enabled": 0, "promoted": 0, "min_samples": 100},
    "FAV_DRIFT_REV": {"enabled": 0, "promoted": 0, "min_samples": 100},
    "MOMENTUM_ACCEL": {"enabled": 0, "promoted": 0, "min_samples": 100},
    "LARGE_SPREAD": {"enabled": 0, "promoted": 0, "min_samples": 100},
}


def _init_signal_registry():
    """Create signal_registry table and seed default rows if not present."""
    try:
        con = sqlite3.connect(_odds_history_db())
        con.execute(
            """CREATE TABLE IF NOT EXISTS signal_registry (
            signal_name  TEXT PRIMARY KEY,
            enabled      INTEGER DEFAULT 1,
            promoted     INTEGER DEFAULT 0,
            min_samples  INTEGER DEFAULT 100,
            owner        TEXT    DEFAULT 'system',
            updated_at   DATETIME DEFAULT CURRENT_TIMESTAMP
        )"""
        )
        for sig, vals in _SIGNAL_REGISTRY_DEFAULTS.items():
            con.execute(
                "INSERT OR IGNORE INTO signal_registry (signal_name, enabled, promoted, min_samples) "
                "VALUES (?,?,?,?)",
                (sig, vals["enabled"], vals["promoted"], vals["min_samples"]),
            )
        con.commit()
        con.close()
    except Exception:
        pass


_signal_registry_cache: dict = {}
_signal_registry_cache_ts: float = 0.0


def _load_signal_registry() -> dict:
    """Return {signal_name: {enabled, promoted}} from the registry, cached for 60s."""
    import time as _time

    global _signal_registry_cache, _signal_registry_cache_ts
    if _time.time() - _signal_registry_cache_ts < 60 and _signal_registry_cache:
        return _signal_registry_cache
    try:
        con = sqlite3.connect(_odds_history_db())
        rows = con.execute(
            "SELECT signal_name, enabled, promoted FROM signal_registry"
        ).fetchall()
        con.close()
        _signal_registry_cache = {
            r[0]: {"enabled": bool(r[1]), "promoted": bool(r[2])} for r in rows
        }
        _signal_registry_cache_ts = _time.time()
        return _signal_registry_cache
    except Exception:
        return {
            k: {"enabled": v["enabled"], "promoted": v["promoted"]}
            for k, v in _SIGNAL_REGISTRY_DEFAULTS.items()
        }


def _purge_odds_history(days=30):
    """Bound odds_history growth. Keep 30 days so signal_discovery.py can evaluate
    signals against a rolling month of settled fixtures. Steam detection only needs
    same-day data but the research pipeline needs longer history."""
    try:
        con = sqlite3.connect(_odds_history_db())
        con.execute(
            "DELETE FROM odds_history WHERE timestamp < datetime('now', ?)",
            (f"-{int(days)} days",),
        )
        con.commit()
        con.close()
    except Exception:
        pass


def _steam_moves(fid, m_type):
    """Return {selection: effective_move} using time-series pattern analysis.

    Upgrades from earliest-vs-latest to a monotonicity-weighted signal:
      effective_move = raw_move * monotonicity_score

    Monotonicity score (0..1): fraction of consecutive probability steps that go
    in the dominant direction. A smooth 2.10→2.05→1.98→1.92 pattern scores 1.0.
    A spike-and-reverse 2.10→1.90→2.08 scores 0.33. This filters "fake steam"
    (single large print then reversal) while rewarding sustained sharp-money flow.

    Also computes recent_momentum (last 2 snapshots only) and returns it in a
    secondary key "__meta__" so callers can display both measures if wanted.
    """
    try:
        conn = sqlite3.connect(_odds_history_db())
        rows = conn.execute(
            "SELECT selection, odds, timestamp FROM odds_history "
            "WHERE fixture_id=? AND market=? ORDER BY timestamp ASC",
            (str(fid), m_type),
        ).fetchall()
        conn.close()
    except Exception:
        return {}

    unique_ts = {ts for _, _, ts in rows}
    if len(unique_ts) < 2:
        return {}

    # Build per-selection time series of devigged probabilities
    from collections import defaultdict

    by_ts: dict = defaultdict(dict)
    for sel, o, ts in rows:
        if o and o > 0:
            by_ts[ts][sel] = o

    # Sort timestamps and build per-selection prob series
    sorted_ts = sorted(by_ts)
    all_sels = {sel for snap in by_ts.values() for sel in snap}
    prob_series: dict = {sel: [] for sel in all_sels}

    for ts in sorted_ts:
        snap = by_ts[ts]
        if len(snap) < 2:
            continue
        dv = _devig_map(snap)
        if not dv:
            continue
        for sel in all_sels:
            if sel in dv:
                prob_series[sel].append(dv[sel])

    # Need earliest and latest devigged maps for the raw move
    snapshots_with_all = [by_ts[ts] for ts in sorted_ts if len(by_ts[ts]) >= 2]
    if len(snapshots_with_all) < 2:
        return {}
    early = _devig_map(snapshots_with_all[0])
    late = _devig_map(snapshots_with_all[-1])
    if not early or not late:
        return {}

    result = {}
    meta = {}
    for sel in late:
        raw_move = late[sel] - early.get(sel, late[sel])
        series = prob_series.get(sel, [])

        # Monotonicity: count steps in the dominant direction
        if len(series) >= 2:
            direction = 1 if raw_move >= 0 else -1
            steps = [series[i + 1] - series[i] for i in range(len(series) - 1)]
            aligned = sum(1 for s in steps if s * direction > 0)
            monotonicity = aligned / len(steps) if steps else 0.5

            # Recent momentum: last 2 points
            recent_move = series[-1] - series[-2] if len(series) >= 2 else 0
        else:
            monotonicity = 0.5
            recent_move = raw_move

        effective_move = raw_move * monotonicity
        result[sel] = effective_move
        meta[sel] = {
            "raw": raw_move,
            "monotonicity": round(monotonicity, 2),
            "recent": recent_move,
            "n_snaps": len(series),
        }

    result["__meta__"] = meta
    return result


def _record_steam_signal(
    fid, league, match, m_type, sel_name, odds, move, kickoff, monotonicity=None
):
    """Append a fired steam pick to the steam_signals research ledger (one row per
    fixture/market/selection — first detection's price sticks). Settled offline by
    tools/steam_report.py. Independent of the model bet path / staking."""
    try:
        conn = sqlite3.connect(_odds_history_db())
        conn.execute(
            """CREATE TABLE IF NOT EXISTS steam_signals (
                   fixture_id TEXT, league TEXT, match TEXT, market TEXT, selection TEXT,
                   entry_odds REAL, steam_move REAL, kickoff TEXT, monotonicity REAL,
                   detected_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                   UNIQUE(fixture_id, market, selection))"""
        )
        try:
            conn.execute("ALTER TABLE steam_signals ADD COLUMN monotonicity REAL")
        except Exception:
            pass
        conn.execute(
            """INSERT OR IGNORE INTO steam_signals
                   (fixture_id, league, match, market, selection, entry_odds, steam_move, kickoff, monotonicity)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                str(fid),
                league,
                match,
                m_type,
                sel_name,
                odds,
                move,
                kickoff,
                monotonicity,
            ),
        )
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
    # ── Top 8 European leagues (original training set) ───────────────────────
    "premier league": "E0",
    "epl": "E0",
    "england 1": "E0",
    "championship": "E1",
    "england 2": "E1",
    "laliga": "SP1",
    "la liga": "SP1",
    "primera division": "SP1",
    "spain 1": "SP1",
    "serie a": "I1",
    "italy 1": "I1",
    "bundesliga": "D1",
    "germany 1": "D1",
    "ligue 1": "F1",
    "france 1": "F1",
    "eredivisie": "N1",
    "netherlands 1": "N1",
    "primeira liga": "P1",
    "liga portugal": "P1",
    "portugal 1": "P1",
    "jupiler pro league": "B1",
    "belgium 1": "B1",
    "pro league": "B1",
    "premiership": "SC0",
    "scottish premiership": "SC0",
    "scotland 1": "SC0",
    # ── football-data.co.uk new-format leagues ───────────────────────────────
    "irish premier division": "IRL",
    "league of ireland premier": "IRL",
    "sse airtricity premier": "IRL",
    "norway 1": "NOR",
    "norwegian eliteserien": "NOR",
    "eliteserien": "NOR",
    "tippeligaen": "NOR",
    "sweden 1": "SWE",
    "swedish allsvenskan": "SWE",
    "allsvenskan": "SWE",
    "romanian liga 1": "ROM",
    "liga 1 betano": "ROM",
    "liga i": "ROM",
    "argentina 1": "ARG",
    "argentine primera division": "ARG",
    "primera division argentina": "ARG",
    "liga profesional": "ARG",
    "a-league": "AUS",
    "a league": "AUS",
    "a-league men": "AUS",
    "australian a-league": "AUS",
    "austrian bundesliga": "AUT",
    "osterreichische bundesliga": "AUT",
    "admiral bundesliga": "AUT",
    "austria 1": "AUT",
    "brasileirao": "BRA",
    "brazilian serie a": "BRA",
    "serie a brasil": "BRA",
    "china 1": "CHN",
    "chinese super league": "CHN",
    "csl": "CHN",
    "danish superliga": "DNK",
    "superliga denmark": "DNK",
    "superliga": "DNK",
    "denmark 1": "DNK",
    "finnish veikkausliiga": "FIN",
    "veikkausliiga": "FIN",
    "finland 1": "FIN",
    "greek super league": "GRC",
    "super league greece": "GRC",
    "greece 1": "GRC",
    "hungarian nb i": "HUN",
    "otp bank liga": "HUN",
    "nb i": "HUN",
    "hungary 1": "HUN",
    "israeli premier league": "ISR",
    "ligat haal": "ISR",
    "winner league": "ISR",
    "israel 1": "ISR",
    "japanese j1 league": "JPN",
    "j1 league": "JPN",
    "j1": "JPN",
    "japan 1": "JPN",
    "mexican liga mx": "MEX",
    "liga mx": "MEX",
    "clausura": "MEX",
    "apertura": "MEX",
    "mexico 1": "MEX",
    "polish ekstraklasa": "POL",
    "ekstraklasa": "POL",
    "poland 1": "POL",
    # South African data not available (RSA.csv contains MLS — skip, gate via require_dc)
    "russian premier league": "RUS",
    "rpl": "RUS",
    "russia 1": "RUS",
    "american mls": "USA",
    "mls": "USA",
    "major league soccer": "USA",
    "usa 1": "USA",
    "turkish super lig": "TUR",
    "sper lig": "TUR",
    "super lig": "TUR",
    "turkey 1": "TUR",
    "czech first league": "CZE",
    "fortuna liga": "CZE",
    "czech liga": "CZE",
    "1. liga": "CZE",
    "czech republic 1": "CZE",
    "slovak super liga": "SVK",
    "fortuna liga slovakia": "SVK",
    "slovakia 1": "SVK",
    # ── TheSportsDB extra leagues ────────────────────────────────────────────
    "icelandic urvalsdeild": "ISL",
    "urvalsdeild": "ISL",
    "besta deild karla": "ISL",
    "iceland 1": "ISL",
    "faroe islands premier league": "FAR",
    "faroese premier league": "FAR",
    "faroe islands 1": "FAR",
    "kuwaiti premier league": "KUW",
    "kuwait premier league": "KUW",
    "kuwait 1": "KUW",
    "moroccan botola pro": "MAR",
    "botola pro": "MAR",
    "botola maroc": "MAR",
    "inwi botola pro": "MAR",
    "morocco 1": "MAR",
    "peruvian liga 1": "PER",
    "liga 1 peru": "PER",
    "liga 1 movistar": "PER",
    "peru 1": "PER",
    "estonian meistriliiga": "EST",
    "meistriliiga": "EST",
    "esiliiga": "EST",
    "estonia 1": "EST",
    "norwegian 1. divisjon": "NOR2",
    "1. divisjon": "NOR2",
    "norway 2": "NOR2",
    "norwegian 2. divisjon": "NOR3",
    "2. divisjon": "NOR3",
    "norway 3": "NOR3",
    "swedish superettan": "SWE2",
    "superettan": "SWE2",
    "sweden 2": "SWE2",
    "swedish division 1": "SWE3",
    "sweden 3": "SWE3",
    "irish first division": "IRL2",
    "league of ireland first": "IRL2",
    "sse airtricity first": "IRL2",
    "ireland 2": "IRL2",
    "kazakhstani premier league": "KAZ",
    "kazakhstan premier league": "KAZ",
    "kazakhstan 1": "KAZ",
    "azerbaijani premier league": "AZE",
    "azerbaycan premyer liqasi": "AZE",
    "azerbaijan 1": "AZE",
    "mozambican mocambola": "MOZ",
    "mocambola": "MOZ",
    "mozambique 1": "MOZ",
    "qatari stars league": "QAT",
    "qatar stars league": "QAT",
    "qatar 1": "QAT",
    "saudi pro league": "SAU",
    "saudi professional league": "SAU",
    "saudi arabia 1": "SAU",
    "uae pro league": "UAE",
    "arabian gulf league": "UAE",
    "uae 1": "UAE",
    "primera nacional": "ARG2",
    "argentina 2": "ARG2",
    "primera b metropolitana": "ARG2",
}


def _load_dc_model():
    global _DC_MODEL
    if _DC_MODEL == "unloaded":
        try:
            from src.models.dixon_coles import DixonColes

            _DC_MODEL = DixonColes.load()
            n = sum(len(lg["teams"]) for lg in _DC_MODEL.leagues.values())
            print(
                f"[+] Dixon-Coles model loaded ({len(_DC_MODEL.leagues)} leagues, {n} teams)"
            )
        except Exception:
            _DC_MODEL = None
    return _DC_MODEL


def _norm_team(s):
    import re
    import unicodedata

    s = unicodedata.normalize("NFD", str(s).lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    drop = {
        "fc",
        "cf",
        "sc",
        "afc",
        "ac",
        "as",
        "ss",
        "ssc",
        "rc",
        "cd",
        "ud",
        "club",
        "calcio",
        "the",
    }
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
            "dc_covered": pred_res.get("dc_covered", False),
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
                # Reconstruct Corners — multiple lines so the bet gate can match
                # whatever line the book is offering (Corners OVER 9.5 etc.)
                if "Corners" not in db_markets and "corners_lambda" in dp:
                    lam_c = dp["corners_lambda"]
                    db_markets["Corners"] = [
                        {
                            "selection": f"Corners OVER {line}",
                            "prob": round(_poisson_sf(line, lam_c) * 100, 1),
                        }
                        for line in [7.5, 8.5, 9.5, 10.5, 11.5, 12.5]
                    ] + [
                        {
                            "selection": f"Corners UNDER {line}",
                            "prob": round((1.0 - _poisson_sf(line, lam_c)) * 100, 1),
                        }
                        for line in [7.5, 8.5, 9.5, 10.5, 11.5, 12.5]
                    ]
                elif "Corners" not in db_markets and "corners_over_85" in dp:
                    # Legacy fallback for predictions stored without corners_lambda
                    db_markets["Corners"] = [
                        {
                            "selection": "Corners OVER 8.5",
                            "prob": dp["corners_over_85"],
                        },
                        {
                            "selection": "Corners OVER 9.5",
                            "prob": dp.get("corners_over_95", dp["corners_over_85"]),
                        },
                    ]
                # Reconstruct Total Cards — multiple lines
                if "Total Cards" not in db_markets and "cards_lambda" in dp:
                    lam_k = dp["cards_lambda"]
                    db_markets["Total Cards"] = [
                        {
                            "selection": f"Cards OVER {line}",
                            "prob": round(_poisson_sf(line, lam_k) * 100, 1),
                        }
                        for line in [1.5, 2.5, 3.5, 4.5]
                    ] + [
                        {
                            "selection": f"Cards UNDER {line}",
                            "prob": round((1.0 - _poisson_sf(line, lam_k)) * 100, 1),
                        }
                        for line in [1.5, 2.5, 3.5, 4.5]
                    ]
                elif "Total Cards" not in db_markets and "cards_yellow_total" in dp:
                    db_markets["Total Cards"] = [
                        {
                            "selection": "Cards OVER 3.5",
                            "prob": dp.get("cards_over_35", 40.0),
                        }
                    ]
                # Reconstruct Goalscorer — uses anytime_goal_prob (now xG-calibrated %)
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
                        for p in dp["goalscorers"][:8]
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
                "dc_covered": extra.get("dc_covered", False),
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


def predict_match(fixture, lineups, player_model, match_model, df, mkt_probs=None):
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
    _dc_covered = bool(_dc_eg)  # True only when DC has ratings for both teams
    if _dc_eg:
        exp_h, exp_a = _dc_eg
        if exp_h > exp_a:
            winner = f"{home_team} WIN"
        elif exp_a > exp_h:
            winner = f"{away_team} WIN"
        else:
            winner = "DRAW"

    # ── Fatigue / fixture congestion adjustment ──────────────────────────────
    # Teams playing their 3rd match in 7 days show ~8% offensive drop per extra
    # game (meta-analysis 2025). Adjust xG BEFORE Poisson sampling.
    _fatigue_info = {}
    if _FATIGUE_OK and _fatigue_xg_mult is not None:
        try:
            import datetime as _dt_fat

            _ko_str = fixture["fixture"].get("date", "")
            _ko_date = _dt_fat.date.today()
            if _ko_str:
                try:
                    _ko_date = _dt_fat.datetime.fromisoformat(
                        _ko_str.replace("Z", "+00:00")
                    ).date()
                except Exception:
                    pass
            _fh_mult, _fa_mult = _fatigue_xg_mult(home_team, away_team, _ko_date)
            exp_h *= _fh_mult
            exp_a *= _fa_mult
            if _congestion_summary is not None:
                _fatigue_info = _congestion_summary(home_team, away_team, _ko_date)
        except Exception:
            pass

    # ── Weather adjustment ────────────────────────────────────────────────────
    # Rain →  −12% xG; wind ≥25 km/h → −5-10% xG, −15% BTTS yes.
    # Adjusts xG here; BTTS/O/U are re-derived below from the adjusted xG.
    _weather_info = {
        "source": "disabled",
        "xg_mult": 1.0,
        "btts_yes_mult": 1.0,
        "over25_mult": 1.0,
    }
    if _WEATHER_OK and _weather_adj is not None:
        try:
            import datetime as _dt_wx

            _ko_str_wx = fixture["fixture"].get("date", "")
            _ko_dt_wx = None
            if _ko_str_wx:
                try:
                    import dateutil.parser as _dup

                    _ko_dt_wx = _dup.parse(_ko_str_wx)
                except Exception:
                    try:
                        _ko_dt_wx = _dt_wx.datetime.fromisoformat(
                            _ko_str_wx.replace("Z", "+00:00")
                        )
                    except Exception:
                        pass
            _weather_info = _weather_adj(home_team, away_team, _ko_dt_wx)
            exp_h *= _weather_info.get("xg_mult", 1.0)
            exp_a *= _weather_info.get("xg_mult", 1.0)
        except Exception:
            pass

    # ── Referee signal ────────────────────────────────────────────────────────
    # High-card refs → more stoppages → slightly fewer goals
    _referee_info = {"found": False, "xg_mult": 1.0}
    if _REFEREE_OK and _referee_signal is not None:
        try:
            _ref_name = (fixture.get("fixture") or {}).get("referee") or None
            _referee_info = _referee_signal(_ref_name)
            exp_h *= _referee_info.get("xg_mult", 1.0)
            exp_a *= _referee_info.get("xg_mult", 1.0)
        except Exception:
            pass

    home_g = np.random.poisson(exp_h)
    away_g = np.random.poisson(exp_a)
    if winner == "DRAW" and home_g != away_g:
        home_g = away_g = max(home_g, away_g)

    intensity_factor = (home_impact + away_impact) / 10.0
    home_fouls = int(np.random.poisson(11.0 + intensity_factor))
    away_fouls = int(np.random.poisson(11.0 + intensity_factor))

    # --- Corner model (team-specific + xG-adjusted Poisson, not sampled noise) ---
    # Priority: (1) trained team historical corner rate, (2) xG-share of league base
    base_crn = _corner_base(league_name)
    h_team_rate = _team_corner_rate(home_team, "home")
    a_team_rate = _team_corner_rate(away_team, "away")
    if h_team_rate is not None and a_team_rate is not None:
        # Use team-specific rates adjusted by xG dominance
        total_xg = max(exp_h + exp_a, 0.01)
        xg_adj = (exp_h - exp_a) / total_xg  # positive = home dominant
        lambda_home_corners = h_team_rate * (1.0 + xg_adj * 0.15)
        lambda_away_corners = a_team_rate * (1.0 - xg_adj * 0.15)
    else:
        total_xg = max(exp_h + exp_a, 0.01)
        h_xg_share = exp_h / total_xg
        lambda_home_corners = base_crn * h_xg_share * 1.07
        lambda_away_corners = base_crn * (1.0 - h_xg_share) * 0.97
    lambda_corners_total = lambda_home_corners + lambda_away_corners
    # Keep integer samples only for display fields (not for probability calculations)
    home_corners = max(1, round(lambda_home_corners))
    away_corners = max(1, round(lambda_away_corners))

    # --- Card model (league calibrated) ---
    lambda_cards_total = _card_base(league_name)
    lambda_home_cards = lambda_cards_total * 0.47  # away teams get slightly more cards
    lambda_away_cards = lambda_cards_total * 0.53
    home_yellows = max(0, round(lambda_home_cards))
    away_yellows = max(0, round(lambda_away_cards))

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

    # Extra lines needed for new markets
    prob_over_30 = sum(
        poisson_prob(exp_h, i) * poisson_prob(exp_a, j)
        for i in range(8)
        for j in range(8)
        if (i + j) > 3.0
    )
    prob_over_20 = sum(
        poisson_prob(exp_h, i) * poisson_prob(exp_a, j)
        for i in range(8)
        for j in range(8)
        if (i + j) > 2.0
    )

    # Normalize due to truncation at 7 goals
    total_1x2 = prob_1 + prob_x + prob_2
    prob_1 /= total_1x2
    prob_x /= total_1x2
    prob_2 /= total_1x2

    # ── LightGBM ensemble (best practice: DC + form + market as features) ──
    # Uses form from history.db + de-vigged market odds to refine DC probs.
    # Falls back silently to DC if model not trained or team unknown.
    _lgbm_result = None
    if _LGBM_AVAILABLE and _lgbm_predict_1x2 is not None:
        try:
            import datetime as _dt

            _today_ord = _dt.datetime.now().toordinal()
            _hform = _get_form(home_team, _today_ord) if _get_form else {}
            _aform = _get_form(away_team, _today_ord) if _get_form else {}
            _h2h = _get_h2h(home_team, away_team, _today_ord) if _get_h2h else {}
            # mkt_probs = (p_h, p_d, p_a) from Pinnacle (de-vigged) when available.
            # These are the top LightGBM features; passing None degrades to 1/3 each.
            _mh = mkt_probs[0] if mkt_probs else None
            _md = mkt_probs[1] if mkt_probs else None
            _ma = mkt_probs[2] if mkt_probs else None
            _lgbm_result = _lgbm_predict_1x2(
                dc_home_prob=prob_1,
                dc_draw_prob=prob_x,
                dc_away_prob=prob_2,
                dc_exp_h=exp_h,
                dc_exp_a=exp_a,
                mkt_h_prob=_mh,
                mkt_d_prob=_md,
                mkt_a_prob=_ma,
                home_form=_hform,
                away_form=_aform,
                h2h=_h2h,
            )
        except Exception:
            _lgbm_result = None

    if _lgbm_result is not None:
        prob_1, prob_x, prob_2 = _lgbm_result
        print(
            f"[LGBM] {home_team} vs {away_team}: {prob_1:.3f}/{prob_x:.3f}/{prob_2:.3f}"
        )

    total_ou = prob_over_25 + prob_under_25
    prob_over_25 /= total_ou
    prob_under_25 /= total_ou

    total_btts = prob_btts_yes + prob_btts_no
    prob_btts_yes /= total_btts
    prob_btts_no /= total_btts

    # --- Player detail generation (xG-calibrated Poisson model) ---
    # Distribute team expected goals across positions using empirical goal-share:
    #   GK ~0%, DF ~10%, MF ~25%, FW ~65% of team's goals.
    # Per-player anytime P = 1 - exp(-lambda_per_player) — properly calibrated
    # to the match's Dixon-Coles xG rather than position*rating heuristics.
    # Card probabilities use league-calibrated rates split by role.
    all_player_details = []

    def _player_probs(idx, team_xg, team_cards_lambda, rating):
        if idx == 0:  # GK
            role = "GK"
            goal_share, shot_rate, sot_rate = 0.002, 0.05, 0.01
            card_rate = team_cards_lambda * 0.04
        elif idx <= 4:  # DF (4 defenders)
            role = "DF"
            goal_share, shot_rate, sot_rate = 0.10 / 4, 0.8, 0.25
            card_rate = team_cards_lambda * 0.28 / 4
        elif idx <= 8:  # MF (4 midfielders)
            role = "MF"
            goal_share, shot_rate, sot_rate = 0.25 / 4, 1.5, 0.5
            card_rate = team_cards_lambda * 0.38 / 4
        else:  # FW (3 forwards)
            role = "FW"
            goal_share, shot_rate, sot_rate = 0.65 / 3, 2.5, 0.9
            card_rate = team_cards_lambda * 0.30 / 3
        lam_goal = team_xg * goal_share
        anytime_pct = round((1.0 - math.exp(-lam_goal)) * 100.0, 1)
        first_pct = round(anytime_pct * 0.28, 1)  # ~28% of anytime scorers score first
        return (
            role,
            anytime_pct,
            first_pct,
            round(shot_rate, 2),
            round(sot_rate, 2),
            round(card_rate * 100, 1),
        )

    # Home starting lineup
    for idx, p in enumerate(lineups[0].get("startXI", [])):
        pname = p["player"]["name"]
        pstats = get_player_rolling_stats(pname, df)
        rating = pstats.get("rating_roll", 6.5)
        role, anytime, first, shots, sot, yellow = _player_probs(
            idx, exp_h, lambda_home_cards, rating
        )
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
                "red_prob": round(yellow * 0.05, 1),
                "rating": round(rating, 2),
            }
        )

    # Away starting lineup
    for idx, p in enumerate(lineups[1].get("startXI", [])):
        pname = p["player"]["name"]
        pstats = get_player_rolling_stats(pname, df)
        rating = pstats.get("rating_roll", 6.5)
        role, anytime, first, shots, sot, yellow = _player_probs(
            idx, exp_a, lambda_away_cards, rating
        )
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
                "red_prob": round(yellow * 0.05, 1),
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
        "corners_lambda": round(lambda_corners_total, 2),
        # Proper Poisson CDF — P(X > threshold) using exact series, not noisy samples
        "corners_over_75": round(_poisson_sf(7.5, lambda_corners_total) * 100, 1),
        "corners_over_85": round(_poisson_sf(8.5, lambda_corners_total) * 100, 1),
        "corners_over_95": round(_poisson_sf(9.5, lambda_corners_total) * 100, 1),
        "corners_over_105": round(_poisson_sf(10.5, lambda_corners_total) * 100, 1),
        "corners_over_115": round(_poisson_sf(11.5, lambda_corners_total) * 100, 1),
        "corners_over_125": round(_poisson_sf(12.5, lambda_corners_total) * 100, 1),
        "cards_lambda": round(lambda_cards_total, 2),
        "cards_yellow_home": home_yellows,
        "cards_yellow_away": away_yellows,
        "cards_yellow_total": home_yellows + away_yellows,
        # Proper Poisson CDF for cards
        "cards_over_15": round(_poisson_sf(1.5, lambda_cards_total) * 100, 1),
        "cards_over_25": round(_poisson_sf(2.5, lambda_cards_total) * 100, 1),
        "cards_over_35": round(_poisson_sf(3.5, lambda_cards_total) * 100, 1),
        "cards_over_45": round(_poisson_sf(4.5, lambda_cards_total) * 100, 1),
        "cards_red_total": round(lambda_cards_total * 0.04, 2),
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
        "dc_covered": _dc_covered,
        "markets": {
            "1X2": [
                {
                    "selection": "Home (1)",
                    "prob": _calibrate_1x2(round(prob_1 * 100, 1)),
                },
                {
                    "selection": "Draw (X)",
                    "prob": _calibrate_1x2(round(prob_x * 100, 1)),
                },
                {
                    "selection": "Away (2)",
                    "prob": _calibrate_1x2(round(prob_2 * 100, 1)),
                },
            ],
            "Over/Under 2.5": [
                # Calibrated for honest display; O/U stays off the betting whitelist.
                {
                    "selection": "Over 2.5",
                    "prob": _calibrate_over25(round(prob_over_25 * 100, 1)),
                },
                {
                    "selection": "Under 2.5",
                    "prob": round(
                        100.0 - _calibrate_over25(round(prob_over_25 * 100, 1)), 1
                    ),
                },
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
            # ── New markets (derived from DC xG) ─────────────────────────────
            "Double Chance": [
                {"selection": "1X", "prob": round((prob_1 + prob_x) * 100, 1)},
                {"selection": "X2", "prob": round((prob_x + prob_2) * 100, 1)},
                {"selection": "12", "prob": round((prob_1 + prob_2) * 100, 1)},
            ],
            "Draw No Bet": [
                {
                    "selection": "Home",
                    "prob": round(prob_1 / max(prob_1 + prob_2, 0.001) * 100, 1),
                },
                {
                    "selection": "Away",
                    "prob": round(prob_2 / max(prob_1 + prob_2, 0.001) * 100, 1),
                },
            ],
            "Over/Under 3.0": [
                {"selection": "Over 3.0", "prob": round(prob_over_30 * 100, 1)},
                {
                    "selection": "Under 3.0",
                    "prob": round((1.0 - prob_over_30) * 100, 1),
                },
            ],
            "Over/Under 2.0": [
                {"selection": "Over 2.0", "prob": round(prob_over_20 * 100, 1)},
                {
                    "selection": "Under 2.0",
                    "prob": round((1.0 - prob_over_20) * 100, 1),
                },
            ],
            "Team Total Home": [
                {
                    "selection": f"Home Over 0.5",
                    "prob": round((1.0 - poisson_prob(exp_h, 0)) * 100, 1),
                },
                {
                    "selection": f"Home Over 1.5",
                    "prob": round(
                        (1.0 - poisson_prob(exp_h, 0) - poisson_prob(exp_h, 1)) * 100, 1
                    ),
                },
            ],
            "Team Total Away": [
                {
                    "selection": f"Away Over 0.5",
                    "prob": round((1.0 - poisson_prob(exp_a, 0)) * 100, 1),
                },
                {
                    "selection": f"Away Over 1.5",
                    "prob": round(
                        (1.0 - poisson_prob(exp_a, 0) - poisson_prob(exp_a, 1)) * 100, 1
                    ),
                },
            ],
            "Asian Handicap": [
                {"selection": f"{home_team} -0.5", "prob": round(prob_1 * 100, 1)},
                {
                    "selection": f"{home_team} +0.5",
                    "prob": round((prob_1 + prob_x) * 100, 1),
                },
                {"selection": f"{away_team} -0.5", "prob": round(prob_2 * 100, 1)},
                {
                    "selection": f"{away_team} +0.5",
                    "prob": round((prob_2 + prob_x) * 100, 1),
                },
            ],
        },
        # ── Signal metadata (displayed on dashboard cards) ─────────────────
        "fatigue": _fatigue_info,
        "weather": {
            "rain": _weather_info.get("rain", False),
            "heavy_wind": _weather_info.get("heavy_wind", False),
            "wind_kmh": _weather_info.get("wind_kmh", 0.0),
            "precipitation_mm": _weather_info.get("precipitation_mm", 0.0),
            "source": _weather_info.get("source", "disabled"),
        },
        "referee": {
            "name": _referee_info.get("referee"),
            "found": _referee_info.get("found", False),
            "booking_rate": _referee_info.get("booking_rate", 3.5),
            "is_high_card": _referee_info.get("is_high_card", False),
            "is_low_card": _referee_info.get("is_low_card", False),
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
    # Faroese clubs: Betarabia uses the full Faroese name; Flashscore uses the
    # English short-form abbreviation.  Zero token overlap -> must alias before tokenizing.
    "argja boltfelag": "ab argir",       # AB Argir (Argja Boltfelag Argir)
    "argja boltfelag argir": "ab argir", # full form
    # Icelandic variants seen in Flashscore
    "breidablik": "breidablik",          # already matches; kept for docs
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
            # Scandinavian / Eastern European suffixes
            "bk",
            "ik",
            "if",
            "sk",
            "aik",
            "ff",
            "bois",
            # Other common suffixes
            "ac",
            "hfc",
            "rfc",
            "utd",
            "jfc",
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
                fresher_tie = (
                    total_score == best_score
                    and sat
                    and best_scraped_at
                    and str(sat) > str(best_scraped_at)
                )
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
                    str(best_scraped_at).replace("Z", "+00:00")
                ).timestamp()
                _betarabia_odds_age_min = (time.time() - _ts) / 60.0
            except Exception:
                _betarabia_odds_age_min = None

        if not best_fid:
            conn.close()
            return None

        # Query markets. ORDER BY market_id so canonical 3-way rows (hyphen IDs,
        # e.g. "26935878-3-0-0-0-0") always sort before secondary 2-way duplicate
        # markets (underscore IDs). Combined with setdefault below this prevents
        # a stray 2-way line (e.g. Home@14.0 / Away@1.002) from overwriting the
        # real 3-way 1X2 odds and inflating EV.
        cur.execute(
            "SELECT market_name, selection_name, raw_odds FROM market"
            " WHERE fixture_id = ? ORDER BY market_id ASC",
            (best_fid,),
        )
        rows = cur.fetchall()
        conn.close()

        odds_dict = {
            "1X2": {},
            "Over/Under 2.5": {},
            "Over/Under 3.0": {},
            "Over/Under 2.0": {},
            "BTTS": {},
            "Double Chance": {},
            "Draw No Bet": {},
            "Corners": {},
            "Total Cards": {},
            "Goalscorer": {},
            "Player Shots on Target": {},
        }

        for mname, sname, price in rows:
            mname_lower = mname.lower()
            sname_lower = sname.lower()

            # Match Result (1X2)
            # Use setdefault: first valid 3-way market wins; later 2-way duplicates
            # (e.g. Asian handicap lines with extreme odds) are ignored.
            if "result" in mname_lower or "1x2" in mname_lower:
                if sname_lower == "x" or "draw" in sname_lower:
                    odds_dict["1X2"].setdefault("Draw", price)
                else:
                    h_score = get_match_score(sname, best_home)
                    a_score = get_match_score(sname, best_away)
                    if h_score >= 0.5 and h_score > a_score:
                        odds_dict["1X2"].setdefault("Home", price)
                    elif a_score >= 0.5 and a_score > h_score:
                        odds_dict["1X2"].setdefault("Away", price)

            # Corners — sname is now "Corners OVER 9.5" after scraper fix
            elif "corner" in mname_lower and "total" in mname_lower:
                odds_dict["Corners"][sname] = price

            # Total Cards / Yellow Cards
            elif (
                "card" in mname_lower
                or "booking" in mname_lower
                or "yellow" in mname_lower
            ) and "total" in mname_lower:
                odds_dict["Total Cards"][sname] = price

            # Total Goals Over/Under — route by line value in selection name
            elif ("total" in mname_lower and "goal" in mname_lower) or (
                ("total" in mname_lower or "goals" in mname_lower)
                and "total" in sname_lower
            ):
                import re as _re

                _line_m = _re.search(r"(\d+\.?\d*)", sname)
                _line_v = float(_line_m.group(1)) if _line_m else 2.5
                if "over" in sname_lower:
                    if abs(_line_v - 2.5) < 0.01:
                        odds_dict["Over/Under 2.5"]["Over"] = price
                    elif abs(_line_v - 3.0) < 0.01:
                        odds_dict["Over/Under 3.0"]["Over"] = price
                    elif abs(_line_v - 2.0) < 0.01:
                        odds_dict["Over/Under 2.0"]["Over"] = price
                    else:
                        odds_dict["Over/Under 2.5"].setdefault("Over", price)
                elif "under" in sname_lower:
                    if abs(_line_v - 2.5) < 0.01:
                        odds_dict["Over/Under 2.5"]["Under"] = price
                    elif abs(_line_v - 3.0) < 0.01:
                        odds_dict["Over/Under 3.0"]["Under"] = price
                    elif abs(_line_v - 2.0) < 0.01:
                        odds_dict["Over/Under 2.0"]["Under"] = price
                    else:
                        odds_dict["Over/Under 2.5"].setdefault("Under", price)

            # Double Chance
            elif "double chance" in mname_lower or "double_chance" in mname_lower:
                if "1x" in sname_lower or "home or draw" in sname_lower:
                    odds_dict["Double Chance"]["1X"] = price
                elif "x2" in sname_lower or "draw or away" in sname_lower:
                    odds_dict["Double Chance"]["X2"] = price
                elif "12" in sname_lower or "home or away" in sname_lower:
                    odds_dict["Double Chance"]["12"] = price

            # Draw No Bet
            elif "draw no bet" in mname_lower or "dnb" in mname_lower:
                h_score_dnb = get_match_score(sname, best_home)
                a_score_dnb = get_match_score(sname, best_away)
                if h_score_dnb >= 0.5 and h_score_dnb > a_score_dnb:
                    odds_dict["Draw No Bet"]["Home"] = price
                elif a_score_dnb >= 0.5 and a_score_dnb > h_score_dnb:
                    odds_dict["Draw No Bet"]["Away"] = price

            # BTTS
            elif "both teams" in mname_lower or "btts" in mname_lower:
                if "yes" in sname_lower:
                    odds_dict["BTTS"]["Yes"] = price
                elif "no" in sname_lower:
                    odds_dict["BTTS"]["No"] = price

            # Player anytime goalscorer — sname like "Kylian Mbappe Over 0.5"
            # Store keyed by player name (strip " Over 0.5")
            elif "goalscorer" in mname_lower or (
                "anytime" in mname_lower and "goal" in mname_lower
            ):
                import re as _re

                player = _re.sub(
                    r"\s+Over\s+\d+\.?\d*$", "", sname, flags=_re.IGNORECASE
                ).strip()
                if player:
                    odds_dict["Goalscorer"][player] = price

            # Player shots on target — sname like "Mbappe Over 1.5"
            elif "shots on target" in mname_lower and "player" in mname_lower:
                import re as _re

                player_sot = _re.sub(
                    r"\s+(Over|Under)\s+\d+\.?\d*$", "", sname, flags=_re.IGNORECASE
                ).strip()
                if player_sot:
                    line_m = _re.search(
                        r"(Over|Under)\s+(\d+\.?\d*)", sname, _re.IGNORECASE
                    )
                    if line_m:
                        direction = line_m.group(1).lower()
                        line_val = float(line_m.group(2))
                        key = f"{player_sot} {direction.title()} {line_val}"
                        odds_dict["Player Shots on Target"][key] = price

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
CLOSING_WINDOW_MIN = 30  # snapshot when kickoff is within this many minutes
CLOSING_CAPTURE_INTERVAL = (
    90  # seconds between capture passes (decoupled from the slow main loop)
)
_closing_started = False
# Handle to the running Betarabia scraper subprocess. The scraper takes ~3 min
# (it scouts each event's markets one-by-one); spawning a fresh one every cycle
# stacks Chromium instances that exhaust memory and die before writing -> stale
# odds. We keep this handle and only launch a new scrape once the prior finished.
_scraper_proc = None
# Throttle deep score lookups (browser-based) to once per 30 minutes
_deep_lookup_last_run = 0.0
_DEEP_LOOKUP_INTERVAL = 1800  # 30 minutes in seconds
# Age (minutes) of the Betarabia odds for the fixture most recently looked up by
# find_betarabia_odds(). The bet gate reads this to REFUSE betting on stale odds —
# defence-in-depth so a future scraper failure can never silently bet old prices.
_betarabia_odds_age_min = None
# Flag set by _pinnacle_fallback_odds() so downstream code knows the odds came
# from Pinnacle (not Betarabia). PINNACLE_VALUE bets are skipped when this is True
# because comparing Pinnacle to itself produces no edge.
_pinnacle_fallback_used = False


def _pinnacle_fallback_odds(home: str, away: str) -> dict | None:
    """Build a synthetic odds_dict from Pinnacle sharp_odds_history.

    Used when Betarabia has no odds for a fixture (common for World Cup knockouts
    and other events the soft book doesn't list). Returns a dict with the same
    structure as find_betarabia_odds() — keys '1X2' and 'Over/Under 2.5' with
    selection→decimal_odds mappings — or None if Pinnacle also has no data.

    Also sets _betarabia_odds_age_min to the Pinnacle snapshot age so the
    freshness gate works correctly.
    """
    global _betarabia_odds_age_min, _pinnacle_fallback_used
    _pin_fb_db = os.path.join(
        DATA_DIR, "deepfield_browser_data", "completed_fixtures.db"
    )
    if not os.path.exists(_pin_fb_db):
        return None
    try:
        from tools.pinnacle_value import _normalize_team

        h_norm = _normalize_team(home)
        a_norm = _normalize_team(away)
        con = sqlite3.connect(_pin_fb_db, timeout=5)
        con.row_factory = sqlite3.Row

        # Need >= 10 snapshots for reliable price (same as check_value)
        cnt = con.execute(
            "SELECT COUNT(*) FROM sharp_odds_history "
            "WHERE LOWER(REPLACE(REPLACE(home_team,'.',''),'-',' '))=? "
            "AND LOWER(REPLACE(REPLACE(away_team,'.',''),'-',' '))=?",
            (h_norm, a_norm),
        ).fetchone()[0]
        if cnt < 10:
            con.close()
            return None

        # Fetch latest 1X2 odds
        x12 = {}
        for sel_key, sel_label in [("home", "Home"), ("draw", "Draw"), ("away", "Away")]:
            row = con.execute(
                "SELECT decimal_odds, ts FROM sharp_odds_history "
                "WHERE LOWER(REPLACE(REPLACE(home_team,'.',''),'-',' '))=? "
                "AND LOWER(REPLACE(REPLACE(away_team,'.',''),'-',' '))=? "
                "AND selection=? ORDER BY ts DESC LIMIT 1",
                (h_norm, a_norm, sel_key),
            ).fetchone()
            if row and row["decimal_odds"] and row["decimal_odds"] > 1.0:
                x12[sel_label] = round(row["decimal_odds"], 2)
                # Track freshness from the most recent snapshot
                try:
                    _betarabia_odds_age_min = (time.time() - row["ts"]) / 60.0
                except Exception:
                    pass

        # Fetch latest O/U 2.5 odds
        ou25 = {}
        for sel_key, sel_label in [("over_2.5", "Over"), ("under_2.5", "Under")]:
            row = con.execute(
                "SELECT decimal_odds FROM sharp_odds_history "
                "WHERE LOWER(REPLACE(REPLACE(home_team,'.',''),'-',' '))=? "
                "AND LOWER(REPLACE(REPLACE(away_team,'.',''),'-',' '))=? "
                "AND selection=? ORDER BY ts DESC LIMIT 1",
                (h_norm, a_norm, sel_key),
            ).fetchone()
            if row and row["decimal_odds"] and row["decimal_odds"] > 1.0:
                ou25[sel_label] = round(row["decimal_odds"], 2)

        con.close()

        if len(x12) < 2:
            return None  # Need at least 2 of 3 outcomes for meaningful odds

        _pinnacle_fallback_used = True
        return {
            "1X2": x12,
            "Over/Under 2.5": ou25,
            "Over/Under 3.0": {},
            "Over/Under 2.0": {},
            "BTTS": {},
            "Double Chance": {},
            "Draw No Bet": {},
            "Corners": {},
            "Total Cards": {},
            "Goalscorer": {},
            "Player Shots on Target": {},
        }
    except Exception:
        return None


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
            "SELECT fixture_id, match_id, side, market_type FROM bet_log "
            "WHERE result = 'OPEN' AND market_type IN ('1X2', 'Over/Under 2.5') "
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
    for fid, match, side, mkt_type in open_bets:
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
        # Look up the correct market section and extract the right key
        mkt_section = odds_dict.get(mkt_type) or {}
        if mkt_type == "Over/Under 2.5":
            # O/U side is "Over 2.5" or "Under 2.5" -> key is "Over"/"Under"
            key = str(side).split()[0] if side else ""
        else:
            key = str(side).split(" (")[0]  # "Home (1)" -> "Home"
        price = mkt_section.get(key)
        if not price or price <= 0:
            continue
        try:
            snap = sqlite3.connect(_odds_history_db())
            # Write the bet's EXACT side string and market type so settlement's
            # CLV lookup (which matches odds_history.selection to bet_log.side)
            # finds it.
            snap.execute(
                "INSERT INTO odds_history (fixture_id, market, selection, odds) "
                "VALUES (?, ?, ?, ?)",
                (str(fid), mkt_type, side, float(price)),
            )
            snap.commit()
            snap.close()
            captured += 1
        except Exception:
            continue
    if captured:
        print(
            f"[CLOSING] Captured {captured} pre-kickoff closing line(s) for open bets."
        )
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
    threading.Thread(
        target=_closing_capture_loop, daemon=True, name="closing-capture"
    ).start()
    print(
        "[*] Closing-line capture thread started "
        f"(every {CLOSING_CAPTURE_INTERVAL}s, kickoff window {CLOSING_WINDOW_MIN}m)."
    )


# Sane decimal-odds bands per market. A price outside its band is almost always a STALE
# or GARBLED scrape (e.g. the phantom "Tindastoll vs Augnablik Under 2.5 @ 4.10" that no
# results source could ever settle because the match didn't exist). Reject such bets at
# logging time so they never enter the ledger as forever-OPEN "awaiting result" rows.
_ODDS_BANDS = {
    "1X2": (1.01, 34.0),  # big underdogs exist; >34 or <1.01 is impossible
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


def log_steam_bet(
    match,
    market,
    selection,
    odds,
    steam_move_pct,
    fixture_id=None,
    league=None,
    monotonicity=None,
    bet_source="STEAM",
):
    """Shadow flat-stake bet for a fired STEAM (line-movement) signal.

    A SEPARATE strategy from the model: bet_source='STEAM', a FLAT stake (the edge is the
    move itself, not a model probability, so Kelly doesn't apply), settled by settle_open_bets
    like any other 1X2 bet. Paper only — never touches real money. Gated by
    settings.steam_betting_enabled (default True) and deduped per fixture/market/selection.
    """
    settings = load_settings()
    if not settings.get("steam_betting_enabled", True):
        return
    if _implausible_odds(market, odds):
        print(
            f"[GUARD] Skipped STEAM bet on implausible {market} odds {odds}: "
            f"{match} ({selection}) — stale/garbled price."
        )
        return
    db_path = os.path.join(DATA_DIR, "bet_log.db")
    if not os.path.exists(db_path):
        return
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM bet_log WHERE match_id=? AND market_type=? AND side=? "
            "AND bet_source=?",
            (match, market, selection, bet_source),
        )
        if cur.fetchone()[0] > 0:
            conn.close()
            return
        # Cross-source dedup: one open bet per fixture total — prevents AI + STEAM doubling
        # up on the same game from opposite/same sides, which doubles loss risk.
        if fixture_id is not None:
            cur.execute(
                "SELECT COUNT(*) FROM bet_log WHERE fixture_id=? AND result='OPEN'",
                (str(fixture_id),),
            )
            if cur.fetchone()[0] > 0:
                conn.close()
                return

        try:
            br_conn = sqlite3.connect(os.path.join(DATA_DIR, "bankroll.db"))
            balance = br_conn.execute(
                "SELECT current_balance FROM bankroll ORDER BY date DESC LIMIT 1"
            ).fetchone()[0]
            br_conn.close()
        except Exception:
            balance = 10000.0

        # Bankroll-proportional stake (a small fixed fraction ~ 1/8-1/4 Kelly), floored/capped.
        # Auto-scales with the bankroll instead of a flat $ that drifts from 2% to 5% as the
        # balance moves. Falls back to the flat stake if steam_kelly_frac is unset.
        frac = settings.get("steam_kelly_frac", 0.02)
        if frac and frac > 0:
            stake = round(balance * frac, 2)
            stake = max(1.0, min(stake, balance * 0.03))  # floor $1, cap 3% of bankroll
        else:
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

        src_prefix = bet_source.replace("_", "")[:10]
        bet_id = f"{src_prefix}_" + uuid.uuid4().hex[:10]

        for col_sql in [
            "ALTER TABLE bet_log ADD COLUMN signal_name TEXT",
            "ALTER TABLE bet_log ADD COLUMN move_size REAL",
            "ALTER TABLE bet_log ADD COLUMN monotonicity REAL",
        ]:
            try:
                conn.execute(col_sql)
            except Exception:
                pass

        cur.execute(
            """INSERT OR IGNORE INTO bet_log
               (bet_id, match_id, player_id, market_type, entry_odds, fair_odds, edge_pct, stake,
                result, pnl, placed_at, bet_source, is_recommended, line, side, fixture_id, league, signal_name, move_size, monotonicity)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                bet_id,
                match,
                f"{match} ({selection})",
                market,
                odds,
                odds,
                round(steam_move_pct, 1),
                stake,
                "OPEN",
                0.0,
                datetime.datetime.now().isoformat(),
                bet_source,
                1,
                2.5,
                selection,
                str(fixture_id) if fixture_id is not None else None,
                league,
                bet_source,
                steam_move_pct,
                monotonicity,
            ),
        )
        # Line-shop: record the BEST price across Betarabia + Kambi (metadata only — the bet
        # still books at Betarabia). Quantifies the +1.9% line-shopping edge before we act on it.
        try:
            from src.line_shop import best_1x2

            ls = best_1x2(match, selection, odds)
            cur.execute(
                "UPDATE bet_log SET best_odds=?, best_book=? WHERE bet_id=?",
                (ls["best_odds"], ls["best_book"], bet_id),
            )
        except Exception:
            pass
        conn.commit()
        conn.close()
        print(
            f"[{bet_source}] Shadow flat-stake bet: {match} ({selection}) @ {odds} "
            f"move +{steam_move_pct:.1f}% stake {stake}"
        )
    except Exception as e:
        print(f"[STEAM BET] error: {e}")


def log_pinnacle_value_bet(
    match,
    market,
    selection,
    odds,
    pinnacle_edge_pct,
    fixture_id=None,
    league=None,
    pinnacle_data=None,
):
    """Shadow bet when Betarabia price exceeds de-vigged Pinnacle fair value by >= min_edge.

    Uses the same Kelly sizing as STEAM (bankroll-proportional or flat fallback).
    bet_source='PINNACLE_VALUE', settled automatically by settle_open_bets.
    Gated by settings.pinnacle_value_betting_enabled (default False — measure first).
    """
    settings = load_settings()
    if not settings.get("pinnacle_value_betting_enabled", False):
        return
    if _implausible_odds(market, odds):
        return
    db_path = os.path.join(DATA_DIR, "bet_log.db")
    if not os.path.exists(db_path):
        return
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM bet_log WHERE match_id=? AND market_type=? AND side=? "
            "AND bet_source='PINNACLE_VALUE'",
            (match, market, selection),
        )
        if cur.fetchone()[0] > 0:
            conn.close()
            return

        # P2 FIX: Opposing bet prevention.
        # Don't bet the other side of a market we already have an OPEN bet on.
        # E.g., if we already bet Over 2.5, don't also bet Under 2.5 on the same fixture.
        if settings.get("opposing_bet_prevention", True) and fixture_id:
            _opposing_sides = {"Home (1)": "Away (2)", "Away (2)": "Home (1)"}
            _opposing_ou = {"Over 2.5": "Under 2.5", "Under 2.5": "Over 2.5"}
            _all_opposing = {**_opposing_sides, **_opposing_ou}
            _opp_side = _all_opposing.get(selection)
            if _opp_side:
                cur.execute(
                    "SELECT COUNT(*) FROM bet_log WHERE fixture_id=? AND market_type=? "
                    "AND side=? AND result='OPEN'",
                    (str(fixture_id), market, _opp_side),
                )
                if cur.fetchone()[0] > 0:
                    print(
                        f"[PINNACLE VALUE] Blocked opposing bet: {match} {selection} "
                        f"(already have {_opp_side} OPEN)"
                    )
                    conn.close()
                    return
            # Also block if we already have ANY other OPEN bet on same fixture+market
            # (prevents 3-way bets on 1X2)
            if market in ("Over/Under 2.5", "Over/Under 3.0", "Over/Under 2.0"):
                cur.execute(
                    "SELECT side FROM bet_log WHERE fixture_id=? AND market_type=? "
                    "AND result='OPEN'",
                    (str(fixture_id), market),
                )
                existing_sides = {r[0] for r in cur.fetchall()}
                if existing_sides and selection not in existing_sides:
                    print(
                        f"[PINNACLE VALUE] Blocked multi-side bet: {match} {market} {selection} "
                        f"(already have {existing_sides} OPEN)"
                    )
                    conn.close()
                    return

        # P1 FIX: Max edge cap for PINNACLE_VALUE bets.
        # Data shows edges > 8% are model error, not real value.
        _max_edge = settings.get("pinnacle_max_edge_pct", 8.0)
        if pinnacle_edge_pct > _max_edge:
            print(
                f"[PINNACLE VALUE] Edge {pinnacle_edge_pct:.1f}% exceeds cap "
                f"{_max_edge}% — skipping (likely model error)"
            )
            conn.close()
            return

        try:
            br_conn = sqlite3.connect(os.path.join(DATA_DIR, "bankroll.db"))
            balance = br_conn.execute(
                "SELECT current_balance FROM bankroll ORDER BY date DESC LIMIT 1"
            ).fetchone()[0]
            br_conn.close()
        except Exception:
            balance = 10000.0

        frac = settings.get("steam_kelly_frac", 0.02)
        if frac and frac > 0:
            stake = round(balance * frac, 2)
            stake = max(1.0, min(stake, balance * 0.03))
        else:
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

        bet_id = "PV_" + uuid.uuid4().hex[:12]
        fair_odds_val = (pinnacle_data or {}).get("fair_odds", odds)
        cur.execute(
            """INSERT INTO bet_log
               (bet_id, match_id, player_id, market_type, entry_odds, fair_odds, edge_pct, stake,
                result, pnl, placed_at, bet_source, is_recommended, line, side, fixture_id, league)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                bet_id,
                match,
                f"{match} ({selection})",
                market,
                odds,
                round(fair_odds_val, 4) if fair_odds_val else odds,
                round(pinnacle_edge_pct, 2),
                stake,
                "OPEN",
                0.0,
                datetime.datetime.now().isoformat(),
                "PINNACLE_VALUE",
                1,
                2.5,
                selection,
                str(fixture_id) if fixture_id is not None else None,
                league,
            ),
        )
        # P5: Line-shop: record the BEST price across Betarabia + Kambi + Pinnacle.
        # Quantifies the line-shopping edge (+1.9% documented CLV) before we act on it.
        try:
            from src.line_shop import best_1x2

            ls = best_1x2(match, selection, odds)
            cur.execute(
                "UPDATE bet_log SET best_odds=?, best_book=? WHERE bet_id=?",
                (ls["best_odds"], ls["best_book"], bet_id),
            )
        except Exception:
            pass
        conn.commit()
        conn.close()
        print(
            f"[PINNACLE VALUE] Shadow bet: {match} ({selection}) @ {odds} "
            f"edge +{pinnacle_edge_pct:.1f}% vs Pinnacle fair stake {stake}"
        )

        # ── CLV TRACKING: Record this bet in the CLV tracking system ──
        if _CLV_TRACKER_OK and _clv_record_bet:
            try:
                pin_devig_prob = (pinnacle_data or {}).get("devig_prob", 0)
                pin_fair_odds = (pinnacle_data or {}).get("fair_odds", odds)
                _clv_record_bet(
                    bet_id=bet_id,
                    fixture_id=fixture_id,
                    match_name=match,
                    league=league or "",
                    selection=selection,
                    bet_source="PINNACLE_VALUE",
                    opening_odds=odds,
                    bet_odds=odds,
                    pinnacle_devig_prob=pin_devig_prob,
                    pinnacle_opening_odds=pin_fair_odds,
                    pinnacle_bet_odds=pin_fair_odds,
                    edge=pinnacle_edge_pct / 100.0,
                    ev=pinnacle_edge_pct / 100.0,
                    stake=stake,
                    market_type=market,
                )
            except Exception as _clv_err:
                print(f"[CLV TRACKING] Error recording PV bet: {_clv_err}")
    except Exception as e:
        print(f"[PINNACLE VALUE BET] error: {e}")


def log_ai_bet(
    match, market, selection, odds, prob, ev, fixture_id=None, league=None, source=None
):
    """AI model-dependent paper bet (shadow mode).
    Gated by settings.model_predictions_disabled (default True = disabled).
    When enabled, uses Dixon-Coles + LightGBM ensemble + Platt calibrators for
    1X2 and O/U 2.5. O/U 2.5 has shown +51% ROI on settled paper bets."""
    settings = load_settings()
    if settings.get("model_predictions_disabled", True):
        return
    db_path = os.path.join(DATA_DIR, "bet_log.db")
    if not os.path.exists(db_path):
        return
    if _implausible_odds(market, odds):
        print(
            f"[GUARD] Skipped AI bet on implausible {market} odds {odds}: "
            f"{match} ({selection}) — stale/garbled price."
        )
        return

    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        # Check if already logged by any AI source
        cur.execute(
            """
            SELECT COUNT(*) FROM bet_log
            WHERE match_id = ? AND market_type = ? AND side = ? AND bet_source = 'AI'
        """,
            (match, market, selection),
        )
        exists = cur.fetchone()[0] > 0
        # Cross-source dedup: skip if ANY source already has an open bet on this fixture
        if not exists and fixture_id is not None:
            cur.execute(
                "SELECT COUNT(*) FROM bet_log WHERE fixture_id=? AND result='OPEN'",
                (str(fixture_id),),
            )
            if cur.fetchone()[0] > 0:
                exists = True

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

            # The AI/1X2 model has NO proven edge (it failed its own 2,386-bet out-of-sample
            # test) and is the vast majority of bets — REAL-staking it just bleeds the bankroll.
            # Default: log AI picks as ZERO-stake SHADOW bets (visible + CLV-tracked, zero
            # bankroll impact). Flip ai_real_staking_enabled=true ONLY when edge_status.py shows
            # AI = GO on CLV. STEAM/SHARP (the validated edges) keep their real stakes.
            if not settings.get("ai_real_staking_enabled", False):
                stake = 0.0

            from src.bankroll_tracker import register_bet

            if stake > 0:
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
                    source or "AI",
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
                    if hasattr(notifier, "_send_whatsapp"):
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
                    print(
                        f"[STAIR AI] Place bet response: {res.status_code} - {res.text}"
                    )
                    if res.status_code in [200, 201]:
                        try:
                            res_data = res.json()
                            if "order_id" in res_data:
                                order_id = res_data["order_id"]
                            elif "orderId" in res_data:
                                order_id = res_data["orderId"]
                            elif "data" in res_data and isinstance(
                                res_data["data"], dict
                            ):
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
_apifootball_cache = {}  # date_str -> (epoch_fetched, {match: (hs, as)})
_APIFOOTBALL_TTL = 3600  # 1 hour


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
    for delta in range(3):  # free plan: today, yesterday, tomorrow only
        day = (now - datetime.timedelta(days=delta)).strftime("%Y-%m-%d")
        cached = _apifootball_cache.get(day)
        if cached and (time.time() - cached[0]) < _APIFOOTBALL_TTL:
            results.update(cached[1])
            continue
        day_results = {}
        try:
            r = requests.get(
                "https://v3.football.api-sports.io/fixtures",
                headers=headers,
                params={"date": day},
                timeout=20,
            )
            payload = r.json()
            if payload.get("errors"):
                # Quota exhausted or auth error — don't cache an empty (so it retries
                # next hour after the daily reset), just skip this date for now.
                print(
                    f"[SETTLEMENT] API-Football skipped for {day}: {payload['errors']}"
                )
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

    # Compute date range: cover the oldest open bet so bets >2 days old can settle.
    # Both scrapers accept a `dates` list; default is today+yesterday only.
    try:
        _bl_conn = sqlite3.connect(os.path.join(DATA_DIR, "bet_log.db"))
        _oldest = _bl_conn.execute(
            "SELECT MIN(placed_at) FROM bet_log WHERE result='OPEN'"
        ).fetchone()[0]
        _bl_conn.close()
    except Exception:
        _oldest = None
    _now_utc = datetime.datetime.now(datetime.timezone.utc)
    if _oldest:
        try:
            _oldest_dt = datetime.datetime.fromisoformat(
                str(_oldest).replace("Z", "+00:00")
            ).replace(tzinfo=datetime.timezone.utc)
            _days_back = max(1, (_now_utc.date() - _oldest_dt.date()).days)
        except Exception:
            _days_back = 3
    else:
        _days_back = 1
    _days_back = min(
        _days_back, 7
    )  # cap at 7 so we don't hammer APIs with ancient bets
    _settle_dates = [
        (_now_utc - datetime.timedelta(days=d)).strftime("%Y-%m-%d")
        for d in range(_days_back + 1)
    ]

    # Sofascore is bot-blocked/empty — use the free, key-less results scraper
    # (ESPN + TheSportsDB) as the primary settlement feed.
    try:
        from src.free_results_scraper import get_finished_results

        free_results = get_finished_results(dates=_settle_dates)
        finished_matches.update(free_results)
        print(
            f"[SETTLEMENT] Free results scraper provided {len(free_results)} finished matches."
        )
    except Exception as e:
        print("[SETTLEMENT] free results scraper failed:", e)

    # Flashscore (keyless, deep coverage down to Brazilian Serie D) — catches the obscure
    # lower-division matches ESPN/TheSportsDB miss. Plain requests, cached, no browser.
    try:
        from src.flashscore_scraper import get_finished_results as fs_results

        flash = fs_results(dates=_settle_dates)
        finished_matches.update(flash)
        print(f"[SETTLEMENT] Flashscore provided {len(flash)} finished matches.")
    except Exception as e:
        print("[SETTLEMENT] Flashscore scraper failed:", e)

    # API-Football as an extra source when its daily quota still allows.
    try:
        finished_matches.update(fetch_api_football_results())
    except Exception as e:
        print("[SETTLEMENT] API-Football merge failed:", e)

    # Sofascore via headless browser (covers leagues ESPN/Flashscore miss).
    try:
        from src.sofascore_results_scraper import get_finished_results as ss_results

        sofa = ss_results(dates=_settle_dates)
        before = len(finished_matches)
        finished_matches.update(sofa)
        print(
            f"[SETTLEMENT] Sofascore added {len(finished_matches) - before} new matches ({len(sofa)} total)."
        )
    except Exception as e:
        print("[SETTLEMENT] Sofascore scraper failed:", e)

    # Dashboard state — same fixture_ids as our bets; covers ALL Betarabia leagues
    # regardless of ESPN/Flashscore/SofaScore gaps.  Indexed by fixture_id for
    # zero-fuzzy-matching direct lookup.
    _fid_to_score: dict = {}  # str(fixture_id) -> (home_score, away_score)
    try:
        _dash_path = os.path.join(DATA_DIR, "todays_dashboard_state.json")
        if os.path.exists(_dash_path):
            with open(_dash_path, "r", encoding="utf-8") as _f:
                _dash = json.load(_f)
            _added = 0
            for _m in _dash:
                _fix = _m.get("fixture") or {}
                _st = (_fix.get("status") or {}).get("short", "")
                _hs = _fix.get("home_score")
                _aws = _fix.get("away_score")
                _fid = _m.get("fixture_id")
                if _st == "FT" and _hs is not None and _aws is not None and _fid:
                    _mn = _m.get("match", "")
                    finished_matches[_mn] = (int(_hs), int(_aws))
                    _fid_to_score[str(_fid)] = (int(_hs), int(_aws))
                    _added += 1
            if _added:
                print(
                    f"[SETTLEMENT] Dashboard state added {_added} FT matches (direct fixture_id)."
                )
    except Exception as e:
        print(f"[SETTLEMENT] Dashboard state load failed: {e}")

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
        prop_match_ids = {
            mid
            for (_, mid, _, mt, *_) in open_bets
            if mt in ("Corners", "Total Cards") and mid
        }
        if prop_match_ids:
            try:
                from src.flashscore_stats import stats_for_matches

                prop_stats = stats_for_matches(prop_match_ids)
                print(
                    f"[SETTLEMENT] Flashscore stats for {len(prop_stats)}/{len(prop_match_ids)} "
                    f"prop match(es)."
                )
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

        # conn_bet / cur_bet are aliases for the already-open bet_log connection.
        conn_bet = conn
        cur_bet = cur

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

            # Parse player_id: "Home vs Away (Selection)" where Selection may itself
            # contain parens e.g. "Away (2)". The old greedy regex captured "Away "
            # as part of away_t, producing a broken match_name.
            # Fix: detect the outermost wrapping parens using a selection-pattern anchor.
            _sel_re = re.search(
                r" \((Home(?:\s*\(\d+\))?|Away(?:\s*\(\d+\))?|X|Draw"
                r"|Over[\s\d.]+|Under[\s\d.]+|[12X])\)$",
                player_id or "",
            )
            if _sel_re:
                selection = _sel_re.group(1).strip()
                _mn = player_id[: _sel_re.start()].strip()
                _parts = _mn.split(" vs ", 1)
                if len(_parts) == 2:
                    home_t, away_t = _parts[0].strip(), _parts[1].strip()
                    match_name = f"{home_t} vs {away_t}"
                else:
                    match_name = match_id if match_id else "Unknown vs Unknown"
            else:
                match_name = match_id if match_id else "Unknown vs Unknown"
                selection = bet_side if bet_side else "Home"

            sel_lower = selection.lower()

            # Find score
            try:
                parts = match_name.split(" vs ")
                bet_home = parts[0].strip()
                bet_away = parts[1].strip()
            except Exception:
                continue

            # Direct fixture_id lookup — bypasses fuzzy matching entirely for
            # leagues (Ethiopian, Georgian, Estonian) that external sources can't name-match.
            _direct = _fid_to_score.get(str(bet_fixture_id)) if bet_fixture_id else None
            candidates = (
                []
            )  # reset per-bet — prevents scope leak from previous iteration
            if _direct:
                matched_score = _direct
                best_name = match_name + " [fid-direct]"
                print(
                    f"[SETTLEMENT] Direct fid match for '{match_name}': {matched_score}"
                )
            else:
                candidates = []  # (total_name_score, result_score, finished_name)
                for finished_name, score in finished_matches.items():
                    try:
                        f_parts = finished_name.split(" vs ")
                        fin_home = f_parts[0].strip()
                        fin_away = f_parts[1].strip()
                    except Exception:
                        continue

                    # Normal orientation: bet_home vs fin_home, bet_away vs fin_away
                    h_score = get_match_score(bet_home, fin_home)
                    a_score = get_match_score(bet_away, fin_away)
                    if h_score >= 0.5 and a_score >= 0.5:
                        candidates.append((h_score + a_score, score, finished_name))

                    # Reversed orientation: feed has teams swapped vs the bet
                    # (e.g. bet="Botev Vratsa vs Levski Sofia", feed="Levski Sofia (Bul) vs Botev Vratsa (Bul)")
                    h_rev = get_match_score(bet_home, fin_away)
                    a_rev = get_match_score(bet_away, fin_home)
                    if h_rev >= 0.5 and a_rev >= 0.5:
                        # Swap scores so home_score/away_score match the bet's perspective
                        fin_hs, fin_as = score
                        candidates.append((h_rev + a_rev, (fin_as, fin_hs), finished_name + " [reversed]"))

                if not candidates:
                    # Secondary pass: use score_lookup's _name_similarity which catches
                    # prefix/substring matches that get_match_score misses (e.g. "Elimai" -> "Yelimay Semey")
                    try:
                        from tools.score_lookup import _name_similarity as _sim2
                        for finished_name, score in finished_matches.items():
                            try:
                                f_parts = finished_name.split(" vs ")
                                fin_home = f_parts[0].strip()
                                fin_away = f_parts[1].strip()
                            except Exception:
                                continue
                            # Normal orientation
                            h2 = _sim2(bet_home, fin_home)
                            a2 = _sim2(bet_away, fin_away)
                            if h2 >= 0.65 and a2 >= 0.65:
                                candidates.append((h2 + a2, score, finished_name + " [sim2]"))
                            # Reversed
                            h2r = _sim2(bet_home, fin_away)
                            a2r = _sim2(bet_away, fin_home)
                            if h2r >= 0.65 and a2r >= 0.65:
                                fin_hs, fin_as = score
                                candidates.append((h2r + a2r, (fin_as, fin_hs), finished_name + " [sim2-rev]"))
                        if candidates:
                            candidates.sort(key=lambda c: c[0], reverse=True)
                    except ImportError:
                        pass

                if not candidates:
                    print(
                        f"[SETTLEMENT] No result found for '{match_name}' in {len(finished_matches)} results."
                    )
                    continue

                candidates.sort(key=lambda c: c[0], reverse=True)
                best_total, matched_score, best_name = candidates[0]

            # AMBIGUITY GUARD (fuzzy-match path only — direct fid is unambiguous).
            if not _direct and len(candidates) > 1:
                second_total, second_score, second_name = candidates[1]
                # Only skip when candidates are close AND disagree on the final score.
                # If both candidates have the same score, settle anyway — the outcome
                # is unambiguous regardless of which specific match it is.
                if (best_total - second_total) < 0.50 and second_score != matched_score:
                    print(
                        f"[SETTLEMENT] Ambiguous result match for '{match_name}': "
                        f"'{best_name}'{matched_score} vs '{second_name}'{second_score} "
                        f"— skipping to avoid wrong settlement."
                    )
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
            elif market_type in (
                "Over/Under 2.5",
                "Over/Under 3.0",
                "Over/Under 2.0",
                "Over/Under 1.5",
                "Over/Under 0.5",
            ):
                import re as _sre

                total_goals = home_score + away_score
                _lm = _sre.search(r"(\d+\.?\d*)", market_type)
                _line = float(_lm.group(1)) if _lm else 2.5
                if "over" in sel_lower:
                    if total_goals == _line:
                        # Push on exact integer line — void the bet
                        cur_bet.execute(
                            "UPDATE bet_log SET result='VOID', pnl=0 WHERE bet_id=?",
                            (bet_id,),
                        )
                        conn_bet.commit()
                        try:
                            from src.bankroll_tracker import (
                                register_settlement as _rs_push,
                            )

                            _rs_push(payout=float(stake or 0), pnl=0.0)
                        except Exception:
                            pass
                        continue
                    won = total_goals > _line
                elif "under" in sel_lower:
                    if total_goals == _line:
                        cur_bet.execute(
                            "UPDATE bet_log SET result='VOID', pnl=0 WHERE bet_id=?",
                            (bet_id,),
                        )
                        conn_bet.commit()
                        try:
                            from src.bankroll_tracker import (
                                register_settlement as _rs_push,
                            )

                            _rs_push(payout=float(stake or 0), pnl=0.0)
                        except Exception:
                            pass
                        continue
                    won = total_goals < _line
            elif market_type == "Double Chance":
                home_won = home_score > away_score
                draw = home_score == away_score
                away_won = away_score > home_score
                if sel_lower == "1x":
                    won = home_won or draw
                elif sel_lower == "x2":
                    won = draw or away_won
                elif sel_lower == "12":
                    won = home_won or away_won
            elif market_type == "Draw No Bet":
                if home_score == away_score:
                    # Push — void and refund
                    cur_bet.execute(
                        "UPDATE bet_log SET result='VOID', pnl=0 WHERE bet_id=?",
                        (bet_id,),
                    )
                    conn_bet.commit()
                    try:
                        from src.bankroll_tracker import register_settlement as _rs_push

                        _rs_push(payout=float(stake or 0), pnl=0.0)
                    except Exception:
                        pass
                    continue
                elif "home" in sel_lower:
                    won = home_score > away_score
                elif "away" in sel_lower:
                    won = away_score > home_score
            elif market_type == "BTTS":
                if "yes" in sel_lower:
                    won = home_score > 0 and away_score > 0
                elif "no" in sel_lower:
                    won = home_score == 0 or away_score == 0
            elif market_type == "1X2 HT":
                # Half-time result — requires ht_home / ht_away scores
                ht_h = finished_data.get("ht_home")
                ht_a = finished_data.get("ht_away")
                if ht_h is None or ht_a is None:
                    continue  # no HT data yet — leave OPEN
                if "home" in sel_lower or sel_lower == "1":
                    won = ht_h > ht_a
                elif "draw" in sel_lower or sel_lower == "x":
                    won = ht_h == ht_a
                elif "away" in sel_lower or sel_lower == "2":
                    won = ht_a > ht_h
            elif market_type == "Asian Handicap":
                # sel_lower e.g. "(-1.5) england" → parse handicap value
                ah_match = re.search(r'\(([+-]?\d+\.?\d*)\)', sel_lower)
                if not ah_match:
                    continue
                handicap = float(ah_match.group(1))
                # Determine if this selection is for the home or away team
                home_name_n = _norm(home_team) if 'home_team' in dir() else ""
                away_name_n = _norm(away_team) if 'away_team' in dir() else ""
                is_home = home_name_n and home_name_n in sel_lower
                if is_home:
                    adj_score = (home_score + handicap) - away_score
                else:
                    adj_score = (away_score + handicap) - home_score
                if adj_score == 0:
                    # Push — void
                    cur_bet.execute("UPDATE bet_log SET result='VOID', pnl=0 WHERE bet_id=?", (bet_id,))
                    conn_bet.commit()
                    try:
                        from src.bankroll_tracker import register_settlement as _rs_push
                        _rs_push(payout=float(stake or 0), pnl=0.0)
                    except Exception:
                        pass
                    continue
                won = adj_score > 0
            elif market_type == "1st Team to Score":
                total = home_score + away_score
                if total == 0:
                    # No goals — "No Goal" wins
                    if "no goal" in sel_lower:
                        won = True
                    else:
                        won = False
                else:
                    # We don't have who-scored-first in our data → leave OPEN
                    continue
            elif market_type == "Correct Score":
                # sel_lower e.g. "2-1" or "2 - 1"
                cs_match = re.search(r'(\d+)\s*[-:]\s*(\d+)', sel_lower)
                if not cs_match:
                    continue
                pred_h, pred_a = int(cs_match.group(1)), int(cs_match.group(2))
                won = home_score == pred_h and away_score == pred_a
            elif re.match(r'^over/under \d', market_type):
                # Generic parameterised O/U — e.g. "Over/Under 3.5", "Over/Under 0.5"
                total_goals = home_score + away_score
                _lm = re.search(r'(\d+\.?\d*)', market_type)
                _line = float(_lm.group(1)) if _lm else 2.5
                if "over" in sel_lower:
                    if total_goals == _line:
                        cur_bet.execute("UPDATE bet_log SET result='VOID', pnl=0 WHERE bet_id=?", (bet_id,))
                        conn_bet.commit()
                        continue
                    won = total_goals > _line
                elif "under" in sel_lower:
                    if total_goals == _line:
                        cur_bet.execute("UPDATE bet_log SET result='VOID', pnl=0 WHERE bet_id=?", (bet_id,))
                        conn_bet.commit()
                        continue
                    won = total_goals < _line
            elif re.match(r'^corners \d', market_type) or re.match(r'^corners$', market_type):
                # Parameterised corners e.g. "Corners 9.5"
                if act_corners is None:
                    ps = prop_stats.get(match_id)
                    if ps and ps.get("corners_total") is not None:
                        act_corners = ps["corners_total"]
                    else:
                        continue
                _lm = re.search(r'(\d+\.?\d*)', market_type + " " + sel_lower)
                _line = float(_lm.group(1)) if _lm else 8.5
                if "over" in sel_lower:
                    won = act_corners > _line
                else:
                    won = act_corners < _line
            elif re.match(r'^total cards', market_type):
                # Parameterised cards e.g. "Total Cards 3.5"
                if act_cards is None:
                    ps = prop_stats.get(match_id)
                    if ps and ps.get("cards_total") is not None:
                        act_cards = ps["cards_total"]
                    else:
                        continue
                _lm = re.search(r'(\d+\.?\d*)', market_type + " " + sel_lower)
                _line = float(_lm.group(1)) if _lm else 3.5
                if "over" in sel_lower:
                    won = act_cards > _line
                else:
                    won = act_cards < _line
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
                        os.path.join(
                            DATA_DIR, "deepfield_browser_data", "completed_fixtures.db"
                        )
                    )
                    sc = snap.cursor()
                    if ko is not None:
                        ko_utc = ko.astimezone(datetime.timezone.utc).strftime(
                            "%Y-%m-%d %H:%M:%S"
                        )
                        sc.execute(
                            "SELECT odds FROM odds_history WHERE fixture_id = ? AND market = ? "
                            "AND selection = ? AND timestamp <= ? ORDER BY timestamp DESC LIMIT 1",
                            (str(bet_fixture_id), market_type, bet_side, ko_utc),
                        )
                        row = sc.fetchone()
                    else:
                        row = None
                    if (
                        not row
                    ):  # no kickoff or no pre-kickoff snapshot -> best available
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
                            closing_odds = (
                                c_odds  # keep the observed close for the record
                            )
            except Exception:
                pass

            # PINNACLE CLV: the gold-standard metric. Compare our entry price to the
            # last pre-kickoff Pinnacle snapshot in sharp_odds_history. This tells us
            # objectively whether we beat the sharp market — even when our closing
            # Betarabia odds may not be representative.
            pinnacle_clv = None
            try:
                if market_type == "1X2":
                    from tools.pinnacle_value import clv_from_pinnacle as _pclv

                    _pclv_val = _pclv(
                        bet_home, bet_away, bet_side or selection, entry_odds
                    )
                    if _pclv_val is not None and abs(_pclv_val) <= 0.40:
                        pinnacle_clv = _pclv_val
                elif market_type == "Over/Under 2.5":
                    from tools.pinnacle_value import clv_from_pinnacle_ou25 as _pclv_ou

                    _pclv_val = _pclv_ou(
                        bet_home, bet_away, bet_side or selection, entry_odds
                    )
                    if _pclv_val is not None and abs(_pclv_val) <= 0.40:
                        pinnacle_clv = _pclv_val
            except Exception:
                pass

            # P3 FIX: Prefer Pinnacle closing price over Betarabia.
            # Pinnacle's last pre-kickoff snapshot is the gold standard.
            # When pinnacle_clv is available, back-calculate the Pinnacle closing
            # odds and use it as the primary CLV source.
            if pinnacle_clv is not None and entry_odds:
                try:
                    _pin_closing_calc = round(entry_odds / (1.0 + pinnacle_clv), 4)
                    if _pin_closing_calc > 1.0:
                        closing_odds = _pin_closing_calc
                        clv = pinnacle_clv
                except Exception:
                    pass  # keep Betarabia CLV as fallback

            try:
                cur.execute("ALTER TABLE bet_log ADD COLUMN pinnacle_clv REAL")
            except Exception:
                pass

            cur.execute(
                "UPDATE bet_log SET result = ?, pnl = ?, closing_odds = ?, clv = ?, pinnacle_clv = ? "
                "WHERE bet_id = ?",
                (result, pnl, closing_odds, clv, pinnacle_clv, bet_id),
            )
            _clv_str = f" CLV {clv*100:+.1f}%" if clv is not None else ""
            _pclv_str = (
                f" PinCLV {pinnacle_clv*100:+.1f}%" if pinnacle_clv is not None else ""
            )
            print(
                f"[SETTLEMENT] Settled bet {bet_id} as {result} (PnL: ${pnl:.2f}){_clv_str}{_pclv_str}"
            )

            # ── CLV TRACKER: Sync closing odds + result to clv_tracking.db ──
            if _CLV_TRACKER_OK:
                # Record closing odds (both Betarabia close and Pinnacle close)
                try:
                    _pin_closing = None
                    if pinnacle_clv is not None and entry_odds:
                        # Back-calculate Pinnacle closing decimal from CLV
                        _pin_closing = round(entry_odds / (1.0 + pinnacle_clv), 4)
                    _clv_record_closing(
                        bet_id=bet_id,
                        closing_odds=closing_odds,
                        pinnacle_closing_odds=_pin_closing,
                    )
                except Exception as _clv_close_err:
                    print(
                        f"[CLV TRACKER] Error recording closing odds for {bet_id}: {_clv_close_err}"
                    )

                # Settle the bet in CLV tracker
                try:
                    _clv_settle_bet(
                        bet_id=bet_id,
                        result=result,
                        pnl=pnl,
                        actual_prob=0.0,
                    )
                except Exception as _clv_sett_err:
                    print(f"[CLV TRACKER] Error settling {bet_id}: {_clv_sett_err}")

            # Capital adjustments via Central Tracker
            from src.bankroll_tracker import register_settlement

            try:
                register_settlement(payout, pnl)
            except Exception as _rs_err:
                print(f"[SETTLEMENT] WARNING: register_settlement failed for {bet_id}: {_rs_err}")

        # PARLAY SETTLEMENT
        cur.execute(
            "SELECT parlay_id, legs_json, stake, total_odds FROM parlay_log WHERE result = 'OPEN'"
        )
        open_parlays = cur.fetchall()

        for p_id, legs_json, p_stake, p_odds in open_parlays:
            import json

            legs = json.loads(legs_json)
            parlay_finished = True
            parlay_won = True
            any_leg_lost = False
            legs_updated = False

            for leg in legs:
                if leg.get("result") in ["W", "L"]:
                    if leg["result"] == "L":
                        any_leg_lost = True
                    continue

                # Try to settle this leg
                leg_match_name = leg["match"]
                leg_market = leg["market"]
                leg_selection = leg["selection"].lower()

                # Find score
                best_s = 0.0
                m_score = None
                for fin_name, score in finished_matches.items():
                    h_s = get_match_score(
                        leg_match_name.split(" vs ")[0], fin_name.split(" vs ")[0]
                    )
                    a_s = get_match_score(
                        leg_match_name.split(" vs ")[1], fin_name.split(" vs ")[1]
                    )
                    if h_s >= 0.5 and a_s >= 0.5:
                        if (h_s + a_s) > best_s:
                            best_s = h_s + a_s
                            m_score = score

                if m_score:
                    h_score, a_score = m_score
                    # Basic 1X2 / OU settlement for parlay legs
                    leg_won = False
                    if leg_market == "Match Result":
                        if "1" in leg_selection or "home" in leg_selection:
                            leg_won = h_score > a_score
                        elif "x" in leg_selection or "draw" in leg_selection:
                            leg_won = h_score == a_score
                        else:
                            leg_won = a_score > h_score
                    elif "Total Goals" in leg_market:
                        line = 2.5  # Default
                        if "over" in leg_selection:
                            leg_won = (h_score + a_score) > line
                        else:
                            leg_won = (h_score + a_score) < line
                    else:
                        # No real data for this leg's market → leave the parlay OPEN rather
                        # than fabricate a leg result from hash (the old "random for demo").
                        parlay_finished = False
                        continue

                    leg["result"] = "W" if leg_won else "L"
                    if not leg_won:
                        any_leg_lost = True
                    legs_updated = True
                else:
                    parlay_finished = False  # Still waiting for some legs

            if any_leg_lost:
                res = "L"
                pnl = -p_stake
                cur.execute(
                    "UPDATE parlay_log SET result = ?, pnl = ?, legs_json = ? WHERE parlay_id = ?",
                    (res, pnl, json.dumps(legs), p_id),
                )
                from src.bankroll_tracker import register_settlement

                register_settlement(0.0, pnl)
                print(f"[SETTLEMENT] Parlay {p_id} LOST.")
            elif parlay_finished:
                res = "W"
                pnl = p_stake * (p_odds - 1)
                payout = p_stake * p_odds
                cur.execute(
                    "UPDATE parlay_log SET result = ?, pnl = ?, legs_json = ? WHERE parlay_id = ?",
                    (res, pnl, json.dumps(legs), p_id),
                )
                from src.bankroll_tracker import register_settlement

                register_settlement(payout, pnl)
                print(f"[SETTLEMENT] Parlay {p_id} WON! (PnL: ${pnl:.2f})")
            elif legs_updated:
                # Update legs even if parlay is still open
                cur.execute(
                    "UPDATE parlay_log SET legs_json = ? WHERE parlay_id = ?",
                    (json.dumps(legs), p_id),
                )

        # DEEP SCORE LOOKUP — final attempt for stuck OPEN bets before VOID.
        # Uses Flashscore search + team page scraping + Google fallback to find
        # scores for matches that no feed-based scraper covers (e.g. Faroe Islands,
        # Darwin Premier League, Kazakh Premier League with variant names).
        # Throttled to once per 30 min to avoid hammering browsers every cycle.
        global _deep_lookup_last_run
        import time as _time_mod
        _now_deep = _time_mod.time()
        if (_now_deep - _deep_lookup_last_run) >= _DEEP_LOOKUP_INTERVAL:
            try:
                _still_open = cur.execute(
                    "SELECT bet_id, match_id, market_type, side, entry_odds, stake "
                    "FROM bet_log WHERE result = 'OPEN' AND match_id IS NOT NULL"
                ).fetchall()
                if _still_open:
                    print(f"[SETTLEMENT] Deep score lookup: {len(_still_open)} remaining OPEN bets")
                    from tools.score_lookup import lookup_score, _grade_bet, _parse_match_teams

                    _settled_deep = 0
                    _seen_matches = {}
                    for _bid, _mid, _mkt, _side, _odds, _stake in _still_open:
                        _teams = _parse_match_teams(_mid)
                        if not _teams:
                            continue
                        _mkey = f"{_teams[0]} vs {_teams[1]}"
                        # Cache lookups per match
                        if _mkey not in _seen_matches:
                            _seen_matches[_mkey] = lookup_score(_teams[0], _teams[1], use_browser=True)
                        _score = _seen_matches[_mkey]
                        if _score:
                            _hs, _as, _src = _score
                            _grade = _grade_bet(_mkt, _side or "", _hs, _as)
                            _stake_f = float(_stake) if _stake else 0.0
                            _odds_f = float(_odds) if _odds else 1.0
                            if _grade == "W":
                                _pnl = _stake_f * (_odds_f - 1)
                            elif _grade == "L":
                                _pnl = -_stake_f
                            else:
                                _pnl = 0.0
                                _grade = "VOID"
                            cur.execute(
                                "UPDATE bet_log SET result=?, pnl=? WHERE bet_id=?",
                                (_grade, _pnl, _bid)
                            )
                            print(f"[SETTLEMENT] DEEP-LOOKUP {_bid}: {_mkey} -> {_hs}-{_as} ({_src}) = {_grade} (PnL: {_pnl:+.2f})")
                            _settled_deep += 1
                            # Credit/debit bankroll
                            try:
                                from src.bankroll_tracker import register_settlement as _rs_deep
                                if _grade == "W":
                                    _rs_deep(payout=_stake_f * _odds_f, pnl=_pnl)
                                elif _grade == "L":
                                    _rs_deep(payout=0.0, pnl=_pnl)
                            except Exception:
                                pass
                    if _settled_deep:
                        conn.commit()
                        print(f"[SETTLEMENT] Deep lookup settled {_settled_deep} bets.")
                _deep_lookup_last_run = _now_deep
            except Exception as _dle:
                print(f"[SETTLEMENT] Deep score lookup failed: {_dle}")

        # VOID bets/parlays that are permanently stuck OPEN after match time.
        # This handles obscure leagues (Ethiopian, Georgian, Estonian, Swedish lower-div)
        # where no external result source has coverage.  Only fires when the bet is
        # genuinely past its window — not a race against a delayed result feed.
        _now_void = datetime.datetime.now(datetime.timezone.utc)

        # Individual bets: VOID prop-market bets whose kickoff was >48h ago with no result.
        # Score-settleable markets (1X2, O/U 2.5, BTTS) are given 7 days before VOID —
        # they should ALWAYS be settleable from score data, so a 48h window risked masking
        # genuine LOSSES as VOID when result scrapers were slow or had coverage gaps.
        # Prop markets (Player Shots, Corners, Cards) may never get stats → 48h is correct.
        _SCORE_MARKETS = {
            "1X2",
            "Over/Under 2.5",
            "BTTS",
            "Double Chance",
            "Draw No Bet",
            "Asian Handicap",
        }
        try:
            cur.execute(
                """
                SELECT b.bet_id, b.market_type, p.kickoff, b.stake
                FROM bet_log b
                LEFT JOIN predictions p ON p.fixture_id = CAST(b.fixture_id AS TEXT)
                WHERE b.result = 'OPEN'
                """
            )
            for _b_id, _b_mkt, _kick, _b_stake in cur.fetchall():
                if not _kick:
                    continue
                try:
                    _kick_dt = datetime.datetime.fromisoformat(
                        str(_kick).replace("Z", "+00:00")
                    ).astimezone(datetime.timezone.utc)
                    _elapsed_h = (_now_void - _kick_dt).total_seconds() / 3600
                    # Score markets: 7-day window (should always be settleable from scores)
                    # Prop markets: 48h window (stats may genuinely never arrive)
                    _void_threshold_h = 168 if (_b_mkt in _SCORE_MARKETS) else 48
                    if _elapsed_h > _void_threshold_h:
                        cur.execute(
                            "UPDATE bet_log SET result='VOID', pnl=0 WHERE bet_id=?",
                            (_b_id,),
                        )
                        print(
                            f"[SETTLEMENT] VOID {_b_id} ({_b_mkt}) — "
                            f"no result found {_elapsed_h:.0f}h past kickoff"
                        )
                        # Credit stake back to bankroll (void = full refund)
                        try:
                            from src.bankroll_tracker import (
                                register_settlement as _rs_void,
                            )

                            _rs_void(payout=float(_b_stake or 0), pnl=0.0)
                        except Exception:
                            pass
                except Exception:
                    pass
        except Exception as _ve:
            print(f"[SETTLEMENT] VOID pass failed: {_ve}")

        # Parlays: VOID any parlay still OPEN that is >7 days old.
        # These are typically old prop-market parlays (Player Shots) where
        # we will never obtain the required player stats.
        try:
            _void_cutoff = (_now_void - datetime.timedelta(days=7)).isoformat()
            cur.execute(
                "SELECT parlay_id, stake FROM parlay_log WHERE result='OPEN' AND placed_at < ?",
                (_void_cutoff,),
            )
            for _p_id, _p_stake in cur.fetchall():
                cur.execute(
                    "UPDATE parlay_log SET result='VOID', pnl=0 WHERE parlay_id=?",
                    (_p_id,),
                )
                print(
                    f"[SETTLEMENT] VOID parlay {_p_id} — open >7 days, no stats available"
                )
                try:
                    from src.bankroll_tracker import register_settlement as _rs_parlay

                    _rs_parlay(payout=float(_p_stake or 0), pnl=0.0)
                except Exception:
                    pass
        except Exception as _pe:
            print(f"[SETTLEMENT] Parlay VOID pass failed: {_pe}")

        conn.commit()
        conn.close()
    except Exception as e:
        print("Error during settlement:", e)


def update_dashboard_json(fixtures, results_cache):
    dashboard_data = []
    res_map = load_predictions_from_db()

    settings = load_settings()
    min_ev_threshold = settings.get("min_ev_threshold", 0.05)

    # Fetch Pinnacle O/U 2.5 totals once per cycle for the OU25 value check.
    # Keyed by "Home vs Away" (Pinnacle team names) with p_over/p_under/over/under.
    _pin_ou25_all = {}
    try:
        from src.pinnacle_feed import fetch_pinnacle_totals as _fpt_ou

        _pin_ou25_all = _fpt_ou(line=2.5) or {}
    except Exception as _ou_fetch_err:
        print(f"[OU25] Pinnacle totals fetch failed (non-fatal): {_ou_fetch_err}")

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
        _pinnacle_fallback_used = False
        odds_dict = find_betarabia_odds(home, away)
        # FALLBACK: When Betarabia has no odds for this fixture (common for WC
        # knockouts and minor leagues), use Pinnacle's own decimal odds from
        # sharp_odds_history. This enables the AI model paper bet path even
        # when the soft book doesn't list the match.
        if odds_dict is None:
            odds_dict = _pinnacle_fallback_odds(home, away)
        # Freshness guard: refuse to bet on STALE Betarabia odds (defence-in-depth so a
        # future scraper regression can never silently bet old prices). Age was set by
        # the find_betarabia_odds call just above for this exact fixture.
        _max_stale_min = load_settings().get("max_odds_staleness_min", 60)
        odds_fresh = (
            _betarabia_odds_age_min is None or _betarabia_odds_age_min <= _max_stale_min
        )

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
                prematch_markets = {
                    "1X2": [],
                    "Over/Under 2.5": [],
                    "Over/Under 3.0": [],
                    "Over/Under 2.0": [],
                    "BTTS": [],
                    "Double Chance": [],
                    "Draw No Bet": [],
                }
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

                # Over/Under 3.0
                for _dc_sel, _dc_key in (("Over 3.0", "Over"), ("Under 3.0", "Under")):
                    if _dc_key in odds_dict.get("Over/Under 3.0", {}):
                        prematch_markets["Over/Under 3.0"].append(
                            {
                                "selection": _dc_sel,
                                "odds": odds_dict["Over/Under 3.0"][_dc_key],
                            }
                        )

                # Over/Under 2.0
                for _dc_sel, _dc_key in (("Over 2.0", "Over"), ("Under 2.0", "Under")):
                    if _dc_key in odds_dict.get("Over/Under 2.0", {}):
                        prematch_markets["Over/Under 2.0"].append(
                            {
                                "selection": _dc_sel,
                                "odds": odds_dict["Over/Under 2.0"][_dc_key],
                            }
                        )

                # Double Chance
                for _sel in ("1X", "X2", "12"):
                    if _sel in odds_dict.get("Double Chance", {}):
                        prematch_markets["Double Chance"].append(
                            {
                                "selection": _sel,
                                "odds": odds_dict["Double Chance"][_sel],
                            }
                        )

                # Draw No Bet
                for _sel in ("Home", "Away"):
                    if _sel in odds_dict.get("Draw No Bet", {}):
                        prematch_markets["Draw No Bet"].append(
                            {"selection": _sel, "odds": odds_dict["Draw No Bet"][_sel]}
                        )

        if prediction and "markets" in prediction:
            # Always attach the real Betarabia price to each market selection so the
            # dashboard shows actual odds (not "@ 0.00"), even for estimated XI.
            # Paper/shadow mode: allow bets without lineup confirmation (Sofascore
            # is bot-blocked so lineups almost never arrive; gating on them kills
            # all model betting). Real-money path keeps its own hard gate in
            # execution_engine.py (SHADOW_MODE). Lineup quality is captured in
            # has_lineup field for post-analysis.
            bet_allowed = True
            if True:
                match_bet_candidates = []
                for m_type, selections in prediction["markets"].items():
                    for sel in selections:
                        sel_name = sel["selection"]
                        prob = sel["prob"]

                        # Determine Key for odds lookup
                        key = None
                        if m_type == "1X2":
                            if "Home" in sel_name or "1" in sel_name:
                                key = "Home"
                            elif "Draw" in sel_name or "X" in sel_name:
                                key = "Draw"
                            elif "Away" in sel_name or "2" in sel_name:
                                key = "Away"
                        elif m_type in (
                            "Over/Under 2.5",
                            "Over/Under 3.0",
                            "Over/Under 2.0",
                        ):
                            if "Over" in sel_name:
                                key = "Over"
                            elif "Under" in sel_name:
                                key = "Under"
                        elif m_type == "BTTS":
                            if "Yes" in sel_name:
                                key = "Yes"
                            elif "No" in sel_name:
                                key = "No"
                        elif m_type == "Double Chance":
                            if sel_name in ("1X", "X2", "12"):
                                key = sel_name
                        elif m_type == "Draw No Bet":
                            if "Home" in sel_name:
                                key = "Home"
                            elif "Away" in sel_name:
                                key = "Away"
                        elif m_type == "Corners":
                            key = (
                                sel_name  # "Corners OVER 9.5" must match scraper output
                            )
                        elif m_type == "Total Cards":
                            key = sel_name  # "Cards OVER 3.5" must match scraper output
                        elif m_type == "Goalscorer":
                            # sel_name = "Kylian Mbappe Anytime Goal" → extract player name
                            import re as _re

                            key = _re.sub(
                                r"\s+Anytime Goal$", "", sel_name, flags=_re.IGNORECASE
                            ).strip()
                        elif m_type == "Player Shots on Target":
                            key = sel_name

                        odds = None
                        all_market_odds = []
                        if odds_dict:
                            if m_type in odds_dict and key and key in odds_dict[m_type]:
                                odds = odds_dict[m_type][key]
                                all_market_odds = list(odds_dict[m_type].values())
                            elif (
                                m_type == "Goalscorer"
                                and key
                                and "Goalscorer" in odds_dict
                            ):
                                # Fuzzy match player name (e.g. "Mbappe" vs "Kylian Mbappe")
                                best_gscore, best_gprice = 0.0, None
                                for pname, pprice in odds_dict["Goalscorer"].items():
                                    gs = get_match_score(key, pname)
                                    if gs > best_gscore:
                                        best_gscore, best_gprice = gs, pprice
                                if best_gscore >= 0.5 and best_gprice is not None:
                                    odds = best_gprice
                                    all_market_odds = list(
                                        odds_dict["Goalscorer"].values()
                                    )

                        if odds is not None:
                            # Sniper / Peak Logic
                            try:
                                conn_sniper = sqlite3.connect(
                                    os.path.join(
                                        DATA_DIR,
                                        "deepfield_browser_data",
                                        "completed_fixtures.db",
                                    )
                                )
                                cur_sniper = conn_sniper.cursor()
                                cur_sniper.execute(
                                    "INSERT INTO odds_history (fixture_id, market, selection, odds) VALUES (?, ?, ?, ?)",
                                    (str(fid), m_type, sel_name, odds),
                                )
                                conn_sniper.commit()
                                cur_sniper.execute(
                                    "SELECT MAX(odds) FROM odds_history WHERE fixture_id = ? AND market = ? AND selection = ?",
                                    (str(fid), m_type, sel_name),
                                )
                                max_seen_odds = cur_sniper.fetchone()[0] or odds
                                conn_sniper.close()
                            except:
                                max_seen_odds = odds

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
                            if (
                                all_market_odds
                                and len(all_market_odds) >= 2
                                and odds
                                and odds > 0
                            ):
                                inv = [1.0 / o for o in all_market_odds if o and o > 0]
                                if inv:
                                    mkt_prob = (1.0 / odds) / sum(inv)
                            blend_w = settings.get("market_blend_weight", 0.5)
                            if blend_w < 1.0 and mkt_prob is not None:
                                prob_used = (
                                    blend_w * prob_used + (1.0 - blend_w) * mkt_prob
                                )

                            ev = prob_used * odds - 1.0
                            prob = round(
                                prob_used * 100.0, 1
                            )  # downstream gates use blended prob
                            is_at_peak = odds >= max_seen_odds * 0.98

                            # LINE SHOPPING: find best price across Pinnacle + The Odds API.
                            # EV stays on Betarabia (what we actually bet); best_odds / ev_best
                            # are display-only so the dashboard shows when to shop elsewhere.
                            if _ODDS_AGG and _get_best_price and m_type == "1X2":
                                try:
                                    _bbo = odds_dict.get("1X2", {})
                                    _bp = _get_best_price(
                                        home,
                                        away,
                                        betarabia_h=_bbo.get("Home"),
                                        betarabia_d=_bbo.get("Draw"),
                                        betarabia_a=_bbo.get("Away"),
                                    )
                                    _sel_key = {
                                        "Home": "home",
                                        "Draw": "draw",
                                        "Away": "away",
                                    }.get(sel_name)
                                    _best_o = (
                                        _bp.get(_sel_key, odds) if _sel_key else odds
                                    )
                                    sel["best_odds"] = (
                                        round(_best_o, 3) if _best_o else odds
                                    )
                                    sel["ev_best"] = (
                                        round(prob_used * _best_o - 1.0, 4)
                                        if _best_o
                                        else ev
                                    )
                                    sel["pinnacle_odds"] = _bp.get(
                                        f"pinnacle_{_sel_key}"
                                    )
                                    sel["line_shop_gain"] = (
                                        round((_best_o - odds) / odds * 100, 1)
                                        if odds and _best_o
                                        else 0.0
                                    )
                                    # ARB / NEAR-ARB detection (display-only, no actual bets)
                                    if _ARB_OK and _check_arb and m_type == "1X2":
                                        try:
                                            _pinn_raw = {
                                                "home": _bp.get("pinnacle_home"),
                                                "draw": _bp.get("pinnacle_draw"),
                                                "away": _bp.get("pinnacle_away"),
                                            }
                                            _best_all = {
                                                "home": _bp.get("home"),
                                                "draw": _bp.get("draw"),
                                                "away": _bp.get("away"),
                                            }
                                            _arb = _check_arb(
                                                _best_all,
                                                (
                                                    _pinn_raw
                                                    if any(_pinn_raw.values())
                                                    else None
                                                ),
                                            )
                                            if _arb["status"] != "NORMAL":
                                                sel["arb_status"] = _arb["status"]
                                                sel["arb_return_pct"] = _arb.get(
                                                    "arb_return_pct", 0.0
                                                )
                                                sel["near_arb"] = _arb.get(
                                                    "near_arb", []
                                                )
                                        except Exception:
                                            pass
                                except Exception:
                                    pass

                            # CONVICTION CAP (tools/backtest_1x2_lines.py finding): the model's
                            # BIGGEST disagreements with the market are where it is most WRONG —
                            # raising the edge bar made out-of-sample ROI worse, not better. So
                            # bet only MODEST, market-adjacent value and skip "too good to be
                            # true" gaps (model error). edge = blended prob - market prob.
                            edge_cap_pct = settings.get("edge_cap_pct", 10.0)
                            model_edge_pct = (
                                ((prob_used - mkt_prob) * 100.0)
                                if mkt_prob is not None
                                else 0.0
                            )
                            # Block when market prob can't be computed — no benchmark means
                            # we can't measure real edge; this is how 86%+ "edge" slips through.
                            conviction_ok = (mkt_prob is not None) and (
                                model_edge_pct <= edge_cap_pct
                            )

                            # Confidence threshold — fixed, no value-chaser discount.
                            # Dropping to 30% at high EV selected exactly the unknown-league
                            # heuristic bets (fake 40-140% EV) that caused all the losses.
                            conf_threshold = settings.get("min_confidence_pct", 55)

                            # MARKET WHITELIST: only bet markets with a proven edge. The
                            # realized record shows ONLY 1X2 is +EV; all props lose 40-80%.
                            # Configurable via settings["allowed_markets"] (default 1X2 only).
                            allowed_markets = settings.get("allowed_markets", ["1X2"])
                            market_allowed = (not allowed_markets) or (
                                m_type in allowed_markets
                            )

                            # LEAGUE BLOCKLIST: skip competitions that have shown no edge
                            # (populate from tools/league_report.py once CLV/ROI data exists).
                            league_blocked = league in (
                                settings.get("league_blocklist") or []
                            )

                            # Draw exclusion: configurable via settings["exclude_draws"].
                            # Defaults to False — all three 1X2 outcomes are evaluated.
                            exclude_draws = settings.get("exclude_draws", False)
                            draw_excluded = exclude_draws and (
                                m_type == "1X2" and key == "Draw"
                            )

                            # STEAM signal (line movement) — validated as genuinely
                            # predictive (tools/backtest_market_signals.py), unlike the
                            # model. Detect the de-vigged move toward this selection from
                            # the odds_history ledger, capture fired picks to the research
                            # ledger, and (opt-in) use it to confirm model picks. 1X2 only.
                            steam_min = settings.get("steam_min_move_pct", 3.0) / 100.0
                            _steam_result = (
                                _steam_moves(fid, m_type) if market_allowed else {}
                            )
                            steam_move = _steam_result.get(sel_name, 0.0)
                            _steam_meta_sel = (_steam_result.get("__meta__") or {}).get(
                                sel_name, {}
                            )
                            steam_mono = _steam_meta_sel.get("monotonicity", None)
                            sel["steam_move"] = round(steam_move * 100.0, 2)
                            _registry = _load_signal_registry()
                            # League whitelist: only fire STEAM on liquid markets where
                            # the backtested edge was demonstrated. Obscure leagues
                            # (Reserve League, USL League Two, 4. deild, Australian NPL, etc.)
                            # show noise-driven moves with no real edge.
                            # EXACT match only — substring matching caused "Queensland Premier
                            # League" to pass as "premier league" (catastrophic false positive).
                            _steam_wl = settings.get("steam_league_whitelist", [])
                            _league_lower = (league or "").lower().strip()
                            _steam_wl_set = {w.lower().strip() for w in _steam_wl}
                            # Normalize league name (strip "England - " etc.) for matching
                            from src.pinnacle_value_engine import (
                                normalize_league as _norm_league,
                            )

                            _league_normalized = _norm_league(league or "")
                            # P0 FIX: Country-aware league resolution.
                            # "Premier League" from Kazakhstan/Kuwait/Iceland must NOT pass
                            # as English PL. resolve_league_country() checks team names
                            # against known country indicators and blocks cross-country collisions.
                            _league_resolution = {}
                            if _pv_resolve_league:
                                try:
                                    _league_resolution = _pv_resolve_league(
                                        league or "", home, away
                                    )
                                except Exception:
                                    pass
                            _league_country_valid = _league_resolution.get(
                                "is_valid", True
                            )
                            _steam_league_ok = (
                                not _steam_wl
                                or _league_lower in _steam_wl_set
                                or _league_normalized in _steam_wl_set
                            ) and _league_country_valid
                            if not _league_country_valid and _league_resolution:
                                _detected = _league_resolution.get("country", "unknown")
                                print(
                                    f"[LEAGUE FILTER] Blocked '{league}' for {home} vs {away} "
                                    f"(detected country: {_detected}, not liquid)"
                                )
                            steam_fired = (
                                steam_move >= steam_min
                                and odds
                                and odds >= dfp_settings.MODEL_MIN_ODDS
                                and market_allowed
                                and not league_blocked
                                and not draw_excluded
                                and odds_fresh
                                and _steam_league_ok
                                and _registry.get("STEAM_FWD", {}).get("enabled", True)
                            )
                            if steam_fired:
                                _record_steam_signal(
                                    fid,
                                    league,
                                    f"{home} vs {away}",
                                    m_type,
                                    sel_name,
                                    odds,
                                    steam_move,
                                    match_time,
                                    monotonicity=steam_mono,
                                )
                                # Flat-stake shadow bet for the steam signal (separate
                                # strategy from the model; paper only; deduped internally).
                                log_steam_bet(
                                    f"{home} vs {away}",
                                    m_type,
                                    sel_name,
                                    odds,
                                    steam_move * 100.0,
                                    fid,
                                    league,
                                    monotonicity=steam_mono,
                                )
                                try:
                                    from src.services.alerting import notifier as _ntfy

                                    _nation = _nation_from_league(league or "")
                                    if "(1)" in sel_name or "home" in sel_name.lower():
                                        _pick = f"{home} to win"
                                    elif (
                                        "(2)" in sel_name or "away" in sel_name.lower()
                                    ):
                                        _pick = f"{away} to win"
                                    else:
                                        _pick = sel_name
                                    _ntfy._notify(
                                        f"Bet {_pick}\n"
                                        f"{home} vs {away}\n"
                                        f"{league} · {_nation}\n"
                                        f"@ {odds:.2f}",
                                        title="STEAM Signal",
                                        priority="high",
                                        tags="soccer,chart_with_upwards_trend",
                                    )
                                except Exception:
                                    pass
                            # Opt-in: require the market to be moving toward a model pick.
                            require_steam = settings.get("require_steam_confirm", False)
                            steam_ok = (not require_steam) or (steam_move >= steam_min)

                            # PINNACLE VALUE: compare Betarabia live price to de-vigged
                            # Pinnacle fair price from sharp_odds_history. Edge > 0 means
                            # Betarabia is more generous than Pinnacle's implied probability.
                            # CLV is guaranteed positive when this fires (we're buying below
                            # the sharp consensus price). Annotated on every selection for
                            # the dashboard; fires a separate PINNACLE_VALUE bet when enabled.
                            _pin_min_edge = (
                                settings.get("pinnacle_min_edge_pct", 3.0) / 100.0
                            )
                            _pin_edge, _pin_data = 0.0, None
                            if (
                                m_type == "1X2"
                                and market_allowed
                                and not draw_excluded
                                and odds
                                and odds > 1.0
                            ):
                                try:
                                    from tools.pinnacle_value import (
                                        check_value as _pv_check,
                                    )

                                    _pin_edge, _pin_data = _pv_check(
                                        home,
                                        away,
                                        sel_name,
                                        odds,
                                        kickoff_ts=match_time,
                                        min_edge=_pin_min_edge,
                                        min_snapshots=settings.get("pinnacle_min_snapshots", 10),
                                    )
                                except Exception:
                                    pass
                            elif (
                                m_type == "Over/Under 2.5"
                                and market_allowed
                                and odds
                                and odds > 1.0
                            ):
                                try:
                                    from tools.pinnacle_value import (
                                        _fuzzy_match_ou25 as _pv_fuzzy,
                                        check_ou25_value as _pv_ou25_check,
                                    )

                                    # Exact match first; fall back to fuzzy (handles
                                    # "Manchester City" vs "Man City" etc.)
                                    _pin_ou25 = _pin_ou25_all.get(f"{home} vs {away}")
                                    if _pin_ou25 is None:
                                        _pin_ou25 = _pv_fuzzy(home, away, _pin_ou25_all)
                                    if _pin_ou25:
                                        _pin_edge, _pin_data = _pv_ou25_check(
                                            home,
                                            away,
                                            sel_name,
                                            odds,
                                            _pin_ou25,
                                            min_edge=_pin_min_edge,
                                        )
                                except Exception:
                                    pass
                            sel["pinnacle_edge"] = round(_pin_edge * 100.0, 2)

                            # PINNACLE STEAM: detect sharp-money line movement in
                            # sharp_odds_history (updated every 120s by pinnacle_feed).
                            # Betarabia STEAM = soft-book noise. Pinnacle STEAM = real sharp
                            # money. When both fire together = highest-confidence signal.
                            _pin_steam_sel, _pin_steam_move, _pin_steam_meta = (
                                None,
                                0.0,
                                {},
                            )
                            _pin_steam_min = settings.get(
                                "pinnacle_steam_min_move_pct", 2.0
                            )
                            if m_type == "1X2" and market_allowed and not draw_excluded:
                                try:
                                    from tools.pinnacle_steam import (
                                        check_pinnacle_steam as _cps,
                                        get_max_pinnacle_move as _gmp,
                                    )

                                    _ps_fired, _pin_steam_sel, _pin_steam_move = _cps(
                                        home,
                                        away,
                                        min_move_pct=_pin_steam_min,
                                        window_hours=6.0,
                                    )
                                    # Annotate the specific selection's move
                                    _gmp_sel, _gmp_pct, _gmp_meta = _gmp(
                                        home, away, window_hours=6.0
                                    )
                                    _pin_steam_meta = _gmp_meta
                                except Exception:
                                    pass

                            # Annotate on selection dict for dashboard display
                            sel["pinnacle_steam"] = round(_pin_steam_move, 2)
                            sel["pinnacle_steam_sel"] = _pin_steam_sel

                            # SHARP_STEAM: combined signal — Betarabia STEAM ≥ threshold
                            # AND Pinnacle is ALSO moving toward the same team.
                            # Fires a separate SHARP_STEAM bet (higher conviction than STEAM alone).
                            # Map daemon sel_name ("Home (1)") -> pinnacle key ("home")
                            _sel_pin_key = (
                                "home"
                                if "home" in sel_name.lower()
                                or sel_name in ("1", "Home (1)")
                                else (
                                    "away"
                                    if "away" in sel_name.lower()
                                    or sel_name in ("2", "Away (2)")
                                    else "draw"
                                )
                            )
                            _pin_steam_fired = (
                                _pin_steam_move >= _pin_steam_min
                                and _pin_steam_sel == _sel_pin_key
                            )
                            _sharp_steam_fired = (
                                steam_fired
                                and _pin_steam_fired
                                and settings.get("sharp_steam_betting_enabled", True)
                                and _steam_league_ok
                            )
                            if _sharp_steam_fired:
                                # Log as SHARP_STEAM — both Betarabia AND Pinnacle are
                                # moving toward the same side (highest-conviction signal).
                                # Use bet_source="SHARP_STEAM" so P&L can be tracked
                                # separately from plain STEAM bets in the ledger.
                                try:
                                    log_steam_bet(
                                        f"{home} vs {away}",
                                        m_type,
                                        sel_name,
                                        odds,
                                        steam_move * 100.0,
                                        fid,
                                        league,
                                        monotonicity=steam_mono,
                                        bet_source="SHARP_STEAM",
                                    )
                                except Exception:
                                    pass

                            # STANDALONE PINNACLE STEAM: bet when Pinnacle moves >= threshold
                            # even when Betarabia hasn't moved (which is almost always — Betarabia
                            # is a static soft book). This is the main high-volume bet path.
                            # Requires Betarabia to have a current price (odds is not None here)
                            # so the bet has a real price to record.
                            _pin_steam_max_odds = settings.get(
                                "pinnacle_steam_max_odds", 10.0
                            )
                            if (
                                _pin_steam_fired
                                and _pin_steam_sel == _sel_pin_key
                                and not draw_excluded
                                and odds
                                and odds >= dfp_settings.MODEL_MIN_ODDS
                                and odds
                                <= _pin_steam_max_odds  # no extreme longshots (e.g. 23.0)
                                and odds_fresh
                                and _steam_league_ok
                                and settings.get("pinnacle_steam_betting_enabled", True)
                            ):
                                try:
                                    log_steam_bet(
                                        f"{home} vs {away}",
                                        m_type,
                                        sel_name,
                                        odds,
                                        _pin_steam_move,  # already in pp units from check_pinnacle_steam
                                        fid,
                                        league,
                                        bet_source="PINNACLE_STEAM",
                                    )
                                except Exception as _pse:
                                    print(f"[PINNACLE_STEAM] bet error: {_pse}")

                            # Optional: require Pinnacle to confirm value before STEAM bets.
                            _require_pin_confirm = settings.get(
                                "require_pinnacle_confirm", False
                            )
                            if _require_pin_confirm and steam_fired and _pin_edge <= 0:
                                steam_fired = False  # Pinnacle doesn't agree — skip

                            # PINNACLE VALUE bet — Pinnacle is the quality filter itself;
                            # no league whitelist needed (if Pinnacle has no odds, edge=0 anyway).
                            _pv_league_ok = _league_country_valid

                            # P7 FIX: Optimal bet timing filter.
                            # Only bet during the optimal window (2-12h after Pinnacle opens).
                            _timing_ok = True
                            if settings.get("bet_timing_enabled", True):
                                try:
                                    from src.bet_timing import is_good_time_to_bet
                                    _timing_ok = is_good_time_to_bet(
                                        fixture_id=fid,
                                        kickoff_time=match_time,
                                        home=home,
                                        away=away,
                                        min_score=50,
                                    )
                                except Exception:
                                    _timing_ok = True  # fail-open

                            if (
                                _pin_edge > 0
                                and not _pinnacle_fallback_used  # skip when odds are from Pinnacle itself
                                and odds
                                and odds >= dfp_settings.MODEL_MIN_ODDS
                                and market_allowed
                                and not league_blocked
                                and not draw_excluded
                                and odds_fresh
                                and _pv_league_ok
                                and _timing_ok
                            ):
                                log_pinnacle_value_bet(
                                    f"{home} vs {away}",
                                    m_type,
                                    sel_name,
                                    odds,
                                    _pin_edge * 100.0,
                                    fixture_id=fid,
                                    league=league,
                                    pinnacle_data=_pin_data,
                                )

                            require_dc = settings.get("require_dc_coverage", True)
                            dc_covered = (prediction or {}).get("dc_covered", False)

                            # Draw-specific guard: model draw probabilities are poorly
                            # calibrated (overconfident long-tail). For AI-path draws,
                            # require Pinnacle to also price this as value (_pin_edge > 0)
                            # before recommending. This keeps draw bets to situations where
                            # the sharp market independently agrees, not just the model.
                            _is_draw = m_type == "1X2" and key == "Draw"
                            _draw_pin_ok = (not _is_draw) or (_pin_edge > 0)

                            is_recommended = (
                                ev >= min_ev_threshold
                                and prob >= conf_threshold
                                and odds >= dfp_settings.MODEL_MIN_ODDS
                                and market_allowed
                                and not league_blocked
                                and not draw_excluded
                                and conviction_ok
                                and steam_ok
                                and odds_fresh
                                and (not require_dc or dc_covered)
                                and (not require_steam or _steam_league_ok)
                                and _draw_pin_ok
                            )

                            # ASIAN HANDICAP paper bet gate (opt-in; off by default)
                            # AH -0.5 = home must WIN outright. AH +0.5 = home must not LOSE.
                            # Probs come directly from DC/LightGBM 1X2; no separate model needed.
                            if (
                                settings.get("ah_betting_enabled", False)
                                and m_type == "Asian Handicap"
                                and not league_blocked
                                and odds
                                and odds_fresh
                                and odds >= dfp_settings.MODEL_MIN_ODDS
                            ):
                                _ah_sel = sel_name  # e.g. "Arsenal -0.5"
                                _ah_prob = prob_used  # already set from the iteration over selections
                                _min_ev = settings.get("min_ev_threshold", 0.03)
                                _ah_ev = _ah_prob * odds - 1.0
                                if _ah_ev >= _min_ev and _ah_prob >= 0.50:
                                    log_ai_bet(
                                        f"{home} vs {away}",
                                        "Asian Handicap",
                                        _ah_sel,
                                        odds,
                                        _ah_ev,
                                        _ah_prob * 100,
                                        fid,
                                        league,
                                        source="AI_AH",
                                    )

                            sel.update(
                                {
                                    "odds": odds,
                                    "max_seen_odds": max_seen_odds,
                                    "ev": ev,
                                    "m_type": m_type,
                                    "all_odds": all_market_odds,
                                }
                            )
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
                            all_outcome_odds=all_odds,  # Pass all odds for proper vig stripping
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
                            expected_mean=expected_mean,
                        )
                        if bet_id:
                            print(
                                f"[DAEMON] VALUE BET placed: {m_type} | {sel_name} @ {odds} (EV: {ev*100:.1f}%)"
                            )
                    except Exception as e:
                        print(f"[ERROR] Failed to place best bet: {e}")

                    log_ai_bet(
                        f"{home} vs {away}",
                        m_type,
                        sel_name,
                        odds,
                        prob,
                        ev,
                        fid,
                        league,
                    )

                    # Arena autopilot handles real-bet notifications (one push per placed order)

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

            # Map normalised name → index so we can update existing cards in-place.
            existing = {
                _nm(d.get("match", "")): i for i, d in enumerate(dashboard_data)
            }
            added = 0
            updated = 0
            for lm in get_live_matches():
                key = _nm(lm["match"])
                if key not in existing:
                    dashboard_data.append(lm)
                    existing[key] = len(dashboard_data) - 1
                    added += 1
                else:
                    # Patch live score + status onto the existing prediction card so
                    # the score refreshes automatically when a pre-match card goes live.
                    d = dashboard_data[existing[key]]
                    if not d.get("fixture"):
                        d["fixture"] = {}
                    lf = lm.get("fixture", {})
                    d["fixture"]["home_score"] = lf.get("home_score")
                    d["fixture"]["away_score"] = lf.get("away_score")
                    if lm.get("status_code"):
                        d["status_code"] = lm["status_code"]
                    updated += 1
            if added or updated:
                print(f"[LIVE] {added} new, {updated} score-updated in-play match(es).")
        except Exception as e:
            print("[LIVE] inject failed:", e)

    # Atomic write: write to temp file then rename so readers never see a partial file
    _state_path = os.path.join(DATA_DIR, "todays_dashboard_state.json")
    _state_tmp = _state_path + ".tmp"
    with open(_state_tmp, "w", encoding="utf-8") as f:
        json.dump(dashboard_data, f, indent=4)
    os.replace(_state_tmp, _state_path)

    # Notifications handled by Arena autopilot (one push per placed bet, not per cycle)


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
                                    "home_score": e.get("homeScore", {}).get(
                                        "normaltime",
                                        e.get("homeScore", {}).get("current"),
                                    ),
                                    "away_score": e.get("awayScore", {}).get(
                                        "normaltime",
                                        e.get("awayScore", {}).get("current"),
                                    ),
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
    (.env is NOT loaded into os.environ at daemon-thread startup, so env alone is empty.)
    """
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
    _init_signal_registry()
    init_stair_ai_agent()

    # Heal exposure drift from any crashed/incomplete previous session
    try:
        from src.bankroll_tracker import reconcile_exposure
        reconcile_exposure()
    except Exception as _re_err:
        print(f"[BANKROLL] reconcile_exposure failed at startup: {_re_err}")

    # Initialize new DeepFieldPro institutional modules
    initialize_deepfield_modules()

    try:
        player_model = joblib.load(os.path.join(MODELS_DIR, "player_impact_model.pkl"))
    except Exception as e:
        print(
            f"[!] Failed to load player_impact_model.pkl: {e}. Continuing without it."
        )
        player_model = None
    try:
        match_model = joblib.load(os.path.join(MODELS_DIR, "bottom_up_match_model.pkl"))
    except Exception as e:
        print(
            f"[!] Failed to load bottom_up_match_model.pkl: {e}. Continuing without it."
        )
        match_model = None
    df = load_player_database()
    initialize_caches(df)

    # Start background telemetry threads FIRST (independent of settlement, which
    # can be slow) so they begin accumulating data immediately on startup:
    #  - closing-line capture: true pre-kickoff prices for open bets (honest CLV)
    #  - Pinnacle feed: live sharp odds every 120s → sharp_odds_history (CLV + value)
    start_closing_capture()
    try:
        from src.pinnacle_feed import start_feed_thread as _start_pf

        _start_pf()
        print("[*] Pinnacle live feed thread started (120s interval).")
    except Exception as _pf_err:
        print(f"[!] Pinnacle feed thread failed to start: {_pf_err}")

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
                print(
                    "[SCRAPER] Previous Betarabia scrape still running; skipping (no stacking)."
                )
            else:
                # Reap finished/crashed process before spawning a new one
                if _scraper_proc is not None:
                    rc = _scraper_proc.poll()
                    if rc is not None and rc != 0:
                        print(
                            f"[SCRAPER] Previous scrape exited with code {rc} — restarting."
                        )
                    try:
                        _scraper_proc.wait(timeout=1)
                    except Exception:
                        pass
                scraper_path = os.path.join(
                    os.path.dirname(__file__), "betarabia_scraper.py"
                )
                _scraper_proc = subprocess.Popen(
                    [sys.executable, scraper_path], close_fds=True
                )
                print("[SCRAPER] Launched fresh Betarabia scrape.")
        except Exception as e:
            print("Failed to start background scraper:", e)

        # Bound odds_history growth once per cycle (keeps steam/CLV queries fast).
        _purge_odds_history()

        # Inject upcoming WC fixtures from Pinnacle so STEAM detection starts early.
        try:
            from tools.wc_upcoming_scraper import inject_wc_upcoming as _wc_inject
            _wc_inject(days_ahead=7, verbose=False)
        except Exception as _wc_err:
            print(f"[WC SCRAPER] Failed: {_wc_err}")

        # 2. Run post-match settlement and reality data completion
        refresh_completed_comparisons()
        time.sleep(5)
        settle_open_bets()
        time.sleep(5)

        # 3. Daily tipster scrape — runs once per calendar day (guard inside)
        try:
            from src.tipster_scraper import run_tipster_cycle
            run_tipster_cycle()
        except Exception as _ts_err:
            print(f"[TIPSTER] cycle failed: {_ts_err}")

        # Load existing predictions from DB
        db_preds = load_predictions_from_db()

        now_utc = datetime.datetime.now(datetime.timezone.utc)
        print(
            f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Scanning fixtures for predictions..."
        )
        fixtures = get_todays_fixtures()
        if not fixtures:
            # Fallback to Betarabia matches
            print(
                "[!] Sofascore fixtures empty! Falling back to Betarabia dummy fixtures..."
            )
            try:
                import hashlib

                b_odds, _ = fetch_betarabia_odds()
                for b_name, b_info in b_odds.items():
                    if " vs " in b_name:
                        h, a = b_name.split(" vs ", 1)
                        fid = (
                            int(hashlib.md5(b_name.encode()).hexdigest(), 16)
                            % 100000000
                        )
                        info = b_info or {}
                        fixtures.append(
                            {
                                "fixture": {
                                    "id": fid,
                                    "date": info.get("kickoff") or now_utc.isoformat(),
                                    "status": {"short": info.get("status") or "NS"},
                                },
                                "teams": {"home": {"name": h}, "away": {"name": a}},
                                "league": {"name": info.get("league") or "Betarabia"},
                            }
                        )
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

        # Pre-fetch Pinnacle 1X2 data once per loop so every predict_match()
        # call gets real market probs for LightGBM (top features: mkt_d_prob,
        # mkt_a_prob). Without this they defaulted to 1/3 — ignoring the market.
        _pinn_data = {}
        if _ODDS_AGG and _get_pinnacle_probs:
            try:
                from src.pinnacle_feed import fetch_pinnacle_1x2 as _fp

                _pinn_data = _fp()
            except Exception:
                pass

        def _mkt_probs_for(home_name, away_name):
            """Look up de-vigged Pinnacle probs for a fixture (None if not found)."""
            if not _ODDS_AGG or not _get_pinnacle_probs:
                return None
            return _get_pinnacle_probs(home_name, away_name)

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

            _h_name = f["teams"]["home"]["name"]
            _a_name = f["teams"]["away"]["name"]
            _mkt_p = _mkt_probs_for(_h_name, _a_name)

            # Lineups window check
            if 0 < time_to_kickoff <= 45:
                lineups = batch_lineups.get(fid, [])
                if len(lineups) == 2 and len(lineups[0].get("startXI", [])) == 11:
                    print(f"[!] Official lineup confirmed for: {_h_name} vs {_a_name}!")
                    res = predict_match(
                        f, lineups, player_model, match_model, df, mkt_probs=_mkt_p
                    )
                    log_prediction_to_db(res, has_lineup=True)
                    new_lineup_found = True
                else:
                    # Lineups not posted or error
                    # Fallback to estimated prediction if not already in DB
                    if fid not in db_preds:
                        print(
                            f"    -> Generating estimated prediction for T-45m match: {_h_name} vs {_a_name}"
                        )
                        home_xi = get_predicted_lineup(_h_name, df)
                        away_xi = get_predicted_lineup(_a_name, df)
                        est_lineups = [{"startXI": home_xi}, {"startXI": away_xi}]
                        res = predict_match(
                            f,
                            est_lineups,
                            player_model,
                            match_model,
                            df,
                            mkt_probs=_mkt_p,
                        )
                        log_prediction_to_db(res, has_lineup=False)
            elif time_to_kickoff > 45:
                # Kickoff is further away, generate estimated prediction if not already in DB
                if fid not in db_preds:
                    print(
                        f"    -> Generating estimated prediction for upcoming match: {_h_name} vs {_a_name}"
                    )
                    home_xi = get_predicted_lineup(_h_name, df)
                    away_xi = get_predicted_lineup(_a_name, df)
                    est_lineups = [{"startXI": home_xi}, {"startXI": away_xi}]
                    res = predict_match(
                        f, est_lineups, player_model, match_model, df, mkt_probs=_mkt_p
                    )
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
                if not os.path.exists(
                    os.path.join(DATA_DIR, f"audit_{now.date()}.done")
                ):
                    run_daily_audit()
                    with open(
                        os.path.join(DATA_DIR, f"audit_{now.date()}.done"), "w"
                    ) as f:
                        f.write("done")

            # Weekly CLV Report & Diagnostics (Run on Sundays at 23:50)
            if now.weekday() == 6 and now.hour == 23 and now.minute >= 50:
                clv_report_file = os.path.join(
                    DATA_DIR, f"clv_weekly_{now.date()}.done"
                )
                if not os.path.exists(clv_report_file):
                    try:
                        from src.clv_tracker_v2 import generate_weekly_report
                        from src.diagnostics import run_diagnostics
                        from src.shadow_framework import get_shadow_status

                        report = generate_weekly_report()
                        diag = run_diagnostics()
                        shadow = get_shadow_status()

                        print(
                            f"[CLV WEEKLY REPORT] Bets: {report.get('total_bets', 0)}, "
                            f"Avg CLV: {report.get('avg_clv_pct', 0):.2f}%, "
                            f"ROI: {report.get('roi_pct', 0):.2f}%"
                        )
                        print(
                            f"[DIAGNOSTICS] Disabled markets: {len(diag.get('disabled_markets', []))}, "
                            f"leagues: {len(diag.get('disabled_leagues', []))}"
                        )
                        print(
                            f"[SHADOW] Ready for real money: {shadow.get('ready', False)}, "
                            f"Paper bets: {shadow.get('paper_bets', 0)}/500"
                        )

                        with open(clv_report_file, "w") as f:
                            f.write("done")
                    except Exception as clv_err:
                        print(f"[CLV REPORT ERROR] {clv_err}")

        except Exception as e:
            print(f"[MONITORING ERROR] {e}")

        # 4. Crowd paper bets — DISABLED (floods bet_log with all-outcome batches)
        # Re-enable only for deliberate research runs via crowd_bets_scraper directly.

        print("[*] Sweep complete. Dashboard state updated. Sleeping for 3 minutes...")

        # Wait 3 minutes (180s) before the next sweep
        time.sleep(180)


if __name__ == "__main__":
    run_daemon()
