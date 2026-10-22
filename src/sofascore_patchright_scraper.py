"""
sofascore_patchright_scraper.py
================================
Fetches today's (and optionally any date's) Sofascore football fixtures using
Patchright — a stealth Playwright fork that patches the two primary Cloudflare
detection vectors:
  1. Runtime.enable CDP leak → JS runs in isolated ExecutionContexts
  2. navigator.webdriver flag → stripped + --disable-blink-features=AutomationControlled

Strategy: navigate to sofascore.com/football, intercept the XHR response to
  api.sofascore.com/api/v1/sport/football/scheduled-events/<date>
and parse it — same JSON the API returns, but delivered through a legitimate
full-page Chromium session that passes Cloudflare's browser fingerprint checks.

Public API (mirrors get_todays_fixtures_free signature):
    get_sofascore_fixtures(date_str=None)  -> list[fixture_dict]
    get_sofascore_fixtures_today()         -> list[fixture_dict]

fixture_dict shape (matches what the daemon / free_scraper_module produce):
    {
        "fixture": {"id": int, "date": str(ISO), "status": {"short": str},
                    "home_score": int|None, "away_score": int|None},
        "league":  {"name": str},
        "teams":   {"home": {"name": str}, "away": {"name": str}},
    }
"""

from __future__ import annotations

import datetime
import json
import time
import hashlib
import logging
from typing import Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Status mapping: Sofascore type → short code the daemon recognises
# ---------------------------------------------------------------------------
_STATUS_MAP = {
    "notstarted": "NS",
    "inprogress": "1H",   # best single code; real period comes from periodId
    "halftime":   "HT",
    "finished":   "FT",
    "postponed":  "PST",
    "canceled":   "CANC",
    "interrupted":"INT",
    "abandoned":  "ABD",
    "coverage":   "NS",   # fixture with coverage but no start yet
}

_PERIOD_MAP = {1: "1H", 2: "2H", 3: "ET", 4: "PEN"}


def _status_short(event: dict) -> str:
    st = event.get("status") or {}
    stype = (st.get("type") or "").lower()
    if stype == "inprogress":
        period = event.get("time", {}).get("period") or event.get("currentPeriodStartTimestamp")
        if isinstance(period, int) and period in _PERIOD_MAP:
            return _PERIOD_MAP[period]
        return "1H"
    return _STATUS_MAP.get(stype, "NS")


def _parse_event(ev: dict) -> Optional[dict]:
    try:
        ht = (ev.get("homeTeam") or {}).get("name") or ""
        at = (ev.get("awayTeam") or {}).get("name") or ""
        if not ht or not at:
            return None

        # Namespace the id so settlement can tell a real Sofascore event id from
        # a locally-minted md5 (which is stable only within this source and must
        # never be joined to another feed's ids).
        from src import fixture_results as _fx

        fid = ev.get("id")
        if not fid:
            key = f"{ht} vs {at}"
            fid = int(hashlib.md5(key.encode()).hexdigest(), 16) % 100_000_000
            fns = _fx.synthetic_ns(_fx.NS_SOFASCORE)
        else:
            fid = int(fid)
            fns = _fx.NS_SOFASCORE

        # Kickoff: Sofascore uses Unix timestamp in "startTimestamp"
        ts = ev.get("startTimestamp")
        if ts:
            dt = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
            date_iso = dt.isoformat()
        else:
            date_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        hs_obj = ev.get("homeScore") or {}
        as_obj = ev.get("awayScore") or {}
        home_score = hs_obj.get("current") if isinstance(hs_obj, dict) else None
        away_score = as_obj.get("current") if isinstance(as_obj, dict) else None

        tournament = ev.get("tournament") or {}
        league_name = tournament.get("name") or tournament.get("uniqueTournament", {}).get("name") or "Sofascore"

        return {
            "fixture_ns": fns,
            "fixture": {
                "id": fid,
                "date": date_iso,
                "status": {"short": _status_short(ev)},
                "home_score": home_score,
                "away_score": away_score,
            },
            "league": {"name": league_name},
            "teams": {
                "home": {"name": ht},
                "away": {"name": at},
            },
        }
    except Exception as e:
        log.debug(f"[SOFASCORE] parse_event failed: {e}")
        return None


def _parse_scheduled_events_payload(payload: dict) -> list[dict]:
    fixtures = []
    events = payload.get("events") or []
    for ev in events:
        parsed = _parse_event(ev)
        if parsed:
            fixtures.append(parsed)
    return fixtures


# ---------------------------------------------------------------------------
# Core scraper
# ---------------------------------------------------------------------------

def _same_origin_fetch(page, url: str) -> Optional[dict]:
    """Execute a fetch() from inside the Sofascore page context (bypasses CORS/CF)."""
    try:
        result = page.evaluate(f"""
            async () => {{
                const r = await fetch("{url}", {{
                    headers: {{
                        "Accept": "application/json",
                        "X-Requested-With": "XMLHttpRequest"
                    }}
                }});
                if (!r.ok) return null;
                return await r.json();
            }}
        """)
        return result
    except Exception as e:
        log.debug(f"[SOFASCORE] fetch({url}) failed: {e}")
        return None


