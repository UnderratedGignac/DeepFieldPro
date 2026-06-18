"""
betfair_odds.py — Betfair Exchange live odds integration.
=========================================================
Fetches pre-match 1X2 exchange odds (best available back price) for today's
football fixtures. Betfair Exchange has ~3% commission vs Betarabia's ~9%
overround — the lower margin means your model needs far less edge to profit.

Setup (add to .env):
    BETFAIR_USERNAME=your_email@example.com
    BETFAIR_PASSWORD=your_password
    BETFAIR_APP_KEY=your_app_key          # from developer.betfair.com

Usage:
    from src.betfair_odds import get_betfair_odds
    odds = get_betfair_odds("Arsenal", "Chelsea")
    # returns {"Home": 2.10, "Draw": 3.40, "Away": 3.60} or None

To get a Betfair App Key:
  1. Log in at developer.betfair.com
  2. My Account -> API access -> Create new application
  3. Use the Delayed (free) key for odds retrieval
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_CLIENT = None


def _get_client():
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT
    try:
        import betfairlightweight
        from betfairlightweight import APIClient
        username = os.getenv("BETFAIR_USERNAME", "")
        password = os.getenv("BETFAIR_PASSWORD", "")
        app_key  = os.getenv("BETFAIR_APP_KEY", "")
        if not all([username, password, app_key]) or "your_" in username:
            logger.debug("[Betfair] Credentials not configured — skipping Exchange odds")
            return None
        _CLIENT = APIClient(username, password, app_key=app_key)
        _CLIENT.login()
        logger.info("[Betfair] Logged in to Exchange API")
        return _CLIENT
    except Exception as e:
        logger.warning(f"[Betfair] Login failed: {e}")
        return None


def get_betfair_odds(home_team: str, away_team: str) -> Optional[dict]:
    """
    Returns {Home, Draw, Away} best back prices from Betfair Exchange, or None.
    Uses fuzzy matching on event name to find the correct market.
    Commission is NOT deducted from the returned odds (apply 0.95 factor after).
    """
    client = _get_client()
    if client is None:
        return None
    try:
        from betfairlightweight.filters import market_filter, time_range
        import datetime

        # Search for today's football Match Odds markets
        now = datetime.datetime.utcnow()
        end = now + datetime.timedelta(days=1)
        mf = market_filter(
            event_type_ids=["1"],           # 1 = Soccer
            market_countries=["GB", "IE", "DE", "ES", "IT", "FR", "PT", "NL", "BE", "TR"],
            market_type_codes=["MATCH_ODDS"],
            bsp_only=False,
            in_play_only=False,
            turn_in_play_enabled=True,
        )
        markets = client.betting.list_market_catalogue(
            filter=mf,
            market_projection=["EVENT", "RUNNER_DESCRIPTION"],
            max_results=200,
            sort="FIRST_TO_START",
        )

        # Find the best-matching market by event name
        from rapidfuzz import fuzz
        best_market = None
        best_score = 0.0
        for m in markets:
            ev_name = m.event.name if m.event else ""
            # Betfair uses "Home v Away" format
            expected = f"{home_team} v {away_team}"
            score = fuzz.token_set_ratio(ev_name.lower(), expected.lower()) / 100.0
            if score > best_score:
                best_score = score
                best_market = m

        if best_market is None or best_score < 0.5:
            return None

        # Fetch best back prices
        books = client.betting.list_market_book(
            market_ids=[best_market.market_id],
            price_projection={"priceData": ["EX_BEST_OFFERS"]},
        )
        if not books:
            return None

        book = books[0]
        runners = {r.selection_id: r for r in book.runners}
        # Match runners to Home/Draw/Away by runner description
        result = {}
        for rd in best_market.runners:
            name = rd.runner_name.strip()
            runner = runners.get(rd.selection_id)
            if runner is None:
                continue
            avail = runner.ex.available_to_back if runner.ex else []
            best_price = avail[0].price if avail else None
            if best_price is None:
                continue
            name_lower = name.lower()
            if "draw" in name_lower:
                result["Draw"] = best_price
            elif not result.get("Home"):
                result["Home"] = best_price
            else:
                result["Away"] = best_price

        return result if len(result) == 3 else None

    except Exception as e:
        logger.warning(f"[Betfair] odds fetch failed: {e}")
        return None


def get_betfair_commission() -> float:
    """Standard Betfair commission (5% in most markets). Override in .env if different."""
    return float(os.getenv("BETFAIR_COMMISSION", "0.05"))


def net_odds(gross_odds: float) -> float:
    """Convert gross Betfair back odds to net (after commission on winnings)."""
    comm = get_betfair_commission()
    return 1.0 + (gross_odds - 1.0) * (1.0 - comm)
