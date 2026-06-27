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
CONF_MIN_DEFAULT = 0.45  # require model confidence >= 45%
EDGE_MIN_DEFAULT = 0.10  # require at least 10pp model edge over market
MAX_USD_PER_BET = 25.00  # hard ceiling — actual cap is AP2_MAX_PER_ORDER
MIN_USD_PER_BET = 1.00  # arena minimum per order
AP2_MAX_PER_ORDER = 5.00  # AP2 mandate cap — real per-order limit
MAX_FAIL_RETRIES = 3  # stop retrying a bet after this many consecutive failures
WALLET_BUFFER = 2.00  # keep $2 reserve — never spend the entire wallet
MAX_BETS_PER_RUN = 5  # at most 5 real-money bets per scan cycle
LIMIT_BUFFER = 0.02  # pay up to mid + this to get filled
TIF_SECONDS = 30  # limit order expires if unfilled

# DFP flat-heuristic filter: only use our own model when it gives a clear winner;
# fall back to Sportmonks (WC-specific) otherwise.
DFP_USEFUL_THRESHOLD = 0.52  # 0.48 is the fallback heuristic output — this blocks it
DFP_MAX_RATIO = 3.0  # if model/market > 3x, DC model does not know this team
WC_MODEL_WEIGHT = 0.65  # weight for WC Elo model when blending with Sportmonks/DFP

# Max fraction of wallet per single bet
MAX_WALLET_FRACTION = 0.12  # max 12% of wallet on any single bet

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
        "tif_seconds": int(tif_seconds),
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
    """POST /api/v1/arena/orders_fok — fill-or-kill order (all-or-nothing)."""
    payload = {
        "fixture_id": str(fixture_id),
        "team_code": team_code,
        "usd_size": float(usd_size),
        "worst_price": float(worst_price),
        "idempotency_key": str(uuid.uuid4()),
    }
    sc, data = _post("/api/v1/arena/orders_fok", payload)
    return sc, data


def list_upcoming_fixtures(limit=40):
    sc, sched = _get(
        f"/api/v1/data/proxy/sportmonks/v3/football/schedules/seasons/{SEASON_ID}"
    )
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


# Mapping cache — fetched once per cycle to avoid 100+ individual API calls.
_mapping_cache = {}
_mapping_cache_ts = 0
_MAPPING_CACHE_TTL = 300  # 5 minutes


def _refresh_mapping_cache():
    """Fetch ALL Polymarket mappings in one call and cache them."""
    global _mapping_cache, _mapping_cache_ts
    now = time.time()
    if _mapping_cache and (now - _mapping_cache_ts) < _MAPPING_CACHE_TTL:
        return
    sc, mp = _get("/api/v1/web/mapping")
    if sc == 200 and isinstance(mp, dict):
        maps = mp.get("mappings", [])
        _mapping_cache = {
            str(m["sportmonks_fixture_id"]): m
            for m in maps
            if m.get("sportmonks_fixture_id")
        }
        _mapping_cache_ts = now
        print(f"[arena] Cached {len(_mapping_cache)} Polymarket mappings")


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


