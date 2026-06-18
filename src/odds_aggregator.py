"""
odds_aggregator.py — Multi-book best-price finder (no API limits).

Sources (all unlimited, no keys required except Betfair):
  1. Pinnacle  — sharpest public book; guest API key; unlimited calls.
  2. 1xBet     — major soft book; public JSON API; no auth; no rate limit.
  3. Betfair   — Exchange market; ~3% commission; unlimited for registered users.
                 Needs BETFAIR_USERNAME / BETFAIR_PASSWORD / BETFAIR_APP_KEY in .env.

Two public functions:
    get_pinnacle_probs(home, away) -> (p_h, p_d, p_a) or None
        De-vigged Pinnacle fair probabilities for LightGBM market features.
        These are the top predictors in the model (mkt_d_prob #1, mkt_a_prob #3).

    get_best_price(home, away, betarabia_h, betarabia_d, betarabia_a) -> dict
        Best decimal odds across all sources. Used to flag line-shopping gaps
        on the dashboard; EV gate still uses the Betarabia price you actually bet.

All sources are cached 5 minutes so the daemon's 30-second loop makes at most
one network call per source per 5-minute window, not one per fixture.
"""
import os
import time
import logging
import requests
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

_CACHE: dict = {}
_TTL = 300  # 5-min module-level cache


# ---------------------------------------------------------------------------
# Helpers shared by all fetchers
# ---------------------------------------------------------------------------

def _sim(a: str, b: str) -> float:
    return SequenceMatcher(None, (a or "").lower(), (b or "").lower()).ratio()


def _fuzzy_match(home: str, away: str, book_dict: dict):
    """Return the closest fixture entry in book_dict by team-name similarity."""
    direct = f"{home} vs {away}"
    if direct in book_dict:
        return book_dict[direct]
    best_score, best_val = 0.0, None
    for k, v in book_dict.items():
        h2 = v.get("home_team") or (k.split(" vs ")[0] if " vs " in k else "")
        a2 = v.get("away_team") or (k.split(" vs ")[-1] if " vs " in k else "")
        score = min(_sim(home, h2), _sim(away, a2))
        if score > best_score:
            best_score, best_val = score, v
    return best_val if best_score >= 0.75 else None


def _devig(h, d, a):
    """De-vig three-way odds → (p_h, p_d, p_a). Returns None on bad input."""
    try:
        inv_h = 1.0 / h if h and h > 1 else 0.0
        inv_d = 1.0 / d if d and d > 1 else 0.0
        inv_a = 1.0 / a if a and a > 1 else 0.0
        tot = inv_h + inv_d + inv_a
        if tot <= 0 or inv_h == 0 or inv_a == 0:
            return None
        return inv_h / tot, inv_d / tot, inv_a / tot
    except Exception:
        return None


def _merge_best(result: dict, src: dict, sel_keys=("home", "draw", "away")):
    """Update result with higher prices from src, in-place."""
    for k in sel_keys:
        v = src.get(k, 0) or 0
        if v > result.get(k, 0):
            result[k] = v


# ---------------------------------------------------------------------------
# Source 1: Pinnacle (unlimited, sharpest line)
# ---------------------------------------------------------------------------

def _fetch_pinnacle() -> dict:
    now = time.time()
    cached = _CACHE.get("pinnacle")
    if cached and now - cached[0] < _TTL:
        return cached[1]
    try:
        from src.sharp_scraper import fetch_pinnacle_1x2
        data = fetch_pinnacle_1x2()
        _CACHE["pinnacle"] = (now, data)
        return data
    except Exception as e:
        logger.debug(f"[ODDSAGG] Pinnacle: {e}")
        return cached[1] if cached else {}


# ---------------------------------------------------------------------------
# Source 2: 1xBet (public JSON API, no auth, no rate limit)
# ---------------------------------------------------------------------------

_1XBET_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://1xbet.com/",
}

