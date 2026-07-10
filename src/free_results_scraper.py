"""
free_results_scraper.py — free, multi-source finished-match results.
=====================================================================
Returns final scores for finished football matches WITHOUT any paid API key,
so bet settlement no longer depends on the rate-limited API-Football key or the
bot-blocked Sofascore endpoint.

Sources (merged, best-effort, "always returns what it can"):
  1. ESPN site API   — free, no key, broad league coverage (incl. Chilean Primera,
                       Brazilian, Argentine, MLS, all big European, many minor).
  2. TheSportsDB     — free key "3", catch-all for leagues ESPN misses.

Public entrypoint:
    get_finished_results(dates=None) -> { "Home vs Away": (home_score, away_score) }

Results are cached per-date in memory (TTL) so the settlement loop can call this
every sweep without hammering the sources.
"""

import time
import datetime
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

_UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

# ESPN soccer league slugs — prioritized list (most popular leagues first for faster results)
ESPN_LEAGUES_PRIORITY = [
    # Top Europe - check these first
    "eng.1", "esp.1", "ita.1", "ger.1", "fra.1",
    "eng.2", "esp.2", "ita.2", "ger.2", "fra.2",
    # Major Americas
    "bra.1", "arg.1", "mex.1", "usa.1",
    # Other important leagues
    "ned.1", "por.1", "uefa.champions", "uefa.europa",
    "fifa.world", "fifa.worldq.uefa", "fifa.worldq.conmebol",
]

ESPN_LEAGUES_OTHER = [
    "eng.3", "eng.4", "eng.fa", "eng.league_cup",
    "esp.copa_del_rey", "ita.coppa_italia", "ger.dfb_pokal", "fra.coupe_de_france",
    "ned.2", "por.2",
    # Rest of Europe
    "sco.1", "sco.2", "sui.1", "aut.1", "bel.1", "gre.1", "tur.1",
    "rus.1", "ukr.1", "den.1", "nor.1", "swe.1", "swe.2", "pol.1",
    "cze.1", "cro.1", "rou.1", "srb.1", "hun.1", "bul.1", "irl.1",
    "svk.1", "slv.1", "isr.1", "cyp.1", "fin.1",
    # Americas (lower priority)
    "usa.usl.1", "usa.nwsl", "mex.2", "bra.2", "arg.2",
    "chi.1", "col.1", "uru.1", "per.1", "ecu.1", "par.1", "ven.1", "bol.1",
    "crc.1", "gua.1", "hon.1",
    # Asia / Oceania / Africa
    "jpn.1", "kor.1", "chn.1", "aus.1", "ksa.1", "qat.1", "are.1",
    "ind.1", "idn.1", "tha.1", "mys.1", "rsa.1", "egy.1", "mar.1", "nga.1", "tun.1",
    # Internationals & continental cups
    "fifa.friendly", "fifa.cwc", "fifa.wwc",
    "uefa.europa.conf", "uefa.nations",
    "conmebol.libertadores", "conmebol.sudamericana",
    "concacaf.champions", "concacaf.league",
    "afc.champions", "caf.champions_league",
    "fifa.worldq.concacaf", "fifa.worldq.afc", "fifa.worldq.caf",
]

ESPN_LEAGUES = ESPN_LEAGUES_PRIORITY + ESPN_LEAGUES_OTHER

_ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
_TSDB_BASE = "https://www.thesportsdb.com/api/v1/json/3"

# date(str) -> (epoch_fetched, {match: (hs, as)})
_cache = {}
_CACHE_TTL = 900  # 15 min


def _default_dates():
    now = datetime.datetime.now(datetime.timezone.utc)
    return [(now - datetime.timedelta(days=d)).strftime("%Y-%m-%d") for d in (0, 1)]


