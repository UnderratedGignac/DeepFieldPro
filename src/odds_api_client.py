"""
odds_api_client.py -- The Odds API integration for DeepFieldPro line shopping.

Provides fetch_best_odds() to query the best available 1X2 decimal prices across
bookmakers for a given match. Uses a 5-minute in-process cache to stay within the
free-tier budget (500 requests/month).

Usage:
    from src.odds_api_client import fetch_best_odds
    result = fetch_best_odds("Arsenal", "Chelsea")
    # {"best_home": 2.10, "best_draw": 3.40, "best_away": 3.60, "bookmakers": [...]}

API key is read from ODDS_API_KEY in the environment or from the project .env file.
If no key is configured the function returns silently with all-None values.
"""

import os
import time
import requests

# ---------------------------------------------------------------------------
# Cache: endpoint URL -> (epoch_fetched, response_data)
# A single entry per sport/market combination (soccer_epl, h2h).
# ---------------------------------------------------------------------------
_CACHE_TTL = 300  # 5 minutes
_odds_cache: dict[str, tuple[float, list]] = {}

# Path to .env relative to this file (src/ -> project root)
_ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")

_BASE_URL = "https://api.the-odds-api.com/v4/sports/{sport}/odds/"
_DEFAULT_SPORT = "soccer_epl"


def _resolve_api_key() -> str:
    """Read ODDS_API_KEY from os.environ first, then fall back to parsing .env directly.

    The .env file is not necessarily loaded into os.environ at import time (e.g. when
    this module is imported inside the daemon thread), so we duplicate the resilient
    pattern used by _stair_api_key() in live_predictions_daemon.py.
    """
    k = os.getenv("ODDS_API_KEY")
    if k and k.strip():
        return k.strip()
    try:
        with open(_ENV_PATH, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line.startswith("ODDS_API_KEY="):
                    value = line.split("=", 1)[1].strip()
                    if value:
                        return value
    except OSError:
        pass
    return ""


def _fetch_raw(sport: str = _DEFAULT_SPORT) -> list:
    """Fetch (or return cached) raw odds data from The Odds API for the given sport.

    Returns a list of event dicts as returned by the /v4/sports/{sport}/odds/ endpoint,
    or an empty list on any error (missing key, network failure, non-200 response).
    """
    api_key = _resolve_api_key()
    if not api_key:
        return []

    cache_key = sport
    cached = _odds_cache.get(cache_key)
    if cached and (time.time() - cached[0]) < _CACHE_TTL:
        return cached[1]

    url = _BASE_URL.format(sport=sport)
    params = {
        "apiKey": api_key,
        "regions": "eu",
        "markets": "h2h",
        "oddsFormat": "decimal",
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            _odds_cache[cache_key] = (time.time(), data)
            return data
        else:
            # Log non-200 responses without crashing (e.g. 401 bad key, 422 quota)
            print(
                f"[OddsAPI] Unexpected status {resp.status_code} for sport={sport}: "
                f"{resp.text[:200]}"
            )
            return []
    except Exception as exc:
        print(f"[OddsAPI] Network error fetching odds for sport={sport}: {exc}")
        return []


def _normalise(name: str) -> str:
    """Lowercase + strip for case-insensitive team name comparison."""
    return name.lower().strip()


def _empty_result() -> dict:
    return {"best_home": None, "best_draw": None, "best_away": None, "bookmakers": []}


def fetch_best_odds(
    home_team: str,
    away_team: str,
    sport: str = _DEFAULT_SPORT,
) -> dict:
    """Query The Odds API for the best available 1X2 prices for a match.

    Matches the given home_team / away_team against the API's home_team / away_team
    fields using case-insensitive comparison. Returns the maximum decimal odds across
    all bookmakers for each of the three 1X2 outcomes.

    Args:
        home_team: Home team name (must match The Odds API naming, case-insensitive).
        away_team: Away team name (must match The Odds API naming, case-insensitive).
        sport: The Odds API sport key (default: "soccer_epl"). Swap for other leagues,
               e.g. "soccer_germany_bundesliga", "soccer_spain_la_liga", etc.

    Returns:
        {
            "best_home": float | None,   # best decimal odds for home win
            "best_draw": float | None,   # best decimal odds for draw
            "best_away": float | None,   # best decimal odds for away win
            "bookmakers": [              # raw bookmaker names that had this fixture
                "Betsson", "Unibet", ...
            ],
        }
        All-None dict (with empty bookmakers list) when:
          - ODDS_API_KEY is not set / blank
          - The match is not found in the API response
          - Any network or parsing error occurs
    """
    raw = _fetch_raw(sport=sport)
    if not raw:
        return _empty_result()

    norm_home = _normalise(home_team)
    norm_away = _normalise(away_team)

    # Find the matching event
    event = None
    for ev in raw:
        if (
            _normalise(ev.get("home_team", "")) == norm_home
            and _normalise(ev.get("away_team", "")) == norm_away
        ):
            event = ev
            break

    if event is None:
        return _empty_result()

    best_home: float | None = None
    best_draw: float | None = None
    best_away: float | None = None
    bookmaker_names: list[str] = []

    for bk in event.get("bookmakers", []):
        bk_name = bk.get("title", "")
        for market in bk.get("markets", []):
            if market.get("key") != "h2h":
                continue
            outcomes = market.get("outcomes", [])
            for outcome in outcomes:
                name = outcome.get("name", "")
                price = outcome.get("price")
                if price is None:
                    continue
                try:
                    price = float(price)
                except (TypeError, ValueError):
                    continue

                norm_name = _normalise(name)
                if norm_name == norm_home:
                    if best_home is None or price > best_home:
                        best_home = price
                        if bk_name not in bookmaker_names:
                            bookmaker_names.append(bk_name)
                elif norm_name == norm_away:
                    if best_away is None or price > best_away:
                        best_away = price
                        if bk_name not in bookmaker_names:
                            bookmaker_names.append(bk_name)
                elif norm_name == "draw":
                    if best_draw is None or price > best_draw:
                        best_draw = price
                        if bk_name not in bookmaker_names:
                            bookmaker_names.append(bk_name)

    return {
        "best_home": best_home,
        "best_draw": best_draw,
        "best_away": best_away,
        "bookmakers": bookmaker_names,
    }


if __name__ == "__main__":
    # Quick smoke-test: python src/odds_api_client.py
    import sys

    home = sys.argv[1] if len(sys.argv) > 2 else "Arsenal"
    away = sys.argv[2] if len(sys.argv) > 2 else "Chelsea"
    result = fetch_best_odds(home, away)
    print(f"fetch_best_odds({home!r}, {away!r}) -> {result}")
