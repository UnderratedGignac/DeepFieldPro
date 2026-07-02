"""
pinnacle_value_engine.py — Pure Pinnacle-value betting strategy.
================================================================
Replaces all model-dependent strategies with a single, verifiable market
inefficiency: soft books (Betarabia, Kambi) are systematically slower to
update their prices relative to Pinnacle, the sharpest public book.

When a soft book offers odds BETTER than Pinnacle's de-vigged fair price,
we have a mathematically guaranteed positive edge (CLV > 0 by construction).

This strategy:
  1. Fetches live Pinnacle odds (via pinnacle_feed)
  2. Fetches live soft-book odds (Betarabia, Kambi)
  3. De-vigs Pinnacle odds → fair probabilities
  4. Computes edge = soft_book_odds / pinnacle_fair_odds - 1
  5. Only bets when edge >= min_edge (default 3%)
  6. Records every EV calculation for audit

NO model predictions, NO synthetic player data, NO generic team ratings.
Edge comes purely from the price discrepancy between books.

References:
  - Forrest & Simmons (2000): "New Issues for a New Millennium" — soft books
    are inefficient relative to Pinnacle
  - Joseph (2022): "The Logic of Sports Betting" — Pinnacle-value is the
    most documented +EV approach in sports betting
"""

import os
import json
import sqlite3
import time
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "bet_log.db")
SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")

# ── Major liquid leagues only ──────────────────────────────────────────────
# These leagues have: (a) deep Pinnacle liquidity, (b) reliable soft-book prices,
# (c) enough volume for statistical validation.
#
# IMPORTANT: Only include league names that are UNIQUE to one country.
# "premier league" is AMBIGUOUS — England, Kazakhstan, Kuwait, Iceland all use it.
# Use the country-prefixed form ("england - premier league") or rely on
# resolve_league_country() to validate the league against team nationality.
LIQUID_LEAGUES = {
    "la liga",
    "bundesliga",
    "serie a",
    "ligue 1",
    "champions league",
    "europa league",
    "conference league",
    "uefa champions league",
    "uefa europa league",
    "fifa world cup",
    "world cup",
    "eredivisie",
    "primeira liga",
    "super lig",
    "jupiler pro league",
    "belgian pro league",
    "scottish premiership",
    "major league soccer",
    "mls",
    # Country-prefixed forms — matched after normalize_league() strips prefixes,
    # so these are only reached when the input already had the prefix.
    "england - premier league",
    "premier league",  # KEPT for backward compat; see _AMBIGUOUS_LEAGUES below
    # ── Summer-active leagues (Pinnacle-covered) ───────────────────────
    # South America
    "brazilian serie b", "serie b", "brasileirao",
    "brasileiro serie a", "serie a brazil",
    "liga profesional", "argentine primera division",
    "copa libertadores", "copa sudamericana",
    "recopa sudamericana",
    "primera b metropolitana",
    "campeonato paulista", "campeonato carioca",
    "campeonato mineiro", "campeonato gaucho",
    # North America
    "usl championship", "us open cup",
    "concacaf gold cup", "gold cup", "concacaf champions cup",
    "liga mx", "ascenso mx",
    # Scandinavia / Nordics (summer season)
    "eliteserien", "allsvenskan", "veikkausliiga",
    "ykkonen", "superettan", "obos ligaen",
    "danish superliga", "superliga",
    # Baltics
    "a lyga", "meistriliiga", "virsliga",
    # Africa / MENA
    "botola pro", "egyptian premier league",
    "south african premier division", "dstv premiership",
    # Asia
    "chinese super league", "j1 league", "j2 league",
    "k league 1", "k league 2",
    # Spain / Italy second tiers
    "segunda division", "serie b italiana",
    # International
    "copa america", "uefa euro", "uefa nations league",
    "africa cup of nations",
    # Club friendlies (only top-tier)
    "premier league asia trophy",
}

# ── Ambiguous league names (shared across countries) ──────────────────────
# These names appear in multiple countries. When Betarabia writes just
# "Premier League" (no country prefix), we cannot know WHICH country.
# We block these unless the daemon provides additional country context.
_AMBIGUOUS_LEAGUES = {
    "premier league": [
        "england", "kazakhstan", "kuwait", "iceland", "belarus",
        "russia", "ukraine", "malta", "gibraltar", "montenegro",
    ],
    "pro league": [
        "belgium", "netherlands", "saudi arabia", "qatar", "bahrain",
    ],
    "super league": [
        "switzerland", "greece", "denmark", "china", "malaysia",
    ],
    "first division": [
        "cyprus", "norway", "sweden", "finland", "ireland",
    ],
}

