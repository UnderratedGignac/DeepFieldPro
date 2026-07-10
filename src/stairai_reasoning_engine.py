"""
Stair AI + Gemini CDP Reasoning Engine — all-league 1X2 filter.

Each daemon cycle:
  1. Reads data/todays_dashboard_state.json — all leagues, all fixtures, DC model probs.
  2. For each pre-kickoff Home/Away pick where model_prob >= CONF_MIN AND
     edge vs de-vigged Betarabia >= EDGE_MIN:
       a. Calls Stair AI's Sportmonks prediction proxy (resolved by team name) for a
          second probability signal (only resolves for WC2026 fixtures; gracefully
          returns None for other leagues — Sportmonks has no other season indexed).
       a2. Reads live Polymarket mid-prices + recent steam (price-drift) moves via
          arena_betting's existing token-mapping/CLOB plumbing (same warm in-process
          cache Arena's own autopilot cycle populates — no extra API load). Also
          WC2026-only, since that's the only mapping arena_betting maintains.
       b. Sends a structured YES/NO prompt to Gemini CDP, including the Stair AI prob
          and Polymarket signal as corroborating (or cautionary) context. Advisory
          only — never a hard gate, since arena_betting.py found Sportmonks-only
          picks lose standalone (10/13).
       c. If Gemini approves (or is unavailable and GEMINI_FALLBACK=True):
           logs a STAIR_AI paper bet via log_ai_bet().

Paper bets only. Quarter-Kelly staking via the daemon's log_ai_bet().
Works on Premier League, La Liga, Copa America, World Cup — all leagues in the feed.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import time
from typing import Callable

# ── Constants ─────────────────────────────────────────────────────────────────
CONF_MIN_PCT = 50.0      # minimum DC model confidence (%) — only confident picks
EDGE_MIN = 0.03          # minimum edge vs de-vigged Betarabia (3pp)
EV_MIN = 0.02            # minimum raw EV gate (same as daemon)
GEMINI_FALLBACK = True   # place the bet when Gemini is unreachable (no Chrome open)

# Stair AI / Sportmonks reasoning layer.
# NOTE: arena_betting.py found Sportmonks-only predictions caused 10/13 losing
# bets (-$79) when used standalone — it's only ever blended with the WC Elo
# model there, never authoritative on its own. So here it is ADVISORY ONLY:
# surfaced to Gemini as context, never a hard gate that kills a DC+market pick.
_STAIRAI_BASE  = "https://stair-ai.com"
_SM_PRED_TYPE  = 237   # Sportmonks fulltime-result (1X2) prediction type
_SM_SEASON_ID  = 26618 # World Cup 2026 — the only season Sportmonks has indexed here

_sm_schedule_cache = {"ts": 0.0, "fixtures": []}
_SM_SCHEDULE_TTL = 300  # seconds — schedule is static intra-day, cache generously

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
_STATE_FILE = os.path.join(_DATA_DIR, "todays_dashboard_state.json")

# Pre-kickoff status codes recognised by the daemon
_LIVE_STATUSES = {"1H", "HT", "2H", "ET", "BT", "P", "INT", "LIVE"}
_DONE_STATUSES = {"FT", "AET", "PEN", "AWD", "WO", "ABD", "CANC"}

# Dedup: (match, side) pairs placed this process lifetime.
# Prevents re-placing the same bet if run_cycle() is called before the
# next Betarabia scrape refreshes odds (which would return the same fixtures).
_logged_this_run: set = set()


# ── Stair AI key (mirrors arena_betting._key()) ───────────────────────────────

def _stairai_key() -> str:
    k = os.getenv("STAIR_AI_API_KEY", "").strip()
    if k:
        return k
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    try:
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                if line.startswith("STAIR_AI_API_KEY="):
                    return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return ""


def _norm_team(name: str) -> str:
    return (name or "").lower().strip().replace(".", "").replace("-", " ")


def _names_match(a: str, b: str) -> bool:
    """True if two team-name strings plausibly refer to the same team (mirrors arena_betting._names_match)."""
    na, nb = _norm_team(a), _norm_team(b)
    if not na or not nb:
        return False
    if na == nb or na in nb or nb in na:
        return True
    if len(na) >= 5 and len(nb) >= 5 and na[:5] == nb[:5]:
        return True
    return False


def _get_sportmonks_schedule() -> list:
    """
    Fetch + cache the Sportmonks WC2026 season schedule via the Stair AI proxy.
    Only season 26618 (World Cup 2026) is indexed here — this is why the
    reasoning probe only ever resolves for WC fixtures.
    """
    now = time.time()
    if now - _sm_schedule_cache["ts"] < _SM_SCHEDULE_TTL and _sm_schedule_cache["fixtures"]:
        return _sm_schedule_cache["fixtures"]

    key = _stairai_key()
    if not key:
        return []
    try:
        import requests as _req
        r = _req.get(
            f"{_STAIRAI_BASE}/api/v1/data/proxy/sportmonks/v3/football/schedules/seasons/{_SM_SEASON_ID}",
            headers={"x-api-key": key},
            timeout=15,
        )
        if r.status_code != 200:
            return _sm_schedule_cache["fixtures"]
        body = r.json()
        inner = body
        if isinstance(body, dict) and "body" in body and "statusCode" in body:
            inner = body["body"]
        if isinstance(inner, str):
            try:
                inner = json.loads(inner)
            except Exception:
                return _sm_schedule_cache["fixtures"]

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

        walk(inner)
        _sm_schedule_cache["ts"] = now
        _sm_schedule_cache["fixtures"] = fixtures
        return fixtures
    except Exception as exc:
        print(f"[STAIR_AI ENGINE] Sportmonks schedule fetch error: {exc}")
        return _sm_schedule_cache["fixtures"]


def _find_sportmonks_fixture_id(home_name: str, away_name: str):
    """Resolve a Sportmonks-native fixture id by team-name match against the WC schedule."""
    for f in _get_sportmonks_schedule():
        fname = f.get("name", "")
        if " vs " not in fname:
            continue
        h, a = fname.split(" vs ", 1)
        if _names_match(home_name, h) and _names_match(away_name, a):
            return f.get("id")
    return None


def _get_stairai_probs(home_name: str, away_name: str) -> dict | None:
    """
    Fetch Sportmonks 1X2 prediction via the Stair AI data proxy, resolved by team name.
    Returns {'home': 0..1, 'draw': 0..1, 'away': 0..1} or None.

    Only WC2026 fixtures are indexed in Sportmonks via this endpoint; all other
    leagues won't be found in the schedule and this gracefully returns None.
    """
    key = _stairai_key()
    if not key:
        return None
    sm_fid = _find_sportmonks_fixture_id(home_name, away_name)
    if not sm_fid:
        return None
    try:
        import requests as _req
        r = _req.get(
            f"{_STAIRAI_BASE}/api/v1/data/proxy/sportmonks/v3/football/fixtures/{sm_fid}",
            headers={"x-api-key": key},
            params={"include": "participants;predictions"},
            timeout=10,
        )
        if r.status_code != 200:
            return None
        body = r.json()
        # Stair AI data-proxy wraps Sportmonks response: {body: {...}, statusCode: 200}
        # (mirrors arena_betting._unwrap() exactly — only unwrap when BOTH keys present)
        inner = body
        if isinstance(body, dict) and "body" in body and "statusCode" in body:
            inner = body["body"]
        if isinstance(inner, str):
            try:
                inner = json.loads(inner)
            except Exception:
                return None
        data = inner.get("data") if isinstance(inner, dict) else None
        if not isinstance(data, dict):
            return None
        preds = data.get("predictions") or []
        top = next((p for p in preds if p.get("type_id") == _SM_PRED_TYPE), None)
        if not top:
            return None
        pp = top.get("predictions") or {}
        return {
            "home": float(pp.get("home", 0)) / 100.0,
            "draw": float(pp.get("draw", 0)) / 100.0,
            "away": float(pp.get("away", 0)) / 100.0,
        }
    except Exception as exc:
        print(f"[STAIR_AI ENGINE] Sportmonks probe error: {exc}")
        return None


# ── Polymarket prediction-market probe (advisory only) ─────────────────────────

def _get_polymarket_data(home_name: str, away_name: str, match: str) -> dict | None:
    """
    Resolve live Polymarket implied probabilities + steam (price-drift) signals
    for a WC2026 fixture.

    Reuses arena_betting's token-mapping/CLOB-mid plumbing and polymarket_steam's
    price-history ledger — the exact same data arena_betting.py already records
    every analyze() cycle (shared in-process caches: both modules run inside the
    same Flask process as the daemon), so this adds no meaningful extra API load.

    Resolution goes through the Sportmonks fixture id (same trick as
    _find_sportmonks_fixture_id above) since that's the id space arena_betting's
    mapping cache is keyed on — it does NOT line up with the dashboard's
    Betarabia/Sofascore fixture_id. Only ever resolves for WC2026 fixtures;
    returns None for every other league or on any lookup failure.

    Returns {'implied_pct': {'home':.., 'draw':.., 'away':..}, 'steam_pct': {...}}
    (de-vigged, 0-100 scale) or None.
    """
    try:
        from src.arena_betting import get_mapping, get_mid
        from src.polymarket_steam import record_scan, get_steam_signals

        sm_fid = _find_sportmonks_fixture_id(home_name, away_name)
        if not sm_fid:
            return None
        mapping = get_mapping(sm_fid)
        if not mapping:
            return None

        mids = {}
        for outcome in ("home", "draw", "away"):
            tok = mapping.get(f"polymarket_{outcome}_token_yes")
            m = get_mid(tok) if tok else None
            if m is not None:
                mids[outcome] = m
        if not mids:
            return None

        record_scan(str(sm_fid), match, mids)
        steam = get_steam_signals(str(sm_fid))

        mid_sum = sum(mids.values())
        implied_pct = (
            {o: v / mid_sum * 100.0 for o, v in mids.items()} if mid_sum > 0 else {}
        )
        return {"implied_pct": implied_pct, "steam_pct": steam}
    except Exception as exc:
        print(f"[STAIR_AI ENGINE] Polymarket probe error: {exc}")
        return None


# ── De-vig helper ──────────────────────────────────────────────────────────────

def _devig_selection(all_odds: list, sel_index: int) -> float | None:
    """
    De-vig a [home_odds, draw_odds, away_odds] list and return the
    implied probability for position sel_index (0=home, 1=draw, 2=away).
    """
    if not all_odds or sel_index >= len(all_odds):
        return None
    raw = []
    for o in all_odds:
        if o and float(o) > 1.0:
            raw.append(1.0 / float(o))
        else:
            raw.append(0.0)
    total = sum(raw)
    if total <= 0 or sel_index >= len(raw):
        return None
    return raw[sel_index] / total


# ── Gemini CDP reasoning ───────────────────────────────────────────────────────

def _gemini_reason(
    match: str,
    league: str,
    side: str,
    model_prob_pct: float,
    betz_odds: float,
    betz_implied_pct: float,
    edge_pp: float,
    stairai_prob_pct: float | None = None,
    polymarket_prob_pct: float | None = None,
    polymarket_steam_pct: float | None = None,
) -> str:
    """
    Ask Gemini CDP for a YES/NO bet decision.
    Returns the full response text, or 'NO_GEMINI' if Chrome/Gemini is unavailable.
    stairai_prob_pct: Sportmonks-sourced probability from Stair AI (None if unavailable).
    polymarket_prob_pct: de-vigged Polymarket mid-implied probability for this side
        (None if unavailable — non-WC fixture or no live token mapping).
    polymarket_steam_pct: recent Polymarket price move (%) toward (+) or away from
        (-) this side, None if no steam data yet.
    """
    try:
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from tools.llm_bridges.gemini_cdp import GeminiCDPBridge

        bridge = GeminiCDPBridge()
        if not bridge.is_available():
            return "NO_GEMINI"

        if stairai_prob_pct is not None:
            stairai_line = (
                f"STAIR AI / SPORTMONKS PROBABILITY: {stairai_prob_pct:.1f}%  "
                f"({'CONFIRMS' if stairai_prob_pct >= 45.0 else 'WEAK SIGNAL'} the pick)\n"
            )
            consensus = (
                "Both our Dixon-Coles model AND the Stair AI / Sportmonks prediction agree on this outcome."
                if stairai_prob_pct >= 45.0
                else "Note: Stair AI / Sportmonks gives only weak support — weigh accordingly."
            )
        else:
            stairai_line = "STAIR AI / SPORTMONKS PROBABILITY: unavailable (non-WC fixture or API timeout)\n"
            consensus = "No Stair AI / Sportmonks corroboration available — rely on Dixon-Coles and market edge alone."

        if polymarket_prob_pct is not None:
            poly_line = (
                f"POLYMARKET PREDICTION MARKET (real money, de-vigged): {polymarket_prob_pct:.1f}% implied  "
                f"({'CONFIRMS' if polymarket_prob_pct >= 45.0 else 'WEAK SIGNAL'} the pick)\n"
            )
        else:
            poly_line = "POLYMARKET PREDICTION MARKET: unavailable (non-WC fixture or no live token mapping)\n"
        if polymarket_steam_pct is not None:
            direction = "toward" if polymarket_steam_pct > 0 else "away from"
            poly_line += f"POLYMARKET STEAM (recent price move): {polymarket_steam_pct:+.1f}% {direction} this side\n"

        prompt = (
            f"You are an expert football betting analyst. Your task is to decide whether a suggested bet has genuine value.\n\n"
            f"MATCH: {match}\n"
            f"COMPETITION: {league}\n"
            f"BET: {side.upper()} WIN (1X2 market)\n"
            f"MODEL PROBABILITY (Dixon-Coles): {model_prob_pct:.1f}%\n"
            f"{stairai_line}"
            f"{poly_line}"
            f"BETARABIA DECIMAL ODDS: {betz_odds:.2f}  (de-vigged implied: {betz_implied_pct:.1f}%)\n"
            f"EDGE VS MARKET: +{edge_pp:.1f} percentage points\n\n"
            f"SIGNAL SUMMARY: {consensus}\n\n"
            f"Assess whether this bet has genuine value:\n"
            f"- Is {model_prob_pct:.1f}% credible for {side.upper()} in this {league} match?\n"
            f"- Does the +{edge_pp:.1f}pp edge justify a quarter-Kelly paper stake?\n"
            f"- Any major concerns (injuries, form, motivation, fixture congestion)?\n\n"
            f"Reply in this exact format ONLY:\n"
            f"DECISION: YES\nREASON: <one sentence>\n\nor:\n\n"
            f"DECISION: NO\nREASON: <one sentence>"
        )
        result = bridge.simple(prompt)
        if not result.ok:
            print(f"[STAIR_AI ENGINE] Gemini error: {result.error}")
            return "NO_GEMINI"
        return result.text.strip()
    except Exception as e:
        print(f"[STAIR_AI ENGINE] Gemini CDP error: {e}")
        return "NO_GEMINI"


def _parse_decision(text: str) -> bool:
    """True = place the bet. Falls back to GEMINI_FALLBACK when Gemini is unavailable."""
    if not text or text == "NO_GEMINI":
        return GEMINI_FALLBACK
    m = re.search(r"DECISION:\s*(YES|NO)", text, re.IGNORECASE)
    if not m:
        return GEMINI_FALLBACK
    return m.group(1).upper() == "YES"


# ── Main cycle ─────────────────────────────────────────────────────────────────

def run_cycle(log_bet_fn: Callable, port: int = 5050) -> int:
    """
    One pass of the Gemini reasoning engine across all leagues.

    Args:
        log_bet_fn: daemon's log_ai_bet() — passed as callback to avoid circular import.
        port:       unused (kept for API compatibility with old WC-only version).

    Returns:
        Number of STAIR_AI paper bets logged this cycle.
    """
    placed = 0

    # ── 1. Load today's predictions (all leagues) ─────────────────────────────
    try:
        with open(_STATE_FILE, encoding="utf-8") as fh:
            fixtures = json.load(fh)
    except Exception as e:
        print(f"[STAIR_AI ENGINE] Cannot read dashboard state: {e}")
        return 0

    print(f"[STAIR_AI ENGINE] Scanning {len(fixtures)} fixtures across all leagues...")

    # ── 2. Evaluate each fixture ──────────────────────────────────────────────
    for item in fixtures:
        status = item.get("status_code", "NS")

        # Skip in-play and finished
        if status in _LIVE_STATUSES or status in _DONE_STATUSES:
            continue

        # Skip if kickoff is already in the past (state file can be a few minutes stale)
        kickoff_str = item.get("kickoff")
        if kickoff_str:
            try:
                ko = datetime.datetime.fromisoformat(kickoff_str.replace("Z", "+00:00"))
                if ko.tzinfo is None:
                    ko = ko.replace(tzinfo=datetime.timezone.utc)
                if ko <= datetime.datetime.now(datetime.timezone.utc):
                    continue
            except (ValueError, TypeError):
                pass

        match = item.get("match", "")
        league = item.get("league", "Unknown")
        fixture_id = item.get("fixture_id")

        prediction = item.get("prediction") or {}
        markets = prediction.get("markets") or {}
        x2_sels = markets.get("1X2")

        if not x2_sels or not isinstance(x2_sels, list):
            continue

        for sel in x2_sels:
            selection_name = sel.get("selection", "")  # "Home (1)", "Draw (X)", "Away (2)"

            # Skip draws — less predictable, illiquid for value betting
            if "X" in selection_name or "Draw" in selection_name:
                continue

            prob_pct = sel.get("prob") or 0      # e.g. 65.1
            odds = sel.get("odds") or 0          # Betarabia decimal odds
            ev = sel.get("ev") or 0              # raw EV vs Betarabia
            all_odds = sel.get("all_odds") or [] # [home, draw, away]

            # Gate 1: minimum confidence
            if prob_pct < CONF_MIN_PCT:
                continue

            # Gate 2: raw EV must be positive (basic value vs vigged market)
            if ev < EV_MIN:
                continue

            # Gate 3: edge vs de-vigged market
            sel_index = 0 if "(1)" in selection_name else 2
            dv_implied = _devig_selection(all_odds, sel_index)
            if dv_implied is None:
                continue
            edge = prob_pct / 100.0 - dv_implied
            if edge < EDGE_MIN:
                continue

            # Human-readable side label
            side_label = "Home" if "(1)" in selection_name else "Away"
            dedup_key = f"{match}::{side_label}"

            if dedup_key in _logged_this_run:
                continue

            ev_val = round(prob_pct / 100.0 * odds - 1.0, 4)

            # ── 3a. Stair AI / Sportmonks reasoning probe (advisory only) ─────
            # Resolved by team name — only ever matches WC2026 fixtures (the
            # only season Sportmonks has indexed via this proxy). No hard gate:
            # arena_betting.py found Sportmonks-only predictions caused 10/13
            # losing bets standalone, so it's surfaced to Gemini as context,
            # never used to kill a pick that already passed DC + market edge.
            home_name, away_name = ("", "")
            if " vs " in match:
                home_name, away_name = match.split(" vs ", 1)
            stairai_probs = _get_stairai_probs(home_name, away_name)
            stairai_prob_pct: float | None = None
            if stairai_probs:
                sa_key = "home" if side_label == "Home" else "away"
                stairai_prob_pct = stairai_probs[sa_key] * 100.0

            stairai_tag = f" SA={stairai_prob_pct:.1f}%" if stairai_prob_pct is not None else " SA=n/a"

            # ── 3a2. Polymarket prediction-market probe (advisory only) ───────
            # WC2026-only (same id-resolution limit as the Stair AI probe above).
            poly = _get_polymarket_data(home_name, away_name, match)
            poly_side_key = "home" if side_label == "Home" else "away"
            poly_prob_pct = poly["implied_pct"].get(poly_side_key) if poly else None
            poly_steam_pct = poly["steam_pct"].get(poly_side_key) if poly else None
            poly_tag = f" PM={poly_prob_pct:.1f}%" if poly_prob_pct is not None else " PM=n/a"
            if poly_steam_pct is not None:
                poly_tag += f"(steam{poly_steam_pct:+.1f}%)"

            print(
                f"[STAIR_AI ENGINE] CANDIDATE: {match} [{league}] | {side_label} @ {odds:.2f} "
                f"model={prob_pct:.1f}% implied={dv_implied*100:.1f}% "
                f"edge=+{edge*100:.1f}pp EV={ev_val*100:.1f}%{stairai_tag}{poly_tag}"
            )

            # ── 3b. Gemini CDP reasoning ──────────────────────────────────────
            gemini_text = _gemini_reason(
                match=match,
                league=league,
                side=side_label,
                model_prob_pct=prob_pct,
                betz_odds=odds,
                betz_implied_pct=dv_implied * 100,
                edge_pp=edge * 100,
                stairai_prob_pct=stairai_prob_pct,
                polymarket_prob_pct=poly_prob_pct,
                polymarket_steam_pct=poly_steam_pct,
            )
            approved = _parse_decision(gemini_text)

            if gemini_text == "NO_GEMINI":
                action = "approving" if GEMINI_FALLBACK else "skipping"
                print(f"[STAIR_AI ENGINE] Gemini unavailable — {action} {match} {side_label}.")
            else:
                reason_m = re.search(r"REASON:\s*(.+)", gemini_text, re.IGNORECASE)
                reason = reason_m.group(1).strip() if reason_m else gemini_text[:80]
                print(f"[STAIR_AI ENGINE] Gemini {'YES' if approved else 'NO'}: {reason}")

            if not approved:
                print(f"[STAIR_AI ENGINE] Gemini rejected {match} {side_label} — skip.")
                continue

            # ── 4. Log paper bet ──────────────────────────────────────────────
            try:
                bet_id = log_bet_fn(
                    match,
                    "1X2",
                    side_label,
                    odds,
                    prob_pct,
                    ev_val,
                    fixture_id,
                    league,
                    source="STAIR_AI",
                )
                if bet_id:
                    _logged_this_run.add(dedup_key)
                    placed += 1
                    print(
                        f"[STAIR_AI ENGINE] BET LOGGED: {match} [{league}] | "
                        f"{side_label} @ {odds:.2f} (EV={ev_val*100:.1f}% edge=+{edge*100:.1f}pp) "
                        f"id={bet_id}"
                    )
            except Exception as e:
                print(f"[STAIR_AI ENGINE] log_bet_fn error for {match}: {e}")

    print(f"[STAIR_AI ENGINE] Cycle complete — {placed} bets logged.")
    return placed
