"""
score_lookup.py — deep-coverage score lookup for stuck bets.
=============================================================
Combines multiple sources to find final scores for lower-league matches
that the standard scrapers (ESPN/TheSportsDB) miss:

1. Flashscore search API — finds team pages, then scrapes recent results
2. Flashscore feed — the existing bulk results (already wired in daemon)
3. Google search fallback — for truly obscure matches

Usage (CLI):
    # Look up a specific match
    .venv\\Scripts\\python.exe tools/score_lookup.py "Palmerston Rovers" "Casuarina"

    # Auto-settle all OPEN bets
    .venv\\Scripts\\python.exe tools/score_lookup.py --settle

    # Look up and settle a specific match
    .venv\\Scripts\\python.exe tools/score_lookup.py "Elimai" "Kyzylzhar" --settle
"""

import os
import re
import sys
import json
import time
import sqlite3
import datetime
import difflib
import unicodedata
from urllib.parse import quote

import requests

# ---------------------------------------------------------------------------
# Flashscore search API (same endpoint used by fixture_verifier.py)
# ---------------------------------------------------------------------------
_FS_SEARCH = (
    "https://s.livesport.services/api/v2/search/"
    "?q={q}&lang-id=1&project-id=2&project-type-id=1&sport-ids=1&type-ids=1,2,3,4"
)
_FS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/125.0 Safari/537.36",
    "Accept": "*/*",
    "Referer": "https://www.flashscore.com/",
}

# Flashscore team results page (for Playwright scraping)
_FS_TEAM_URL = "https://www.flashscore.com/team/{slug}/{id}/results/"


def _norm(s: str) -> str:
    """Normalize team name for fuzzy comparison."""
    if not s:
        return ""
    n = s.lower()
    # Remove accents
    n = "".join(c for c in unicodedata.normalize("NFD", n) if unicodedata.category(c) != "Mn")
    # Remove punctuation except spaces
    n = re.sub(r"[^a-z0-9\s]", "", n)
    # Remove common suffixes
    suffixes = {"fc", "cf", "sc", "ac", "afc", "united", "city", "fc"}
    words = [w for w in n.split() if w not in suffixes]
    return "".join(words)


def _name_similarity(a: str, b: str) -> float:
    """Return 0-1 similarity between two team names."""
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return 0.0
    # Exact match after normalization
    if na == nb:
        return 1.0
    # One contains the other (full substring)
    if na in nb or nb in na:
        return 0.95
    # Partial word overlap — check if significant words match
    words_a = set(na.split())
    words_b = set(nb.split())
    if words_a and words_b:
        overlap = words_a & words_b
        if overlap:
            # At least one word matches; give credit based on coverage
            coverage = len(overlap) / max(len(words_a), len(words_b))
            if coverage >= 0.5:
                return 0.8 + coverage * 0.1
    # Check if the shorter name is a significant prefix/subset of the longer
    shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
    if len(shorter) >= 4 and shorter[:4] in longer:
        return 0.7
    # Sequence matcher as fallback
    ratio = difflib.SequenceMatcher(None, na, nb).ratio()
    return ratio