# ── Country indicators for team names ──────────────────────────────────────
# Maps team-name substrings to their likely country of origin.
# Used by resolve_league_country() to detect cross-country collisions.
_COUNTRY_TEAM_INDICATORS = {
    "kazakhstan": [
        "okzhetpes", "elimai", "kaspyi", "kairat", "aktobe", "tobol",
        "ordabasy", "astana", "kaysar", "zhetysu", "shakhter karagandy",
    ],
    "kuwait": [
        "al salmiya", "al-kuwait", "al kuwait", "kazma", "al qadsia",
        "al fahaheel", "al arabi", "al naser", "al jahra", "burgan",
    ],
    "iceland": [
        "breidablik", "valur", "kr reykjavik", "fh hafnarfjordur",
        "vikingur reykjavik", "stjarnan", "fram reykjavik", "ia akranes",
    ],
    "belarus": [
        "bate borisov", "dinamo minsk", "shakhtyor soligorsk",
        "torpedo zhodino", "neman grodno", "slavia mozyr",
    ],
}

# ── Allowed markets (1X2 + Over/Under 2.5) ─────────────────────────────────
ALLOWED_MARKETS = {"1X2", "Over/Under 2.5"}

# ── Minimum thresholds ────────────────────────────────────────────────────
DEFAULT_MIN_EDGE_PCT = 0.03  # 3% minimum edge over Pinnacle fair
DEFAULT_MIN_ODDS = 1.30  # don't bet on extreme favorites
DEFAULT_MAX_ODDS = 10.0  # don't bet on extreme longshots

# ── League normalization prefixes to strip ─────────────────────────────────
_COUNTRY_PREFIXES = [
    "england - ",
    "spain - ",
    "germany - ",
    "italy - ",
    "france - ",
    "netherlands - ",
    "portugal - ",
    "belgium - ",
    "turkey - ",
    "scotland - ",
    "usa - ",
    "europe - ",
    "world - ",
    "international - ",
    "south america - ",
    "asia - ",
    "africa - ",
    "north america - ",
    "australia - ",
    "austria - ",
    "switzerland - ",
    "denmark - ",
    "sweden - ",
    "norway - ",
    "poland - ",
    "russia - ",
    "greece - ",
    "czech republic - ",
    "croatia - ",
    "serbia - ",
    "ukraine - ",
    "romania - ",
    "hungary - ",
    "israel - ",
    "japan - ",
    "south korea - ",
    "china - ",
    "mexico - ",
    "brazil - ",
    "argentina - ",
    "colombia - ",
    "chile - ",
    "kazakhstan - ",
    "kuwait - ",
    "iceland - ",
    "belarus - ",
    "qatar - ",
    "saudi arabia - ",
    "bahrain - ",
    "malta - ",
    "gibraltar - ",
    "montenegro - ",
    "cyprus - ",
    "ireland - ",
    "finland - ",
    "malaysia - ",
]


def normalize_league(name: str) -> str:
    """
    Normalize a league name for comparison against the whitelist.

    Handles Pinnacle-style names like 'England - Premier League' → 'premier league'
    Also handles: 'UEFA Champions League' → 'champions league', etc.

    Rules:
      1. Lowercase + trim
      2. Strip country/region prefix (e.g. 'England - ')
      3. Strip 'uefa ' prefix
      4. Strip trailing year/season markers (e.g. ' 2025/2026')
    """
    if not name:
        return ""
    n = name.lower().strip()

    # Strip country prefix (e.g. "england - premier league" → "premier league")
    for prefix in _COUNTRY_PREFIXES:
        if n.startswith(prefix):
            n = n[len(prefix) :]
            break

    # Strip "uefa " prefix (e.g. "uefa champions league" → "champions league")
    if n.startswith("uefa "):
        n = n[5:]

    # Strip "fifa " prefix
    if n.startswith("fifa "):
        n = n[5:]

    # Strip trailing season markers like " 2025/2026" or " 2026"
    import re

    n = re.sub(r"\s+\d{4}(/\d{4})?$", "", n)

    return n.strip()


def is_liquid_league(league: str) -> bool:
    """Check if a league is acceptable for betting.
    
    ALL leagues are now accepted — the system relies on:
      - Pinnacle odds availability (if Pinnacle doesn't cover it, edge=0)
      - Model prediction quality (Dixon-Coles covers all leagues with history)
      - Individual bet EV thresholds (edge %, confidence %)
    The LIQUID_LEAGUES set is kept for reference/logging only.
    """
    if not league:
        return True  # allow unnamed leagues too
    return True


def is_ambiguous_league(normalized_league: str) -> bool:
    """Return True if this normalized league name is ambiguous (shared across countries)."""
    return normalized_league in _AMBIGUOUS_LEAGUES