def _wallet_kelly_size(edge, market_mid, wallet_balance):
    """
    Tiered Kelly stake — bigger size on bigger edges.

    Kelly fraction for a Polymarket binary bet: f* = edge / (1 - market_mid)

    Tier   | edge     | multiplier
    -------+----------+-----------
    Huge   | >= 15pp  | 1.00  (full-Kelly)
    Strong | >= 10pp  | 0.75  (3/4-Kelly)
    Good   | >=  5pp  | 0.50  (half-Kelly)
    Marginal| <  5pp  | 0.25  (quarter-Kelly)

    Hard caps: MAX_WALLET_FRACTION of wallet and MAX_USD_PER_BET.
    """
    if market_mid >= 1.0 or market_mid <= 0 or wallet_balance <= 0:
        return MIN_USD_PER_BET
    kelly_f = max(0.0, edge / (1.0 - market_mid))
    edge_pp = edge * 100.0
    if edge_pp >= 15.0:
        multiplier = 1.00
    elif edge_pp >= 10.0:
        multiplier = 0.75
    elif edge_pp >= 5.0:
        multiplier = 0.50
    else:
        multiplier = 0.25
    size = kelly_f * multiplier * wallet_balance
    hard_cap = min(
        wallet_balance * MAX_WALLET_FRACTION, MAX_USD_PER_BET, AP2_MAX_PER_ORDER
    )
    return round(max(MIN_USD_PER_BET, min(size, hard_cap)), 2)


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
# Core: analyze fixtures into candidate picks
# ---------------------------------------------------------------------------
def analyze(
    limit=40,
    conf_min=CONF_MIN_DEFAULT,
    edge_min=EDGE_MIN_DEFAULT,
    max_usd=MAX_USD_PER_BET,
    wallet_balance=None,
):
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

        # 3. Fall back to Sportmonks for fixtures our system hasn't predicted yet
        sm_probs = None
        if probs is None:
            sm_probs = get_model_probs(fid)
            if sm_probs and wc_probs:
                probs = blend_with_sportmonks(wc_probs, sm_probs, WC_MODEL_WEIGHT)
                prob_source = "WC+SM"
            elif sm_probs:
                probs = sm_probs
                prob_source = "Sportmonks"
            elif wc_probs:
                probs = wc_probs
                prob_source = "WC"
        elif wc_probs:
            probs = blend_with_sportmonks(wc_probs, probs, WC_MODEL_WEIGHT)
            prob_source = "WC+DFP"

        mapping = get_mapping(fid)
        if not probs or not mapping:
            continue
        # Extract team codes from the event ticker (format: fifwc-{home}-{away}-YYYY-MM-DD)
        # The orders API expects ticker codes (e.g. "RSA"), not ISO short codes (e.g. "ZAF")
        ticker = (
            mapping.get("polymarket_event_ticker")
            or mapping.get("polymarket_event_slug")
            or ""
        )
        ticker_parts = ticker.split("-")
        home_code = (
            ticker_parts[1].upper()
            if len(ticker_parts) > 2
            else mapping.get("home_short_code", "HOME")
        )
        away_code = (
            ticker_parts[2].upper()
            if len(ticker_parts) > 3
            else mapping.get("away_short_code", "AWAY")
        )
        codes = {
            "home": home_code,
            "draw": "draw",
            "away": away_code,
        }
        for outcome in ("home", "draw", "away"):
            token = mapping.get(f"polymarket_{outcome}_token_yes")
            mid = get_mid(token)
            model_p = probs.get(outcome)
            if mid is None or model_p is None:
                continue
            # Sanity: DFP is 3x more bullish than market → DC model doesn't know this team
            if prob_source == "DFP" and mid > 0.01 and model_p / mid > DFP_MAX_RATIO:
                continue
            edge = model_p - mid
            qualifies = bool(model_p >= conf_min and edge >= edge_min)
            limit_price = round(min(0.99, mid + LIMIT_BUFFER), 2)

            if qualifies:
                if wallet_balance is not None:
                    suggested = _wallet_kelly_size(edge, mid, wallet_balance)
                else:
                    suggested = _size_for_edge(edge, max_usd)
            else:
                suggested = None

            candidates.append(
                {
                    "fixture_id": str(fid),
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
                }
            )
    # qualifying first, then by edge desc
    candidates.sort(key=lambda c: (c["qualifies"], c["edge"]), reverse=True)
    return candidates


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
    # AP2 mandate pre-flight (logs every attempt even if the live gate blocks it)
    _ap2_row = None
    if _AP2:
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
        except Exception:
            pass  # AP2 never blocks main flow on its own internal error

    # HARD SAFETY GATE — the single chokepoint for ALL real-money orders. No state
    # flag, frontend toggle, or orphaned process can place a real bet unless the
    # operator explicitly sets DEEPFIELD_ARENA_LIVE=1 in the environment. Default OFF.
    if not _arena_live():
        # Log the live-gate block to the AP2 ledger before returning
        if _AP2 and _ap2_row:
            try:
                _log_result(_ap2_row, None, "blocked", "DEEPFIELD_ARENA_LIVE != 1")
            except Exception:
                pass
        return 0, {
            "error": "blocked",
            "reason": "real-money placement disabled (DEEPFIELD_ARENA_LIVE != 1)",
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

    picks = [
        c
        for c in analyze(
            limit, conf_min, edge_min, per_bet_cap, wallet_balance=wallet_balance
        )
        if c["qualifies"]
        # Draws have no Polymarket YES token — posting team_code="draw" returns 402
        and (c.get("team_code") or "").lower() not in ("draw", "x", "tie")
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
        note = (
            f"DeepFieldPro [{c['prob_source']}]: model {c['model_prob']:.0%} vs market "
            f"{c['market_mid']:.0%} on {c['team_code']} (edge {c['edge_pp']}pp)."
        )
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
DAILY_SPEND_CAP = 999.0  # wallet-limited; no artificial daily cap
STATE_FILE = os.path.join(
    os.path.dirname(__file__), "..", "data", "arena_autopilot.json"
)

_state_lock = threading.Lock()
_autopilot_started = False


def _today():
    return time.strftime("%Y-%m-%d", time.gmtime())


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

    wallet = get_wallet()
    wallet_balance = wallet["available_balance_usdc"] if wallet else 0.0
    budget = max(0.0, wallet_balance - WALLET_BUFFER) if wallet else 0.0
    daily_remaining = max(0.0, DAILY_SPEND_CAP - state["daily"]["spent"])
    placed_keys = set(state.get("placed_keys", []))
    # Rebuild from placed history to catch keys lost during state resets
    for _p in state.get("placed", []):
        if _p.get("ok"):
            placed_keys.add(_p["key"])
    ledger_keys = set(state.get("ledger_keys", []))
    now_ts = time.time()

    all_candidates = analyze(AUTO_SCAN_LIMIT, wallet_balance=wallet_balance or None)
    qualifying = [c for c in all_candidates if c["qualifies"]]
    state["last_candidates"] = qualifying[:50]
    # All scanned matches with edge info (for the "all matches" edge table in the UI)
    _keep = (
        "match",
        "kickoff",
        "team_code",
        "model_prob",
        "market_mid",
        "edge_pp",
        "qualifies",
        "suggested_usd",
        "kickoff_ts",
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
        ko = c.get("kickoff_ts")
        if ko and ko <= now_ts:
            continue
        if key not in ledger_keys:
            note = (
                f"DeepFieldPro [{c['prob_source']}]: model {c['model_prob']:.0%} "
                f"vs market {c['market_mid']:.0%} on {c['team_code']} (edge {c['edge_pp']}pp)."
            )
            submit_ledger(c["fixture_id"], c["team_code"], c["model_prob"], note)
            ledger_keys.add(key)
            ledger_now += 1

    # Real-money orders only for qualifying picks when live gate is armed.
    for c in qualifying:
        # Draws have no Polymarket YES token — posting team_code="draw" returns 402
        if (c.get("team_code") or "").lower() in ("draw", "x", "tie"):
            continue
        key = _pick_key(c)
        ko = c.get("kickoff_ts")
        if ko and ko <= now_ts:
            continue

        # Real-money orders only when live gate is armed.
        if not autopilot_enabled:
            continue
        if placed_now >= MAX_BETS_PER_RUN:
            continue
        if key in placed_keys:
            continue
        failed_keys = state.get("failed_keys", {})
        if failed_keys.get(key, 0) >= MAX_FAIL_RETRIES:
            continue  # stop hammering a bet that keeps failing
        room = min(budget - spent, daily_remaining - spent)
        size = round(
            min(
                c["suggested_usd"] or MIN_USD_PER_BET,
                MAX_USD_PER_BET,
                AP2_MAX_PER_ORDER,
                room,
            ),
            2,
        )
        if size < MIN_USD_PER_BET:
            continue
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
        state["placed"].insert(
            0,
            {
                "key": key,
                "fixture_id": c["fixture_id"],
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
                "ok": ok,
                "prob_source": c["prob_source"],
                "ts": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
            },
        )
        if ok:
            placed_keys.add(key)
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
            # Track failures so we stop retrying after MAX_FAIL_RETRIES
            fk = state.setdefault("failed_keys", {})
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

    # Recent orders
    try:
        recent_orders = list_orders(
            status="unfilled,processing,filled,closing,closed,settled,completed,rejected"
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
            }
            for o in (recent_orders or [])[:30]
        ]
    except Exception:
        pass

    # Settlements — check placed bets for settled matches
    try:
        settled_fids = set()
        new_settlements = []
        for p in state.get("placed", []):
            fid = p.get("fixture_id")
            if fid and fid not in settled_fids and p.get("ok"):
                settled_fids.add(fid)
                s = get_settlement(fid)
                if s and isinstance(s, dict) and s.get("settled"):
                    new_settlements.append(
                        {
                            "fixture_id": fid,
                            "outcome": s.get("outcome") or s.get("winning_outcome"),
                            "resolved_at": s.get("resolved_at")
                            or s.get("settlement_time"),
                        }
                    )
        if new_settlements:
            existing = {s["fixture_id"] for s in state.get("settlements", [])}
            for ns in new_settlements:
                if ns["fixture_id"] not in existing:
                    state.setdefault("settlements", []).insert(0, ns)
            state["settlements"] = state["settlements"][:50]
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
                    # Ignore messages we sent ourselves (they have our titles)
                    own_titles = {
                        "DeepField Hot Bets",
                        "DeepField Setup Test",
                        "DeepField Best Bet",
                        "DeepField LIVE BET EXECUTED",
                        "DeepField SHADOW BET",
                        "DeepField CRITICAL ERROR",
                    }
                    if msg.get("title") in own_titles:
                        continue

                    print(f"[NTFY] Received from phone: '{text}'")

                    # Parse as a wallet balance (e.g. "5.87" or "$5.87" or "balance 5.87")
                    import re as _re

                    numbers = _re.findall(r"\d+(?:\.\d+)?", text)
                    if numbers:
                        balance = float(numbers[0])
                        print(
                            f"[NTFY] Balance ${balance:.2f} received — unlocking future bets + triggering cycle"
                        )
                        try:
                            # Unlock placed_keys for future fixtures so we can top up
                            with _state_lock:
                                st = _load_state()
                            now_ts2 = time.time()
                            candidates = st.get("last_candidates", [])
                            kickoff_map2 = {
                                c["fixture_id"]: c.get("kickoff_ts", 0)
                                for c in candidates
                            }
                            old_pk = set(st.get("placed_keys", []))
                            keep_pk = set()
                            unlocked_count = 0
                            for pk in old_pk:
                                fid2 = pk.split(":")[0]
                                ko2 = kickoff_map2.get(fid2, 0)
                                if ko2 and ko2 <= now_ts2:
                                    keep_pk.add(pk)  # already kicked off
                                else:
                                    unlocked_count += 1
                            st["placed_keys"] = list(keep_pk)
                            st["daily"] = {
                                "date": time.strftime("%Y-%m-%d"),
                                "spent": 0.0,
                            }
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


def autopilot_status():
    state = _load_state()
    return {
        "enabled": state.get("enabled", False),
        "last_scan_ts": state.get("last_scan_ts"),
        "next_scan_ts": state.get("next_scan_ts"),
        "scan_interval": SCAN_INTERVAL,
        "last_summary": state.get("last_summary"),
        "last_error": state.get("last_error"),
        "daily": state.get("daily"),
        "daily_cap": DAILY_SPEND_CAP,
        "conf_min": CONF_MIN_DEFAULT,
        "edge_min": EDGE_MIN_DEFAULT,
        "max_usd": MAX_USD_PER_BET,
        "max_bets_per_run": MAX_BETS_PER_RUN,
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
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
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


@arena_bp.route("/arena/api/toggle", methods=["POST"])
def arena_toggle():
    """Safety pause/resume for the autonomous loop (does not change betting logic)."""
    body = request.get_json(silent=True) or {}
    with _state_lock:
        s = _load_state()
        s["enabled"] = bool(body.get("enabled", not s.get("enabled", False)))
        _save_state(s)
    return jsonify({"enabled": s["enabled"]})


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
    remote = request.remote_addr or ""
    if remote not in ("127.0.0.1", "::1", "localhost"):
        return (
            jsonify({"error": "Forbidden: placement only allowed from localhost."}),
            403,
        )
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
    """Close a filled position."""
    body = request.get_json(silent=True) or {}
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


@arena_bp.route("/arena/api/order_fok", methods=["POST"])
def arena_order_fok():
    """Fill-or-kill order (all-or-nothing)."""
    body = request.get_json(silent=True) or {}
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
