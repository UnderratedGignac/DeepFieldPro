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


def _cache_path(date_str: str) -> str:
    return os.path.join(_DATA_DIR, f"sofascore_cache_{date_str}.json")


def _load_cache(date_str: str):
    p = _cache_path(date_str)
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            obj = json.load(f)
        return obj.get("fetched_at", 0), obj.get("results", {})
    except Exception:
        return None


def _save_cache(date_str: str, results: dict):
    p = _cache_path(date_str)
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"fetched_at": time.time(), "results": results}, f)
    except Exception:
        pass


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

    all_events: list = []

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
                if evs and len(evs) > 0:
                    all_events.extend(evs)
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

    results = _parse_events(all_events)
    print(f"[SOFASCORE] {date_str}: {len(results)} finished from {len(all_events)} total events")
    return results


def _fetch_date_sync(date_str: str) -> dict:
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
        return {}


def _get_for_date(date_str: str) -> dict:
    mem = _mem_cache.get(date_str)
    if mem and (time.time() - mem[0]) < _CACHE_TTL:
        return mem[1]

    disk = _load_cache(date_str)
    if disk and (time.time() - disk[0]) < _CACHE_TTL:
        _mem_cache[date_str] = disk
        return disk[1]

    results = _fetch_date_sync(date_str)
    if results:  # don't cache empty results — may be a transient failure
        _mem_cache[date_str] = (time.time(), results)
        _save_cache(date_str, results)
    return results


def get_finished_results(dates=None) -> dict:
    """Return finished results for the given dates (default: today + yesterday).
    Drop-in for free_results_scraper.get_finished_results().
    """
    if dates is None:
        now = datetime.datetime.now(datetime.timezone.utc)
        dates = [
            (now - datetime.timedelta(days=d)).strftime("%Y-%m-%d")
            for d in range(2)
        ]
    out: dict = {}
    for d in dates:
        out.update(_get_for_date(d))
    return out


if __name__ == "__main__":
    import sys
    import io as _io
    sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

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