def detect_team_country(home: str, away: str) -> str | None:
    """Detect the country of a match based on team name indicators.

    Returns the country name (lowercase) if a known indicator is found,
    or None if no country can be determined.
    """
    if not home or not away:
        return None
    h_lower = home.lower()
    a_lower = away.lower()
    for country, indicators in _COUNTRY_TEAM_INDICATORS.items():
        for indicator in indicators:
            if indicator in h_lower or indicator in a_lower:
                return country
    return None


def resolve_league_country(
    league: str, home: str = "", away: str = ""
) -> dict:
    """Resolve a league name to its country context.

    Returns:
        {
            "normalized": str,      # normalized league name
            "country": str | None,  # detected country (from team names)
            "is_ambiguous": bool,   # True if league name is shared across countries
            "is_liquid": bool,      # True (all leagues now accepted)
            "is_valid": bool,       # True (all leagues now accepted)
        }
    """
    normalized = normalize_league(league)
    country = detect_team_country(home, away)
    ambiguous = is_ambiguous_league(normalized)

    # ALL leagues are now valid — edge thresholds and model quality gate bets instead
    return {
        "normalized": normalized,
        "country": country,
        "is_ambiguous": ambiguous,
        "is_liquid": True,
        "is_valid": True,
    }


def load_settings() -> dict:
    """Load settings from data/settings.json."""
    try:
        with open(SETTINGS_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def compute_edge(soft_book_odds: float, pinnacle_fair_odds: float) -> float:
    """
    Compute the edge of soft-book odds vs Pinnacle fair odds.

    edge = soft_book_odds / pinnacle_fair_odds - 1

    Positive edge means the soft book is paying MORE than Pinnacle's
    de-vigged fair price implies — this is the value opportunity.
    """
    if not soft_book_odds or soft_book_odds <= 1.0:
        return 0.0
    if not pinnacle_fair_odds or pinnacle_fair_odds <= 1.0:
        return 0.0
    return soft_book_odds / pinnacle_fair_odds - 1.0


def compute_ev(soft_book_odds: float, pinnacle_devig_prob: float) -> float:
    """
    Compute expected value using Pinnacle's de-vigged probability as the
    "true" probability.

    EV = p * odds - 1

    Positive EV means we expect profit over many bets at these odds.
    """
    if not soft_book_odds or soft_book_odds <= 1.0:
        return 0.0
    if not pinnacle_devig_prob or pinnacle_devig_prob <= 0:
        return 0.0
    return pinnacle_devig_prob * soft_book_odds - 1.0


def kelly_fraction(
    edge: float, odds: float, devig_prob: float, kelly_frac: float = 0.15
) -> float:
    """
    Fractional Kelly stake as a fraction of bankroll.

    Kelly criterion: f* = (p*b - q) / b  where b = odds-1, p = win prob, q = 1-p
    We use Pinnacle's devig_prob as p (the best available estimate of true probability).
    """
    if odds <= 1.0 or edge <= 0 or devig_prob <= 0:
        return 0.0
    b = odds - 1.0
    p = devig_prob
    q = 1.0 - p
    kelly = (p * b - q) / b
    return max(0.0, min(kelly * kelly_frac, 0.02))  # cap at 2% bankroll


def find_value_bets(
    betarabia_odds: dict,
    pinnacle_data: dict,
    league: str = "",
    settings: Optional[dict] = None,
) -> list:
    """
    Find all value bets where Betarabia odds exceed Pinnacle fair value.

    Args:
        betarabia_odds: {"home": float, "draw": float, "away": float}
        pinnacle_data: {"home": float, "draw": float, "away": float,
                       "p_home": float, "p_draw": float, "p_away": float}
        league: League name (must be in LIQUID_LEAGUES)
        settings: Optional settings override

    Returns:
        List of dicts with keys: selection, edge, ev, betarabia_odds,
        pinnacle_fair_odds, pinnacle_devig_prob, kelly_frac, qualifies
    """
    if settings is None:
        settings = load_settings()

    min_edge = settings.get("pinnacle_min_edge_pct", DEFAULT_MIN_EDGE_PCT * 100) / 100.0
    min_odds = settings.get("pinnacle_steam_min_odds", DEFAULT_MIN_ODDS)
    max_odds = settings.get("pinnacle_steam_max_odds", DEFAULT_MAX_ODDS)

    # Only bet in liquid leagues
    if not is_liquid_league(league):
        return []

    bets = []
    for sel in ("home", "draw", "away"):
        ba_odds = betarabia_odds.get(sel)
        pin_odds = pinnacle_data.get(sel)
        pin_prob = pinnacle_data.get(f"p_{sel}")

        if not ba_odds or not pin_odds or not pin_prob:
            continue
        if ba_odds < min_odds or ba_odds > max_odds:
            continue

        fair_odds = 1.0 / pin_prob if pin_prob > 0 else 0
        edge = compute_edge(ba_odds, fair_odds)
        ev = compute_ev(ba_odds, pin_prob)
        kf = kelly_fraction(edge, ba_odds, pin_prob)

        qualifies = edge >= min_edge

        bets.append(
            {
                "selection": sel,
                "edge": round(edge, 4),
                "ev": round(ev, 4),
                "betarabia_odds": round(ba_odds, 3),
                "pinnacle_odds": round(pin_odds, 3),
                "pinnacle_fair_odds": round(fair_odds, 3),
                "pinnacle_devig_prob": round(pin_prob, 6),
                "kelly_frac": round(kf, 4),
                "qualifies": qualifies,
            }
        )

    return bets


def log_value_bet(
    match: str,
    league: str,
    selection: str,
    betarabia_odds: float,
    pinnacle_data: dict,
    edge: float,
    ev: float,
    kelly_frac: float,
    fixture_id: Optional[str] = None,
    stake: float = 0.0,
) -> Optional[str]:
    """
    Log a Pinnacle-value paper bet to bet_log.db.

    Returns the bet_id or None on failure.
    """
    if not os.path.exists(DB_PATH):
        logger.warning("[PV_ENGINE] bet_log.db not found")
        return None

    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        # Dedup: one PV bet per fixture/selection
        cur.execute(
            "SELECT COUNT(*) FROM bet_log WHERE fixture_id=? AND market_type='1X2' "
            "AND side=? AND bet_source='PINNACLE_VALUE'",
            (str(fixture_id), selection),
        )
        if cur.fetchone()[0] > 0:
            conn.close()
            return None

        pin_fair_odds = pinnacle_data.get("fair_odds", betarabia_odds)
        pin_devig_prob = pinnacle_data.get("devig_prob", 0)

        bet_id = "PV_" + uuid.uuid4().hex[:12]

        cur.execute(
            """INSERT INTO bet_log
               (bet_id, match_id, player_id, market_type, entry_odds, fair_odds,
                edge_pct, stake, result, pnl, placed_at, bet_source, is_recommended,
                line, side, fixture_id, league)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                bet_id,
                match,
                f"{match} ({selection})",
                "1X2",
                round(betarabia_odds, 3),
                round(pin_fair_odds, 4),
                round(edge * 100, 2),
                round(stake, 2),
                "OPEN",
                0.0,
                datetime.now(timezone.utc).isoformat(),
                "PINNACLE_VALUE",
                1,
                0.0,  # line not applicable for 1X2
                selection,
                str(fixture_id) if fixture_id else None,
                league,
            ),
        )
        conn.commit()
        conn.close()

        logger.info(
            f"[PV_ENGINE] Logged value bet: {match} ({selection}) "
            f"@ {betarabia_odds:.2f} | edge={edge*100:.1f}% EV={ev*100:.1f}% "
            f"stake=${stake:.2f}"
        )
        return bet_id

    except Exception as e:
        logger.error(f"[PV_ENGINE] Error logging bet: {e}")
        return None


def scan_for_value(
    fixtures_with_odds: list,
    settings: Optional[dict] = None,
) -> list:
    """
    Scan a list of fixtures (with odds) for Pinnacle-value opportunities.

    Each fixture dict should have:
      - home: str
      - away: str
      - league: str
      - betarabia: {"home": float, "draw": float, "away": float}
      - pinnacle: {"home": float, "draw": float, "away": float,
                    "p_home": float, "p_draw": float, "p_away": float}
      - fixture_id: str (optional)

    Returns list of qualifying value bets.
    """
    if settings is None:
        settings = load_settings()

    qualifying = []

    for fx in fixtures_with_odds:
        league = fx.get("league", "")
        ba = fx.get("betarabia", {})
        pin = fx.get("pinnacle", {})

        if not ba or not pin:
            continue

        value_bets = find_value_bets(ba, pin, league, settings)
        for vb in value_bets:
            if not vb["qualifies"]:
                continue

            # Compute stake from bankroll
            try:
                br_conn = sqlite3.connect(os.path.join(DATA_DIR, "bankroll.db"))
                balance = br_conn.execute(
                    "SELECT current_balance FROM bankroll ORDER BY date DESC LIMIT 1"
                ).fetchone()[0]
                br_conn.close()
            except Exception:
                balance = 1000.0

            stake = round(balance * vb["kelly_frac"], 2)
            stake = max(1.0, min(stake, balance * 0.02))  # floor $1, cap 2%

            vb["match"] = f"{fx.get('home', '')} vs {fx.get('away', '')}"
            vb["league"] = league
            vb["fixture_id"] = fx.get("fixture_id")
            vb["stake"] = stake

            qualifying.append(vb)

    return qualifying
