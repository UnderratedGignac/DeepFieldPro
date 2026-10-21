"""Each event page must yield its deep-markets file before the scraper moves on.

Over/Under, BTTS and every other non-1X2 market live only in an event's
single-pre-event.json, which the SPA fetches ~3.5-4.5s after navigation (later
on a freshly recycled page). The scraper slept a fixed 3s after
domcontentloaded and then navigated away or closed the page; a body still in
flight at that point is lost, and handle_response swallowed the error. On
2026-10-21 that captured 2 of 50 events, so 152 of 154 fixtures had no O/U
price and MODEL_VALUE_ALIGN had nothing to evaluate.

_scout_event() waits for THIS event's deep file (bounded by a timeout) and
stores it before returning.
"""

import asyncio
import importlib

scraper = importlib.import_module("src.betarabia_scraper")

DEEP = "https://pre-88o-sp.websbkt.com/cache/88/en/lb/{eid}/single-pre-event.json?hidenseek=ea4"


class _Resp:
    def __init__(self, url, data):
        self.url = url
        self._data = data

    async def json(self):
        return self._data


class _Expect:
    def __init__(self, coro):
        self._coro = coro

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    @property
    def value(self):
        return self._coro


class FakePage:
    """Serves responses for an event page; the deep file lands after goto returns."""

    def __init__(self, responses, delay_s=0.05):
        self.responses = responses  # list of (url, data) the page will load
        self.delay_s = delay_s
        self.visited = []

    def expect_response(self, predicate, timeout=None):
        async def _wait():
            await asyncio.sleep(self.delay_s)
            for url, data in self.responses:
                r = _Resp(url, data)
                if predicate(r):
                    return r
            raise TimeoutError(f"no matching response within {timeout} ms")

        return _Expect(_wait())

    async def goto(self, url, **_kw):
        self.visited.append(url)


def _run(coro):
    return asyncio.run(coro)


def test_deep_file_arriving_after_page_load_is_captured():
    store = scraper._ResponseStore()
    page = FakePage([(DEEP.format(eid=30220932), {"data": {"info": {"id": 30220932}}})])

    ok = _run(scraper._scout_event(page, 30220932, store))

    assert ok is True
    assert DEEP.format(eid=30220932) in {r["url"] for r in store.as_list()}
    assert page.visited == [
        "https://www.betarabia.com/en/sports/kickertech/football/event/30220932"
    ]


def test_another_events_deep_file_does_not_count():
    """A late file from the previous event must not satisfy this event's wait."""
    store = scraper._ResponseStore()
    page = FakePage([(DEEP.format(eid=30141288), {"data": {}})])

    ok = _run(scraper._scout_event(page, 30220932, store))

    assert ok is False
    assert len(store) == 0


def test_event_without_deep_file_returns_false_without_raising():
    store = scraper._ResponseStore()
    page = FakePage([])

    assert _run(scraper._scout_event(page, 1, store)) is False
