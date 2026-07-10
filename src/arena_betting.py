"""
arena_betting.py — StairAI World-Cup Arena betting page (Flask blueprint).
============================================================================
Fetches upcoming World Cup 2026 fixtures from the Stair AI arena, compares our
DeepFieldPro (Dixon-Coles) 1X2 probability to the live Polymarket midpoint, and
bets ONLY on high-EV outcomes the model is confident in.

Model priority:
  1. DeepFieldPro Dixon-Coles calibrated probs (read from todays_dashboard_state.json)
     — these are the SAME probs the paper Betarabia bets use, so the Arena mirrors
       the paper strategy on real money.
  2. Sportmonks 1X2 predictions (fallback for WC fixtures our system hasn't predicted)

Decision rule (a pick qualifies only if BOTH hold for one outcome):
    model_prob >= CONF_MIN           ("the AI is sure it will win")
    model_prob - market_mid >= EDGE_MIN   ("high EV" / underpriced by the market)

Sizing: quarter-Kelly based on actual wallet balance (scales with the real bankroll).

REAL MONEY: orders spend USDC from the arena wallet. Placement only happens on a
POST to /arena/api/place with {"confirm": true}. The GET /arena/api/analyze route
is read-only. Hard safeguards: per-order cap, wallet buffer, max bets per run.

API (production): base https://stair-ai.com, auth header x-api-key.
"""

import os
import json
import time
import uuid
import threading

import requests
from flask import Blueprint, jsonify, render_template, request

from src import execution_analytics as _exec_analytics
from src import adaptive_kelly as _adaptive_kelly
from src.calibration_metrics import expected_calibration_error as _expected_calibration_error
from src.attribution_engine import settlement_map as _settlement_map

# ---------------------------------------------------------------------------
# AP2 commerce layer — secondary safety gate + audit ledger
# ---------------------------------------------------------------------------
try:
    import sys as _ap2sys
    import os as _ap2os

    _ap2sys.path.insert(0, _ap2os.path.join(_ap2os.path.dirname(__file__), ".."))
    from src.ap2_mandate import SpendingMandate as _Mandate, DEFAULT_MANDATE as _MANDATE
    from src.ap2_ledger import (
        init_ledger as _init_ledger,
        log_intent as _log_intent,
        log_result as _log_result,
        get_daily_spent as _get_daily_spent,
    )

    _init_ledger()
    _AP2 = True
except Exception as _ap2_exc:
    _AP2 = False

# Thread-local context: callers set _ap2_ctx before place_order() so the
# ledger can record model_prob / mid / edge / wallet_balance without
# changing the public place_order signature.
_ap2_tls = threading.local()


def _ap2_set_ctx(model_prob=0.0, mid=0.0, edge=0.0, wallet_balance=999.0):
    """Set AP2 order context for the current thread before calling place_order()."""
    _ap2_tls.ctx = {
        "model_prob": float(model_prob),
        "mid": float(mid),
        "edge": float(edge),
        "wallet_balance": float(wallet_balance),
    }


def _ap2_get_ctx():
    return getattr(
        _ap2_tls,
        "ctx",
        {
            "model_prob": 1.0,
            "mid": 0.0,
            "edge": 1.0,
            "wallet_balance": 999.0,
        },
    )


ARENA = "https://stair-ai.com"
SEASON_ID = 26618  # World Cup 2026 (Sportmonks)
PRED_TYPE_1X2 = 237  # Sportmonks fulltime-result prediction type

# ---- Risk defaults (overridable per request) -------------------------------
# Tightened 2026-07-10 back to the validated 2026-07-05 regime after the
# "TOURNAMENT MODE" drift (conf 0.0 / edge -1.0 / $100 per order / $999 daily /
# $0.25 buffer / full-wallet fraction) left the ARMED autopilot with no dollar
# ceiling below the whole wallet and a -$226 unrealized book on $113 available.
# tests/test_arena_risk_caps.py pins every value below — loosen them only
# together with that file, deliberately.
CONF_MIN_DEFAULT = 0.50   # no bets below 50% model confidence
EDGE_MIN_DEFAULT = 0.05   # require >= 5pp edge vs the Polymarket mid
MAX_USD_PER_BET = 10.00   # hard per-order cap
MIN_USD_PER_BET = 1.00    # arena minimum per order (Stair AI hard floor)
AP2_MAX_PER_ORDER = 10.00  # matches MAX_USD_PER_BET
MAX_FAIL_RETRIES = 3  # QF markets link late + transient unfilled orders deserve retries
WALLET_BUFFER = 10.00     # the last $10 of the wallet is untouchable
MAX_BETS_PER_RUN = 3      # a cycle may open at most 3 new positions
LIMIT_BUFFER = 0.02       # 2¢ above mid to help fill
TIF_SECONDS = 30          # limit order expires if unfilled

# DFP flat-heuristic filter
DFP_USEFUL_THRESHOLD = 0.10  # accept any model signal
DFP_MAX_RATIO = 99.0          # no sanity cap
WC_MODEL_WEIGHT = 0.65       # weight for WC Elo model when blending with Sportmonks/DFP

# Max fraction of wallet per single bet
MAX_WALLET_FRACTION = 0.10    # a single pick may risk at most 10% of the wallet

# Default drawdown tiers used when data/settings.json has no arena_drawdown_tiers key.
# Mirrors the Phase-1 spec table: (drawdown_pct, kelly_multiplier, disable_directional).
# "Never disable arbitrage" is enforced separately by callers checking c["real_arb"] —
# disable_directional here only ever gates non-arb picks.
_DEFAULT_DRAWDOWN_TIERS = [
    {"drawdown_pct": 0.40, "kelly_multiplier": 0.0, "disable_directional": True},
    {"drawdown_pct": 0.30, "kelly_multiplier": 0.25, "disable_directional": False},
    {"drawdown_pct": 0.20, "kelly_multiplier": 0.50, "disable_directional": False},
    {"drawdown_pct": 0.10, "kelly_multiplier": 0.75, "disable_directional": False},
]

_SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "settings.json")


