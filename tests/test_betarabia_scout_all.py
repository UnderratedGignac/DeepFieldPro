"""The scraper must open every upcoming match, soonest first, within a time budget.

It opened the first 50 events in feed order, including matches already under
way, so on 2026-10-21 Betarabia had Over/Under for 49 of 127 fixtures. Each
page now waits for its deep-markets file (~4-5s), so the run is bounded by
time instead of a count: soonest kickoffs first, and whatever the budget does
not reach is picked up by the next run. The budget stays under the daemon's
hung-scrape limit so a long run is never killed as hung.
"""

import asyncio
import datetime
import importlib

scraper = importlib.import_module("src.betarabia_scraper")
lpd = importlib.import_module("src.live_predictions_daemon")

NOW = datetime.datetime(2026, 10, 21, 12, 0, tzinfo=datetime.timezone.utc)


def _iso(minutes):
    return (NOW + datetime.timedelta(minutes=minutes)).isoformat()


def test_every_upcoming_event_soonest_first():
    events = {str(i): {"kickoff_time": _iso(10 * i)} for i in range(1, 81)}  # 80 upcoming
    events["live"] = {"kickoff_time": _iso(-30)}  # already kicked off
    events["late"] = {"kickoff_time": _iso(5)}  # soonest of all
    ids = scraper._events_to_scout(events, NOW.timestamp())
    assert len(ids) == 81, "no 50-event cap"
    assert "live" not in ids
    assert ids[0] == "late" and ids[1:4] == ["1", "2", "3"]


class _Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_loop_stops_at_the_time_budget_and_recycles_pages():
    clock = _Clock()
    recycled, opened = [], []

    async def scout_one(eid):
        opened.append(eid)
        clock.t += 5.0  # each page takes 5s
        return eid != "e3"  # one page without deep markets

    async def recycle():
        recycled.append(len(opened))

    captured, attempted = asyncio.run(
        scraper._scout_events([f"e{i}" for i in range(10)], scout_one, recycle,
                              budget_sec=22.0, clock=clock)
    )
    assert opened == ["e0", "e1", "e2", "e3", "e4"]  # 5th page starts at t=20 < 22
    assert (captured, attempted) == (4, 5)
    assert recycled == [scraper._PAGE_RECYCLE_EVERY]


def test_budget_fits_inside_the_daemons_hung_scrape_limit():
    """Budget + browser start-up + parsing must finish before the daemon calls it hung."""
    assert scraper._SCOUT_BUDGET_SEC + 3 * 60 <= lpd._SCRAPE_MAX_RUNTIME_SEC
