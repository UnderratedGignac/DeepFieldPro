"""
fifa_ratings.py — Player FIFA rating lookup & auto-enrichment.
===============================================================
Provides:
  - get_rating(player_name, team_name=None) -> int (0 if unknown)
  - get_player_info(player_name, team_name=None) -> dict
  - enrich_from_espn(home, away, date) -> caches new ratings from ESPN rosters

Uses local SQLite DB (data/fifa_ratings.db) seeded by seed_fifa_ratings.py.
Falls back to ESPN athlete API for players not in the local DB.
"""

import os
import re
import sqlite3
import time
import unicodedata
import requests
from difflib import SequenceMatcher

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "fifa_ratings.db")

_UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}
_ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"

# Import the ESPN leagues list from the existing scraper
try:
    from src.free_results_scraper import ESPN_LEAGUES
except ImportError:
    try:
        from free_results_scraper import ESPN_LEAGUES
    except ImportError:
        ESPN_LEAGUES = ["eng.1", "esp.1", "ger.1", "ita.1", "fra.1"]

# In-memory cache for fast repeated lookups: (name_norm, team_norm) -> rating
_mem_cache = {}
_MEM_TTL = 3600  # 1 hour

# ESPN fetch cache to avoid rate limits
_espn_cache = {}
_ESPN_TTL = 1800  # 30 min


def _norm_name(name: str) -> str:
    """Normalize player name for matching."""
    if not name:
        return ""
    n = unicodedata.normalize("NFKD", str(name).lower())
    n = "".join(c for c in n if not unicodedata.combining(c))
    n = re.sub(r"[^a-z0-9 ]", " ", n)
    return " ".join(n.split())


def _norm_team(name: str) -> str:
    """Normalize team name for matching."""
    if not name:
        return ""
    n = unicodedata.normalize("NFKD", str(name).lower())
    n = "".join(c for c in n if not unicodedata.combining(c))
    n = re.sub(r"[^a-z0-9 ]", " ", n)
    noise = {"fc", "cf", "sc", "cd", "ac", "afc", "club", "deportivo", "de",
             "the", "united", "city", "real", "atletico", "athletic", "calcio",
             "sporting", "red bull", "rb"}
    return " ".join(w for w in n.split() if w and w not in noise)


def _resolve_team_alias(team_norm: str) -> str:
    """Resolve a team alias to its canonical form."""
    if not team_norm:
        return ""
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            "SELECT team_norm FROM team_aliases WHERE alias_norm = ?",
            (team_norm,),
        ).fetchone()
        return row[0] if row else team_norm
    finally:
        conn.close()


def _last_name(full_name: str) -> str:
    """Extract the last word (surname) from a player name."""
    parts = _norm_name(full_name).split()
    return parts[-1] if parts else ""


def _fuzzy_match_score(a: str, b: str) -> float:
    """SequenceMatcher ratio on normalized names."""
    return SequenceMatcher(None, a, b).ratio()


