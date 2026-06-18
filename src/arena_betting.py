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
CONF_MIN_DEFAULT = 0.50  # model prob must beat 50/50 for the outcome
EDGE_MIN_DEFAULT = 0.02  # 2pp edge vs Polymarket mid (captures clear favourites)
MAX_USD_PER_BET = 10.00  # arena hard ceiling per order
MIN_USD_PER_BET = 1.00  # arena minimum per order
WALLET_BUFFER = 0.05  # keep this much USDC unspent
MAX_BETS_PER_RUN = 15  # raised so we cover all WC matches in one cycle
LIMIT_BUFFER = 0.02  # pay up to mid + this to get filled
TIF_SECONDS = 30  # limit order expires if unfilled

# Max fraction of wallet per single bet (hard safety cap)
MAX_WALLET_FRACTION = 0.20  # never more than 20% of wallet on one bet

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
    w = data.get("wallet") or {}
    try:
        avail = float(w.get("available_balance_usdc") or 0.0)
    except (TypeError, ValueError):
        avail = 0.0
    return {
        "display_name": data.get("display_name"),
        "agent_id": data.get("agent_id"),
        "lifecycle_phase": data.get("lifecycle_phase"),
        "available_balance_usdc": avail,
        "locked_balance_usdc": w.get("locked_balance_usdc"),
    }


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


def get_mapping(fid):
    sc, mp = _get("/api/v1/web/mapping", fixture_id=fid)
    maps = mp.get("mappings") if isinstance(mp, dict) else None
    return maps[0] if maps else None


def get_mid(token_id):
    if not token_id:
        return None
    sc, mid = _get("/api/v1/data/proxy/polymarket-clob/midpoint", token_id=token_id)
    mid = _unwrap(mid)
    if isinstance(mid, dict) and mid.get("mid") is not None:
        try:
            return float(mid["mid"])
        except (TypeError, ValueError):
            return None
    return None