def _fs_row_matches_opponent(m: dict, opponent: str) -> bool:
    """True if a scraped Flashscore results row (with 'home'/'away' keys)
    represents a match against `opponent`, at the SAME squad level (senior
    vs U21/U23/reserves/youth). Textual similarity alone isn't enough — a
    club's senior and youth/reserve sides both fuzzy-match the parent club
    name (2026-07-12 regression: 'Heidelberg Utd' vs 'Heidelberg Utd U21')."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
    from name_matching import _level_signature

    opponent_lvl = _level_signature(opponent)
    home_sim = _name_similarity(m["home"], opponent)
    away_sim = _name_similarity(m["away"], opponent)
    if home_sim > 0.6 and _level_signature(m["home"]) == opponent_lvl:
        return True
    if away_sim > 0.6 and _level_signature(m["away"]) == opponent_lvl:
        return True
    return False


# ---------------------------------------------------------------------------
# Flashscore search (no browser needed)
# ---------------------------------------------------------------------------
def _fs_search_team(name: str) -> dict | None:
    """Find a team on Flashscore by name. Returns {name, slug, id} or None."""
    try:
        r = requests.get(
            _FS_SEARCH.format(q=quote(name)),
            headers=_FS_HEADERS,
            timeout=15,
        )
        if r.status_code != 200:
            return None
        data = r.json()
    except Exception as e:
        print(f"[FS-SEARCH] error for '{name}': {e}")
        return None

    # type.id == 2 is Team
    teams = [it for it in data if it.get("type", {}).get("id") == 2]
    target = _norm(name)
    best, best_score = None, 0.0
    for it in teams:
        it_name = it.get("name", "")
        sc = _name_similarity(name, it_name)
        if sc > best_score:
            best, best_score = it, sc

    if best and best_score >= 0.5:
        return {
            "name": best.get("name"),
            "slug": best.get("url") or "",  # 'url' field is the slug
            "id": best.get("id"),
            "score": best_score,
        }
    return None


# ---------------------------------------------------------------------------
# Flashscore results page scraping (Playwright)
# ---------------------------------------------------------------------------
def _fs_scrape_team_results(team_id: str, team_slug: str, opponent: str, searched_team_name: str = "") -> dict | None:
    """
    Load a Flashscore team results page and look for a match against `opponent`.
    Returns {home, away, home_score, away_score, searched_team_home: bool} or None.
    searched_team_name is used to determine which participant is the searched team.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[FS-SCRAPE] Playwright not available")
        return None

    url = f"https://www.flashscore.com/team/{team_slug}/{team_id}/results/"
    print(f"[FS-SCRAPE] Loading {url}")

    try:
        with sync_playwright() as p:
            # This settlement lookup fires repeatedly (every daemon cycle, for
            # every still-unresolved bet) — block rendering-only resources so
            # each launch/teardown is as cheap as possible.
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--disable-extensions",
                    "--disable-background-networking",
                    "--disable-background-timer-throttling",
                    "--disable-backgrounding-occluded-windows",
                    "--disable-renderer-backgrounding",
                    "--mute-audio",
                    "--blink-settings=imagesEnabled=false",
                ],
            )
            try:
                page = browser.new_page(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
                )
                page.route(
                    "**/*",
                    lambda route: route.abort()
                    if route.request.resource_type in ("image", "media", "font", "stylesheet")
                    else route.continue_(),
                )
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                page.wait_for_timeout(3000)

                # Extract all recent match results
                results_js = """() => {
                    const out = [];
                    document.querySelectorAll('.event__match').forEach(m => {
                        const home = m.querySelector('.event__homeParticipant');
                        const away = m.querySelector('.event__awayParticipant');
                        const scoreHome = m.querySelector('.event__score--home');
                        const scoreAway = m.querySelector('.event__score--away');
                        const stage = m.querySelector('.event__stage');
                        const time = m.querySelector('.event__time');
                        if (home && away && scoreHome && scoreAway) {
                            out.push({
                                home: (home.innerText || '').trim(),
                                away: (away.innerText || '').trim(),
                                home_score: scoreHome.innerText.trim(),
                                away_score: scoreAway.innerText.trim(),
                                stage: stage ? stage.innerText.trim() : '',
                                time: time ? time.innerText.trim() : '',
                            });
                        }
                    });
                    return out;
                }"""
                matches = page.evaluate(results_js)

                # Look for opponent — but ONLY in matches played within the last
                # few days. A team's results page lists its full history, so
                # without a date check any PREVIOUS meeting of the same two
                # teams settles today's (possibly unplayed) fixture.
                def _row_is_recent(time_text: str) -> bool:
                    m_dt = re.search(r"(\d{1,2})\.(\d{1,2})\.", time_text or "")
                    if not m_dt:
                        return False  # no parseable date -> cannot trust the row
                    day, month = int(m_dt.group(1)), int(m_dt.group(2))
                    now = datetime.datetime.now(datetime.timezone.utc)
                    try:
                        row_date = datetime.date(now.year, month, day)
                    except ValueError:
                        return False
                    # Handle year boundary (a December row seen in January)
                    if row_date > now.date() + datetime.timedelta(days=1):
                        row_date = row_date.replace(year=now.year - 1)
                    return (now.date() - row_date).days <= 3

                for m in matches:
                    if not _row_is_recent(m.get("time", "")):
                        continue
                    home_sim = _name_similarity(m["home"], opponent)
                    away_sim = _name_similarity(m["away"], opponent)
                    if _fs_row_matches_opponent(m, opponent):
                        try:
                            hs = int(m["home_score"])
                            as_ = int(m["away_score"])
                            # Determine if the searched team was home on this page
                            # Use the searched_team_name if provided, otherwise infer
                            if searched_team_name:
                                searched_is_home = _name_similarity(m["home"], searched_team_name) > _name_similarity(m["away"], searched_team_name)
                            else:
                                searched_is_home = home_sim < away_sim  # opponent is on the other side
                            print(f"[FS-SCRAPE] Found: {m['home']} {hs}-{as_} {m['away']} (searched_team_home={searched_is_home})")
                            return {
                                "home": m["home"],
                                "away": m["away"],
                                "home_score": hs,
                                "away_score": as_,
                                "searched_team_home": searched_is_home,
                            }
                        except (ValueError, TypeError):
                            continue

                print(f"[FS-SCRAPE] No match against '{opponent}' found in {len(matches)} results")
                return None
            finally:
                browser.close()
    except Exception as e:
        print(f"[FS-SCRAPE] error: {e}")
        return None