def get_player_info(player_name: str, team_name: str = None) -> dict:
    """
    Look up a player's FIFA rating info.
    Returns dict with keys: name, rating, position, team, source, found
    """
    name_norm = _norm_name(player_name)
    team_norm = _norm_team(team_name) if team_name else ""

    # Check memory cache
    cache_key = (name_norm, team_norm)
    if cache_key in _mem_cache:
        cached = _mem_cache[cache_key]
        if time.time() - cached.get("_ts", 0) < _MEM_TTL:
            return cached

    result = {
        "name": player_name,
        "rating": 0,
        "position": "",
        "team": team_name or "",
        "source": "none",
        "found": False,
        "_ts": time.time(),
    }

    if not os.path.exists(DB_PATH):
        _mem_cache[cache_key] = result
        return result

    conn = sqlite3.connect(DB_PATH)
    try:
        # Strategy 1: Exact normalized name match (optionally with team)
        if team_norm:
            resolved_team = _resolve_team_alias(team_norm)
            row = conn.execute(
                "SELECT name, rating, position, team FROM players "
                "WHERE name_norm = ? AND team = ?",
                (name_norm, resolved_team),
            ).fetchone()
            if not row:
                # Try without team constraint
                row = conn.execute(
                    "SELECT name, rating, position, team FROM players "
                    "WHERE name_norm = ?",
                    (name_norm,),
                ).fetchone()
        else:
            row = conn.execute(
                "SELECT name, rating, position, team FROM players "
                "WHERE name_norm = ?",
                (name_norm,),
            ).fetchone()

        if row:
            result.update({
                "name": row[0], "rating": row[1], "position": row[2],
                "team": row[3], "source": "db", "found": True,
            })
            _mem_cache[cache_key] = result
            return result

        # Strategy 2: Surname-only match (last word)
        surname = _last_name(player_name)
        if surname and len(surname) > 2:
            rows = conn.execute(
                "SELECT name, rating, position, team FROM players "
                "WHERE name_norm LIKE ?",
                (f"%{surname}%",),
            ).fetchall()
            if len(rows) == 1:
                row = rows[0]
                result.update({
                    "name": row[0], "rating": row[1], "position": row[2],
                    "team": row[3], "source": "db_surname", "found": True,
                })
                _mem_cache[cache_key] = result
                return result
            elif len(rows) > 1 and team_norm:
                # Multiple surname matches — try team to disambiguate
                resolved = _resolve_team_alias(team_norm)
                for r in rows:
                    if _norm_team(r[3]) == resolved or _fuzzy_match_score(_norm_team(r[3]), resolved) > 0.7:
                        result.update({
                            "name": r[0], "rating": r[1], "position": r[2],
                            "team": r[3], "source": "db_surname_team", "found": True,
                        })
                        _mem_cache[cache_key] = result
                        return result

        # Strategy 3: Fuzzy match (SequenceMatcher > 0.85)
        all_players = conn.execute(
            "SELECT name, name_norm, rating, position, team FROM players"
        ).fetchall()
        best_match = None
        best_score = 0.85
        for p in all_players:
            score = _fuzzy_match_score(name_norm, p[1])
            if score > best_score:
                best_score = score
                best_match = p
        if best_match:
            result.update({
                "name": best_match[0], "rating": best_match[2],
                "position": best_match[3], "team": best_match[4],
                "source": "db_fuzzy", "found": True,
            })
            _mem_cache[cache_key] = result
            return result

    finally:
        conn.close()

    _mem_cache[cache_key] = result
    return result


def get_rating(player_name: str, team_name: str = None) -> int:
    """Quick lookup: returns just the FIFA rating (0 if unknown)."""
    return get_player_info(player_name, team_name)["rating"]


