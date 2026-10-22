"""
sofascore_results_scraper.py — Playwright-based Sofascore results fetcher.
===========================================================================
Sofascore blocks direct API calls (both api.sofascore.com and
www.sofascore.com/api/v1/scheduled-events) with Cloudflare challenges.
However: the page loads fine in headless Chromium and makes per-tournament
API calls that ARE accessible. We intercept those via the Playwright
response handler, scroll the page to trigger more league data, and
aggregate all finished events.

Strategy:
  1. Navigate to sofascore.com/football/{date}.
  2. Intercept all responses from www.sofascore.com/api/v1/* containing events.
  3. Scroll down twice to trigger lazy-loading of more leagues.
  4. Wait 15s total for all XHR to complete.
  5. Filter finished events → {match_name: (home_score, away_score)}.
  6. Cache per-date for 30 min (disk + in-memory).

Public API:
    get_finished_results(dates=None) -> { "Home vs Away": (home_score, away_score) }
    get_events(dates=None) -> { date_str: [trimmed event dicts] }  (all statuses)
"""

import asyncio
import datetime
import json
import os
import time

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_DIR = os.path.join(_BASE_DIR, "data")
_CACHE_TTL = 1800  # 30 minutes

_mem_cache: dict = {}

# One entry per distinct date was kept for the process lifetime. Settlement asks
# for at most ~8 dates per pass, so anything beyond a couple of days of slack is
# dead weight in a daemon meant to run for months.
_MEM_CACHE_MAX = 16


def _mem_cache_put(date_str: str, value) -> None:
    """Insert into the date cache, evicting the oldest entry past _MEM_CACHE_MAX."""
    _mem_cache.pop(date_str, None)  # re-insert so dict order == recency
    _mem_cache[date_str] = value
    while len(_mem_cache) > _MEM_CACHE_MAX:
        _mem_cache.pop(next(iter(_mem_cache)))


def _cache_path(date_str: str) -> str:
    return os.path.join(_DATA_DIR, f"sofascore_cache_{date_str}.json")


def _load_cache(date_str: str):
    p = _cache_path(date_str)
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            obj = json.load(f)
        # "events" is absent in pre-upgrade cache files -> None (results still valid)
        return obj.get("fetched_at", 0), obj.get("results", {}), obj.get("events")
    except Exception:
        return None


def _save_cache(date_str: str, results: dict, events: list):
    p = _cache_path(date_str)
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(
                {"fetched_at": time.time(), "results": results, "events": events}, f
            )
    except Exception:
        pass


def _trim_event(ev: dict):
    """Keep only the fields the daemon's completion scan needs, in the raw
    Sofascore event shape (so consumers parse it exactly like the API payload)."""
    try:
        return {
            "id": ev.get("id"),
            "status": {"type": (ev.get("status") or {}).get("type", "")},
            "homeScore": {
                "current": (ev.get("homeScore") or {}).get("current"),
                "normaltime": (ev.get("homeScore") or {}).get("normaltime"),
            },
            "awayScore": {
                "current": (ev.get("awayScore") or {}).get("current"),
                "normaltime": (ev.get("awayScore") or {}).get("normaltime"),
            },
            "homeTeam": {"name": (ev.get("homeTeam") or {}).get("name", "")},
            "awayTeam": {"name": (ev.get("awayTeam") or {}).get("name", "")},
            "tournament": {"name": (ev.get("tournament") or {}).get("name", "")},
        }
    except Exception:
        return None


class _EventCollector:
    """Trims and dedups Sofascore events as they arrive off the response stream.

    The handler used to append every raw event of every api/v1 response to a
    list, then scroll four times (which re-fetches the same leagues) and only
    trim + dedup at the end. Peak was therefore full raw payloads x duplicates,
    per date, for up to 8 dates a settlement pass. Doing the work on arrival
    holds only one trimmed copy per distinct event id, with identical output.
    """

    __slots__ = ("_by_id",)

    def __init__(self):
        self._by_id = {}

    def extend(self, raw_events) -> None:
        for ev in raw_events or []:
            if not isinstance(ev, dict):
                continue
            eid = ev.get("id")
            if eid is None or eid in self._by_id:
                continue
            trimmed = _trim_event(ev)
            if trimmed is None or trimmed.get("id") is None:
                continue
            self._by_id[eid] = trimmed

    def events(self) -> list:
        return list(self._by_id.values())

    def __len__(self):
        return len(self._by_id)


def _parse_events(events: list) -> dict:
    out = {}
    for ev in events:
        status_type = (ev.get("status") or {}).get("type", "")
        if status_type != "finished":
            continue
        home = (ev.get("homeTeam") or {}).get("name", "")
        away = (ev.get("awayTeam") or {}).get("name", "")
        if not home or not away:
            continue
        hs = (ev.get("homeScore") or {}).get("current")
        as_ = (ev.get("awayScore") or {}).get("current")
        if hs is None or as_ is None:
            continue
        try:
            out[f"{home} vs {away}"] = (int(hs), int(as_))
        except (TypeError, ValueError):
            continue
    return out