# ---------------------------------------------------------------------------
# Flashscore feed fuzzy matching (already-loaded bulk data)
# ---------------------------------------------------------------------------
def _fs_feed_fuzzy(home: str, away: str, days_back: int = 5) -> tuple[int, int] | None:
    """
    Search the Flashscore feed results (already cached or fresh) for a match
    using fuzzy name matching. This catches matches where the feed has the score
    but the names don't match exactly (e.g., 'Elimai' vs 'Yelimay Semey').
    """
    try:
        # Import here to avoid circular dependency
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
        from flashscore_scraper import get_finished_results
        from name_matching import _level_signature

        import datetime
        now = datetime.datetime.now(datetime.timezone.utc)
        dates = [(now - datetime.timedelta(days=d)).strftime("%Y-%m-%d") for d in range(days_back)]
        results = get_finished_results(dates=dates)

        home_norm = _norm(home)
        away_norm = _norm(away)
        best_match = None
        best_score = 0.0

        # Cross-level pairs (senior vs U21/U23/reserves/youth) are never the
        # same team — reject them here exactly like get_match_score() does,
        # mirroring the daemon's sim2-pass fix (2026-07-12 Melbourne City
        # NPL vs Melbourne City U21 collision).
        home_lvl = _level_signature(home)
        away_lvl = _level_signature(away)

        for match_key, score in results.items():
            parts = match_key.split(" vs ")
            if len(parts) != 2:
                continue
            feed_home, feed_away = parts[0].strip(), parts[1].strip()
            feed_home_lvl = _level_signature(feed_home)
            feed_away_lvl = _level_signature(feed_away)

            # Normal match (home=home, away=away)
            # Require BOTH teams to have at least some similarity
            if home_lvl == feed_home_lvl and away_lvl == feed_away_lvl:
                home_sim = _name_similarity(home, feed_home)
                away_sim = _name_similarity(away, feed_away)
                combined = min(home_sim, away_sim)
                if combined > best_score and home_sim >= 0.5 and away_sim >= 0.5:
                    best_score = combined
                    best_match = (score[0], score[1], match_key, False)

            # Reversed match (home=away, away=home)
            if home_lvl == feed_away_lvl and away_lvl == feed_home_lvl:
                home_sim_rev = _name_similarity(home, feed_away)
                away_sim_rev = _name_similarity(away, feed_home)
                combined_rev = min(home_sim_rev, away_sim_rev)
                if combined_rev > best_score and home_sim_rev >= 0.5 and away_sim_rev >= 0.5:
                    best_score = combined_rev
                    best_match = (score[1], score[0], match_key, True)  # swap scores

        if best_match and best_score >= 0.65:
            hs, as_, key, reversed_ = best_match
            print(f"[FS-FEED] Fuzzy match: '{home} vs {away}' -> '{key}' (sim={best_score:.2f})")
            return hs, as_
        return None
    except Exception as e:
        print(f"[FS-FEED] fuzzy search failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Google search fallback (uses existing tools/score_scraper.py)
# ---------------------------------------------------------------------------
def _google_score(home: str, away: str) -> tuple[int, int] | None:
    """Use Google search to find a match score. Delegates to tools/score_scraper."""
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
        from score_scraper import scrape_score
        result = scrape_score(home, away)
        if result and result.get("home_score") is not None:
            hs, as_ = result["home_score"], result["away_score"]
            # Google shows "0 - 0" in its score box for matches that haven't
            # started (or just kicked off) — indistinguishable from a real 0-0
            # final at this layer. Never trust 0-0 from Google; a genuine 0-0
            # will be picked up by the date-checked feed/Flashscore sources.
            if hs == 0 and as_ == 0:
                print("[GOOGLE] Ignoring 0-0 (pre-match/live placeholder, not a verifiable final)")
                return None
            return hs, as_
    except Exception as e:
        print(f"[GOOGLE] fallback failed: {e}")
    return None


# ---------------------------------------------------------------------------
# Combined lookup
# ---------------------------------------------------------------------------
# ─── Negative-result cache ───────────────────────────────────────────────────
# lookup_score() is the deep fallback: a Flashscore team search + results-page
# scrape for BOTH teams, then a Google fallback — each launching its own
# headless Chromium. One observed daemon cycle did 10 lookups = 18 FS-SCRAPE
# launches + 9 Google launches = 27 Chromium spawns. Nothing remembered the
# misses, so fixtures Flashscore simply does not carry (reserve sides, obscure
# minor leagues) were re-attempted on every settlement pass — every ~45s,
# indefinitely.
#
# Remembering a miss for NEG_CACHE_TTL collapses that retry storm. Hits are
# never cached: a real score always returns immediately.
# Must exceed the daemon's own deep-lookup throttle
# (live_predictions_daemon._DEEP_LOOKUP_INTERVAL, 1800s) or the cache expires
# exactly when the throttle lifts and suppresses nothing. At 2h an
# unresolvable fixture is retried ~4x/day instead of ~48x. The deep lookup is
# the LAST-resort path — ESPN/Flashscore/Sofascore/dashboard-state all still run
# unthrottled every cycle — so a delay here cannot hold up a normal settlement.
NEG_CACHE_TTL = float(os.getenv("DEEPFIELD_LOOKUP_NEG_TTL", "7200"))  # 2 h
NEG_CACHE_MAX = 2000

_NEG_CACHE: dict = {}


def _neg_key(home: str, away: str) -> tuple:
    return (str(home).strip().lower(), str(away).strip().lower())


def _neg_cached(home: str, away: str) -> bool:
    """True if this fixture missed recently and should not be retried yet."""
    key = _neg_key(home, away)
    exp = _NEG_CACHE.get(key)
    if exp is None:
        return False
    if time.time() >= exp:
        _NEG_CACHE.pop(key, None)
        return False
    return True


def _neg_remember(home: str, away: str) -> None:
    key = _neg_key(home, away)
    _NEG_CACHE.pop(key, None)  # re-insert so dict order == recency
    _NEG_CACHE[key] = time.time() + NEG_CACHE_TTL
    while len(_NEG_CACHE) > NEG_CACHE_MAX:
        _NEG_CACHE.pop(next(iter(_NEG_CACHE)))


def clear_lookup_cache() -> None:
    """Forget every remembered miss (used by tests and manual re-settles)."""
    _NEG_CACHE.clear()


def lookup_score(home: str, away: str, use_browser: bool = True) -> tuple[int, int, str] | None:
    """
    Find the final score for a match. Returns (home_score, away_score, source) or None.

    Strategy:
    1. Flashscore feed fuzzy matching (fast, no browser, catches name variants)
    2. Flashscore search for home team -> scrape results page for away team
    3. Flashscore search for away team -> scrape results page for home team
    4. Google search fallback (if use_browser=True)
    """
    if _neg_cached(home, away):
        print(
            f"[LOOKUP] Skipping {home} vs {away} — no result found recently (cached miss)"
        )
        return None

    print(f"\n[LOOKUP] Searching for: {home} vs {away}")

    def _sane(hs, as_) -> bool:
        # Football sanity bounds — the Google fallback once parsed "12-9"
        # from an unrelated search result and settled an unplayed match.
        ok = 0 <= hs <= 9 and 0 <= as_ <= 9 and hs + as_ <= 12
        if not ok:
            print(f"[LOOKUP] Rejecting implausible score {hs}-{as_}")
        return ok

    # Strategy 1: Flashscore feed fuzzy matching (fast, no browser needed)
    feed_result = _fs_feed_fuzzy(home, away)
    if feed_result and _sane(feed_result[0], feed_result[1]):
        return feed_result[0], feed_result[1], "flashscore-feed-fuzzy"

    # Strategy 2: Search for home team on Flashscore and scrape results page
    home_info = _fs_search_team(home)
    if home_info and use_browser:
        print(f"[LOOKUP] Found home team: {home_info['name']} (score={home_info['score']:.2f})")
        result = _fs_scrape_team_results(home_info["id"], home_info["slug"], away, searched_team_name=home_info["name"])
        if result and _sane(result["home_score"], result["away_score"]):
            # The page shows a match with home team. Determine score orientation:
            # If searched team (home) was home on the page -> scores are in correct order
            # If searched team (home) was away on the page -> scores are swapped
            if result["searched_team_home"]:
                return result["home_score"], result["away_score"], "flashscore-home"
            else:
                return result["away_score"], result["home_score"], "flashscore-home"

    # Strategy 3: Search for away team on Flashscore and scrape results page
    away_info = _fs_search_team(away)
    if away_info and use_browser:
        print(f"[LOOKUP] Found away team: {away_info['name']} (score={away_info['score']:.2f})")
        result = _fs_scrape_team_results(away_info["id"], away_info["slug"], home, searched_team_name=away_info["name"])
        if result and _sane(result["home_score"], result["away_score"]):
            # The page shows a match with away team. Determine score orientation:
            # If searched team (away) was home on the page -> result[home_score] is away's score
            # If searched team (away) was away on the page -> result[away_score] is away's score
            if result["searched_team_home"]:
                # Away team was home on their page: page shows Away X - Y Home
                # We want Home's score first: return (away_score, home_score)
                return result["away_score"], result["home_score"], "flashscore-away"
            else:
                # Away team was away on their page: page shows Home X - Y Away
                # We want Home's score first: return (home_score, away_score)
                return result["home_score"], result["away_score"], "flashscore-away"

    # Strategy 4: Google fallback
    if use_browser:
        print("[LOOKUP] Trying Google fallback...")
        result = _google_score(home, away)
        if result and _sane(result[0], result[1]):
            return result[0], result[1], "google"

    # Every strategy missed — remember it so the next settlement pass (~45s
    # away) does not spawn the same ~3 browsers again for this fixture.
    _neg_remember(home, away)
    return None


# ---------------------------------------------------------------------------
# Settle OPEN bets
# ---------------------------------------------------------------------------
def _get_open_bets(db_path: str) -> list[dict]:
    """Get all OPEN bets from the database."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("""
            SELECT bet_id, match_id, market_type, side, entry_odds, stake, fixture_id, league
            FROM bet_log
            WHERE result IS NULL OR result = 'OPEN'
            ORDER BY placed_at DESC
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _parse_match_teams(match_id: str) -> tuple[str, str] | None:
    """Parse 'Home vs Away' from match_id."""
    if not match_id:
        return None
    parts = match_id.split(" vs ")
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return None


def _grade_bet(market_type: str, side: str, home_score: int, away_score: int) -> str:
    """Grade a bet as W/L/V based on the final score."""
    total = home_score + away_score

    if market_type == "1X2":
        if "Home" in side or side == "1":
            return "W" if home_score > away_score else "L"
        elif "Away" in side or side == "2":
            return "W" if away_score > home_score else "L"
        elif "Draw" in side or side == "X":
            return "W" if home_score == away_score else "L"

    elif market_type == "Over/Under 2.5":
        if "Over" in side:
            return "W" if total > 2.5 else "L"
        elif "Under" in side:
            return "W" if total < 2.5 else "L"

    elif market_type == "BTTS":
        btts = home_score > 0 and away_score > 0
        if "Yes" in side:
            return "W" if btts else "L"
        elif "No" in side:
            return "W" if not btts else "L"

    return "V"  # Void for unknown markets


def settle_open_bets(db_path: str, use_browser: bool = True) -> dict:
    """
    Find scores for all OPEN bets and settle them.
    Returns a summary dict.
    """
    print("[SETTLE] Loading OPEN bets...")
    open_bets = _get_open_bets(db_path)
    print(f"[SETTLE] Found {len(open_bets)} OPEN bets")

    if not open_bets:
        return {"settled": 0, "not_found": 0}

    # Group by match to avoid duplicate lookups
    matches = {}
    for bet in open_bets:
        teams = _parse_match_teams(bet["match_id"])
        if teams:
            key = f"{teams[0]} vs {teams[1]}"
            matches.setdefault(key, {"home": teams[0], "away": teams[1], "bets": []})
            matches[key]["bets"].append(bet)

    print(f"[SETTLE] {len(matches)} unique matches to look up")

    settled = 0
    not_found = 0
    results = {}

    # Look up scores for each match
    for match_key, match_info in matches.items():
        score = lookup_score(match_info["home"], match_info["away"], use_browser=use_browser)
        if score:
            hs, as_, source = score
            results[match_key] = (hs, as_, source)
            print(f"[SETTLE] FOUND: {match_key} -> {hs}-{as_} ({source})")

            # Settle all bets for this match
            conn = sqlite3.connect(db_path)
            try:
                for bet in match_info["bets"]:
                    grade = _grade_bet(bet["market_type"], bet["side"], hs, as_)
                    stake = float(bet["stake"]) if bet["stake"] else 0.0
                    odds = float(bet["entry_odds"]) if bet["entry_odds"] else 1.0

                    if grade == "W":
                        pnl = stake * (odds - 1)
                    elif grade == "L":
                        pnl = -stake
                    else:
                        pnl = 0.0
                        grade = "VOID"

                    conn.execute(
                        "UPDATE bet_log SET result=?, pnl=?, closing_odds=? WHERE bet_id=?",
                        (grade, pnl, odds, bet["bet_id"])
                    )
                    print(f"  [SETTLED] {bet['bet_id']}: {bet['market_type']} {bet['side']} -> {grade} (PnL: {pnl:+.2f})")
                    settled += 1
                conn.commit()
            finally:
                conn.close()
        else:
            print(f"[SETTLE] NOT FOUND: {match_key}")
            not_found += 1

    return {"settled": settled, "not_found": not_found, "results": results}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    import argparse
    parser = argparse.ArgumentParser(description="Deep-coverage score lookup for stuck bets")
    parser.add_argument("home", nargs="?", help="Home team name")
    parser.add_argument("away", nargs="?", help="Away team name")
    parser.add_argument("--settle", action="store_true", help="Auto-settle all OPEN bets")
    parser.add_argument("--no-browser", action="store_true", help="Skip browser-based lookups")

    args = parser.parse_args()
    db_path = os.path.join(os.path.dirname(__file__), "..", "data", "bet_log.db")

    if args.settle:
        result = settle_open_bets(db_path, use_browser=not args.no_browser)
        print(f"\n=== Summary ===")
        print(f"Settled: {result['settled']}")
        print(f"Not found: {result['not_found']}")

    elif args.home and args.away:
        result = lookup_score(args.home, args.away, use_browser=not args.no_browser)
        if result:
            hs, as_, source = result
            print(f"\nResult: {args.home} {hs}-{as_} {args.away} (source: {source})")
        else:
            print(f"\nNo result found for {args.home} vs {args.away}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