def enrich_from_espn_roster(home_name: str, away_name: str, date_str: str) -> dict:
    """
    Fetch roster from ESPN for a specific match and cache player ratings.
    Returns dict of {player_name: rating} for all roster players found.

    This is called by the lineup service to auto-populate the DB for players
    not in the seed data.
    """
    cache_key = f"espn_{_norm_team(home_name)}_{_norm_team(away_name)}_{date_str}"
    if cache_key in _espn_cache:
        cached = _espn_cache[cache_key]
        if time.time() - cached["_ts"] < _ESPN_TTL:
            return {k: v for k, v in cached.items() if k != "_ts"}

    from src.free_lineup_scraper import _find_event, _similar

    date_compact = (date_str or "").replace("-", "")[:8]
    if len(date_compact) != 8:
        return {}

    lg, eid = _find_event(home_name, away_name, date_compact)
    if not eid:
        return {}

    try:
        r = requests.get(
            f"{_ESPN_BASE}/{lg}/summary", headers=_UA, params={"event": eid}, timeout=12
        )
        rosters = r.json().get("rosters") or []
    except Exception:
        return {}

    ratings_map = {}
    conn = sqlite3.connect(DB_PATH)

    try:
        for roster in rosters:
            team_name = (roster.get("team") or {}).get("displayName", "")
            team_norm = _norm_team(team_name)

            for player in (roster.get("roster") or []):
                athlete = player.get("athlete") or {}
                name = athlete.get("displayName", "")
                if not name:
                    continue

                # Try to get rating from ESPN athlete data
                rating = 0
                # ESPN provides 'overallRating' on some athlete objects
                raw_rating = athlete.get("overallRating") or athlete.get("rating")
                if raw_rating:
                    try:
                        rating = int(raw_rating)
                    except (ValueError, TypeError):
                        pass

                # Also get position
                pos = ""
                positions = athlete.get("positions") or []
                if positions:
                    pos = (positions[0] or {}).get("abbreviation", "")

                name_norm = _norm_name(name)

                # Check if already in DB
                existing = conn.execute(
                    "SELECT rating FROM players WHERE name_norm = ?",
                    (name_norm,),
                ).fetchone()

                if existing and existing[0] > 0:
                    ratings_map[name] = existing[0]
                elif rating > 0:
                    # Cache new rating from ESPN
                    conn.execute(
                        "INSERT INTO players (name, name_norm, team, position, rating, source) "
                        "VALUES (?, ?, ?, ?, ?, 'espn')",
                        (name, name_norm, team_norm, pos, rating),
                    )
                    ratings_map[name] = rating
                else:
                    # No ESPN rating available — store as 0 for tracking
                    if not existing:
                        conn.execute(
                            "INSERT INTO players (name, name_norm, team, position, rating, source) "
                            "VALUES (?, ?, ?, ?, 0, 'espn_unknown')",
                            (name, name_norm, team_norm, pos),
                        )
                    ratings_map[name] = 0

        conn.commit()
    finally:
        conn.close()

    _espn_cache[cache_key] = {**ratings_map, "_ts": time.time()}
    return ratings_map


def get_ratings_for_players(player_list: list, team_name: str = None) -> dict:
    """
    Batch lookup: returns {player_name: rating} for a list of player names.
    """
    result = {}
    for name in player_list:
        info = get_player_info(name, team_name)
        result[name] = info["rating"]
    return result


def get_db_stats() -> dict:
    """Returns stats about the FIFA ratings database."""
    if not os.path.exists(DB_PATH):
        return {"total_players": 0, "with_ratings": 0, "sources": {}}

    conn = sqlite3.connect(DB_PATH)
    try:
        total = conn.execute("SELECT COUNT(*) FROM players").fetchone()[0]
        with_ratings = conn.execute(
            "SELECT COUNT(*) FROM players WHERE rating > 0"
        ).fetchone()[0]
        sources = {}
        for row in conn.execute(
            "SELECT source, COUNT(*) FROM players GROUP BY source"
        ).fetchall():
            sources[row[0]] = row[1]
        aliases = conn.execute("SELECT COUNT(*) FROM team_aliases").fetchone()[0]

        return {
            "total_players": total,
            "with_ratings": with_ratings,
            "without_ratings": total - with_ratings,
            "sources": sources,
            "team_aliases": aliases,
        }
    finally:
        conn.close()


if __name__ == "__main__":
    # Test lookups
    tests = [
        ("Haaland", "Manchester City"),
        ("Erling Haaland", None),
        ("Mbappe", "Real Madrid"),
        ("Lionel Messi", "Inter Miami"),
        ("Saka", "Arsenal"),
        ("Unknown Player", "Some Team"),
    ]
    for name, team in tests:
        info = get_player_info(name, team)
        rating = info["rating"]
        source = info["source"]
        print(f"  {name:30s} ({team or 'any':20s}) -> {rating:3d}  [{source}]")

    print(f"\n  DB stats: {get_db_stats()}")