def _fetch_espn_league(lg, compact):
    """Fetch a single ESPN league's scoreboard. Returns dict of matches or empty dict."""
    try:
        r = requests.get(
            f"{_ESPN_BASE}/{lg}/scoreboard",
            headers=_UA,
            params={"dates": compact},
            timeout=3,  # Very short timeout per league
        )
        if r.status_code != 200:
            return {}
        events = r.json().get("events", []) or []
    except Exception:
        return {}
    
    out = {}
    for e in events:
        comp = (e.get("competitions") or [{}])[0]
        status = (comp.get("status") or {}).get("type") or {}
        if not status.get("completed"):
            continue
        cs = comp.get("competitors") or []
        if len(cs) != 2:
            continue
        home = next((c for c in cs if c.get("homeAway") == "home"), None)
        away = next((c for c in cs if c.get("homeAway") == "away"), None)
        if not home or not away:
            continue
        try:
            hs = int(home.get("score"))
            as_ = int(away.get("score"))
        except (TypeError, ValueError):
            continue
        hn = (home.get("team") or {}).get("displayName")
        an = (away.get("team") or {}).get("displayName")
        if hn and an:
            out[f"{hn} vs {an}"] = (hs, as_)
    return out


def _espn_day(date_str):
    """All completed ESPN soccer matches for a date -> {match: (hs, as)}."""
    out = {}
    compact = date_str.replace("-", "")
    
    # Use thread pool to fetch multiple leagues in parallel
    with ThreadPoolExecutor(max_workers=10) as executor:
        # Submit all league fetches
        future_to_league = {
            executor.submit(_fetch_espn_league, lg, compact): lg
            for lg in ESPN_LEAGUES
        }
        
        # Collect results as they complete
        for future in as_completed(future_to_league, timeout=20):
            try:
                result = future.result()
                out.update(result)
            except Exception:
                pass  # Ignore failed futures
    
    return out


# TheSportsDB only reports FINISHED matches here. It also returns LIVE matches with a
# current score (strStatus '1H'/'2H'/'HT'/...), and treating those as final settles bets
# mid-match (the "Spain 0-0 Cape Verde settled while live in the 57'" bug). Whitelist only
# genuinely-finished statuses; anything else (live, scheduled, unknown) is excluded.
_TSDB_FINISHED = {
    "FT",
    "AET",
    "PEN",
    "AP",
    "AWD",
    "MATCH FINISHED",
    "AFTER EXTRA TIME",
    "AFTER PENALTIES",
    "FINISHED",
}


def _tsdb_day(date_str):
    """TheSportsDB FINISHED soccer results for a date -> {match: (hs, as)}."""
    out = {}
    try:
        r = requests.get(
            f"{_TSDB_BASE}/eventsday.php",
            headers=_UA,
            params={"d": date_str, "s": "Soccer"},
            timeout=10,  # Reasonable timeout for TheSportsDB
        )
        events = (r.json() or {}).get("events") or []
    except Exception:
        return out
    for e in events:
        status = str(e.get("strStatus") or "").strip().upper()
        if status not in _TSDB_FINISHED:
            continue  # skip live / scheduled / unknown — never settle a non-final match
        hs, as_ = e.get("intHomeScore"), e.get("intAwayScore")
        h, a = e.get("strHomeTeam"), e.get("strAwayTeam")
        if h and a and hs not in (None, "") and as_ not in (None, ""):
            try:
                out[f"{h} vs {a}"] = (int(hs), int(as_))
            except (TypeError, ValueError):
                continue
    return out


def _results_for_date(date_str):
    cached = _cache.get(date_str)
    if cached and (time.time() - cached[0]) < _CACHE_TTL:
        return cached[1]
    merged = {}
    merged.update(_tsdb_day(date_str))  # broad but sparse
    merged.update(_espn_day(date_str))  # authoritative; overrides on overlap
    _cache[date_str] = (time.time(), merged)
    return merged


def get_finished_results(dates=None):
    """Merged finished results across sources for the given dates (default: today+yesterday UTC)."""
    out = {}
    for d in dates or _default_dates():
        try:
            out.update(_results_for_date(d))
        except Exception as e:
            print(f"[RESULTS] free scraper error for {d}: {e}")
    return out


if __name__ == "__main__":
    res = get_finished_results()
    print(f"finished results: {len(res)}")
    for k, v in list(res.items())[:15]:
        print("  ", k, v)