def _fetch_1xbet() -> dict:
    """
    Fetches today's soccer 1X2 prices from 1xBet's public API.
    1xBet is a high-volume soft book; its prices often lag Pinnacle by 30-60 min,
    creating genuine line-shopping opportunities.

    API pattern (public, no auth):
      GET https://1xbet.com/LineFeed/GetSports
          ?sports=1&type=online&count=50&lng=en&tf=10800&tz=1
      Returns a list of events with odds including home/draw/away (market type 1).
    """
    now = time.time()
    cached = _CACHE.get("1xbet")
    if cached and now - cached[0] < _TTL:
        return cached[1]

    result: dict = {}
    try:
        resp = requests.get(
            "https://1xbet.com/LineFeed/GetSports",
            params={"sports": "1", "type": "online", "count": "100",
                    "lng": "en", "tf": "10800", "tz": "1"},
            headers=_1XBET_HEADERS,
            timeout=15,
        )
        if resp.status_code != 200:
            logger.debug(f"[1xBet] HTTP {resp.status_code}")
            _CACHE["1xbet"] = (now, result)
            return result

        data = resp.json()
        events = data if isinstance(data, list) else data.get("Value", [])

        for ev in events:
            # Skip non-match events (outrights, etc.)
            if not ev.get("O") or not ev.get("O2"):  # home / away team
                continue
            home = ev.get("O", "").strip()
            away = ev.get("O2", "").strip()
            if not home or not away:
                continue

            odds_1 = odds_x = odds_2 = None
            for odd in (ev.get("E") or []):
                t = odd.get("T")   # market type; 1=1X2
                g = odd.get("G")   # group (1=home, 2=draw, 3=away for 1X2)
                v = odd.get("C")   # decimal odds value
                if t == 1 and v and float(v) > 1.0:
                    if g == 1:
                        odds_1 = float(v)
                    elif g == 2:
                        odds_x = float(v)
                    elif g == 3:
                        odds_2 = float(v)

            if odds_1 and odds_2:
                result[f"{home} vs {away}"] = {
                    "home": odds_1,
                    "draw": odds_x or 0.0,
                    "away": odds_2,
                    "home_team": home,
                    "away_team": away,
                }
    except Exception as e:
        logger.debug(f"[1xBet] {e}")

    _CACHE["1xbet"] = (now, result)
    return result


# ---------------------------------------------------------------------------
# Source 3: Betfair Exchange (unlimited for registered users, ~3% commission)
# ---------------------------------------------------------------------------

def _fetch_betfair(home: str, away: str) -> dict | None:
    """
    Fetch Betfair Exchange best-back prices for a specific match.
    Returns {"home": float, "draw": float, "away": float} (gross odds, pre-commission)
    or None if Betfair is not configured / match not found.

    Commission (default 5%) is NOT applied here — the caller can decide whether
    to net-down for EV display vs show gross for comparison.
    """
    try:
        from src.betfair_odds import get_betfair_odds
        return get_betfair_odds(home, away)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_pinnacle_probs(home: str, away: str):
    """
    De-vigged Pinnacle 1X2 fair probabilities → (p_home, p_draw, p_away) or None.
    Pass as (mkt_h_prob, mkt_d_prob, mkt_a_prob) when calling LightGBM.
    """
    pm = _fuzzy_match(home, away, _fetch_pinnacle())
    if not pm:
        return None
    return _devig(pm.get("home"), pm.get("draw"), pm.get("away"))


def get_best_price(home: str, away: str,
                   betarabia_h=None, betarabia_d=None, betarabia_a=None) -> dict:
    """
    Best available decimal odds across Pinnacle, 1xBet, Betfair, and Betarabia.

    Returns:
        {
            "home":           float,        # best H odds across all sources
            "draw":           float,
            "away":           float,
            "pinnacle_home":  float | None, # raw Pinnacle price (CLV reference)
            "pinnacle_draw":  float | None,
            "pinnacle_away":  float | None,
            "betfair_home":   float | None, # Betfair gross (pre-commission)
            "betfair_draw":   float | None,
            "betfair_away":   float | None,
            "sources":        int,          # number of book sources
        }

    How to use the results:
      - bet_ev      = prob * betarabia_price - 1   (what paper bet actually gets)
      - best_ev     = prob * result["home"] - 1    (max with line shopping)
      - clv_vs_pinn = betarabia_price / result["pinnacle_home"] - 1
      - Flag for dashboard: result["home"] > betarabia_h + 0.02 → "BETTER PRICE"
    """
    result = {
        "home": betarabia_h or 0.0,
        "draw": betarabia_d or 0.0,
        "away": betarabia_a or 0.0,
        "pinnacle_home": None,
        "pinnacle_draw": None,
        "pinnacle_away": None,
        "betfair_home": None,
        "betfair_draw": None,
        "betfair_away": None,
        "sources": 1 if betarabia_h else 0,
    }

    # Pinnacle
    pm = _fuzzy_match(home, away, _fetch_pinnacle())
    if pm:
        ph, pd_, pa = pm.get("home"), pm.get("draw"), pm.get("away")
        result["pinnacle_home"] = ph
        result["pinnacle_draw"] = pd_
        result["pinnacle_away"] = pa
        _merge_best(result, {"home": ph, "draw": pd_, "away": pa})
        result["sources"] += 1

    # 1xBet
    xm = _fuzzy_match(home, away, _fetch_1xbet())
    if xm:
        _merge_best(result, xm)
        result["sources"] += 1

    # Betfair Exchange (per-match call; only fires if credentials configured)
    bf = _fetch_betfair(home, away)
    if bf:
        result["betfair_home"] = bf.get("Home")
        result["betfair_draw"] = bf.get("Draw")
        result["betfair_away"] = bf.get("Away")
        _merge_best(result, {
            "home": bf.get("Home", 0),
            "draw": bf.get("Draw", 0),
            "away": bf.get("Away", 0),
        })
        result["sources"] += 1

    return result