def get_sofascore_fixtures(date_str: Optional[str] = None, headless: bool = True, timeout: int = 30) -> list[dict]:
    """
    Fetch football fixtures for *date_str* (YYYY-MM-DD, default today) via Patchright.

    The correct Sofascore API lives at www.sofascore.com/api/v1/ (not api.sofascore.com).
    We navigate to sofascore.com to establish a valid CF-cleared session, then use
    same-origin fetch() from inside the page to call:
      1. /api/v1/sport/football/scheduled-tournaments/{date}/page/1  → tournament IDs
      2. /api/v1/unique-tournament/{id}/scheduled-events/{date}       → events per tournament

    Returns fixture dicts compatible with the daemon, or [] on failure.
    """
    if date_str is None:
        date_str = datetime.date.today().isoformat()

    log.info(f"[SOFASCORE] Fetching fixtures for {date_str} ...")

    try:
        from patchright.sync_api import sync_playwright
    except ImportError:
        log.error("[SOFASCORE] patchright not installed. Run: pip install patchright && python -m patchright install chromium")
        return []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        try:
            ctx = browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="en-US",
                timezone_id="Europe/London",
            )
            page = ctx.new_page()

            # Establish a valid Cloudflare-cleared session on the main site
            log.info("[SOFASCORE] Navigating to sofascore.com ...")
            page.goto("https://www.sofascore.com/football", wait_until="domcontentloaded", timeout=timeout * 1000)
            page.wait_for_timeout(3000)

            # Step 1: get list of tournaments scheduled for this date
            tournaments_url = f"/api/v1/sport/football/scheduled-tournaments/{date_str}/page/1"
            log.info(f"[SOFASCORE] Fetching tournaments: {tournaments_url}")
            t_data = _same_origin_fetch(page, tournaments_url)

            if not t_data:
                log.warning("[SOFASCORE] Could not fetch tournament list")
                return []

            # Response shape: {"scheduled": [{"tournament": {"uniqueTournament": {"id":...}}}]}
            scheduled = t_data.get("scheduled") or []
            log.info(f"[SOFASCORE] Found {len(scheduled)} tournaments")

            # Step 2: fetch events per tournament in parallel via Promise.all
            tournament_ids = []
            for item in scheduled:
                t = item.get("tournament") or {}
                ut = t.get("uniqueTournament") or {}
                tid = ut.get("id")
                if tid:
                    tournament_ids.append(str(tid))

            if not tournament_ids:
                return []

            # Build a JS Promise.all to fetch all tournaments concurrently
            fetch_calls = ", ".join(
                f'fetch("/api/v1/unique-tournament/{tid}/scheduled-events/{date_str}",'
                f'{{headers:{{"Accept":"application/json"}}}}).then(r=>r.ok?r.json():null).catch(()=>null)'
                for tid in tournament_ids
            )
            log.info(f"[SOFASCORE] Fetching events for {len(tournament_ids)} tournaments ...")
            all_results = page.evaluate(f"async () => {{ return await Promise.all([{fetch_calls}]); }}")

            fixtures = []
            for result in (all_results or []):
                if result and "events" in result:
                    fixtures.extend(_parse_scheduled_events_payload(result))

            log.info(f"[SOFASCORE] Total fixtures: {len(fixtures)}")
            return fixtures

        finally:
            browser.close()

    return []


def get_sofascore_fixtures_today() -> list[dict]:
    return get_sofascore_fixtures()


def fetch_api_json(paths: list, headless: bool = True, timeout: int = 30) -> dict:
    """
    Fetch one or more www.sofascore.com/api/v1 *paths* (e.g.
    "/api/v1/event/123/statistics") in a single Patchright browser session via
    same-origin fetch(). Returns {path: parsed_json_or_None}.

    Replaces the old per-call SeleniumBase uc-Chrome launches (whose teardown
    forced a full-heap gc.collect() in the daemon and which Cloudflare blocks
    on api.sofascore.com anyway).
    """
    out: dict = {p: None for p in paths}
    if not paths:
        return out

    try:
        from patchright.sync_api import sync_playwright
    except ImportError:
        log.error("[SOFASCORE] patchright not installed. Run: pip install patchright && python -m patchright install chromium")
        return out

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            try:
                ctx = browser.new_context(
                    viewport={"width": 1280, "height": 800},
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                    locale="en-US",
                    timezone_id="Europe/London",
                )
                page = ctx.new_page()
                page.goto(
                    "https://www.sofascore.com/football",
                    wait_until="domcontentloaded",
                    timeout=timeout * 1000,
                )
                page.wait_for_timeout(2000)
                for path in paths:
                    out[path] = _same_origin_fetch(page, path)
            finally:
                browser.close()
    except Exception as e:
        log.warning(f"[SOFASCORE] fetch_api_json failed: {e}")
    return out


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    date = sys.argv[1] if len(sys.argv) > 1 else None
    results = get_sofascore_fixtures(date)
    print(f"\nOK {len(results)} fixtures\n")
    for f in results[:10]:
        t = f["teams"]
        fx = f["fixture"]
        lg = f["league"]["name"]
        line = f"  [{fx['status']['short']}] {t['home']['name']} vs {t['away']['name']}  |  {lg}  |  {fx['date'][:16]}"
        print(line.encode("ascii", errors="replace").decode("ascii"))
    if len(results) > 10:
        print(f"  … and {len(results) - 10} more")
