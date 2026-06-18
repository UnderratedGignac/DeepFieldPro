"""
sofascore_scraper.py — keyless Sofascore result scraper via Playwright.
=======================================================================
Sofascore's JSON API (api.sofascore.com) is Cloudflare-blocked — even same-origin
fetch() from inside a loaded page returns 403. But FULL PAGE NAVIGATIONS work: the
match page ships its data in the embedded `__NEXT_DATA__` <script>. So we drive a real
Chromium (the same Playwright we already use for Betarabia), navigate to a match URL,
and parse the score out of that JSON. No API key, no paid feed.

This covers the obscure leagues ESPN/TheSportsDB miss (e.g. Brazilian Série C/D) that
were leaving bets stuck on OPEN forever.

Public API:
    scrape_match(url) -> {"home","away","home_score","away_score","finished"} or None
    scrape_many(urls) -> list of the above (one browser session)

This is intentionally NOT wired into the hot daemon loop (Playwright is heavy and
Sofascore has no keyless way to *discover* a match URL from team names — discovery is
blocked). It's an on-demand settlement aid: paste the Sofascore link for a stuck bet.
See tools/settle_from_sofascore.py.
"""

import json

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def _extract_event(next_data_text, want_url=None):
    """Find the focal finished/live event in a match page's __NEXT_DATA__ JSON."""
    data = json.loads(next_data_text)
    best = None
    stack = [data]
    while stack:
        o = stack.pop()
        if isinstance(o, dict):
            if (
                "homeTeam" in o
                and "awayTeam" in o
                and ("homeScore" in o or "status" in o)
            ):
                ht = (o.get("homeTeam") or {}).get("name")
                at = (o.get("awayTeam") or {}).get("name")
                hs = o.get("homeScore") or {}
                as_ = o.get("awayScore") or {}
                st = o.get("status") or {}
                hs_v = hs.get("current") if isinstance(hs, dict) else hs
                as_v = as_.get("current") if isinstance(as_, dict) else as_
                st_v = st.get("type") if isinstance(st, dict) else st
                # The match page's PRIMARY event is the one with a real score / finished
                # status; featured side-events are 'notstarted'. Prefer a finished one.
                cand = {
                    "home": ht,
                    "away": at,
                    "home_score": hs_v,
                    "away_score": as_v,
                    "finished": (st_v == "finished"),
                }
                if ht and at:
                    if cand["finished"] and hs_v is not None and as_v is not None:
                        return cand  # definitive
                    if best is None:
                        best = cand
            stack.extend(o.values())
        elif isinstance(o, list):
            stack.extend(o)
    return best


def scrape_match(url, _page=None):
    """Return the score dict for one Sofascore match URL, or None on failure."""
    if _page is not None:
        return _scrape_with_page(_page, url)
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            pg = b.new_page(user_agent=_UA)
            return _scrape_with_page(pg, url)
        finally:
            b.close()


def _scrape_with_page(pg, url):
    try:
        pg.goto(url, wait_until="domcontentloaded", timeout=30000)
        pg.wait_for_timeout(3500)
        nd = pg.evaluate(
            "() => { const el=document.getElementById('__NEXT_DATA__');"
            " return el ? el.textContent : null; }"
        )
        if not nd:
            return None
        return _extract_event(nd)
    except Exception as e:
        print(f"[SOFASCORE] scrape failed for {url}: {e}")
        return None


def scrape_many(urls):
    """Scrape several match URLs in one browser session."""
    from playwright.sync_api import sync_playwright

    out = []
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            pg = b.new_page(user_agent=_UA)
            for u in urls:
                out.append(_scrape_with_page(pg, u))
        finally:
            b.close()
    return out


if __name__ == "__main__":
    import sys

    for u in sys.argv[1:]:
        print(u, "->", scrape_match(u))
