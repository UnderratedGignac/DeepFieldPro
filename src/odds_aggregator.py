"""
odds_aggregator.py — Multi-book best-price finder.

Wraps Pinnacle (via sharp_scraper) and The Odds API (free tier, 500 req/month)
to find the best available decimal odds across bookmakers for a given match.

Two public functions:
    get_pinnacle_probs(home, away) -> (p_h, p_d, p_a) or None
        De-vigged Pinnacle fair probabilities — passed as market features to
        LightGBM (top predictors: mkt_d_prob rank 1, mkt_a_prob rank 3).

    get_best_price(home, away, betarabia_h, betarabia_d, betarabia_a) -> dict
        Best decimal odds across all sources per selection. Used to flag when
        line shopping would give you a better price than Betarabia.

The Odds API key is optional — set ODDS_API_KEY in .env for multi-book coverage.
Without it the aggregator still supplies Pinnacle (the sharpest line in the market).
"""
import os
import time
import logging
import requests
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

_CACHE: dict = {}
_TTL = 300  # 5-min cache — refreshes every daemon loop without hammering APIs


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _sim(a: str, b: str) -> float:
    return SequenceMatcher(None, (a or "").lower(), (b or "").lower()).ratio()


def _fuzzy_match(home: str, away: str, book_dict: dict):
    """Return the closest fixture entry in book_dict by team name similarity."""
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


def _load_odds_api_key() -> str:
    key = os.getenv("ODDS_API_KEY", "")
    if not key:
        try:
            from dotenv import dotenv_values
            key = dotenv_values(".env").get("ODDS_API_KEY", "") or ""
        except Exception:
            pass
    return key


def _devig(h, d, a):
    """De-vig three-way odds to (p_h, p_d, p_a). Returns None if inputs invalid."""
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


# ---------------------------------------------------------------------------
# Data fetchers (cached)
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
        logger.debug(f"[ODDSAGG] Pinnacle fetch error: {e}")
        # Return stale on failure rather than empty — avoids losing probs mid-loop
        return (cached[1] if cached else {})


def _fetch_odds_api() -> dict:
    """
    The Odds API (https://the-odds-api.com), free tier.
    Returns best price per match across all contributing bookmakers.
    Requires ODDS_API_KEY in .env; silently returns {} if key is absent.
    """
    now = time.time()
    cached = _CACHE.get("oddsapi")
    if cached and now - cached[0] < _TTL:
        return cached[1]

    key = _load_odds_api_key()
    if not key:
        return {}

    # Top soccer competitions — keep to 5 to preserve the 500 req/month free quota
    SPORTS = [
        "soccer_epl", "soccer_spain_la_liga", "soccer_germany_bundesliga",
        "soccer_france_ligue_one", "soccer_italy_serie_a",
        "soccer_uefa_champs_league", "soccer_uefa_europa_league",
    ]
    result: dict = {}
    try:
        for sport_key in SPORTS:
            resp = requests.get(
                f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds",
                params={"apiKey": key, "regions": "eu,uk",
                        "markets": "h2h", "oddsFormat": "decimal"},
                timeout=12,
            )
            if resp.status_code == 401:
                logger.warning("[ODDSAPI] Bad key — set ODDS_API_KEY in .env")
                break
            if resp.status_code != 200:
                continue

            for event in resp.json():
                home = event.get("home_team", "")
                away = event.get("away_team", "")
                mk = f"{home} vs {away}"
                entry = result.setdefault(
                    mk, {"home": 0.0, "draw": 0.0, "away": 0.0,
                         "books": 0, "home_team": home, "away_team": away})
                for bm in (event.get("bookmakers") or []):
                    for mkt in (bm.get("markets") or []):
                        if mkt.get("key") != "h2h":
                            continue
                        entry["books"] += 1
                        for outcome in (mkt.get("outcomes") or []):
                            n = outcome.get("name", "")
                            p = float(outcome.get("price", 0) or 0)
                            if n == home and p > entry["home"]:
                                entry["home"] = p
                            elif n == away and p > entry["away"]:
                                entry["away"] = p
                            elif n == "Draw" and p > entry["draw"]:
                                entry["draw"] = p
        # Drop entries without valid home+away
        result = {k: v for k, v in result.items()
                  if v["home"] > 1.0 and v["away"] > 1.0}
    except Exception as e:
        logger.warning(f"[ODDSAPI] {e}")

    _CACHE["oddsapi"] = (now, result)
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_pinnacle_probs(home: str, away: str):
    """
    De-vigged Pinnacle 1X2 fair probabilities → (p_home, p_draw, p_away) or None.
    Pass the result directly as (mkt_h_prob, mkt_d_prob, mkt_a_prob) in LightGBM.
    """
    pm = _fuzzy_match(home, away, _fetch_pinnacle())
    if not pm:
        return None
    return _devig(pm.get("home"), pm.get("draw"), pm.get("away"))


def get_best_price(home: str, away: str,
                   betarabia_h=None, betarabia_d=None, betarabia_a=None) -> dict:
    """
    Best available decimal odds across Pinnacle, The Odds API, and Betarabia.

    Returns:
        {
            "home":           float,        # best home odds across all sources
            "draw":           float,        # best draw odds
            "away":           float,        # best away odds
            "pinnacle_home":  float | None, # Pinnacle raw price (for CLV tracking)
            "pinnacle_draw":  float | None,
            "pinnacle_away":  float | None,
            "sources":        int,          # number of book sources contributing
        }

    EV calculated on Betarabia price tells you what the paper bet gets.
    EV on "home"/"draw"/"away" here tells you the theoretical max with line shopping.
    Flag bets where best_price > betarabia_price for dashboard "BETTER PRICE" alerts.
    """
    result = {
        "home": betarabia_h or 0.0,
        "draw": betarabia_d or 0.0,
        "away": betarabia_a or 0.0,
        "pinnacle_home": None,
        "pinnacle_draw": None,
        "pinnacle_away": None,
        "sources": 1 if betarabia_h else 0,
    }

    # Pinnacle
    pm = _fuzzy_match(home, away, _fetch_pinnacle())
    if pm:
        ph, pd_, pa = pm.get("home"), pm.get("draw"), pm.get("away")
        result["pinnacle_home"] = ph
        result["pinnacle_draw"] = pd_
        result["pinnacle_away"] = pa
        if ph and ph > result["home"]:
            result["home"] = ph
        if pd_ and pd_ > result["draw"]:
            result["draw"] = pd_
        if pa and pa > result["away"]:
            result["away"] = pa
        result["sources"] += 1

    # The Odds API (only fires if ODDS_API_KEY is set)
    om = _fuzzy_match(home, away, _fetch_odds_api())
    if om:
        if om.get("home", 0) > result["home"]:
            result["home"] = om["home"]
        if om.get("draw", 0) > result["draw"]:
            result["draw"] = om["draw"]
        if om.get("away", 0) > result["away"]:
            result["away"] = om["away"]
        result["sources"] += om.get("books", 1)

    return result