def _wallet_kelly_size(edge, market_mid, wallet_balance):
    """
    Quarter-Kelly stake sized to the actual wallet balance.
    Kelly fraction for a Polymarket binary bet: f* = edge / (1 - market_mid)
    where edge = model_prob - market_mid.
    Hard caps: never more than MAX_WALLET_FRACTION of wallet or MAX_USD_PER_BET.
    """
    if market_mid >= 1.0 or market_mid <= 0 or wallet_balance <= 0:
        return MIN_USD_PER_BET
    kelly_f = max(0.0, edge / (1.0 - market_mid))
    size = kelly_f * 1.0 * wallet_balance  # full-Kelly (capped by MAX_WALLET_FRACTION)
    hard_cap = min(wallet_balance * MAX_WALLET_FRACTION, MAX_USD_PER_BET)
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
    fixtures = list_upcoming_fixtures(limit)
    candidates = []
    for f in fixtures:
        fid = f["id"]

        # Extract team names to look up our own model probs
        fname = f.get("name", "")
        home_name, away_name = ("", "")
        if " vs " in fname:
            home_name, away_name = fname.split(" vs ", 1)

        # 1. Try our Dixon-Coles model (same as Betarabia paper bets)
        probs = _match_dfp(home_name, away_name) if home_name else None
        prob_source = "DFP"
        # DFP falls back to a flat heuristic (~36/28/36) for international teams it
        # hasn't been trained on. If no outcome clears conf_min, the probs are useless
        # for WC fixtures — defer to Sportmonks which has WC-specific predictions.
        if probs is not None and max(probs.values()) < conf_min:
            probs = None
        # 2. Fall back to Sportmonks for fixtures our system hasn't predicted yet
        if probs is None:
            probs = get_model_probs(fid)
            prob_source = "Sportmonks"

        mapping = get_mapping(fid)
        if not probs or not mapping:
            continue
        codes = {
            "home": mapping.get("home_short_code"),
            "draw": "draw",
            "away": mapping.get("away_short_code"),
        }
        for outcome in ("home", "draw", "away"):
            token = mapping.get(f"polymarket_{outcome}_token_yes")
            mid = get_mid(token)
            model_p = probs.get(outcome)
            if mid is None or model_p is None:
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
    if os.getenv("DEEPFIELD_ARENA_LIVE") != "1":
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
SCAN_INTERVAL = 300  # seconds between autonomous scans
AUTO_SCAN_LIMIT = 30  # nearest-kickoff fixtures scanned per cycle
DAILY_SPEND_CAP = 40.0  # max real USDC the autopilot may stake per UTC day
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
        "placed": [],  # newest-first log of auto-bets
        "last_candidates": [],  # qualifying picks from the last cycle
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
    """One autonomous scan + bet pass. Bets only on qualifying, pre-kickoff WC picks."""
    with _state_lock:
        state = _load_state()
    state["last_scan_ts"] = time.time()
    state["next_scan_ts"] = time.time() + SCAN_INTERVAL

    # Armed only when BOTH the operator env gate is set AND the state flag is on.
    arena_live = os.getenv("DEEPFIELD_ARENA_LIVE") == "1"
    if not (arena_live and state.get("enabled", False)):
        state["last_summary"] = (
            "paused" if arena_live else "paused (real-money gate off)"
        )
        with _state_lock:
            _save_state(state)
        return "paused"

    if state["daily"].get("date") != _today():
        state["daily"] = {"date": _today(), "spent": 0.0}

    wallet = get_wallet()
    if not wallet:
        state["last_error"] = "wallet unavailable"
        with _state_lock:
            _save_state(state)
        return "wallet unavailable"

    wallet_balance = wallet["available_balance_usdc"]
    budget = max(0.0, wallet_balance - WALLET_BUFFER)
    daily_remaining = max(0.0, DAILY_SPEND_CAP - state["daily"]["spent"])
    placed_keys = set(state.get("placed_keys", []))
    now_ts = time.time()

    qualifying = [
        c
        for c in analyze(AUTO_SCAN_LIMIT, wallet_balance=wallet_balance)
        if c["qualifies"]
    ]
    state["last_candidates"] = qualifying[:25]

    spent = 0.0
    placed_now = 0
    for c in qualifying:
        if placed_now >= MAX_BETS_PER_RUN:
            break
        key = _pick_key(c)
        if key in placed_keys:
            continue
        ko = c.get("kickoff_ts")
        if ko and ko <= now_ts:
            continue
        room = min(budget - spent, daily_remaining - spent)
        size = round(
            min(c["suggested_usd"] or MIN_USD_PER_BET, MAX_USD_PER_BET, room), 2
        )
        if size < MIN_USD_PER_BET:
            continue
        note = (
            f"DeepFieldPro autopilot [{c['prob_source']}]: model {c['model_prob']:.0%} "
            f"vs market {c['market_mid']:.0%} on {c['team_code']} (edge {c['edge_pp']}pp)."
        )
        submit_ledger(c["fixture_id"], c["team_code"], c["model_prob"], note)
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

    state["placed_keys"] = list(placed_keys)
    state["placed"] = state["placed"][:100]
    state["daily"]["spent"] = round(state["daily"]["spent"] + spent, 2)
    state["last_error"] = None
    state["last_summary"] = (
        f"{len(qualifying)} qualifying · {placed_now} bet · ${spent:.2f} staked"
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


def start_autopilot():
    global _autopilot_started
    if _autopilot_started:
        return
    _autopilot_started = True
    threading.Thread(target=autopilot_loop, daemon=True, name="arena-autopilot").start()
    print("[*] Arena autopilot started — autonomous World Cup betting active.")


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
        "placed": state.get("placed", [])[:50],
        "candidates": state.get("last_candidates", []),
        "total_placed": len(state.get("placed_keys", [])),
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