async def _fetch_date_async(date_str: str) -> dict:
    from playwright.async_api import async_playwright, TimeoutError as PWTimeout

    collector = _EventCollector()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            viewport={"width": 1280, "height": 800},
        )
        page = await ctx.new_page()

        async def on_response(response):
            url = response.url
            # Capture any API response that may contain events
            if "www.sofascore.com/api/v1" not in url:
                return
            if response.status != 200:
                return
            try:
                data = await response.json()
                if not isinstance(data, dict):
                    return
                evs = data.get("events") or []
                if evs:
                    # Trimmed + deduped on arrival — see _EventCollector.
                    collector.extend(evs)
            except Exception:
                pass

        page.on("response", on_response)

        try:
            await page.goto(
                f"https://www.sofascore.com/football/{date_str}",
                wait_until="domcontentloaded",
                timeout=30000,
            )
        except PWTimeout:
            print(f"[SOFASCORE] domcontentloaded timeout for {date_str}")
        except Exception as e:
            print(f"[SOFASCORE] nav error for {date_str}: {e}")

        # Wait and scroll to trigger lazy-loading of more league data
        await asyncio.sleep(5)
        try:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
            await asyncio.sleep(3)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(4)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(3)
        except Exception:
            pass

        await browser.close()

    # Trimmed full-event cache (all statuses) — consumed by the daemon's
    # completion scan so it doesn't need its own browser fetch of the same data.
    events = collector.events()
    results = _parse_events(events)
    print(
        f"[SOFASCORE] {date_str}: {len(results)} finished from {len(events)} total events"
    )
    return results, events


def _fetch_date_sync(date_str: str):
    try:
        try:
            # asyncio.run() creates a fresh event loop each call — works cleanly
            return asyncio.run(_fetch_date_async(date_str))
        except RuntimeError:
            # Already inside a running loop (e.g. called from daemon thread)
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                future = ex.submit(asyncio.run, _fetch_date_async(date_str))
                return future.result(timeout=90)
    except Exception as e:
        print(f"[SOFASCORE] error for {date_str}: {e}")
        return {}, []


def _get_for_date(date_str: str):
    """Return (results, events) for a date, via mem cache → disk cache → fetch."""
    mem = _mem_cache.get(date_str)
    if mem and (time.time() - mem[0]) < _CACHE_TTL:
        return mem[1], mem[2]

    disk = _load_cache(date_str)
    if disk and (time.time() - disk[0]) < _CACHE_TTL:
        _mem_cache_put(date_str, disk)
        return disk[1], disk[2]

    results, events = _fetch_date_sync(date_str)
    if results or events:  # don't cache empty — may be a transient failure
        _mem_cache_put(date_str, (time.time(), results, events))
        _save_cache(date_str, results, events)
    return results, events


def get_finished_results(dates=None) -> dict:
    """Return finished results for the given dates (default: today + yesterday).
    Drop-in for free_results_scraper.get_finished_results().
    """
    if dates is None:
        now = datetime.datetime.now(datetime.timezone.utc)
        dates = [
            (now - datetime.timedelta(days=d)).strftime("%Y-%m-%d") for d in range(2)
        ]
    out: dict = {}
    for d in dates:
        out.update(_get_for_date(d)[0])
    return out


def get_events(dates=None) -> dict:
    """Return {date_str: [trimmed event dicts]} for the given dates (default:
    today + yesterday). All statuses included, raw Sofascore event shape.
    Rides the same 30-min cache as get_finished_results — a cycle that already
    refreshed results pays nothing extra here. Pre-upgrade cache files have no
    events; those return [] until the next TTL refresh."""
    if dates is None:
        now = datetime.datetime.now(datetime.timezone.utc)
        dates = [
            (now - datetime.timedelta(days=d)).strftime("%Y-%m-%d") for d in range(2)
        ]
    out: dict = {}
    for d in dates:
        out[d] = _get_for_date(d)[1] or []
    return out


if __name__ == "__main__":
    import sys
    import io as _io

    sys.stdout = _io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace"
    )

    now = datetime.datetime.now(datetime.timezone.utc)
    dates = [(now - datetime.timedelta(days=d)).strftime("%Y-%m-%d") for d in range(3)]
    print(f"Fetching results for: {dates}")
    results = get_finished_results(dates=dates)
    print(f"\nTotal: {len(results)} finished matches")

    targets = ["Utsiktens", "Atvidaberg", "Mochtas", "Lucan", "Goytacaz", "America RJ"]
    print("\n=== Stuck bets lookup ===")
    for t in targets:
        found = [k for k in results if t.lower() in k.lower()]
        if found:
            for k in found:
                v = results[k]
                print(f"  FOUND: {k} -> {v}")
        else:
            print(f"  NOT FOUND: {t}")

    print("\n=== Sample results (first 30) ===")
    for k, v in list(results.items())[:30]:
        print(f"  {k.encode('ascii', 'replace').decode()} {v}")
