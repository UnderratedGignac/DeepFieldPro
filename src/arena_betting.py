"""
arena_betting.py — StairAI World-Cup Arena betting page (Flask blueprint).
============================================================================
Fetches upcoming World Cup 2026 fixtures from the Stair AI arena, compares the
Sportmonks 1X2 model probability to the live Polymarket midpoint, and bets ONLY
on high-EV outcomes the model is confident in.

Decision rule (a pick qualifies only if BOTH hold for one outcome):
    model_prob >= CONF_MIN           ("the AI is sure it will win")
    model_prob - market_mid >= EDGE_MIN   ("high EV" / underpriced by the market)

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

ARENA = "https://stair-ai.com"
SEASON_ID = 26618  # World Cup 2026 (Sportmonks)
PRED_TYPE_1X2 = 237  # Sportmonks fulltime-result prediction type

# ---- Risk defaults (overridable per request) -------------------------------
CONF_MIN_DEFAULT = 0.60          # min model win prob to consider an outcome
EDGE_MIN_DEFAULT = 0.05          # min (model - market) edge, in probability
MAX_USD_PER_BET = 5.00           # arena hard ceiling per order
MIN_USD_PER_BET = 1.00           # arena minimum per order
WALLET_BUFFER = 0.05             # keep this much USDC unspent
MAX_BETS_PER_RUN = 10            # safety cap so auto-place can't drain the wallet
LIMIT_BUFFER = 0.02              # pay up to mid + this to get filled
TIF_SECONDS = 30                 # limit order expires if unfilled

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
    r = requests.get(f"{ARENA}{path}", headers=_headers(), params=params or None, timeout=25)
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
    """Return {'home':p,'draw':p,'away':p} as 0..1 from the Sportmonks 1X2 prediction."""
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


def _size_for_edge(edge, max_usd):
    """Conviction sizing: bigger edge -> bigger stake, within [MIN, max_usd]."""
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
def analyze(limit=40, conf_min=CONF_MIN_DEFAULT, edge_min=EDGE_MIN_DEFAULT,
            max_usd=MAX_USD_PER_BET):
    fixtures = list_upcoming_fixtures(limit)
    candidates = []
    for f in fixtures:
        fid = f["id"]
        probs = get_model_probs(fid)
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
            candidates.append({
                "fixture_id": str(fid),
                "match": f.get("name"),
                "kickoff": f.get("starting_at"),
                "kickoff_ts": f.get("starting_at_timestamp"),
                "outcome": outcome,
                "team_code": codes[outcome],
                "model_prob": round(model_p, 4),
                "market_mid": round(mid, 4),
                "edge": round(edge, 4),
                "edge_pp": round(edge * 100, 1),
                "qualifies": qualifies,
                "suggested_usd": _size_for_edge(edge, max_usd) if qualifies else None,
                "limit_price": limit_price,
                "token_id": token,
            })
    # qualifying first, then by edge desc
    candidates.sort(key=lambda c: (c["qualifies"], c["edge"]), reverse=True)
    return candidates


# ---------------------------------------------------------------------------
# Submission (REAL MONEY)
# ---------------------------------------------------------------------------
def submit_ledger(fid, outcome_code, model_prob, note):
    prob = max(0.001, min(0.999, float(model_prob)))
    payload = {
        "records": [{
            "behavior": "Acting",
            "action_type": "prediction",
            "parameters": {
                "fixture_id": str(fid),
                "outcome": outcome_code,
                "probability": prob,
            },
            "notes": note[:2048],
        }],
        "fixture_id": str(fid),
    }
    return _post("/api/v1/arena/ledger/records/batch", payload)


def place_order(fid, team_code, usd_size, limit_price):
    # HARD SAFETY GATE — the single chokepoint for ALL real-money orders. No state
    # flag, frontend toggle, or orphaned process can place a real bet unless the
    # operator explicitly sets DEEPFIELD_ARENA_LIVE=1 in the environment. Default OFF.
    if os.getenv("DEEPFIELD_ARENA_LIVE") != "1":
        return 0, {"error": "blocked",
                   "reason": "real-money placement disabled (DEEPFIELD_ARENA_LIVE != 1)"}
    payload = {
        "fixture_id": str(fid),
        "team_code": team_code,
        "usd_size": f"{float(usd_size):.2f}",
        "limit_price": round(float(limit_price), 2),
        "time_in_force_seconds": TIF_SECONDS,
        "idempotency_key": str(uuid.uuid4()),
    }
    return _post("/api/v1/arena/orders", payload)


def run_autoplace(limit=40, conf_min=CONF_MIN_DEFAULT, edge_min=EDGE_MIN_DEFAULT,
                  max_usd=MAX_USD_PER_BET, dry_run=False):
    wallet = get_wallet()
    if not wallet:
        return {"error": "Could not load arena wallet (check STAIR_AI_API_KEY)."}
    budget = max(0.0, wallet["available_balance_usdc"] - WALLET_BUFFER)
    per_bet_cap = min(max_usd, MAX_USD_PER_BET)

    picks = [c for c in analyze(limit, conf_min, edge_min, per_bet_cap) if c["qualifies"]]
    results = []
    spent = 0.0
    placed = 0
    now_ts = time.time()
    for c in picks:
        # Only bet BEFORE kickoff — never on a match that has already started/finished.
        ko = c.get("kickoff_ts")
        if ko and ko <= now_ts:
            results.append({**c, "status": "skipped", "reason": "match already started"})
            continue
        if placed >= MAX_BETS_PER_RUN:
            results.append({**c, "status": "skipped", "reason": "max bets per run reached"})
            continue
        size = min(c["suggested_usd"], per_bet_cap, budget - spent)
        if size < MIN_USD_PER_BET:
            results.append({**c, "status": "skipped", "reason": "insufficient remaining balance"})
            continue
        size = round(size, 2)
        note = (f"DeepFieldPro: model {c['model_prob']:.0%} vs market {c['market_mid']:.0%} "
                f"on {c['team_code']} (edge {c['edge_pp']}pp).")
        if dry_run:
            results.append({**c, "status": "dry_run", "would_stake_usd": size})
            spent += size
            placed += 1
            continue
        l_sc, l_resp = submit_ledger(c["fixture_id"], c["team_code"], c["model_prob"], note)
        o_sc, o_resp = place_order(c["fixture_id"], c["team_code"], size, c["limit_price"])
        ok = o_sc in (200, 201)
        if ok:
            spent += size
            placed += 1
        results.append({
            **c, "status": "placed" if ok else "order_failed",
            "staked_usd": size,
            "ledger_status": l_sc, "order_status": o_sc,
            "order_response": o_resp,
        })
    return {
        "wallet": wallet, "budget": round(budget, 2),
        "qualifying": len(picks), "placed": placed,
        "total_staked": round(spent, 2), "dry_run": dry_run,
        "results": results,
    }


# ---------------------------------------------------------------------------
# Autopilot — fully autonomous betting loop (no user interaction)
# ---------------------------------------------------------------------------
SCAN_INTERVAL = 300            # seconds between autonomous scans
AUTO_SCAN_LIMIT = 30           # nearest-kickoff fixtures scanned per cycle
DAILY_SPEND_CAP = 25.0         # max real USDC the autopilot may stake per UTC day
STATE_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "arena_autopilot.json")

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
        "placed_keys": [],          # (fixture:outcome) already bet — dedup
        "placed": [],               # newest-first log of auto-bets
        "last_candidates": [],      # qualifying picks from the last cycle
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
    if not (arena_live and state.get("enabled", False)):   # FAIL-SAFE: paused otherwise
        state["last_summary"] = "paused" if arena_live else "paused (real-money gate off)"
        with _state_lock:
            _save_state(state)
        return "paused"

    if state["daily"].get("date") != _today():          # daily cap rollover
        state["daily"] = {"date": _today(), "spent": 0.0}

    wallet = get_wallet()
    if not wallet:
        state["last_error"] = "wallet unavailable"
        with _state_lock:
            _save_state(state)
        return "wallet unavailable"

    budget = max(0.0, wallet["available_balance_usdc"] - WALLET_BUFFER)
    daily_remaining = max(0.0, DAILY_SPEND_CAP - state["daily"]["spent"])
    placed_keys = set(state.get("placed_keys", []))
    now_ts = time.time()

    qualifying = [c for c in analyze(AUTO_SCAN_LIMIT) if c["qualifies"]]
    state["last_candidates"] = qualifying[:25]

    spent = 0.0
    placed_now = 0
    for c in qualifying:
        if placed_now >= MAX_BETS_PER_RUN:
            break
        key = _pick_key(c)
        if key in placed_keys:                          # never double-bet a pick
            continue
        ko = c.get("kickoff_ts")
        if ko and ko <= now_ts:                          # only BEFORE kickoff
            continue
        room = min(budget - spent, daily_remaining - spent)
        size = round(min(c["suggested_usd"], MAX_USD_PER_BET, room), 2)
        if size < MIN_USD_PER_BET:
            continue
        note = (f"DeepFieldPro autopilot: model {c['model_prob']:.0%} vs market "
                f"{c['market_mid']:.0%} on {c['team_code']} (edge {c['edge_pp']}pp).")
        submit_ledger(c["fixture_id"], c["team_code"], c["model_prob"], note)
        o_sc, o_resp = place_order(c["fixture_id"], c["team_code"], size, c["limit_price"])
        ok = o_sc in (200, 201)
        state["placed"].insert(0, {
            "key": key, "fixture_id": c["fixture_id"], "match": c["match"],
            "team_code": c["team_code"], "outcome": c["outcome"],
            "model_prob": c["model_prob"], "market_mid": c["market_mid"],
            "edge_pp": c["edge_pp"], "staked_usd": size, "limit_price": c["limit_price"],
            "kickoff": c["kickoff"], "order_status": o_sc, "ok": ok,
            "ts": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
        })
        if ok:
            placed_keys.add(key)
            spent += size
            placed_now += 1

    state["placed_keys"] = list(placed_keys)
    state["placed"] = state["placed"][:100]
    state["daily"]["spent"] = round(state["daily"]["spent"] + spent, 2)
    state["last_error"] = None
    state["last_summary"] = f"{len(qualifying)} qualifying · {placed_now} bet · ${spent:.2f} staked"
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
        "enabled": state.get("enabled", False),   # FAIL-SAFE default
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
    try:
        cands = analyze(**p)
    except Exception as e:  # surface upstream/API failures cleanly
        return jsonify({"error": str(e)}), 500
    return jsonify({
        "params": p,
        "qualifying": sum(1 for c in cands if c["qualifies"]),
        "candidates": cands,
    })


@arena_bp.route("/arena/api/place", methods=["POST"])
def arena_place():
    body = request.get_json(silent=True) or {}
    if not body.get("confirm"):
        return jsonify({"error": "Refused: real-money placement requires {'confirm': true}."}), 400
    p = _params()
    dry = bool(body.get("dry_run", False))
    try:
        out = run_autoplace(dry_run=dry, **p)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify(out)