def _load_risk_settings():
    """
    Read operator-level Kelly/drawdown risk knobs from data/settings.json.

    These are read fresh each call (not cached / not folded into
    _default_settings()'s per-run state["settings"] overlay) because they are
    risk boundaries an operator sets, not per-cycle UI-editable thresholds —
    same spirit as ap2_mandate.SpendingMandate.from_settings(). Falls back to
    today's hardcoded defaults (0.25 quarter-Kelly / $1-$100 bet range / the
    tiers above) if any key is absent, so sizing behavior for anyone who
    hasn't touched settings.json is unchanged except for the 40%-floor
    removal itself (which is unconditional, see autopilot_cycle()).
    """
    try:
        with open(_SETTINGS_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        cfg = {}

    def _f(key, default):
        try:
            v = cfg.get(key)
            return float(v) if v is not None else default
        except (TypeError, ValueError):
            return default

    tiers = cfg.get("arena_drawdown_tiers")
    if not isinstance(tiers, list) or not tiers:
        tiers = _DEFAULT_DRAWDOWN_TIERS
    else:
        # Validate shape defensively — a malformed settings.json entry must
        # never crash the autopilot loop or silently disable all protection.
        clean = []
        for t in tiers:
            if not isinstance(t, dict):
                continue
            try:
                clean.append(
                    {
                        "drawdown_pct": float(t["drawdown_pct"]),
                        "kelly_multiplier": float(t["kelly_multiplier"]),
                        "disable_directional": bool(t.get("disable_directional", False)),
                    }
                )
            except (KeyError, TypeError, ValueError):
                continue
        tiers = clean or _DEFAULT_DRAWDOWN_TIERS

    protection_enabled = cfg.get("arena_drawdown_protection_enabled")
    if not isinstance(protection_enabled, bool):
        protection_enabled = True

    liquidity_gate_enabled = cfg.get("arena_liquidity_gate_enabled")
    if not isinstance(liquidity_gate_enabled, bool):
        liquidity_gate_enabled = True

    adaptive_kelly_enabled = cfg.get("arena_adaptive_kelly_enabled")
    if not isinstance(adaptive_kelly_enabled, bool):
        adaptive_kelly_enabled = False  # Phase 10 — off by default until validated

    forebet_required = cfg.get("arena_forebet_required")
    if not isinstance(forebet_required, bool):
        forebet_required = True  # preserves the 2026-07-06 FOREBET-ONLY MODE default

    arb_enabled = cfg.get("arena_arb_enabled")
    if not isinstance(arb_enabled, bool):
        arb_enabled = True  # arbitrage bypass has always been on; now explicitly configurable

    return {
        "kelly_fraction": _f("arena_kelly_fraction", 0.25),
        "minimum_bet": _f("arena_minimum_bet", MIN_USD_PER_BET),
        "maximum_bet": _f("arena_maximum_bet", MAX_USD_PER_BET),
        "drawdown_protection_enabled": protection_enabled,
        "drawdown_tiers": sorted(tiers, key=lambda t: t["drawdown_pct"], reverse=True),
        # Phase 2 — execution quality / liquidity gate (see execution_analytics.py)
        "liquidity_gate_enabled": liquidity_gate_enabled,
        "required_liquidity_multiple": _f("arena_required_liquidity_multiple", 3.0),
        "liquidity_check_pct": _f("arena_liquidity_check_pct", 0.01),
        # Phase 10 — adaptive Kelly composite (see adaptive_kelly.py)
        "adaptive_kelly_enabled": adaptive_kelly_enabled,
        "adaptive_kelly_ece_cap": _f("arena_adaptive_kelly_ece_cap", 0.15),
        "adaptive_kelly_slippage_cap": _f("arena_adaptive_kelly_slippage_cap", 0.05),
        "adaptive_kelly_vig_cap_pp": _f("arena_adaptive_kelly_vig_cap_pp", 10.0),
        # Phase 13 — configuration sweep: strategy values that were previously
        # hardcoded, now configurable (defaults preserve prior behavior exactly).
        "forebet_required": forebet_required,
        "arb_enabled": arb_enabled,
        "wc_model_weight": _f("arena_wc_model_weight", WC_MODEL_WEIGHT),
        # Conviction cap (2026-07-10): skip picks whose model-vs-market
        # disagreement exceeds this many percentage points — see
        # _conviction_capped() for why big "edges" are errors, not value.
        "edge_cap_pp": _f("arena_edge_cap_pp", 20.0),
    }


arena_bp = Blueprint("arena", __name__)


# ---------------------------------------------------------------------------
# Low-level API helpers
# ---------------------------------------------------------------------------
def _key():
    k = os.getenv("STAIR_AI_API_KEY")
    if k:
        return k.strip()
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    try:
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                if line.startswith("STAIR_AI_API_KEY="):
                    return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return ""


def _arena_live():
    """Read DEEPFIELD_ARENA_LIVE from os.environ first, then .env file directly.
    Needed because .env is not always loaded into os.environ on daemon threads.
    """
    v = os.getenv("DEEPFIELD_ARENA_LIVE")
    if v is not None:
        return v.strip() == "1"
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    try:
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                if line.startswith("DEEPFIELD_ARENA_LIVE="):
                    return line.split("=", 1)[1].strip() == "1"
    except OSError:
        pass
    return False


def _headers():
    return {"x-api-key": _key()}


def _get(path, **params):
    r = requests.get(
        f"{ARENA}{path}", headers=_headers(), params=params or None, timeout=25
    )
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, {"_text": r.text[:500]}


def _post(path, payload):
    r = requests.post(f"{ARENA}{path}", headers=_headers(), json=payload, timeout=25)
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, {"_text": r.text[:500]}


def _unwrap(o):
    """Data-proxy responses wrap the upstream payload under 'body'."""
    if isinstance(o, dict) and "body" in o and "statusCode" in o:
        return o["body"]
    return o


# ---------------------------------------------------------------------------
# DeepFieldPro model prob lookup (mirrors the Betarabia paper strategy)
# ---------------------------------------------------------------------------
_DFP_STATE_FILE = os.path.join(
    os.path.dirname(__file__), "..", "data", "todays_dashboard_state.json"
)
_dfp_cache = {"ts": 0.0, "data": []}
_DFP_CACHE_TTL = 60  # seconds — daemon writes every ~3 min so 60s staleness is fine


def _load_dfp_state():
    """Read the daemon's latest predictions from the dashboard state file."""
    if time.time() - _dfp_cache["ts"] < _DFP_CACHE_TTL:
        return _dfp_cache["data"]
    try:
        with open(_DFP_STATE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        _dfp_cache["ts"] = time.time()
        _dfp_cache["data"] = data if isinstance(data, list) else []
    except (OSError, ValueError):
        pass
    return _dfp_cache["data"]


def _norm(name):
    return name.lower().strip().replace(".", "").replace("-", " ")


def _names_match(a, b):
    """Return True if two team name strings plausibly refer to the same team."""
    na, nb = _norm(a), _norm(b)
    if na == nb:
        return True
    if na in nb or nb in na:
        return True
    # first-5 prefix handles "Czech Republic" vs "Czechia", "Korea Republic" vs "Korea" etc.
    if len(na) >= 5 and len(nb) >= 5 and na[:5] == nb[:5]:
        return True
    return False


def _match_dfp(home_name, away_name):
    """
    Return our Dixon-Coles calibrated probs for a fixture by team name,
    read from todays_dashboard_state.json (the same source the paper bets use).
    Returns {'home': p, 'draw': p, 'away': p} as 0..1, or None if not found.
    """
    for entry in _load_dfp_state():
        match_str = entry.get("match", "")
        if " vs " not in match_str:
            continue
        h, a = match_str.split(" vs ", 1)
        if _names_match(home_name, h) and _names_match(away_name, a):
            dd = (entry.get("prediction") or {}).get("detailed_prediction") or {}
            try:
                hp = float(dd["home_prob"]) / 100.0
                dp = float(dd["draw_prob"]) / 100.0
                ap = float(dd["away_prob"]) / 100.0
                if hp + dp + ap > 0:
                    return {
                        "home": round(hp, 4),
                        "draw": round(dp, 4),
                        "away": round(ap, 4),
                    }
            except (KeyError, TypeError, ValueError):
                pass
    return None


# ---------------------------------------------------------------------------
# Domain helpers
# ---------------------------------------------------------------------------
def get_wallet():
    sc, data = _get("/api/v1/arena/agents/me")
    if sc != 200 or not isinstance(data, dict):
        return None
    # API may nest wallet under data.wallet or data.data.wallet; handle both casings
    w = data.get("wallet") or (data.get("data") or {}).get("wallet") or {}
    try:
        avail = float(
            w.get("available_balance_usdc") or w.get("availableBalance") or 0.0
        )
    except (TypeError, ValueError):
        avail = 0.0
    return {
        "display_name": data.get("display_name")
        or (data.get("data") or {}).get("display_name"),
        "agent_id": data.get("agent_id") or (data.get("data") or {}).get("agent_id"),
        "lifecycle_phase": data.get("lifecycle_phase")
        or (data.get("data") or {}).get("lifecycle_phase"),
        "available_balance_usdc": avail,
        "locked_balance_usdc": w.get("locked_balance_usdc") or w.get("lockedBalance"),
    }


# ---------------------------------------------------------------------------
# Extended API helpers — positions, orders, settlements, market data
# ---------------------------------------------------------------------------
def _delete(path, **params):
    r = requests.delete(
        f"{ARENA}{path}", headers=_headers(), params=params or None, timeout=25
    )
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, {"_text": r.text[:500]}


def list_arena_matches(status=None):
    """GET /api/v1/arena/matches — list matches with timing windows."""
    params = {}
    if status:
        params["status"] = status
    sc, data = _get("/api/v1/arena/matches", **params)
    if sc != 200 or not isinstance(data, dict):
        return []
    matches = data.get("matches") or data.get("data") or []
    if isinstance(matches, dict):
        matches = matches.get("matches") or matches.get("data") or []
    return matches if isinstance(matches, list) else []


def get_match_timing(fixture_id):
    """GET /api/v1/arena/matches/{fixture_id} — match timing + current window."""
    sc, data = _get(f"/api/v1/arena/matches/{fixture_id}")
    if sc != 200:
        return None
    return _unwrap(data)


def get_exposure(fixture_id=None):
    """GET /api/v1/arena/exposure — token holdings with P&L."""
    params = {}
    if fixture_id:
        params["fixture_id"] = fixture_id
    sc, data = _get("/api/v1/arena/exposure", **params)
    if sc != 200:
        return None
    return _unwrap(data) if isinstance(data, dict) else data


def list_orders(fixture_id=None, status=None):
    """GET /api/v1/arena/orders — list agent orders."""
    params = {}
    if fixture_id:
        params["fixture_id"] = fixture_id
    if status:
        params["status"] = status
    sc, data = _get("/api/v1/arena/orders", **params)
    if sc != 200:
        return []
    if isinstance(data, dict):
        orders = data.get("orders") or data.get("data") or []
        return orders if isinstance(orders, list) else []
    return []


def get_order_detail(order_id):
    """GET /api/v1/arena/orders/{order_id} — single order detail."""
    sc, data = _get(f"/api/v1/arena/orders/{order_id}")
    if sc != 200:
        return None
    return _unwrap(data)


def close_position(order_id, limit_price, tif_seconds=30):
    """POST /api/v1/arena/orders/{order_id}/close — close a filled position."""
    payload = {
        "limit_price": float(limit_price),
        "time_in_force_seconds": int(tif_seconds),
        "idempotency_key": str(uuid.uuid4()),
    }
    sc, data = _post(f"/api/v1/arena/orders/{order_id}/close", payload)
    return sc, data


def get_market_data(fixture_id):
    """GET /api/v1/data/polymarket/markets/{fixture_id} — live CLOB mid-prices."""
    sc, data = _get(f"/api/v1/data/polymarket/markets/{fixture_id}")
    if sc != 200:
        return None
    return _unwrap(data)


def get_settlement(fixture_id):
    """GET /api/v1/data/polymarket/markets/{fixture_id}/settlement — post-match outcome."""
    sc, data = _get(f"/api/v1/data/polymarket/markets/{fixture_id}/settlement")
    if sc != 200:
        return None
    return _unwrap(data)


def get_polymarket_listings():
    """GET /api/v1/data/polymarket/listings — all active Polymarket markets."""
    sc, data = _get("/api/v1/data/polymarket/listings")
    if sc != 200:
        return []
    if isinstance(data, dict):
        return data.get("listings") or data.get("data") or []
    return data if isinstance(data, list) else []


def get_leaderboard(sort_by="psl", direction="desc", limit=25, offset=0):
    """GET /api/v1/web/leaderboard — public agent rankings."""
    params = {
        "sort_by": sort_by,
        "direction": direction,
        "limit": limit,
        "offset": offset,
    }
    sc, data = _get("/api/v1/web/leaderboard", **params)
    if sc != 200:
        return []
    if isinstance(data, dict):
        return data.get("leaderboard") or data.get("data") or []
    return data if isinstance(data, list) else []


def get_leaderboard_stats():
    """GET /api/v1/web/leaderboard/stats — summary stats for the leaderboard."""
    sc, data = _get("/api/v1/web/leaderboard/stats")
    if sc != 200:
        return None
    return _unwrap(data)


def get_tournament():
    """GET /api/v1/web/tournament — tournament info."""
    sc, data = _get("/api/v1/web/tournament")
    if sc != 200:
        return None
    return _unwrap(data)


def submit_order_fok(fixture_id, team_code, usd_size, worst_price):
    """POST /api/v1/arena/orders_fok — fill-or-kill order (all-or-nothing).

    Gated like place_order (2026-07-10): this helper moves REAL money and is
    called from tools (arg_fill_hunter, mar_leg_watcher) as well as the HTTP
    endpoint, so the live gate, the AP2 mandate (fail-closed), and the
    per-order cap live INSIDE it — no caller can skip them.
    """
    if not _arena_live():
        return 0, {
            "error": "blocked",
            "reason": "real-money placement disabled (DEEPFIELD_ARENA_LIVE != 1)",
        }
    usd_size = min(float(usd_size), MAX_USD_PER_BET)
    if not _AP2:
        return 402, {
            "error": "AP2 mandate layer unavailable (fail-closed): order refused"
        }
    try:
        _m = _Mandate.from_settings()
        _wallet = get_wallet()
        _wb = _wallet["available_balance_usdc"] if _wallet else 0.0
        _ok, _reason = _m.check(usd_size, _get_daily_spent(), _wb)
        if not _ok:
            return 402, {"error": f"AP2 mandate blocked: {_reason}"}
    except Exception as _ap2_err:
        return 402, {
            "error": f"AP2 mandate check errored (fail-closed): {_ap2_err}"
        }
    payload = {
        "fixture_id": str(fixture_id),
        "team_code": team_code,
        "usd_size": f"{usd_size:.2f}",
        "worst_price": float(worst_price),
        "idempotency_key": str(uuid.uuid4()),
    }
    sc, data = _post("/api/v1/arena/orders_fok", payload)
    return sc, data


def list_upcoming_fixtures(limit=40):
    sc, sched = _get(
        f"/api/v1/data/proxy/sportmonks/v3/football/schedules/seasons/{SEASON_ID}"
    )
    # The data-proxy returns a wrapped response {body: ..., statusCode: ...}.
    # Must unwrap to access the actual Sportmonks schedule data.
    sched = _unwrap(sched)
    fixtures = []

    def walk(o):
        if isinstance(o, dict):
            if isinstance(o.get("fixtures"), list):
                fixtures.extend(o["fixtures"])
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(sched)
    now = time.time()
    seen, upcoming = set(), []
    for f in fixtures:
        fid = f.get("id")
        ts = f.get("starting_at_timestamp") or 0
        if fid and fid not in seen and ts > now:
            seen.add(fid)
            upcoming.append(f)
    upcoming.sort(key=lambda f: f.get("starting_at_timestamp") or 0)
    return upcoming[:limit]


def get_model_probs(fid):
    """Return {'home':p,'draw':p,'away':p} as 0..1 from Sportmonks 1X2 prediction (fallback)."""
    sc, det = _get(
        f"/api/v1/data/proxy/sportmonks/v3/football/fixtures/{fid}",
        include="participants;predictions",
    )
    fx = _unwrap(det)
    fx = fx.get("data") if isinstance(fx, dict) else None
    if not isinstance(fx, dict):
        return None
    preds = fx.get("predictions") or []
    top = next((p for p in preds if p.get("type_id") == PRED_TYPE_1X2), None)
    if not top:
        return None
    pp = top.get("predictions") or {}
    try:
        return {
            "home": float(pp.get("home", 0)) / 100.0,
            "draw": float(pp.get("draw", 0)) / 100.0,
            "away": float(pp.get("away", 0)) / 100.0,
        }
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Polymarket gamma API — direct token discovery for knockout stage
# ---------------------------------------------------------------------------
_POLYMARKET_GAMMA = "https://gamma-api.polymarket.com"

# Country name → Polymarket slug code (3-letter)
_SLUG_CODES = {
    "south africa": "rsa", "canada": "can", "brazil": "bra", "japan": "jpn",
    "germany": "ger", "paraguay": "par", "netherlands": "ned", "morocco": "mar",
    "c\u00f4te d'ivoire": "civ", "cote d'ivoire": "civ", "ivory coast": "civ",
    "norway": "nor", "france": "fra", "sweden": "swe", "mexico": "mex",
    "ecuador": "ecu", "england": "eng", "congo dr": "cod",
    "belgium": "bel", "senegal": "sen", "portugal": "por", "croatia": "cro",
    "colombia": "col", "ghana": "gha", "spain": "esp", "austria": "aut",
    "switzerland": "sui", "algeria": "alg", "united states": "usa",
    "bosnia and herzegovina": "bih", "australia": "aus", "egypt": "egy",
    "argentina": "arg", "cape verde islands": "cpv", "cape verde": "cpv",
    "tunisia": "tun", "uruguay": "uru", "korea republic": "kor",
    "czech republic": "cze", "qatar": "qat", "haiti": "hti", "turkey": "tur",
    "cura\u00e7ao": "cuw", "curacao": "cuw", "new zealand": "nzl",
    "iran": "irn", "saudi arabia": "ksa", "iraq": "irq", "jordan": "jor",
    "panama": "pan", "uzbekistan": "uzb", "scotland": "sco",
}

# Knockout mapping file — persisted to avoid re-querying gamma API every cycle
_KNOCKOUT_MAPPING_FILE = os.path.join(
    os.path.dirname(__file__), "..", "data", "knockout_mapping.json"
)
_knockout_mapping_cache = {}
_knockout_mapping_ts = 0
_KNOCKOUT_CACHE_TTL = 600  # 10 minutes


def _load_knockout_mapping_file():
    """Load persisted knockout mapping from disk."""
    global _knockout_mapping_cache
    if os.path.exists(_KNOCKOUT_MAPPING_FILE):
        try:
            with open(_KNOCKOUT_MAPPING_FILE) as fp:
                data = json.load(fp)
            maps = data.get("mappings", []) if isinstance(data, dict) else data
            _knockout_mapping_cache.update({
                str(m["sportmonks_fixture_id"]): m
                for m in maps if m.get("sportmonks_fixture_id")
            })
        except (json.JSONDecodeError, KeyError, OSError):
            pass


def _save_knockout_mapping_file(mappings_dict):
    """Persist knockout mapping to disk."""
    try:
        with open(_KNOCKOUT_MAPPING_FILE, "w") as fp:
            json.dump({"mappings": list(mappings_dict.values())}, fp, indent=2)
    except OSError:
        pass


def _discover_knockout_tokens(fixtures):
    """Query Polymarket gamma API to find token IDs for knockout matches.

    For each fixture without a mapping, searches Polymarket for the event
    and extracts YES token IDs from the 3 markets (home/draw/away).
    """
    import time as _tm
    new_mappings = {}
    searched = 0
    for f in fixtures:
        fid = str(f.get("id", ""))
        if not fid or fid in _mapping_cache or fid in _knockout_mapping_cache:
            continue
        fname = f.get("name", "")
        kickoff = f.get("starting_at", "")
        date_part = kickoff[:10] if kickoff else ""
        parts = fname.split(" vs ", 1)
        if len(parts) != 2:
            continue
        home_name, away_name = parts[0].lower(), parts[1].lower()
        home_code = _SLUG_CODES.get(home_name, home_name[:3])
        away_code = _SLUG_CODES.get(away_name, away_name[:3])
        # Skip "Winner Match X" type fixtures — teams TBD
        if "winner" in home_name or "winner" in away_name:
            continue
        # Try slug: fifwc-{home}-{away}-{date}
        slug = f"fifwc-{home_code}-{away_code}-{date_part}"
        try:
            r = requests.get(
                f"{_POLYMARKET_GAMMA}/events",
                params={"slug": slug}, timeout=10
            )
            searched += 1
            if r.status_code != 200 or not r.json():
                continue
            ev = r.json()[0]
            markets = ev.get("markets", [])
            home_tok = draw_tok = away_tok = None
            home_cid = draw_cid = away_cid = None
            for m in markets:
                q = m.get("question", "").lower()
                cid = m.get("conditionId", "")
                raw_tokens = m.get("clobTokenIds", "[]")
                toks = json.loads(raw_tokens) if isinstance(raw_tokens, str) else raw_tokens
                yes_tok = toks[0] if isinstance(toks, list) and len(toks) >= 1 else None
                # NOTE: match the slug's own outcome suffix, not a raw substring.
                # Every per-outcome market's slug shares the event's full prefix
                # (e.g. "fifwc-fra-mar-2026-07-09-mar" contains "fra" too), so a
                # bare `code in slug` check matches every market in the event and
                # silently overwrites home with the away team's token (or vice
                # versa) once the elif chain reaches it. endswith(f"-{code}")
                # only matches the market that's actually about that team.
                slug_l = m.get("slug", "").lower()
                if "draw" in q:
                    draw_tok, draw_cid = yes_tok, cid
                elif home_name.split()[0] in q or slug_l.endswith(f"-{home_code}"):
                    home_tok, home_cid = yes_tok, cid
                elif away_name.split()[0] in q or slug_l.endswith(f"-{away_code}"):
                    away_tok, away_cid = yes_tok, cid
            if home_tok or away_tok or draw_tok:
                new_mappings[fid] = {
                    "sportmonks_fixture_id": fid,
                    "sportmonks_match_name": fname,
                    "polymarket_event_slug": slug,
                    "home_country": parts[0],
                    "away_country": parts[1],
                    "home_short_code": home_code.upper(),
                    "away_short_code": away_code.upper(),
                    "polymarket_home_token_yes": home_tok,
                    "polymarket_home_condition_id": home_cid,
                    "polymarket_draw_token_yes": draw_tok,
                    "polymarket_draw_condition_id": draw_cid,
                    "polymarket_away_token_yes": away_tok,
                    "polymarket_away_condition_id": away_cid,
                }
        except Exception:
            pass
        _tm.sleep(0.15)  # rate-limit
    if new_mappings:
        print(f"[arena] Discovered {len(new_mappings)} knockout Polymarket tokens via gamma API")
    return new_mappings


# ---------------------------------------------------------------------------
# Mapping cache — fetched once per cycle to avoid 100+ individual API calls.
# ---------------------------------------------------------------------------
_mapping_cache = {}
_mapping_cache_ts = 0
_MAPPING_CACHE_TTL = 300  # 5 minutes


def _refresh_mapping_cache():
    """Fetch ALL Polymarket mappings in one call and cache them.

    Merges group-stage mappings from /api/v1/web/mapping with knockout-stage
    token IDs discovered directly from Polymarket's gamma API.
    """
    global _mapping_cache, _mapping_cache_ts
    now = time.time()
    if _mapping_cache and (now - _mapping_cache_ts) < _MAPPING_CACHE_TTL:
        return
    # 1. Load group-stage mappings from StairAI API
    sc, mp = _get("/api/v1/web/mapping")
    if sc == 200 and isinstance(mp, dict):
        maps = mp.get("mappings", [])
        _mapping_cache = {
            str(m["sportmonks_fixture_id"]): m
            for m in maps
            if m.get("sportmonks_fixture_id")
        }
        print(f"[arena] Cached {len(_mapping_cache)} Polymarket mappings")
    # 2. Load persisted knockout mappings
    _load_knockout_mapping_file()
    _mapping_cache.update(_knockout_mapping_cache)
    # 3. Discover knockout tokens from Polymarket gamma API for upcoming fixtures
    try:
        fixtures = list_upcoming_fixtures(limit=40)
        new_ko = _discover_knockout_tokens(fixtures)
        if new_ko:
            _knockout_mapping_cache.update(new_ko)
            _mapping_cache.update(new_ko)
            # Merge into persisted file
            _save_knockout_mapping_file(
                {**_knockout_mapping_cache, **new_ko}
            )
    except Exception:
        pass
    _mapping_cache_ts = now


def get_mapping(fid):
    """Look up Polymarket token mapping for a fixture. Uses cache."""
    _refresh_mapping_cache()
    return _mapping_cache.get(str(fid))


# Mid-price cache — avoids hundreds of CLOB midpoint calls per cycle.
_mid_cache = {}
_mid_cache_ts = 0
_MID_CACHE_TTL = 120  # 2 minutes — prices move fast


def _clear_mid_cache():
    """Reset mid cache at the start of each analyze() cycle."""
    global _mid_cache, _mid_cache_ts
    _mid_cache = {}
    _mid_cache_ts = time.time()


def get_mid(token_id):
    if not token_id:
        return None
    now = time.time()
    cached = _mid_cache.get(token_id)
    if cached is not None and (now - _mid_cache_ts) < _MID_CACHE_TTL:
        return cached
    sc, mid = _get("/api/v1/data/proxy/polymarket-clob/midpoint", token_id=token_id)
    mid = _unwrap(mid)
    if isinstance(mid, dict) and mid.get("mid") is not None:
        try:
            val = float(mid["mid"])
            _mid_cache[token_id] = val
            return val
        except (TypeError, ValueError):
            return None
    return None


# Order-book cache — keyed per-token with its own timestamp (unlike the
# single-shared-ts _mid_cache above, which is reset once per analyze() cycle
# via _clear_mid_cache()) since get_order_book() is called standalone from
# the liquidity gate, not from within analyze()'s per-cycle loop.
_book_cache = {}  # token_id -> (book_dict, fetched_at_ts)
_BOOK_CACHE_TTL = 60  # seconds — liquidity moves slower than best-price ticks


def get_order_book(token_id):
    """
    GET /api/v1/data/proxy/polymarket-clob/book — full bid/ask depth for a
    Polymarket token, proxied through StairAI. Returns the unwrapped
    {"bids": [...], "asks": [...]} dict, or None on any failure (the
    liquidity gate in execution_analytics.py fails OPEN on None — a data-proxy
    hiccup must never silently block all betting).
    """
    if not token_id:
        return None
    now = time.time()
    cached = _book_cache.get(token_id)
    if cached is not None and (now - cached[1]) < _BOOK_CACHE_TTL:
        return cached[0]
    try:
        sc, book = _get("/api/v1/data/proxy/polymarket-clob/book", token_id=token_id)
    except Exception:
        return None
    book = _unwrap(book)
    if not isinstance(book, dict) or "asks" not in book:
        return None
    _book_cache[token_id] = (book, now)
    return book


def _wallet_kelly_size(
    edge,
    market_mid,
    wallet_balance,
    max_usd=None,
    kelly_fraction=None,
    min_usd=None,
    dd_multiplier=1.0,
):
    """
    Configurable-fraction Kelly capped stake — conservative sizing to reduce ruin risk.

    Kelly fraction for a Polymarket binary bet: f* = edge / (1 - market_mid)
    We cap at `kelly_fraction` (default: quarter-Kelly, 0.25, read from
    data/settings.json via _load_risk_settings() when not passed explicitly).
    Full Kelly has ~50% drawdowns and is far too aggressive when model
    probabilities have uncertainty.

    Edge tier only controls whether we bet at all (larger edge = more confident
    the bet qualifies), but sizing is always kelly_fraction max.

    `dd_multiplier` (default 1.0, no effect) lets a caller scale the Kelly
    fraction down further for drawdown protection — see
    _update_drawdown_state(). NOTE: a dd_multiplier of 0.0 does NOT zero the
    returned size; the min_usd floor below still applies. Callers that need
    to fully disable directional betting at the worst drawdown tier must
    bypass this function entirely (see autopilot_cycle()'s
    _directional_blocked() check), not rely on dd_multiplier reaching zero.

    Hard caps: MAX_WALLET_FRACTION of wallet and max_usd (defaults to the
    configured arena_maximum_bet / MAX_USD_PER_BET).
    """
    if market_mid >= 1.0 or market_mid <= 0 or wallet_balance <= 0:
        return min_usd if min_usd is not None else MIN_USD_PER_BET
    _risk = _load_risk_settings() if kelly_fraction is None or min_usd is None else None
    fraction = kelly_fraction if kelly_fraction is not None else _risk["kelly_fraction"]
    floor_usd = min_usd if min_usd is not None else _risk["minimum_bet"]
    kelly_f = max(0.0, edge / (1.0 - market_mid))
    # Real USDC (confirmed 2026-07-09), not a virtual tournament bankroll —
    # configurable-fraction Kelly per this function's own sizing rationale above.
    multiplier = fraction * dd_multiplier
    size = kelly_f * multiplier * wallet_balance
    bet_cap = max_usd if max_usd is not None else MAX_USD_PER_BET
    hard_cap = min(wallet_balance * MAX_WALLET_FRACTION, bet_cap)
    return round(max(floor_usd, min(size, hard_cap)), 2)


def _size_for_edge(edge, max_usd):
    """Conviction sizing (legacy, used when wallet balance not available)."""
    edge_pp = edge * 100.0
    if edge_pp >= 15:
        base = 5.0
    elif edge_pp >= 10:
        base = 3.0
    else:
        base = 2.0
    return round(max(MIN_USD_PER_BET, min(base, max_usd)), 2)


# ---------------------------------------------------------------------------
# Paper bet logger — logs to bet_log.db for monitoring/CLV tracking
# ---------------------------------------------------------------------------
_steam_paper_logged: set = set()  # deduplicate steam paper bets per fixture:outcome


def _log_steam_paper_bet(fixture_id: str, match_name: str, outcome: str, mid: float, steam_move: float):
    """Log a steam-triggered paper bet to bet_log.db. No real money."""
    # SIGNAL-ONLY (2026-07-08): POLY_STEAM ran 0-for-7 — disabled unless
    # explicitly re-enabled in settings for a future research run.
    try:
        import json as _j

        _sp = os.path.join(os.path.dirname(__file__), "..", "data", "settings.json")
        if not _j.load(open(_sp, encoding="utf-8")).get(
            "poly_steam_paper_enabled", False
        ):
            return
    except Exception:
        return
    key = f"{fixture_id}:{outcome}"
    if key in _steam_paper_logged:
        return
    _steam_paper_logged.add(key)
    try:
        import sqlite3 as _sq
        import uuid as _uuid
        _bet_log = os.path.join(os.path.dirname(__file__), "..", "data", "bet_log.db")
        entry_odds = round(1.0 / mid, 3) if mid > 0 else 0
        conn = _sq.connect(_bet_log)
        # DB-level dedup — the in-memory set resets on restart and re-logs the
        # same signal. Skip if an OPEN steam bet on this match+outcome exists.
        _dupe = conn.execute(
            "SELECT COUNT(*) FROM bet_log WHERE bet_source='POLY_STEAM' AND side=? "
            "AND result='OPEN' AND (match_id=? OR match_id=?)",
            (outcome, match_name or fixture_id, str(fixture_id)),
        ).fetchone()[0]
        if _dupe:
            conn.close()
            return
        import datetime as _dt
        conn.execute("""
            INSERT INTO bet_log
              (bet_id, match_id, player_id, market_type, line, side,
               entry_odds, fair_odds, edge_pct, stake, book,
               placed_at, result, pnl, regime, bet_source, signal_name, move_size)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            str(_uuid.uuid4()),
            match_name or fixture_id,  # team names, not a bare fixture id, for the UI
            outcome,
            "1X2",
            None,
            outcome,
            entry_odds,
            entry_odds,  # fair_odds same as entry for steam bets (we're following smart money)
            round(steam_move, 2),   # edge_pct = steam move size as proxy
            25.0,                    # fixed paper stake
            "POLYMARKET",
            _dt.datetime.now().isoformat(),  # ISO-T like every other writer (sortable)
            "OPEN",
            0.0,
            "steam_signal",
            "POLY_STEAM",  # distinct source — must NOT masquerade as the AI model
            f"steam_+{steam_move:.1f}pct",
            steam_move,
        ))
        conn.commit()
        conn.close()
        print(f"[STEAM] Paper bet logged: {match_name} → {outcome} @ {entry_odds} (steam move +{steam_move:.1f}%)")
    except Exception as e:
        print(f"[STEAM] Paper bet log error: {e}")


# ---------------------------------------------------------------------------
# Bet quality grader — A/B/C/D/F based on convergent signals
# ---------------------------------------------------------------------------
def _bet_grade(edge_pp: float, steam_confirmed: bool, edge_vs_devigged, real_arb: bool) -> str:
    """Letter grade for a candidate pick based on independent signal convergence."""
    if real_arb:
        return "A+"
    evd = edge_vs_devigged or 0
    if edge_pp >= 8 and steam_confirmed and evd >= 5:
        return "A"
    if edge_pp >= 5 and (steam_confirmed or evd >= 3):
        return "B"
    if edge_pp >= 3:
        return "C"
    if edge_pp >= 1:
        return "D"
    return "F"


# ---------------------------------------------------------------------------
# Core: analyze fixtures into candidate picks
# ---------------------------------------------------------------------------
def analyze(
    limit=40,
    conf_min=CONF_MIN_DEFAULT,
    edge_min=EDGE_MIN_DEFAULT,
    max_usd=MAX_USD_PER_BET,
    wallet_balance=None,
    kelly_fraction=None,
):
    # Read once per analyze() call, not per-candidate — this loop runs up to
    # ~limit x 3 outcomes per cycle, so per-candidate disk reads would be
    # wasteful. A caller (autopilot_cycle) that wants drawdown-adjusted sizing
    # passes kelly_fraction explicitly (already folded with the drawdown
    # multiplier); manual/preview callers that don't pass it get the plain
    # configured fraction with no drawdown effect.
    _risk_cfg = _load_risk_settings()
    _kf = kelly_fraction if kelly_fraction is not None else _risk_cfg["kelly_fraction"]
    _wc_weight = _risk_cfg["wc_model_weight"]
    _clear_mid_cache()
    _refresh_mapping_cache()
    fixtures = list_upcoming_fixtures(limit)
    candidates = []
    for f in fixtures:
        fid = f["id"]

        # Extract team names to look up our own model probs
        fname = f.get("name", "")
        home_name, away_name = ("", "")
        if " vs " in fname:
            home_name, away_name = fname.split(" vs ", 1)

        # 1. Try World Cup Elo model (purpose-built for international football)
        wc_probs = None
        try:
            from src.worldcup_model import predict as wc_predict, blend_with_sportmonks

            wc_probs = wc_predict(home_name, away_name)
        except ImportError:
            pass

        # 2. Try our Dixon-Coles model (same as Betarabia paper bets)
        probs = _match_dfp(home_name, away_name) if home_name else None
        prob_source = "DFP"
        if probs is not None and max(probs.values()) < DFP_USEFUL_THRESHOLD:
            probs = None

        # 3. WC-only or WC+DFP blend — Sportmonks-only fallback DISABLED.
        #    Sportmonks alone caused 10/13 losing bets (-$79 staked).
        #    Only use Sportmonks to blend with our WC Elo model.
        sm_probs = None
        if probs is None:
            if wc_probs:
                sm_probs = get_model_probs(fid)
                if sm_probs:
                    probs = blend_with_sportmonks(wc_probs, sm_probs, _wc_weight)
                    prob_source = "WC+SM"
                else:
                    probs = wc_probs
                    prob_source = "WC"
            # If no WC probs either, skip this fixture entirely (no Sportmonks-only bets)
        elif wc_probs:
            probs = blend_with_sportmonks(wc_probs, probs, _wc_weight)
            prob_source = "WC+DFP"

        mapping = get_mapping(fid)
        if not probs or not mapping:
            continue
        # Extract Arena fixture code (e.g. "WC2026-GS-M1") — what orders/ledger require.
        # The mapping bridges Sportmonks numeric IDs to Arena-side identifiers.
        arena_fid = (
            mapping.get("fixture_id")
            or mapping.get("arena_fixture_id")
            or mapping.get("arena_id")
            or str(fid)  # fallback: Sportmonks numeric ID (API may also accept this)
        )
        # Use the short codes from the mapping — Stair AI orders use these (e.g. CRO, RSA),
        # NOT the FIFA ticker segments (e.g. HRV, ZAF) which differ for several nations.
        home_code = mapping.get("home_short_code") or "HOME"
        away_code = mapping.get("away_short_code") or "AWAY"
        codes = {
            "home": home_code,
            "draw": "draw",
            "away": away_code,
        }
        # Build full model+market data for reasoning trace
        _all_model = {"home": round(probs.get("home", 0), 4),
                      "draw": round(probs.get("draw", 0), 4),
                      "away": round(probs.get("away", 0), 4)}
        _all_mid = {}
        for _o in ("home", "draw", "away"):
            _t = mapping.get(f"polymarket_{_o}_token_yes")
            _m = get_mid(_t)
            if _m is not None:
                _all_mid[_o] = round(_m, 4)

        # ── Market analytics ─────────────────────────────────────────────────
        _mid_sum = sum(_all_mid.values()) if len(_all_mid) == 3 else None

        # Market overround/vig: how much the market charges.
        # Normal: +2-5pp (market makes money). Negative: potential arb zone.
        _market_vig_pp = round((_mid_sum - 1.0) * 100, 2) if _mid_sum is not None else None

        # De-vigged market probability: removes overround so we compare apples to apples.
        # devigged_mid = mid / sum(mids)  →  reflects the market's TRUE implied probability.
        _devigged = {
            o: round(_all_mid[o] / _mid_sum, 4)
            for o in _all_mid
        } if _mid_sum and _mid_sum > 0 else {}

        # Real three-way arbitrage check.
        # Buy all 3 outcomes at ask (mid + LIMIT_BUFFER each); collect $1 on the winner.
        # Guaranteed profit = 1.0 - sum(asks) = 1.0 - sum(mids) - 3*LIMIT_BUFFER
        # We need sum(mids) < 1.0 - 3*LIMIT_BUFFER  (= 0.94 at current 2¢ buffer)
        _real_arb_threshold = 1.0 - 3 * LIMIT_BUFFER
        _real_arb = bool(_mid_sum is not None and _mid_sum < _real_arb_threshold)
        _arb_profit_pp = (
            round((1.0 - (_mid_sum + 3 * LIMIT_BUFFER)) * 100, 2) if _real_arb else None
        )

        # Polymarket price-drift / steam signals.
        # Tracks mid-price history across scans; detects ≥3% moves as smart-money signal.
        _steam = {}
        if _all_mid:
            try:
                from src.polymarket_steam import record_scan, get_steam_signals
                record_scan(str(fid), fname, _all_mid)
                _steam = get_steam_signals(str(fid))
                # Steam ≥5% on a pre-kickoff match → log paper bet immediately
                for _s_outcome, _s_move in _steam.items():
                    if abs(_s_move) >= 5.0 and _s_move > 0:  # rising price = smart money
                        _s_mid = _all_mid.get(_s_outcome)
                        if _s_mid:
                            _log_steam_paper_bet(str(fid), fname, _s_outcome, _s_mid, _s_move)
            except Exception:
                pass

        for outcome in ("home", "draw", "away"):
            token = mapping.get(f"polymarket_{outcome}_token_yes")
            mid = get_mid(token)
            model_p = probs.get(outcome)
            if mid is None or model_p is None:
                continue
            # Sanity: ALL-IN MODE — ratio check disabled
            # if prob_source == "DFP" and mid > 0.01 and model_p / mid > DFP_MAX_RATIO:
            #     continue
            # LONGSHOT FILTER: ALL-IN MODE — only skip tokens below $0.05
            if mid < 0.05:
                continue
            edge = model_p - mid
            # ALL-IN MODE: no draw premium, no dual-model boost — bet everything
            _draw_edge_min = edge_min
            _effective_edge_min = _draw_edge_min
            qualifies = bool(model_p >= conf_min and edge >= _effective_edge_min)
            limit_price = round(min(0.99, mid + LIMIT_BUFFER), 2)

            if qualifies:
                if wallet_balance is not None:
                    suggested = _wallet_kelly_size(
                        edge, mid, wallet_balance, max_usd=max_usd, kelly_fraction=_kf
                    )
                else:
                    suggested = _size_for_edge(edge, max_usd)
            else:
                suggested = None

            candidates.append(
                {
                    "fixture_id": arena_fid,           # Arena code for orders/ledger
                    "sportmonks_fixture_id": str(fid), # kept for internal reference
                    "polymarket_fid": mapping.get("fixture_id"),  # Polymarket market ID for settlement
                    "match": fname,
                    "kickoff": f.get("starting_at"),
                    "kickoff_ts": f.get("starting_at_timestamp"),
                    "outcome": outcome,
                    "team_code": codes[outcome],
                    "model_prob": round(model_p, 4),
                    "market_mid": round(mid, 4),
                    "edge": round(edge, 4),
                    "edge_pp": round(edge * 100, 1),
                    "qualifies": qualifies,
                    "suggested_usd": suggested,
                    "limit_price": limit_price,
                    "token_id": token,
                    "prob_source": prob_source,
                    "all_model_probs": _all_model,        # full 1X2 model probs for reasoning
                    "all_market_mids": _all_mid,          # full 1X2 market mids for reasoning
                    # ── Enhanced market analytics ──────────────────────────
                    "devigged_mid": _devigged.get(outcome),   # market prob with overround removed
                    "edge_vs_devigged": round(model_p - _devigged.get(outcome, mid), 4) if _devigged else None,
                    "market_vig_pp": _market_vig_pp,      # overround in pp; <0 = arb zone
                    "real_arb": _real_arb,                # True = buy all 3 for guaranteed profit
                    "arb_profit_pp": _arb_profit_pp,      # pp profit if real arb
                    "steam_move": _steam.get(outcome),    # % price change since 4h ago; +ve = rising
                    "steam_confirmed": bool(abs(_steam.get(outcome) or 0) >= 3.0),
                    "grade": _bet_grade(
                        edge_pp=round((model_p - mid) * 100, 2),
                        steam_confirmed=bool(abs(_steam.get(outcome) or 0) >= 3.0),
                        edge_vs_devigged=round(model_p - _devigged.get(outcome, mid), 4) if _devigged else None,
                        real_arb=_real_arb,
                    ),
                }
            )
    # qualifying first, then by edge desc
    candidates.sort(key=lambda c: (c["qualifies"], c["edge"]), reverse=True)
    return candidates


# ---------------------------------------------------------------------------
# Reasoning Trace Builder — for tournament scoring
# ---------------------------------------------------------------------------
def _build_reasoning_trace(c):
    """Build a data-grounded, consistent reasoning trace for ledger submission.

    Scoring criteria (Stair AI tournament):
    1. Data grounding: claims must trace back to actual numbers from models/markets
    2. Reasoning consistency: stable framework applied across all matches
    """
    match = c.get("match", "?")
    outcome = c.get("outcome", "?")
    team = c.get("team_code", "?")
    source = c.get("prob_source", "?")
    model_p = c.get("model_prob", 0)
    market_mid = c.get("market_mid", 0)
    edge_pp = c.get("edge_pp", 0)
    all_model = c.get("all_model_probs", {})
    all_mid = c.get("all_market_mids", {})
    devigged_mid = c.get("devigged_mid")
    edge_vs_dv = c.get("edge_vs_devigged")
    market_vig_pp = c.get("market_vig_pp")
    steam_move = c.get("steam_move")
    real_arb = c.get("real_arb", False)
    arb_profit_pp = c.get("arb_profit_pp")

    # Stable framework header
    trace = (
        f"DeepFieldPro Reasoning Trace — Match: {match}\n"
        f"Prediction: {outcome.upper()} ({team})\n"
        f"Model probability: {model_p:.1%}\n"
        f"Market midpoint (raw): {market_mid:.1%}"
    )
    if devigged_mid is not None:
        trace += f"  |  De-vigged: {devigged_mid:.1%}"
    trace += f"\nEdge (vs raw): {edge_pp:+.1f}pp"
    if edge_vs_dv is not None:
        trace += f"  |  Edge (vs de-vigged): {edge_vs_dv*100:+.1f}pp"
    trace += "\n\n"

    # Factor 1: Model output (always cited)
    trace += "[Factor 1: Model Output]\n"
    if all_model:
        trace += (
            f"  Home: {all_model.get('home',0):.1%} | "
            f"Draw: {all_model.get('draw',0):.1%} | "
            f"Away: {all_model.get('away',0):.1%}\n"
        )
    trace += f"  Source: {source}\n"
    if "WC+DFP" in source:
        trace += "  Blend: WC Elo (65%) + Dixon-Coles (35%)\n"
    elif "WC+SM" in source:
        trace += "  Blend: WC Elo (65%) + Sportmonks (35%)\n"
    elif "WC" in source:
        trace += "  Source: World Cup Elo model (international team strength ratings)\n"
    elif "DFP" in source:
        trace += "  Source: Dixon-Coles calibrated model (same as Betarabia paper bets)\n"
    trace += "\n"

    # Factor 2: Market pricing + overround analysis
    trace += "[Factor 2: Market Pricing]\n"
    if all_mid:
        trace += (
            f"  Polymarket raw midpoints — "
            f"Home: {all_mid.get('home',0):.1%} | "
            f"Draw: {all_mid.get('draw',0):.1%} | "
            f"Away: {all_mid.get('away',0):.1%}\n"
        )
        mid_sum = sum(all_mid.values())
        vig_pp = round((mid_sum - 1.0) * 100, 2)
        trace += f"  Market overround: {vig_pp:+.1f}pp (sum={mid_sum:.3f}) "
        if real_arb:
            trace += f"⚡ REAL ARB: guaranteed +{arb_profit_pp:.1f}pp profit buying all 3\n"
        elif mid_sum < 0.97:
            trace += "(loose market — negative vig, above-average EV environment)\n"
        elif mid_sum < 1.00:
            trace += "(near-arb: market underpricing total probability slightly)\n"
        elif mid_sum < 1.04:
            trace += "(efficient market, standard ~2-4% vig)\n"
        else:
            trace += "(elevated vig — market charging >4% overround)\n"
    trace += "\n"

    # Factor 3: Edge assessment (vs both raw and de-vigged)
    trace += "[Factor 3: Edge Assessment]\n"
    if edge_pp > 15:
        trace += f"  Strong edge: {edge_pp:+.1f}pp — model significantly more confident than market\n"
    elif edge_pp > 5:
        trace += f"  Moderate edge: {edge_pp:+.1f}pp — model modestly more bullish than market\n"
    elif edge_pp > 0:
        trace += f"  Slight edge: {edge_pp:+.1f}pp — marginal advantage, sizing conservatively\n"
    else:
        trace += f"  Negative edge: {edge_pp:+.1f}pp — model less confident than market\n"
    if edge_vs_dv is not None:
        dv_pp = round(edge_vs_dv * 100, 1)
        if dv_pp > 0:
            trace += f"  True edge (de-vigged): +{dv_pp:.1f}pp — model outperforms fair market\n"
        else:
            trace += f"  True edge (de-vigged): {dv_pp:+.1f}pp — model below fair market probability\n"

    # Factor 4: Steam / price momentum signal
    trace += "\n[Factor 4: Market Momentum (Steam)]\n"
    if steam_move is not None:
        direction = "rising" if steam_move > 0 else "falling"
        strength = "strong" if abs(steam_move) >= 5 else "moderate" if abs(steam_move) >= 3 else "mild"
        trace += (
            f"  Price drift: {steam_move:+.1f}% over 4h ({strength}, {direction})\n"
        )
        if steam_move > 3:
            trace += "  → Positive steam: smart money backing this outcome (follow signal)\n"
        elif steam_move < -3:
            trace += "  → Negative steam: market rotating away from this outcome\n"
    else:
        trace += "  No significant price movement detected (stable market)\n"

    # Factor 5: Outcome context
    trace += "\n[Factor 5: Outcome Context]\n"
    if outcome == "draw":
        trace += "  Draw bets carry higher variance in Polymarket (thin liquidity)\n"
        trace += "  WC 2026 tournament draw rate historically elevated vs league play\n"
    elif model_p > 0.70:
        trace += "  High-confidence favorite — model strongly favors this outcome\n"
    elif model_p > 0.45:
        trace += "  Competitive match — no dominant favorite identified\n"
    else:
        trace += "  Underdog pick — model sees value where market is skeptical\n"

    # Factor 6: Independent confirmation + stake sizing
    trace += "\n[Factor 6: Confirmation & Sizing]\n"
    if c.get("tipster_confirmed"):
        trace += (
            "  Forebet CONFIRMS this pick — the only strategy in our research "
            "ledger with a 95% CI entirely above zero (+41.7% ROI, n=259).\n"
        )
    elif real_arb:
        trace += "  No tipster needed — structural arbitrage (sum of asks < $1).\n"
    else:
        trace += (
            "  No independent Forebet confirmation — pick is blocked from "
            "real-money staking under FOREBET-ONLY MODE (ledger prediction only).\n"
        )
    if c.get("suggested_usd") is not None:
        trace += (
            f"  Stake: fractional Kelly (quarter-Kelly x drawdown tier) -> "
            f"${c['suggested_usd']:.2f} suggested, hard-capped at "
            f"${MAX_USD_PER_BET:.2f}/order, ${DAILY_SPEND_CAP:.2f}/day, "
            f"{MAX_WALLET_FRACTION:.0%} of wallet per pick.\n"
        )

    # Decision
    trace += "\n[Decision]\n"
    if c.get("qualifies"):
        trace += (
            f"  ACTION: PREDICT — model probability ({model_p:.1%}) exceeds "
            f"market ({market_mid:.1%}) by {edge_pp:+.1f}pp, warranting a position.\n"
        )
    else:
        trace += (
            f"  ACTION: SKIP — edge ({edge_pp:+.1f}pp) insufficient to justify "
            f"position given Polymarket fees and liquidity risk.\n"
        )

    return trace[:2048]  # API limit


# ---------------------------------------------------------------------------
# Submission (REAL MONEY)
# ---------------------------------------------------------------------------
def submit_ledger(fid, outcome_code, model_prob, note):
    prob = max(0.001, min(0.999, float(model_prob)))
    payload = {
        "records": [
            {
                "behavior": "Acting",
                "action_type": "prediction",
                "parameters": {
                    "fixture_id": str(fid),
                    "outcome": outcome_code,
                    "probability": prob,
                },
                "notes": note[:2048],
            }
        ],
        "fixture_id": str(fid),
    }
    return _post("/api/v1/arena/ledger/records/batch", payload)


def place_order(fid, team_code, usd_size, limit_price):
    # HARD SAFETY GATE — the single chokepoint for ALL real-money orders. No state
    # flag, frontend toggle, or orphaned process can place a real bet unless the
    # operator explicitly sets DEEPFIELD_ARENA_LIVE=1 in the environment. Default OFF.
    # Runs FIRST (primary gate, per ap2_mandate.py's contract) — a disarmed system
    # attempts nothing, not even mandate bookkeeping.
    if not _arena_live():
        return 0, {
            "error": "blocked",
            "reason": "real-money placement disabled (DEEPFIELD_ARENA_LIVE != 1)",
        }

    # AP2 mandate pre-flight — secondary gate + audit ledger.
    # FAIL-CLOSED (2026-07-10): real money never moves without a working mandate
    # check — an unavailable AP2 layer or an internal error blocks the order
    # instead of silently waving it through (was `except: pass`).
    _ap2_row = None
    if not _AP2:
        return 402, {
            "error": "AP2 mandate layer unavailable (fail-closed): order refused"
        }
    try:
        _ctx = _ap2_get_ctx()
        _m = _Mandate.from_settings()
        _spent = _get_daily_spent()
        _wb = _ctx.get("wallet_balance", 999.0)
        _conf = _ctx.get("model_prob", 1.0)
        _edg = _ctx.get("edge", 1.0)
        _ok, _reason = _m.check(float(usd_size), _spent, _wb, _conf, _edg)
        _ap2_row = _log_intent(
            fid,
            team_code,
            float(usd_size),
            float(limit_price),
            _ctx.get("model_prob", 0.0),
            _ctx.get("mid", 0.0),
            _ctx.get("edge", 0.0),
            _ok,
            _reason,
        )
        if not _ok:
            return 402, {"error": f"AP2 mandate blocked: {_reason}"}
    except Exception as _ap2_err:
        return 402, {
            "error": f"AP2 mandate check errored (fail-closed): {_ap2_err}"
        }

    payload = {
        "fixture_id": str(fid),
        "team_code": team_code,
        "usd_size": f"{float(usd_size):.2f}",
        "limit_price": round(float(limit_price), 2),
        "time_in_force_seconds": TIF_SECONDS,
        "idempotency_key": str(uuid.uuid4()),
    }
    o_sc, o_resp = _post("/api/v1/arena/orders", payload)
    # AP2 post-flight: record the outcome
    if _AP2 and _ap2_row:
        try:
            if o_sc in (200, 201):
                _order_id = (
                    str(o_resp.get("order_id") or o_resp.get("id") or "")
                    if isinstance(o_resp, dict)
                    else ""
                )
                _log_result(_ap2_row, _order_id or None, "placed")
            else:
                _err_msg = (
                    str(o_resp.get("error") or o_resp.get("message") or o_resp)
                    if isinstance(o_resp, dict)
                    else str(o_resp)
                )
                _log_result(_ap2_row, None, "failed", _err_msg[:500])
        except Exception:
            pass
    return o_sc, o_resp


def run_autoplace(
    limit=40,
    conf_min=CONF_MIN_DEFAULT,
    edge_min=EDGE_MIN_DEFAULT,
    max_usd=MAX_USD_PER_BET,
    dry_run=False,
):
    wallet = get_wallet()
    if not wallet:
        return {"error": "Could not load arena wallet (check STAIR_AI_API_KEY)."}
    wallet_balance = wallet["available_balance_usdc"]
    budget = max(0.0, wallet_balance - WALLET_BUFFER)
    per_bet_cap = min(max_usd, MAX_USD_PER_BET)

    # Manual /place path honors the same research-derived gates as the
    # autopilot (2026-07-10): Forebet confirmation and the conviction cap.
    # Previously this path bypassed both — one localhost curl could commit
    # the wallet to unconfirmed bug-sized-"edge" picks.
    _risk = _load_risk_settings()
    _cands = analyze(
        limit, conf_min, edge_min, per_bet_cap, wallet_balance=wallet_balance
    )
    try:
        _tips = _get_tipster_picks()
        for c in _cands:
            c["tipster_confirmed"] = _tipster_agrees(
                _tips, c.get("match", ""), c.get("outcome", "")
            )
    except Exception as _tip_err:
        print(f"[arena] tipster annotate failed (run_autoplace): {_tip_err}")
    picks = [
        c
        for c in _cands
        if c["qualifies"]
        and not _forebet_gate_blocked(c, _risk)
        and not _conviction_capped(c, _risk)
    ]
    results = []
    spent = 0.0
    placed = 0
    now_ts = time.time()
    for c in picks:
        ko = c.get("kickoff_ts")
        if ko and ko <= now_ts:
            results.append(
                {**c, "status": "skipped", "reason": "match already started"}
            )
            continue
        if placed >= MAX_BETS_PER_RUN:
            results.append(
                {**c, "status": "skipped", "reason": "max bets per run reached"}
            )
            continue
        size = min(c["suggested_usd"], per_bet_cap, budget - spent)
        if size < MIN_USD_PER_BET:
            results.append(
                {**c, "status": "skipped", "reason": "insufficient remaining balance"}
            )
            continue
        size = round(size, 2)
        # Build rich, data-grounded reasoning trace for tournament scoring
        note = _build_reasoning_trace(c)
        if dry_run:
            results.append({**c, "status": "dry_run", "would_stake_usd": size})
            spent += size
            placed += 1
            continue
        l_sc, l_resp = submit_ledger(
            c["fixture_id"], c["team_code"], c["model_prob"], note
        )
        _ap2_set_ctx(
            model_prob=c.get("model_prob", 1.0),
            mid=c.get("market_mid", 0.0),
            edge=c.get("edge", 1.0),
            wallet_balance=wallet_balance if wallet_balance is not None else 999.0,
        )
        o_sc, o_resp = place_order(
            c["fixture_id"], c["team_code"], size, c["limit_price"]
        )
        ok = o_sc in (200, 201)
        if ok:
            spent += size
            placed += 1
            # Cross-path bookkeeping (2026-07-10 review finding): record the
            # pick + spend in the autopilot state so the 60s loop neither
            # re-bets a fixture the manual path just bet, nor overshoots the
            # daily cap by not seeing this spend.
            try:
                with _state_lock:
                    _st = _load_state()
                    _k = _pick_key(c)
                    if _k not in _st.get("placed_keys", []):
                        _st.setdefault("placed_keys", []).append(_k)
                    _daily = _st.setdefault("daily", {"date": _today(), "spent": 0.0})
                    _daily["spent"] = round(float(_daily.get("spent", 0.0)) + size, 2)
                    _save_state(_st)
            except Exception as _bk_err:
                print(f"[arena] run_autoplace state bookkeeping failed: {_bk_err}")
        results.append(
            {
                **c,
                "status": "placed" if ok else "order_failed",
                "staked_usd": size,
                "ledger_status": l_sc,
                "order_status": o_sc,
                "order_response": o_resp,
            }
        )
    return {
        "wallet": wallet,
        "budget": round(budget, 2),
        "qualifying": len(picks),
        "placed": placed,
        "total_staked": round(spent, 2),
        "dry_run": dry_run,
        "results": results,
    }


# ---------------------------------------------------------------------------
# Autopilot — fully autonomous betting loop (no user interaction)
# ---------------------------------------------------------------------------
SCAN_INTERVAL = 60  # scan every minute — catch every pre-kickoff window
AUTO_SCAN_LIMIT = 104  # look at all upcoming WC fixtures each cycle
DAILY_SPEND_CAP = 25.0  # hard ceiling on new real-money stake per UTC day
STATE_FILE = os.path.join(
    os.path.dirname(__file__), "..", "data", "arena_autopilot.json"
)

_state_lock = threading.Lock()
_autopilot_started = False


def _today():
    return time.strftime("%Y-%m-%d", time.gmtime())


def _default_settings():
    return {
        "conf_min": CONF_MIN_DEFAULT,
        "edge_min": EDGE_MIN_DEFAULT,
        "max_per_bet": MAX_USD_PER_BET,
        "max_bets_per_run": MAX_BETS_PER_RUN,
        # Capital-velocity rule: only bet games kicking off within this window
        # so the bankroll recycles match-to-match instead of sitting locked in
        # fixtures days away (which also have the thinnest order books).
        "bet_window_hours": 24,
    }


def _default_state():
    return {
        # Starts PAUSED for the real-money safety gate; one "Resume" click on the
        # arena page arms it, after which it runs fully autonomously (state persists).
        "enabled": False,
        "last_scan_ts": None,
        "next_scan_ts": None,
        "last_summary": "starting…",
        "last_error": None,
        "daily": {"date": _today(), "spent": 0.0},
        "placed_keys": [],  # (fixture:outcome) already bet — dedup
        "failed_keys": {},  # (fixture:outcome) -> failure count — stop retrying after MAX_FAIL_RETRIES
        "placed": [],  # newest-first log of auto-bets
        "last_candidates": [],  # qualifying picks from the last cycle
        "settings": _default_settings(),  # live-editable thresholds
        # --- positions, orders, P&L tracking ---
        "positions": [],  # current token holdings from /exposure
        "orders_recent": [],  # recent orders from /orders
        "settlements": [],  # settled matches with outcomes
        "pnl": {
            "unrealized": 0.0,
            "realized": 0.0,
            "total_staked": 0.0,
            "total_value": 0.0,
        },
        "leaderboard_rank": None,  # agent's rank on the leaderboard
        "tournament": None,  # tournament info (start date, participants, etc.)
    }


def _load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            base = _default_state()
            base.update(json.load(f))
            # NOTE: failed_keys intentionally NOT cleared on restart.
            # fixture_not_listed failures are permanent (no Polymarket market exists);
            # wiping the counter on restart just causes infinite re-hammering.
            # The daily date-change reset in autopilot_cycle() clears them at a
            # sensible cadence (new day = new fixtures, fresh start).
            return base
    except (OSError, ValueError):
        return _default_state()


def _save_state(state):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except OSError:
        pass


def _pick_key(c):
    return f"{c['fixture_id']}:{c['outcome']}"


# ---------------------------------------------------------------------------
# Drawdown protection — Phase 1 risk management (2026-07-09)
#
# Tracks each UTC day's STARTING available-cash balance (not total equity —
# open-position mark value is excluded, matching the spec's literal "starting
# daily bankroll" wording) and maps same-day drawdown from that baseline to a
# configurable Kelly-multiplier tier. Confirmed with the user: the baseline is
# a FRESH snapshot taken the first time this code runs each day — it does not
# retroactively count any pre-existing unrealized loss against the new tiers.
# ---------------------------------------------------------------------------
def _update_drawdown_state(state, wallet_balance, risk_cfg):
    """
    Snapshot today's starting Arena wallet balance once per UTC day, compute
    drawdown_pct against it, and map to the configured Kelly-multiplier tier.

    Mutates state["daily"]["start_balance"] (persisted by the caller's
    subsequent _save_state()). Returns a dict with drawdown_pct,
    kelly_multiplier, and disable_directional. Never raises — any bad input
    (missing/zero/negative wallet_balance, malformed tiers) resolves to the
    "no drawdown" default so a data hiccup can never accidentally halt or
    (via a bug) accidentally loosen live betting.
    """
    daily = state.setdefault("daily", {})
    start_balance = daily.get("start_balance")

    if start_balance is None:
        # New day (or first cycle ever after this feature was deployed to an
        # existing arena_autopilot.json). Snapshot now rather than inventing a
        # retroactive baseline — see module docstring above.
        daily["start_balance"] = wallet_balance
        return {"drawdown_pct": 0.0, "kelly_multiplier": 1.0, "disable_directional": False}

    try:
        start_balance = float(start_balance)
        wallet_balance = float(wallet_balance)
    except (TypeError, ValueError):
        return {"drawdown_pct": 0.0, "kelly_multiplier": 1.0, "disable_directional": False}

    if start_balance <= 0:
        drawdown_pct = 0.0
    else:
        drawdown_pct = max(0.0, (start_balance - wallet_balance) / start_balance)

    if not risk_cfg.get("drawdown_protection_enabled", True):
        # Still report the real percentage for UI/operator visibility even
        # when the feature is switched off — only the ENFORCEMENT is skipped.
        return {"drawdown_pct": drawdown_pct, "kelly_multiplier": 1.0, "disable_directional": False}

    for tier in risk_cfg.get("drawdown_tiers") or _DEFAULT_DRAWDOWN_TIERS:
        if drawdown_pct >= tier["drawdown_pct"]:
            return {
                "drawdown_pct": drawdown_pct,
                "kelly_multiplier": tier["kelly_multiplier"],
                "disable_directional": tier["disable_directional"],
            }
    return {"drawdown_pct": drawdown_pct, "kelly_multiplier": 1.0, "disable_directional": False}


def _forebet_gate_blocked(c, risk_cfg):
    """
    True if this candidate must be skipped under the Forebet-confirmation
    gate (Phase 13, configurable — see arena_forebet_required /
    arena_arb_enabled). Defaults (True, True) reproduce the unconditional
    2026-07-06 FOREBET-ONLY MODE behavior exactly.
    """
    arb_exempt = risk_cfg["arb_enabled"] and c.get("real_arb")
    return bool(risk_cfg["forebet_required"] and not c.get("tipster_confirmed") and not arb_exempt)


def _conviction_capped(c, risk_cfg):
    """
    True if this pick must be skipped because the model disagrees with the
    market by more than arena_edge_cap_pp (default 20pp).

    Rationale (2026-07-10): the project's 2,386-bet out-of-sample line study
    showed the model's LARGEST disagreements with the market are its largest
    errors — raising the edge bar made ROI monotonically worse. The two
    biggest recent real-money orders were placed at "66.5pp" and "72.3pp"
    edges (France $87.05, Argentina $35.17 — model ~80% vs market mid 8-14%),
    numbers only a mapping/data bug or model failure produces. The paper
    daemon has enforced edge_cap_pct=10 since 2026-06-14; this brings the
    same protection to the real-money arena path. Real arbitrage is exempt:
    it is structural (sum of asks < $1), not model-conviction-driven.
    """
    if c.get("real_arb"):
        return False
    cap = float(risk_cfg.get("edge_cap_pp", 20.0))
    edge_pp = c.get("edge_pp")
    if edge_pp is None:
        edge_pp = (c.get("edge") or 0.0) * 100.0
    return float(edge_pp) > cap


def _directional_blocked(c, dd_info):
    """
    True if this candidate must be skipped under the current drawdown tier.

    Real arbitrage picks are NEVER blocked, per spec ("never disable
    arbitrage") — this checks the structural c["real_arb"] flag (computed in
    analyze() from sum(mids) < 1), not an edge threshold, since an
    edge-threshold approximation would also suppress genuine arb picks.
    """
    return bool(dd_info.get("disable_directional")) and not c.get("real_arb")


def _current_calibration_and_execution_scores(state, risk_cfg):
    """
    Phase 10 (Adaptive Kelly) — the two GLOBAL (not per-candidate) sub-scores:
    calibration (from settled Arena bets' ECE) and execution (from
    execution_log.db's recorded slippage). Computed once per cycle, not once
    per candidate. Both default to the neutral 1.0 when there isn't yet
    enough settled/fill data — see adaptive_kelly.py's module docstring for
    why "unknown" must not be penalized the same as "known to be bad."
    """
    settled = _settlement_map(state)
    probs, outcomes = [], []
    for p in state.get("placed", []) or []:
        if not p.get("ok"):
            continue
        winning_outcome = settled.get(str(p.get("fixture_id")))
        if winning_outcome is None or p.get("model_prob") is None:
            continue
        probs.append(float(p["model_prob"]))
        outcomes.append(1 if p.get("outcome") == winning_outcome else 0)
    ece = _expected_calibration_error(probs, outcomes) if probs else None
    calibration = _adaptive_kelly.calibration_score(ece, ece_cap=risk_cfg["adaptive_kelly_ece_cap"])

    try:
        slip = _exec_analytics.slippage_report()
        avg_slippage = slip.get("avg_slippage")
    except Exception:
        avg_slippage = None
    execution = _adaptive_kelly.execution_score(avg_slippage, slippage_cap=risk_cfg["adaptive_kelly_slippage_cap"])
    return calibration, execution


def _settled_outcome_label(settled_team_code, fid):
    """
    Convert a settlement's team-code result (e.g. "COL", or the literal
    "draw") into this project's home/draw/away outcome convention — matching
    how p["outcome"] is stored on placed bets — using the match's own
    home/away short codes from the Polymarket mapping. Falls back to
    returning the raw team code unconverted if the mapping can't be found
    (better than silently dropping the settlement) — but this can then fail
    to match p["outcome"] downstream, which is why get_mapping()'s
    availability matters here.
    """
    if settled_team_code == "draw":
        return "draw"
    m = get_mapping(fid)
    if not m:
        return settled_team_code
    if settled_team_code == m.get("home_short_code"):
        return "home"
    if settled_team_code == m.get("away_short_code"):
        return "away"
    return settled_team_code


def _check_settlements(state):
    """
    Check every ok=True placed bet's fixture for a real-world settlement via
    GET /api/v1/data/polymarket/markets/{fixture_id}/settlement, and append
    any newly-settled fixtures to state["settlements"] (deduped, capped at
    50, newest first). Mutates `state` in place; returns the list of newly
    detected settlements (same shape appended to state["settlements"]).

    Bug fixed 2026-07-09: this previously never detected ANY settlement,
    for two independent reasons, both now corrected:
    1. It checked `s.get("settled")` (a boolean key) — the real API returns
       `"status": "settled"` (a string field), which is what's checked now.
    2. Even when settled, it stored the raw team-code winner (e.g. "COL")
       directly as `outcome` — but every other consumer of
       state["settlements"] (attribution_engine.settlement_map(), the
       calibration/CLV/reporting tools) compares against p["outcome"], which
       is stored as "home"/"draw"/"away". Team codes never matched that
       convention, so even a "successfully detected" settlement would have
       silently failed to line up with any bet. See _settled_outcome_label().

    The ID passed to get_settlement() is always the raw Sportmonks numeric
    fixture_id (same as p["fixture_id"]) — confirmed empirically 2026-07-09
    that this endpoint does NOT need a separate "Polymarket fixture_id"; the
    previous `polymarket_fid` indirection was based on an incorrect
    assumption and is no longer used for settlement lookups.
    """
    settled_fids = set()
    new_settlements = []
    for p in state.get("placed", []):
        fid = p.get("fixture_id")
        if not fid or not p.get("ok") or fid in settled_fids:
            continue
        settled_fids.add(fid)
        s = get_settlement(fid)
        if not (s and isinstance(s, dict) and s.get("status") == "settled"):
            continue
        settled_team_code = s.get("settled_outcome") or s.get("outcome") or s.get("winning_outcome")
        if settled_team_code is None:
            continue
        new_settlements.append(
            {
                "fixture_id": fid,
                "outcome": _settled_outcome_label(settled_team_code, fid),
                "settled_team_code": settled_team_code,
                "resolved_at": s.get("settled_at") or s.get("resolved_at") or s.get("settlement_time"),
            }
        )
    if new_settlements:
        existing = {s["fixture_id"] for s in state.get("settlements", [])}
        for ns in new_settlements:
            if ns["fixture_id"] not in existing:
                state.setdefault("settlements", []).insert(0, ns)
        state["settlements"] = state["settlements"][:50]
    return new_settlements


def _directional_bet_size(suggested_usd, risk_cfg, max_per_bet, room):
    """
    Final per-pick stake for a qualifying, non-blocked directional/arb pick.

    Pure Kelly (already drawdown-adjusted upstream via analyze()'s
    kelly_fraction param) — no forced minimum-of-wallet floor. Still capped by
    the per-bet ceiling and remaining run/day budget (`room`).
    """
    return round(
        min(
            suggested_usd or risk_cfg["minimum_bet"],
            risk_cfg["maximum_bet"],
            max_per_bet,
            room,
        ),
        2,
    )


# ---------------------------------------------------------------------------
# Tipster confirmation — research-validated best strategy (2026-07-06):
# TIPSTER_FOREBET is the ONLY paper strategy whose 95% CI is entirely above
# zero (+41.7% ROI, CI [+14.5%, +68.9%], n=259 since the ledger cleanup).
# The arena boosts picks Forebet agrees with and halves stakes on the rest.
# ---------------------------------------------------------------------------
_tipster_cache = {"ts": 0.0, "picks": []}
_TIPSTER_TTL = 1800  # 30 min — Forebet updates slowly

_SIDE_TO_OUTCOME = {"Home (1)": "home", "Draw (X)": "draw", "Away (2)": "away"}


def _get_tipster_picks():
    now = time.time()
    if _tipster_cache["picks"] and now - _tipster_cache["ts"] < _TIPSTER_TTL:
        return _tipster_cache["picks"]
    picks = []
    try:
        import datetime as _dtm

        from src.tipster_scraper import get_forebet_predictions

        today = _dtm.date.today()
        picks = list(get_forebet_predictions(today.isoformat()) or [])
        try:
            picks += get_forebet_predictions(
                (today + _dtm.timedelta(days=1)).isoformat()
            ) or []
        except Exception:
            pass  # tomorrow page is best-effort
    except Exception as e:
        print(f"[arena] tipster fetch failed (non-fatal): {e}")
    if picks:
        _tipster_cache["picks"] = picks
        _tipster_cache["ts"] = now
    return picks


def _tipster_agrees(picks, match_name, outcome):
    """True when Forebet's 1X2 pick for this match equals the candidate outcome."""
    if not picks or not match_name or not outcome:
        return False
    try:
        home, away = [t.strip().lower() for t in match_name.split(" vs ")[:2]]
    except ValueError:
        return False
    for p in picks:
        ph = (p.get("home_team") or "").strip().lower()
        pa = (p.get("away_team") or "").strip().lower()
        if not ph or not pa:
            continue
        if (ph in home or home in ph) and (pa in away or away in pa):
            return _SIDE_TO_OUTCOME.get(p.get("predicted_side") or "") == outcome
    return False


def autopilot_cycle():
    """One autonomous scan + bet pass. Bets only on qualifying, pre-kickoff WC picks.

    Ledger submissions (predictions that count for leaderboard P&L) ALWAYS fire for
    every qualifying pre-kickoff pick — even when DEEPFIELD_ARENA_LIVE is off.
    Real-money orders are gated by DEEPFIELD_ARENA_LIVE=1 AND enabled=True.
    """
    with _state_lock:
        state = _load_state()
    state["last_scan_ts"] = time.time()
    state["next_scan_ts"] = time.time() + SCAN_INTERVAL

    arena_live = _arena_live()
    autopilot_enabled = arena_live and state.get("enabled", False)

    if state["daily"].get("date") != _today():
        state["daily"] = {"date": _today(), "spent": 0.0}
        state["failed_keys"] = (
            {}
        )  # new day → fresh start, don't carry yesterday's failures

    wallet = get_wallet()
    wallet_balance = wallet["available_balance_usdc"] if wallet else 0.0
    budget = max(0.0, wallet_balance - WALLET_BUFFER) if wallet else 0.0
    daily_remaining = max(0.0, DAILY_SPEND_CAP - state["daily"]["spent"])

    # Phase 1 risk management: operator-level Kelly/drawdown config, read
    # fresh each cycle, and the resulting drawdown tier for TODAY. Must run
    # after the date-rollover reset above so a new day's baseline snapshot
    # never reuses yesterday's start_balance.
    _risk = _load_risk_settings()
    dd_info = _update_drawdown_state(state, wallet_balance, _risk)

    # Phase 10 (Adaptive Kelly) — global sub-scores, computed once per cycle
    # (not per candidate). Off by default (arena_adaptive_kelly_enabled);
    # skip the DB reads entirely when disabled.
    if _risk["adaptive_kelly_enabled"]:
        _calibration_score, _execution_score = _current_calibration_and_execution_scores(state, _risk)
    else:
        _calibration_score = _execution_score = 1.0

    placed_keys = set(state.get("placed_keys", []))
    for _p in state.get("placed", []):
        if _p.get("ok"):
            placed_keys.add(_p["key"])
    ledger_keys = set(state.get("ledger_keys", []))
    now_ts = time.time()

    # Read live settings (user-adjustable from the UI)
    cfg = {**_default_settings(), **state.get("settings", {})}
    _conf_min = cfg["conf_min"]
    _edge_min = cfg["edge_min"]
    _max_per_bet = cfg["max_per_bet"]
    _max_bets = cfg["max_bets_per_run"]
    _window_sec = float(cfg.get("bet_window_hours") or 24) * 3600.0

    all_candidates = analyze(
        AUTO_SCAN_LIMIT,
        conf_min=_conf_min,
        edge_min=_edge_min,
        wallet_balance=wallet_balance or None,
        kelly_fraction=_risk["kelly_fraction"] * dd_info["kelly_multiplier"],
    )
    qualifying = [c for c in all_candidates if c["qualifies"]]

    # Tipster confirmation — the research ledger's only CI-above-zero strategy.
    try:
        _tips = _get_tipster_picks()
        for c in all_candidates:
            c["tipster_confirmed"] = _tipster_agrees(
                _tips, c.get("match", ""), c.get("outcome", "")
            )
    except Exception as _tip_err:
        print(f"[arena] tipster annotate failed: {_tip_err}")

    # Sort order: real arb first (guaranteed profit), then TIPSTER-confirmed
    # (research: +41.7% ROI, only CI>0 strategy), then steam-confirmed
    # (demoted — POLY_STEAM's live record is 0-3), then edge descending.
    def _sort_key(c):
        arb_bonus = 1000 if c.get("real_arb") else 0
        tip_bonus = 200 if c.get("tipster_confirmed") else 0
        steam_bonus = 10 if c.get("steam_confirmed") and (c.get("steam_move") or 0) > 0 else 0
        return arb_bonus + tip_bonus + steam_bonus + (c.get("edge", 0) * 10)

    qualifying.sort(key=_sort_key, reverse=True)
    state["last_candidates"] = qualifying[:50]
    # All scanned matches with edge info (for the "all matches" edge table in the UI)
    _keep = (
        "match",
        "kickoff",
        "team_code",
        "outcome",
        "model_prob",
        "market_mid",
        "edge_pp",
        "qualifies",
        "suggested_usd",
        "kickoff_ts",
        "real_arb",
        "arb_profit_pp",
        "market_vig_pp",
        "steam_move",
        "steam_confirmed",
        "tipster_confirmed",
        "devigged_mid",
        "edge_vs_devigged",
        "grade",
    )
    state["last_all_candidates"] = sorted(
        [{k: c[k] for k in _keep if k in c} for c in all_candidates],
        key=lambda x: x.get("edge_pp", 0) or 0,
        reverse=True,
    )[:100]

    spent = 0.0
    placed_now = 0
    ledger_now = 0

    # Submit ledger predictions for ALL pre-kickoff WC outcomes (not just qualifying ones).
    # Every prediction counts toward the leaderboard regardless of whether we place an order.
    for c in all_candidates:
        key = _pick_key(c)
        sm_key_l = f"{c.get('sportmonks_fixture_id', '')}:{c['outcome']}"
        ko = c.get("kickoff_ts")
        if ko and ko <= now_ts:
            continue
        if key not in ledger_keys and sm_key_l not in ledger_keys:
            # Build rich, data-grounded reasoning trace for tournament scoring
            note = _build_reasoning_trace(c)
            submit_ledger(c["fixture_id"], c["team_code"], c["model_prob"], note)
            ledger_keys.add(key)
            if sm_key_l:
                ledger_keys.add(sm_key_l)
            ledger_now += 1

    # Real-money orders only for qualifying picks when live gate is armed.
    for c in qualifying:
        key = _pick_key(c)
        sm_key = f"{c.get('sportmonks_fixture_id', '')}:{c['outcome']}"
        ko = c.get("kickoff_ts")
        if ko and ko <= now_ts:
            continue
        # Capital-velocity window: only bet games kicking off within the next
        # N hours — cash stays free to compound instead of sitting locked in
        # far-out fixtures with the thinnest books. (Ledger picks above are
        # exempt: they cost nothing and score on every fixture.)
        if ko and ko > now_ts + _window_sec:
            continue

        # Real-money orders only when live gate is armed.
        if not autopilot_enabled:
            continue
        if placed_now >= _max_bets:
            continue
        if key in placed_keys or (sm_key and sm_key in placed_keys):
            continue
        failed_keys = state.get("failed_keys", {})
        if failed_keys.get(key, 0) >= MAX_FAIL_RETRIES:
            continue  # stop hammering a bet that keeps failing
        # Cooldown for market-not-ready picks (thin knockout books / late token
        # linking): retried every 30 min instead of permanently blocked.
        if state.get("retry_after", {}).get(key, 0) > now_ts:
            continue
        # FOREBET-ONLY MODE (user directive 2026-07-06): the autopilot bets
        # ONLY picks Forebet agrees with — the sole strategy whose research CI
        # is entirely above zero. Exception: real arbitrages (guaranteed profit).
        # Phase 13 (2026-07-09): both the overall requirement and the arb
        # exception are now configurable (arena_forebet_required,
        # arena_arb_enabled) — defaults (True, True) preserve this exact
        # behavior for anyone who hasn't touched settings.json.
        if _forebet_gate_blocked(c, _risk):
            continue
        # Conviction cap (2026-07-10): a model-vs-market gap beyond
        # arena_edge_cap_pp is treated as error, not value — skip it.
        if _conviction_capped(c, _risk):
            continue
        # Drawdown circuit breaker (Phase 1, 2026-07-09): at the worst
        # configured tier, new directional bets are hard-blocked regardless of
        # sizing math — real arbitrage is NEVER blocked (see _directional_blocked()).
        if _directional_blocked(c, dd_info):
            continue
        room = min(budget - spent, daily_remaining - spent)
        # Pure Kelly sizing (Phase 1, 2026-07-09): the old "never less than 40%
        # of wallet" floor is removed — c["suggested_usd"] already reflects the
        # configured kelly_fraction and any drawdown-tier multiplier applied
        # upstream in analyze(). Capped by the per-bet ceiling and remaining
        # run/day budget only.
        size = _directional_bet_size(c["suggested_usd"], _risk, _max_per_bet, room)
        if size < _risk["minimum_bet"]:
            continue

        # Phase 2 (2026-07-09): pre-trade liquidity gate. Fails OPEN (does not
        # block) if the order book can't be fetched — a data-proxy hiccup
        # must never silently halt all betting — but rejects when the book IS
        # available and shows insufficient depth for the desired size.
        book = get_order_book(c.get("token_id"))
        liq_ok, liq_metrics = _exec_analytics.liquidity_gate_ok(
            book,
            c.get("market_mid", 0.0),
            desired_usd=size,
            required_multiple=_risk["required_liquidity_multiple"],
            band_pct=_risk["liquidity_check_pct"],
        )
        if _risk["liquidity_gate_enabled"] and not liq_ok:
            state.setdefault("liquidity_rejections", []).insert(
                0,
                {
                    "key": key,
                    "match": c["match"],
                    "team_code": c["team_code"],
                    "desired_usd": size,
                    "liquidity_metrics": liq_metrics,
                    "ts": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
                },
            )
            state["liquidity_rejections"] = state["liquidity_rejections"][:50]
            continue

        # Phase 10 (Adaptive Kelly, 2026-07-09): optional composite sizing
        # multiplier (Kelly x calibration x execution x liquidity x market
        # quality). Off by default. liquidity/market-quality are PER-PICK
        # (reuse the book/vig data already fetched above for the liquidity
        # gate); calibration/execution are the per-cycle globals computed
        # once, before this loop.
        if _risk["adaptive_kelly_enabled"]:
            _band_label = {0.005: "liq_0.5pct", 0.01: "liq_1pct", 0.02: "liq_2pct", 0.03: "liq_3pct"}.get(
                _risk["liquidity_check_pct"], "liq_1pct"
            )
            _liquidity_score = _adaptive_kelly.liquidity_score(
                liq_metrics.get(_band_label, 0.0), size, _risk["required_liquidity_multiple"]
            )
            _market_quality_score = _adaptive_kelly.market_quality_score(
                c.get("market_vig_pp"), vig_cap_pp=_risk["adaptive_kelly_vig_cap_pp"]
            )
            size = _adaptive_kelly.adaptive_kelly_size(
                size, _calibration_score, _execution_score, _liquidity_score, _market_quality_score
            )
            if size < _risk["minimum_bet"]:
                continue

        signal_ts = time.time()
        best_bid, best_ask = _exec_analytics.best_bid_ask(book)
        _ap2_set_ctx(
            model_prob=c.get("model_prob", 1.0),
            mid=c.get("market_mid", 0.0),
            edge=c.get("edge", 1.0),
            wallet_balance=wallet_balance,
        )
        o_sc, o_resp = place_order(
            c["fixture_id"], c["team_code"], size, c["limit_price"]
        )
        ok = o_sc in (200, 201)
        if ok:
            _order_id_for_log = (
                str(o_resp.get("order_id") or o_resp.get("id") or "")
                if isinstance(o_resp, dict)
                else ""
            )
            try:
                _exec_analytics.log_signal(
                    {
                        "order_id": _order_id_for_log or key,
                        "signal_ts": signal_ts,
                        "fixture_id": c["fixture_id"],
                        "match": c["match"],
                        "outcome": c["outcome"],
                        "model_prob": c.get("model_prob"),
                        "fair_prob": c.get("devigged_mid"),
                        "market_mid": c.get("market_mid"),
                        "best_bid": best_bid,
                        "best_ask": best_ask,
                        "spread": (best_ask - best_bid) if (best_bid is not None and best_ask is not None) else None,
                        "requested_size": size,
                        "limit_price": c.get("limit_price"),
                        "liquidity_depth": liq_metrics,
                        "ev_at_signal": c.get("edge", 0.0) * size,
                        "kickoff_ts": c.get("kickoff_ts"),
                    }
                )
            except Exception as _log_exc:
                print(f"[arena] execution_analytics.log_signal failed (non-fatal): {_log_exc}")
        state["placed"].insert(
            0,
            {
                "key": key,
                "fixture_id": c["fixture_id"],
                "polymarket_fid": c.get("polymarket_fid"),  # for settlement lookup
                "match": c["match"],
                "team_code": c["team_code"],
                "outcome": c["outcome"],
                "model_prob": c["model_prob"],
                "market_mid": c["market_mid"],
                "edge_pp": c["edge_pp"],
                "staked_usd": size,
                "limit_price": c["limit_price"],
                "kickoff": c["kickoff"],
                "order_status": o_sc,
                "order_response": str(o_resp)[:500] if o_resp else None,
                "ok": ok,
                "prob_source": c["prob_source"],
                "ts": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
            },
        )
        if ok:
            placed_keys.add(key)
            if sm_key:
                placed_keys.add(sm_key)
            spent += size
            placed_now += 1
            # One push per placed bet — fires exactly once when the order is confirmed
            try:
                from src.services.alerting import notifier as _n
                import datetime as _dt

                ko_str = c.get("kickoff", "")
                try:
                    ko_dt = _dt.datetime.strptime(ko_str[:16], "%Y-%m-%d %H:%M")
                    ko_label = ko_dt.strftime("%b %d, %H:%M UTC")
                except Exception:
                    ko_label = ko_str[:16]
                outcome_label = {
                    "home": c["match"].split(" vs ")[0].strip() + " to win",
                    "away": c["match"].split(" vs ")[-1].strip() + " to win",
                    "draw": "Draw",
                }.get(c["outcome"], c["outcome"].upper())
                _n._notify(
                    f"FIFA World Cup 2026\n"
                    f"{c['match']}\n"
                    f"Kickoff: {ko_label}\n"
                    f"Pick: {outcome_label} ({c['team_code']})\n"
                    f"Edge: +{c['edge_pp']}pp | Staked: ${size:.2f}",
                    title="Bet Placed",
                    priority="high",
                    tags="money_with_wings,soccer",
                )
            except Exception:
                pass
        else:
            # Only count real API failures (4xx/5xx) — status=0 means the live
            # gate blocked internally, and 402 means the AP2 mandate (or its
            # fail-closed error path) blocked for BUDGET reasons (daily cap,
            # per-order cap). Neither is the pick's fault — blacklisting a good
            # pick because the day's budget ran out would silently kill it for
            # the whole day (2026-07-10 review finding).
            if o_sc > 0 and o_sc != 402:
                err_body = str(o_resp).lower() if o_resp else ""
                fk = state.setdefault("failed_keys", {})
                # "No Polymarket market linked" is NOT permanent in the knockout
                # rounds — tokens link days late (Argentina, France both did).
                # Cool the pick down 30 min and retry until kickoff instead of
                # blacklisting it. Real API errors still increment toward
                # MAX_FAIL_RETRIES (auth failures, rate limits may self-heal).
                if "fixture_not_listed" in err_body or "no polymarket market" in err_body:
                    state.setdefault("retry_after", {})[key] = now_ts + 1800
                else:
                    fk[key] = fk.get(key, 0) + 1

    state["placed_keys"] = list(placed_keys)
    state["ledger_keys"] = list(ledger_keys)
    state["placed"] = state["placed"][:200]
    state["daily"]["spent"] = round(state["daily"]["spent"] + spent, 2)
    state["last_error"] = None

    # --- Fetch exposure (positions), recent orders, and settlements ---
    try:
        exposure = get_exposure()
        if exposure and isinstance(exposure, dict):
            holdings = exposure.get("holdings") or exposure.get("positions") or []
            if not isinstance(holdings, list):
                holdings = []
            state["positions"] = [
                {
                    "token_id": h.get("outcome_token_id") or h.get("token_id", ""),
                    "fixture_id": h.get("fixture_id", ""),
                    "outcome": h.get("team_code") or h.get("outcome", ""),
                    "quantity": float(h.get("quantity", 0) or 0),
                    "avg_cost": float(h.get("avg_cost_usdc", 0) or 0),
                    "mark_price": float(h.get("mark_price", 0) or 0),
                    "value_usd": float(h.get("value_usdc", 0) or 0),
                    "unrealized_pnl": float(h.get("unrealized_pnl_usdc", 0) or 0),
                }
                for h in holdings[:50]
            ]
            # Aggregate P&L
            total_value = sum(p["value_usd"] for p in state["positions"])
            total_cost = sum(p["avg_cost"] * p["quantity"] for p in state["positions"])
            total_unrealized = sum(p["unrealized_pnl"] for p in state["positions"])
            state["pnl"]["total_value"] = round(total_value, 2)
            state["pnl"]["total_staked"] = round(total_cost, 2)
            state["pnl"]["unrealized"] = round(total_unrealized, 2)
    except Exception as e:
        state["last_error"] = f"exposure fetch error: {str(e)[:100]}"

    # Drawdown audit trail (Phase 1, 2026-07-09) — persisted after the PnL
    # refresh above so realized/unrealized reflect this cycle, not last cycle's.
    state["drawdown"] = {
        "date": _today(),
        "start_balance": state["daily"].get("start_balance"),
        "current_balance": wallet_balance,
        "drawdown_pct": dd_info["drawdown_pct"],
        "kelly_multiplier": dd_info["kelly_multiplier"],
        "directional_disabled": dd_info["disable_directional"],
        "realized_pnl": state["pnl"].get("realized", 0.0),
        "unrealized_pnl": state["pnl"].get("unrealized", 0.0),
    }

    # Recent orders
    try:
        recent_orders = list_orders(
            status="unfilled,processing,filled,closing,closed,settled,completed,rejected"
        )
        # Fills first — retry hunters generate rejected orders every few
        # minutes, which otherwise push real fills out of the 30-row window
        # and blank the UI's bet feed / W-L record.
        recent_orders = sorted(
            recent_orders or [],
            key=lambda o: 0
            if (o.get("status") or "").lower()
            in ("completed", "filled", "settled", "closed")
            else 1,
        )
        state["orders_recent"] = [
            {
                "order_id": o.get("order_id") or o.get("id", ""),
                "fixture_id": o.get("fixture_id", ""),
                "team_code": o.get("team_code", ""),
                "status": o.get("status", ""),
                "usd_size": o.get("usd_size") or o.get("usd_size_filled", "0"),
                "limit_price": o.get("limit_price", 0),
                "fill_price": o.get("open_avg_fill_price")
                or o.get("fill_price")
                or o.get("avg_fill_price"),
                "realized_pnl": o.get("realized_pnl_usdc") or o.get("realized_pnl"),
                "window": o.get("window", ""),
                "submitted_at": o.get("submitted_at") or o.get("created_at"),
            }
            for o in (recent_orders or [])[:30]
        ]

        # Phase 2 (2026-07-09): backfill execution_log fill data for orders
        # that have reached a terminal filled/settled state. Best-effort —
        # a failure here must never break order reconciliation below.
        try:
            for o in state["orders_recent"]:
                if (o.get("status") or "").lower() in ("filled", "completed", "settled", "closed"):
                    oid = o.get("order_id")
                    if oid and o.get("fill_price") is not None:
                        _exec_analytics.update_fill(
                            str(oid),
                            filled_size=o.get("usd_size"),
                            fill_price=o.get("fill_price"),
                        )
        except Exception as _fill_log_exc:
            print(f"[arena] execution_analytics fill backfill failed (non-fatal): {_fill_log_exc}")

        # Reconcile: an order the exchange ACCEPTED then REJECTED (thin book,
        # FOK killed) never filled — its key must not sit in placed_keys or the
        # pick is silently never retried. Free the key with a 30-min cooldown.
        try:
            import re as _re2

            rejected_oids = {
                str(o.get("order_id") or "")
                for o in state["orders_recent"]
                if (o.get("status") or "").lower() == "rejected"
            }
            if rejected_oids:
                pk_now = set(state.get("placed_keys", []))
                freed = 0
                for p in state.get("placed", []):
                    m2 = _re2.search(
                        r"'order_id': '([0-9a-f\-]+)'",
                        str(p.get("order_response") or ""),
                    )
                    if not (m2 and m2.group(1) in rejected_oids):
                        continue
                    # CRITICAL: flip the history entry too — the top-of-cycle
                    # placed_keys rebuild re-adds every ok:True entry, which
                    # re-blocked the pick every cycle (the bet never fired).
                    if p.get("ok"):
                        p["ok"] = False
                        p["order_status"] = "rejected_reconciled"
                        freed += 1
                    for k2 in (
                        p.get("key"),
                        f"{p.get('fixture_id')}:{p.get('outcome')}",
                        f"{p.get('polymarket_fid')}:{p.get('outcome')}",
                    ):
                        if k2 and k2 in pk_now:
                            pk_now.discard(k2)
                            state.setdefault("retry_after", {})[k2] = (
                                time.time() + 1800
                            )
                if freed:
                    state["placed_keys"] = list(pk_now)
                    print(f"[arena] freed {freed} rejected-order keys for retry")
        except Exception:
            pass
    except Exception:
        pass

    # Settlements — check placed bets for settled matches (see _check_settlements()).
    try:
        _refresh_mapping_cache()
        new_settlements = _check_settlements(state)

        # Phase 2 (2026-07-09): backfill execution_log.final_settlement
        # for every placed order on a newly-settled fixture. Best-effort,
        # matches the order_id extraction pattern already used above for
        # the rejected-order reconciliation.
        if new_settlements:
            try:
                import re as _re3

                by_fixture = {ns["fixture_id"]: ns["outcome"] for ns in new_settlements}
                for p in state.get("placed", []):
                    outcome_result = by_fixture.get(p.get("fixture_id"))
                    if not outcome_result or not p.get("ok"):
                        continue
                    m3 = _re3.search(
                        r"'order_id': '([0-9a-f\-]+)'", str(p.get("order_response") or "")
                    )
                    if m3:
                        _exec_analytics.update_settlement(m3.group(1), outcome_result)
            except Exception as _settle_log_exc:
                print(f"[arena] execution_analytics settlement backfill failed (non-fatal): {_settle_log_exc}")

        # CLV tracking: for each placed bet, compare entry price vs Polymarket closing price.
        # closing price = last recorded Polymarket mid before kickoff from price_history.
        _clv_done = {r["key"] for r in state.get("clv_records", [])}
        for p in state.get("placed", []):
            if not p.get("ok"):
                continue
            pk = p.get("key", "")
            if pk in _clv_done:
                continue
            entry_price = p.get("limit_price")
            kickoff_str = p.get("kickoff", "")
            sm_fid = str(p.get("fixture_id", ""))
            outcome = p.get("outcome", "")
            if not entry_price or not kickoff_str or not sm_fid or not outcome:
                continue
            try:
                import sqlite3 as _sq3
                import datetime as _dtclv
                ko_dt = _dtclv.datetime.strptime(kickoff_str[:16], "%Y-%m-%d %H:%M")
                ko_unix = ko_dt.timestamp()
                _steam_db = os.path.join(os.path.dirname(__file__), "..", "data", "polymarket_steam.db")
                if not os.path.exists(_steam_db):
                    continue
                _c3 = _sq3.connect(_steam_db)
                row = _c3.execute(
                    "SELECT mid FROM price_history "
                    "WHERE fixture_id=? AND outcome=? AND recorded_at<=? "
                    "ORDER BY recorded_at DESC LIMIT 1",
                    (sm_fid, outcome, ko_unix),
                ).fetchone()
                _c3.close()
                if row:
                    closing_mid = row[0]
                    # CLV: positive = we bought cheaper than closing = positive EV proxy
                    clv_pp = round((closing_mid / entry_price - 1) * 100, 2)
                    state.setdefault("clv_records", []).insert(0, {
                        "key": pk,
                        "match": p.get("match", ""),
                        "outcome": outcome,
                        "entry_price": entry_price,
                        "closing_mid": closing_mid,
                        "clv_pp": clv_pp,
                        "ts": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
                    })
                    _clv_done.add(pk)
            except Exception:
                pass
        state["clv_records"] = state.get("clv_records", [])[:100]
    except Exception:
        pass

    # Leaderboard rank (check every 5th cycle to reduce API load)
    cycle_count = state.get("_cycle_count", 0) + 1
    state["_cycle_count"] = cycle_count
    if cycle_count % 5 == 0:
        try:
            lb = get_leaderboard(limit=100)
            if isinstance(lb, list):
                agent_id = (get_wallet() or {}).get("agent_id")
                for i, entry in enumerate(lb):
                    if entry.get("agent_id") == agent_id:
                        state["leaderboard_rank"] = i + 1
                        break
        except Exception:
            pass

    mode = (
        "LIVE"
        if autopilot_enabled
        else ("armed-predict-only" if arena_live else "predict-only")
    )
    pnl_r = state["pnl"].get("realized", 0)
    pnl_u = state["pnl"].get("unrealized", 0)
    state["last_summary"] = (
        f"[{mode}] {len(all_candidates)} scanned · {len(qualifying)} qualifying · "
        f"{ledger_now} ledger · {placed_now} bet · ${spent:.2f} staked · "
        f"PnL ${pnl_r:.2f}R/${pnl_u:.2f}U"
    )
    with _state_lock:
        # The cycle held this state in memory for its whole run; re-read the
        # LIVE user-editable fields from disk so a mid-cycle settings change
        # or pause toggle is never clobbered by our stale copy.
        try:
            _cur = _load_state()
            if isinstance(_cur.get("settings"), dict):
                state["settings"] = _cur["settings"]
            if "enabled" in _cur:
                state["enabled"] = _cur["enabled"]
        except Exception:
            pass
        _save_state(state)
    return state["last_summary"]


def autopilot_loop():
    while True:
        try:
            autopilot_cycle()
        except Exception as e:
            try:
                with _state_lock:
                    s = _load_state()
                    s["last_error"] = str(e)[:300]
                    s["next_scan_ts"] = time.time() + SCAN_INTERVAL
                    _save_state(s)
            except Exception:
                pass
        time.sleep(SCAN_INTERVAL)


def _apply_ntfy_unlock(st, now_ts):
    """
    Unlock placed_keys for FUTURE fixtures so a balance top-up can re-bet them.
    Fixtures that already kicked off stay deduped.

    Deliberately does NOT touch st["daily"]["spent"] (changed 2026-07-10):
    the old behavior zeroed the daily counter on every unlock, so repeated
    phone messages could spend multiples of DAILY_SPEND_CAP in one day
    (2026-07-06: $449.64 accepted in a day this way). The daily cap must
    bind across unlocks — ntfy is an unauthenticated public channel and the
    topic name is the only secret.

    Mutates st in place; returns the number of unlocked picks.
    """
    candidates = st.get("last_candidates", []) or []
    kickoff_map = {c["fixture_id"]: c.get("kickoff_ts", 0) for c in candidates}
    keep_pk = []
    unlocked_count = 0
    for pk in st.get("placed_keys", []) or []:
        fid = pk.split(":")[0]
        ko = kickoff_map.get(fid, 0)
        if ko and ko <= now_ts:
            keep_pk.append(pk)  # already kicked off — keep deduped
        else:
            unlocked_count += 1
    st["placed_keys"] = keep_pk
    return unlocked_count


def _ntfy_listener_loop():
    """
    Listens on the ntfy topic for incoming messages from the user's phone.
    When a numeric message arrives (e.g. "5.87"), treats it as a wallet balance
    update and immediately triggers an autopilot cycle so bets are placed right away.
    Runs as a background daemon thread.
    """
    import json as _json
    from src.services.alerting import notifier as _notifier

    def _read_topic():
        env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
        try:
            with open(env_path, encoding="utf-8") as f:
                for line in f:
                    if line.startswith("NTFY_TOPIC="):
                        return line.split("=", 1)[1].strip()
        except OSError:
            pass
        return None

    topic = _read_topic()
    if not topic:
        print("[NTFY] No topic configured — listener not started")
        return

    seen_ids = set()
    # Seed seen_ids with messages already in the topic so we don't reprocess old ones
    try:
        r = requests.get(f"https://ntfy.sh/{topic}/json?poll=1&since=10m", timeout=10)
        for line in r.text.strip().splitlines():
            try:
                seen_ids.add(_json.loads(line).get("id"))
            except Exception:
                pass
    except Exception:
        pass

    print(
        f"[NTFY] Listener active on topic '{topic}' — send balance from phone to trigger a cycle"
    )

    while True:
        try:
            # SSE stream — reconnects automatically
            with requests.get(
                f"https://ntfy.sh/{topic}/sse",
                stream=True,
                timeout=90,
                headers={"Cache-Control": "no-cache"},
            ) as resp:
                for line in resp.iter_lines(decode_unicode=True):
                    if not line or not line.startswith("data:"):
                        continue
                    try:
                        msg = _json.loads(line[5:].strip())
                    except Exception:
                        continue
                    mid = msg.get("id")
                    if mid in seen_ids:
                        continue
                    seen_ids.add(mid)
                    if msg.get("event") != "message":
                        continue

                    text = (msg.get("message") or "").strip()
                    # Ignore EVERYTHING we sent ourselves — all our outgoing
                    # notifications are titled "DeepField...". Matching a fixed
                    # set of titles caused a feedback loop: the "Bets Triggered"
                    # confirmation was read back in as a new balance command.
                    if (msg.get("title") or "").startswith("DeepField"):
                        continue

                    print(f"[NTFY] Received from phone: '{text}'")

                    # Unlock command requires an explicit keyword + a number
                    # ("balance 89.38" / "unlock 89"). Bare numbers are NOT
                    # commands — bet pushes contain odds and were false-firing
                    # the unlock (wiping dedup keys + daily spend).
                    import re as _re

                    numbers = _re.findall(r"\d+(?:\.\d+)?", text)
                    _is_unlock_cmd = bool(numbers) and any(
                        w in text.lower() for w in ("balance", "unlock", "wallet")
                    )
                    if _is_unlock_cmd:
                        balance = float(numbers[0])
                        print(
                            f"[NTFY] Balance ${balance:.2f} received — unlocking future bets + triggering cycle"
                        )
                        # Store as today's Betarabia balance for pick-alert sizing
                        try:
                            from src.daily_signal_alerts import store_betarabia_balance
                            store_betarabia_balance(balance)
                        except Exception as _dsa_e:
                            print(f"[NTFY] daily balance store failed: {_dsa_e}")
                        try:
                            # Unlock placed_keys for future fixtures so we can top up.
                            # daily.spent is preserved — DAILY_SPEND_CAP binds across
                            # unlocks (see _apply_ntfy_unlock docstring).
                            with _state_lock:
                                st = _load_state()
                            unlocked_count = _apply_ntfy_unlock(st, time.time())
                            with _state_lock:
                                _save_state(st)
                            print(f"[NTFY] Unlocked {unlocked_count} future fixtures")

                            summary = autopilot_cycle()
                            wallet = get_wallet()
                            actual_bal = (
                                wallet["available_balance_usdc"] if wallet else balance
                            )
                            _notifier._notify(
                                f"Wallet: ${actual_bal:.2f} | {unlocked_count} picks unlocked\n"
                                f"{summary}",
                                title="DeepField - Bets Triggered",
                                priority="default",
                                tags="white_check_mark",
                            )
                        except Exception as _e:
                            print(f"[NTFY] Cycle failed: {_e}")
                    else:
                        # Non-numeric message — echo it back as confirmation
                        _notifier._notify(
                            f"Received: '{text}'\nSend a number (e.g. 5.87) to trigger a bet cycle.",
                            title="DeepField",
                            priority="low",
                            tags="bell",
                        )
        except Exception as e:
            print(f"[NTFY] Stream error: {e} — reconnecting in 10s")
            time.sleep(10)


_ntfy_listener_started = False


def start_ntfy_listener():
    global _ntfy_listener_started
    if _ntfy_listener_started:
        return
    _ntfy_listener_started = True
    threading.Thread(
        target=_ntfy_listener_loop, daemon=True, name="ntfy-listener"
    ).start()


def start_autopilot():
    global _autopilot_started
    if _autopilot_started:
        return
    _autopilot_started = True
    threading.Thread(target=autopilot_loop, daemon=True, name="arena-autopilot").start()
    start_ntfy_listener()
    print("[*] Arena autopilot + ntfy listener started.")


def _bets_overview(state):
    """Join Stair AI orders with match names and settlements into one readable
    bet feed (newest first) + a W/L record and locked-capital total. This is
    what the UI needs: 'what did the AI bet, what's locked, what won'."""
    fid_to_match = {}
    fid_to_kickoff = {}
    for src in (
        state.get("placed", []),
        state.get("last_candidates", []),
        state.get("last_all_candidates", []),
    ):
        for c in src:
            fid = str(c.get("fixture_id") or "")
            if fid and c.get("match") and fid not in fid_to_match:
                fid_to_match[fid] = c["match"]
                if c.get("kickoff"):
                    fid_to_kickoff[fid] = c["kickoff"]

    winners = {}
    for s in state.get("settlements", []):
        fid = str(s.get("fixture_id") or "")
        if fid and s.get("winning_outcome"):
            winners[fid] = str(s["winning_outcome"]).upper()

    # Stair AI's settlement feed lags days behind matches — infer final 1X2
    # outcomes locally so the bet feed shows WON/LOST instead of eternal OPEN.
    # Source 1: the research daemon's settled paper ledger (settled from real
    # ESPN scores). Source 2: the dashboard state's FT scores (recent matches).
    outcomes_by_match = {}  # "home vs away" lower -> 'home'|'away'|'draw'
    try:
        import sqlite3 as _sq3

        _blp = os.path.join(os.path.dirname(__file__), "..", "data", "bet_log.db")
        _c = _sq3.connect(_blp)
        for _m, _s2, _r in _c.execute(
            "SELECT match_id, side, result FROM bet_log "
            "WHERE market_type='1X2' AND result='W'"
        ):
            _sl = (_s2 or "").lower()
            _o = (
                "home"
                if "home" in _sl
                else "away"
                if "away" in _sl
                else "draw"
                if "draw" in _sl
                else None
            )
            if _o and _m and " vs " in str(_m).lower():
                outcomes_by_match[str(_m).strip().lower()] = _o
        _c.close()
    except Exception:
        pass
    try:
        import json as _json2

        _stp = os.path.join(
            os.path.dirname(__file__), "..", "data", "todays_dashboard_state.json"
        )
        for _mm in _json2.load(open(_stp, encoding="utf-8")):
            _fx = _mm.get("fixture") or {}
            _short = ((_fx.get("status") or {}).get("short") or "").upper()
            _hs, _as = _fx.get("home_score"), _fx.get("away_score")
            if _short == "FT" and _hs is not None and _as is not None:
                _o = "home" if _hs > _as else "away" if _as > _hs else "draw"
                _nm = (_mm.get("match") or "").strip().lower()
                if _nm:
                    outcomes_by_match.setdefault(_nm, _o)
    except Exception:
        pass

    def _final_outcome(match_name):
        mn = (match_name or "").strip().lower()
        if not mn or " vs " not in mn:
            return None
        if mn in outcomes_by_match:
            return outcomes_by_match[mn]
        h, a = [t.strip() for t in mn.split(" vs ")[:2]]
        for k, v in outcomes_by_match.items():
            kh, ka = [t.strip() for t in k.split(" vs ")[:2]]
            if (kh in h or h in kh) and (ka in a or a in ka):
                return v
        return None

    # Stair AI's /orders list carries no timestamps — recover them from our own
    # placement log (order_id appears in the recorded order_response string).
    import re as _re
    import datetime as _dt

    oid_to_ts = {}
    for p in state.get("placed", []):
        ts = p.get("ts")
        resp = str(p.get("order_response") or "")
        if not ts:
            continue
        m = _re.search(r"'order_id': '([0-9a-f\-]+)'", resp)
        if not m:
            continue
        try:
            epoch_ms = int(
                _dt.datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                .replace(tzinfo=_dt.timezone.utc)
                .timestamp()
                * 1000
            )
            oid_to_ts[m.group(1)] = epoch_ms
        except (ValueError, TypeError):
            continue

    FILLED = {"completed", "filled", "settled", "closed"}
    bets = []
    won = lost = open_n = 0
    locked = 0.0
    realized = 0.0
    for o in state.get("orders_recent", []):
        status = (o.get("status") or "").lower()
        if status not in FILLED:
            continue
        fid = str(o.get("fixture_id") or "")
        try:
            size = float(o.get("usd_size") or 0)
        except (TypeError, ValueError):
            size = 0.0
        if size <= 0:
            continue
        try:
            fill = float(o.get("fill_price") or 0)
        except (TypeError, ValueError):
            fill = 0.0
        team = (o.get("team_code") or "").upper()
        win_outcome = winners.get(fid)
        rp = o.get("realized_pnl")
        if rp is not None:
            # exchange already settled this order — trust its number
            rp = float(rp)
            realized += rp
            if rp >= 0:
                result = "WON"
                won += 1
            else:
                result = "LOST"
                lost += 1
        elif win_outcome is not None:
            if team and team in win_outcome:
                result = "WON"
                won += 1
                if fill > 0:
                    realized += size / fill - size
            else:
                result = "LOST"
                lost += 1
                realized -= size
        else:
            # Local inference: final score known + mapping tells us whether
            # this bet's team code was the home or away side.
            _fin = _final_outcome(fid_to_match.get(fid, ""))
            _bet_won = None
            if _fin:
                try:
                    _map = get_mapping(fid) or {}
                except Exception:
                    _map = {}
                _home = (_map.get("home_short_code") or "").upper()
                _away = (_map.get("away_short_code") or "").upper()
                if team == "DRAW":
                    _bet_won = _fin == "draw"
                elif team and team == _home:
                    _bet_won = _fin == "home"
                elif team and team == _away:
                    _bet_won = _fin == "away"
            if _bet_won is True:
                result = "WON"
                won += 1
                if fill > 0:
                    realized += size / fill - size
            elif _bet_won is False:
                result = "LOST"
                lost += 1
                realized -= size
            else:
                result = "OPEN"
                open_n += 1
                locked += size
        bets.append(
            {
                "match": fid_to_match.get(fid, f"fixture {fid}"),
                "kickoff": fid_to_kickoff.get(fid),
                "team_code": team,
                "pick": f"{team} to win" if team else "?",
                "stake_usd": round(size, 2),
                "fill_price": fill or None,
                "potential_payout": round(size / fill, 2) if fill else None,
                "result": result,
                "realized_pnl": round(rp, 2) if rp is not None else None,
                "submitted_at": o.get("submitted_at")
                or oid_to_ts.get(str(o.get("order_id") or "")),
                "order_id": o.get("order_id"),
            }
        )
    # newest first — submitted_at is epoch ms from Stair AI; missing sorts last
    bets.sort(key=lambda b: b.get("submitted_at") or 0, reverse=True)
    return {
        "bets": bets,
        "record": {"won": won, "lost": lost, "open": open_n},
        "locked_usd": round(locked, 2),
        "realized_est_usd": round(realized, 2),
    }


def autopilot_status():
    state = _load_state()
    cfg = {**_default_settings(), **state.get("settings", {})}
    return {
        "enabled": state.get("enabled", False),
        "last_scan_ts": state.get("last_scan_ts"),
        "next_scan_ts": state.get("next_scan_ts"),
        "scan_interval": SCAN_INTERVAL,
        "last_summary": state.get("last_summary"),
        "last_error": state.get("last_error"),
        "daily": state.get("daily"),
        "daily_cap": DAILY_SPEND_CAP,
        "conf_min": cfg["conf_min"],
        "edge_min": cfg["edge_min"],
        "max_usd": cfg["max_per_bet"],
        "max_bets_per_run": cfg["max_bets_per_run"],
        "settings": cfg,
        "wallet": get_wallet(),
        "placed": [p for p in state.get("placed", []) if p.get("ok")],
        "candidates": state.get("last_candidates", []),
        "all_candidates": state.get("last_all_candidates", []),
        "total_placed": len(state.get("placed_keys", [])),
        "total_ledger": len(state.get("ledger_keys", [])),
        # --- NEW: positions, orders, P&L, leaderboard ---
        "positions": state.get("positions", []),
        "orders_recent": state.get("orders_recent", []),
        "settlements": state.get("settlements", []),
        "pnl": state.get(
            "pnl", {"unrealized": 0, "realized": 0, "total_staked": 0, "total_value": 0}
        ),
        "leaderboard_rank": state.get("leaderboard_rank"),
        "arena_live": _arena_live(),
        "bets_overview": _bets_overview(state),
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
def _require_localhost():
    """403 helper for state-changing endpoints on the 0.0.0.0-bound server.

    The dashboard binds all interfaces, so without this anyone on the LAN
    could arm the autopilot or loosen its thresholds. Returns a Flask
    (response, status) tuple to short-circuit with, or None when allowed.
    """
    remote = request.remote_addr or ""
    if remote not in ("127.0.0.1", "::1", "localhost"):
        return (
            jsonify({"error": "Forbidden: control endpoints allowed from localhost only."}),
            403,
        )
    return None


def _params():
    conf = request.values.get("conf", type=float)
    edge = request.values.get("edge", type=float)
    limit = request.values.get("limit", default=40, type=int)
    max_usd = request.values.get("max_usd", default=MAX_USD_PER_BET, type=float)
    return {
        "limit": max(1, min(limit, 104)),
        "conf_min": CONF_MIN_DEFAULT if conf is None else conf,
        "edge_min": EDGE_MIN_DEFAULT if edge is None else edge,
        "max_usd": min(max_usd, MAX_USD_PER_BET),
    }


@arena_bp.route("/arena")
def arena_page():
    return render_template("arena.html")


@arena_bp.route("/arena/api/wallet")
def arena_wallet():
    w = get_wallet()
    return jsonify(w or {"error": "wallet unavailable"})


@arena_bp.route("/arena/api/status")
def arena_status():
    return jsonify(autopilot_status())


@arena_bp.route("/arena/api/insights")
def arena_insights():
    """Return market intelligence: steam signals, arb opportunities, market health.

    This endpoint aggregates all the enhanced market analytics from analyze():
    - Active steam moves (>3% price drift in 4h) across all tracked WC fixtures
    - Real arbitrage opportunities (sum of asks < $1.00 guaranteed profit)
    - Per-fixture market overround (vig) — negative vig = loose market = higher EV
    - Consensus score: how much our model and de-vigged market agree
    """
    try:
        from src.polymarket_steam import get_all_steam_signals
        steam_signals = get_all_steam_signals(min_move_pct=3.0)
    except Exception as e:
        steam_signals = []

    # Pull latest candidates from state for arb/market health data
    state = _load_state()
    all_candidates = state.get("last_all_candidates", [])

    # Group by fixture to compute per-fixture market health
    fixtures_seen = {}
    arb_opportunities = []
    for c in state.get("last_candidates", []) + all_candidates:
        fid = c.get("fixture_id") or c.get("match", "?")
        match = c.get("match", "?")
        vig = c.get("market_vig_pp")
        real_arb = c.get("real_arb", False)
        arb_pp = c.get("arb_profit_pp")
        if fid not in fixtures_seen:
            fixtures_seen[fid] = {
                "fixture_id": fid,
                "match": match,
                "kickoff": c.get("kickoff"),
                "market_vig_pp": vig,
                "real_arb": real_arb,
                "arb_profit_pp": arb_pp,
            }
            if real_arb and arb_pp is not None:
                arb_opportunities.append(fixtures_seen[fid])

    # Market health summary
    all_vigs = [f["market_vig_pp"] for f in fixtures_seen.values() if f["market_vig_pp"] is not None]
    market_health = {
        "fixtures_tracked": len(fixtures_seen),
        "avg_vig_pp": round(sum(all_vigs) / len(all_vigs), 2) if all_vigs else None,
        "loose_markets": sum(1 for v in all_vigs if v < 0),
        "tight_markets": sum(1 for v in all_vigs if v > 5),
        "real_arb_count": len(arb_opportunities),
    }

    return jsonify({
        "steam_signals": steam_signals,
        "arb_opportunities": arb_opportunities,
        "market_health": market_health,
        "fixtures": list(fixtures_seen.values()),
        "last_scan": state.get("last_scan_ts"),
    })


@arena_bp.route("/arena/api/toggle", methods=["POST"])
def arena_toggle():
    """Safety pause/resume for the autonomous loop (does not change betting logic).

    Asymmetric gate (2026-07-10): PAUSING is allowed from anywhere — it is the
    emergency kill switch and must stay reachable from a phone on the LAN.
    ARMING (enabled=true) requires localhost, so no remote device can start
    real-money betting.
    """
    with _state_lock:
        s = _load_state()
        body = request.get_json(silent=True) or {}
        target = bool(body.get("enabled", not s.get("enabled", False)))
        if target:
            _denied = _require_localhost()
            if _denied:
                return _denied
        s["enabled"] = target
        _save_state(s)
    return jsonify({"enabled": s["enabled"]})


@arena_bp.route("/arena/api/settings", methods=["GET", "POST"])
def arena_settings_api():
    """GET: return current live settings. POST: update one or more settings."""
    if request.method == "GET":
        state = _load_state()
        return jsonify({**_default_settings(), **state.get("settings", {})})
    _denied = _require_localhost()
    if _denied:
        return _denied
    body = request.get_json(silent=True) or {}
    with _state_lock:
        s = _load_state()
        cfg = s.setdefault("settings", _default_settings())
        if "conf_min" in body:
            cfg["conf_min"] = round(max(0.0, min(0.99, float(body["conf_min"]))), 3)
        if "edge_min" in body:
            cfg["edge_min"] = round(max(0.0, min(0.60, float(body["edge_min"]))), 3)
        if "max_per_bet" in body:
            cfg["max_per_bet"] = round(
                max(1.0, min(100.0, float(body["max_per_bet"]))), 2
            )
        if "max_bets_per_run" in body:
            cfg["max_bets_per_run"] = max(1, min(100, int(body["max_bets_per_run"])))
        if "bet_window_hours" in body:
            cfg["bet_window_hours"] = round(
                max(1.0, min(168.0, float(body["bet_window_hours"]))), 1
            )
        _save_state(s)
    return jsonify(cfg)


@arena_bp.route("/arena/api/analyze")
def arena_analyze():
    p = _params()
    wallet = get_wallet()
    wallet_balance = wallet["available_balance_usdc"] if wallet else None
    try:
        cands = analyze(wallet_balance=wallet_balance, **p)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify(
        {
            "params": p,
            "wallet_balance": wallet_balance,
            "qualifying": sum(1 for c in cands if c["qualifies"]),
            "candidates": cands,
        }
    )


@arena_bp.route("/arena/api/place", methods=["POST"])
def arena_place():
    # Restrict real-money placement to requests originating from localhost only
    _denied = _require_localhost()
    if _denied:
        return _denied
    body = request.get_json(silent=True) or {}
    if not body.get("confirm"):
        return (
            jsonify(
                {"error": "Refused: real-money placement requires {'confirm': true}."}
            ),
            400,
        )
    p = _params()
    dry = bool(body.get("dry_run", False))
    try:
        out = run_autoplace(dry_run=dry, **p)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify(out)


# ---------------------------------------------------------------------------
# Extended routes — positions, orders, settlements, matches, leaderboard
# ---------------------------------------------------------------------------
@arena_bp.route("/arena/api/positions")
def arena_positions():
    """Current token holdings with P&L."""
    state = _load_state()
    return jsonify(
        {"positions": state.get("positions", []), "pnl": state.get("pnl", {})}
    )


@arena_bp.route("/arena/api/orders")
def arena_orders():
    """List recent orders."""
    state = _load_state()
    return jsonify({"orders": state.get("orders_recent", [])})


@arena_bp.route("/arena/api/order/<order_id>")
def arena_order_detail(order_id):
    """Single order detail."""
    detail = get_order_detail(order_id)
    if detail is None:
        return jsonify({"error": "order not found"}), 404
    return jsonify(detail)


@arena_bp.route("/arena/api/close", methods=["POST"])
def arena_close_position():
    """Close a filled position. Sells at caller's price — localhost + confirm only."""
    _denied = _require_localhost()
    if _denied:
        return _denied
    body = request.get_json(silent=True) or {}
    if not body.get("confirm"):
        return (
            jsonify(
                {"error": "Refused: closing a real position requires {'confirm': true}."}
            ),
            400,
        )
    order_id = body.get("order_id")
    limit_price = body.get("limit_price")
    if not order_id or limit_price is None:
        return jsonify({"error": "order_id and limit_price required"}), 400
    sc, data = close_position(order_id, float(limit_price))
    return jsonify({"status_code": sc, "data": data})


@arena_bp.route("/arena/api/settlements")
def arena_settlements():
    """Settlement status for placed bets."""
    state = _load_state()
    return jsonify({"settlements": state.get("settlements", [])})


@arena_bp.route("/arena/api/redcards")
def arena_redcards():
    """Recent red card alerts from the live in-play edge monitor."""
    try:
        from src.redcard_monitor import get_recent_alerts
        limit = request.args.get("limit", default=20, type=int)
        alerts = get_recent_alerts(limit)
        actionable = [a for a in alerts if a.get("actionable")]
        return jsonify({
            "alerts": alerts,
            "actionable_count": len(actionable),
            "total_count": len(alerts),
        })
    except Exception as e:
        return jsonify({"alerts": [], "error": str(e)})


@arena_bp.route("/arena/api/clv")
def arena_clv():
    """CLV (Closing Line Value) records for arena bets."""
    state = _load_state()
    records = state.get("clv_records", [])
    if records:
        avg_clv = round(sum(r.get("clv_pp", 0) for r in records) / len(records), 2)
        positive = sum(1 for r in records if (r.get("clv_pp") or 0) > 0)
    else:
        avg_clv = None
        positive = 0
    return jsonify({
        "clv_records": records[:50],
        "total": len(records),
        "avg_clv_pp": avg_clv,
        "positive_clv_bets": positive,
    })


@arena_bp.route("/arena/api/performance")
def arena_performance():
    """Model calibration, Brier score, and bet performance metrics."""
    since = request.args.get("since")
    try:
        from src.brier_tracker import get_performance_summary
        summary = get_performance_summary(since_date=since)
        # Augment with CLV data from arena state
        state = _load_state()
        clv_records = state.get("clv_records", [])
        if clv_records:
            avg_arena_clv = round(
                sum(r.get("clv_pp", 0) for r in clv_records) / len(clv_records), 2
            )
            summary["arena_clv"] = {
                "n": len(clv_records),
                "avg_clv_pp": avg_arena_clv,
                "positive_rate": round(
                    sum(1 for r in clv_records if (r.get("clv_pp") or 0) > 0) / len(clv_records), 3
                ),
            }
        return jsonify(summary)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@arena_bp.route("/arena/api/match_events")
def arena_match_events():
    """Live WC match events (goals, red cards, score changes)."""
    try:
        from src.match_events_monitor import get_live_matches, get_match_events
        event_id = request.args.get("event_id")
        matches = get_live_matches()
        events = get_match_events(event_id)
        live_count = sum(1 for m in matches if m.get("status") == "LIVE")
        return jsonify({
            "matches": matches,
            "recent_events": events,
            "live_count": live_count,
        })
    except Exception as e:
        return jsonify({"matches": [], "recent_events": [], "error": str(e)})


@arena_bp.route("/arena/api/price_lag")
def arena_price_lag():
    """Polymarket price lag alerts after lineup announcements (research: 36% underreaction at T+0)."""
    try:
        from src.lineup_price_lag import get_recent_alerts
        limit = request.args.get("limit", default=20, type=int)
        alerts = get_recent_alerts(limit)
        lag_detected = [a for a in alerts if a.get("lag_detected")]
        return jsonify({
            "alerts": alerts,
            "lag_detected_count": len(lag_detected),
            "total": len(alerts),
        })
    except Exception as e:
        return jsonify({"alerts": [], "error": str(e)})


@arena_bp.route("/arena/api/market/<fixture_id>")
def arena_market(fixture_id):
    """Live Polymarket data for a fixture."""
    data = get_market_data(fixture_id)
    if data is None:
        return jsonify({"error": "market data not available"}), 404
    return jsonify(data)


@arena_bp.route("/arena/api/matches")
def arena_matches():
    """Arena matches with timing windows."""
    status = request.args.get("status")
    matches = list_arena_matches(status=status)
    return jsonify({"matches": matches})


@arena_bp.route("/arena/api/leaderboard")
def arena_leaderboard():
    """Public leaderboard."""
    sort_by = request.args.get("sort_by", "psl")
    direction = request.args.get("direction", "desc")
    limit = request.args.get("limit", default=25, type=int)
    offset = request.args.get("offset", default=0, type=int)
    lb = get_leaderboard(
        sort_by=sort_by, direction=direction, limit=limit, offset=offset
    )
    return jsonify({"leaderboard": lb})


@arena_bp.route("/arena/api/tournament")
def arena_tournament():
    """Tournament details."""
    data = get_tournament()
    if data is None:
        return jsonify({"error": "tournament data not available"}), 404
    return jsonify(data)


@arena_bp.route("/arena/api/scan_now", methods=["POST"])
def arena_scan_now():
    """Trigger an immediate autopilot cycle (don't wait for the 60s interval)."""
    try:
        import threading as _thr
        def _run():
            autopilot_cycle()
        t = _thr.Thread(target=_run, daemon=True)
        t.start()
        return jsonify({"ok": True, "message": "Autopilot cycle triggered — results in ~5s via /arena/api/status"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@arena_bp.route("/arena/api/system_test", methods=["POST"])
def arena_system_test():
    """
    Run the full model + feature test suite.
    Returns JSON report with PASS/WARN/FAIL per test.
    ?test=T06 runs a single test by ID.
    """
    try:
        import threading as _thr
        from src.system_tester import run_all, ALL_TESTS
        test_param = request.args.get("test") or (request.get_json(silent=True) or {}).get("test")
        tests = [test_param] if test_param and test_param in ALL_TESTS else None
        result = {}

        def _run():
            nonlocal result
            result.update(run_all(tests))

        t = _thr.Thread(target=_run, daemon=True)
        t.start()
        t.join(timeout=120)
        return jsonify({"ok": True, **result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@arena_bp.route("/arena/api/research_sweep", methods=["POST"])
def arena_research_sweep():
    """
    Place paper bets on ALL outcomes (1X2, O/U, BTTS) for every upcoming fixture.
    source param: 'all' (default, all leagues), 'wc' (WC only), 'both'
    Regime = 'research'. $10 fixed stake. Deduped so re-calls only add new matches.
    """
    _denied = _require_localhost()
    if _denied:
        return _denied
    if not (request.get_json(silent=True) or {}).get("confirm"):
        return (
            jsonify(
                {"error": "Refused: research sweep places real orders — requires {'confirm': true}."}
            ),
            400,
        )
    try:
        import threading as _thr
        from src.research_betting import run_research_sweep
        source = (request.args.get("source") or
                  (request.get_json(silent=True) or {}).get("source", "all"))
        result = {}

        def _run():
            nonlocal result
            result.update(run_research_sweep(source=source))

        t = _thr.Thread(target=_run, daemon=True)
        t.start()
        t.join(timeout=60)
        return jsonify({"ok": True, **result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@arena_bp.route("/arena/api/order_fok", methods=["POST"])
def arena_order_fok():
    """Fill-or-kill order (all-or-nothing). Real money — localhost + confirm only."""
    _denied = _require_localhost()
    if _denied:
        return _denied
    body = request.get_json(silent=True) or {}
    if not body.get("confirm"):
        return (
            jsonify(
                {"error": "Refused: real-money placement requires {'confirm': true}."}
            ),
            400,
        )
    fixture_id = body.get("fixture_id")
    team_code = body.get("team_code")
    usd_size = body.get("usd_size")
    worst_price = body.get("worst_price")
    if not all([fixture_id, team_code, usd_size, worst_price]):
        return (
            jsonify({"error": "fixture_id, team_code, usd_size, worst_price required"}),
            400,
        )
    sc, data = submit_order_fok(
        fixture_id, team_code, float(usd_size), float(worst_price)
    )
    return jsonify({"status_code": sc, "data": data})
