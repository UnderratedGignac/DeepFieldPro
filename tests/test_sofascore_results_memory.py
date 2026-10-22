"""Memory bounds in the Sofascore settlement results scraper.

_fetch_date_async() registered a page.on("response") handler that appended the
FULL raw event payload of every api/v1 response into all_events, then scrolled
the page four times to force lazy-loading — which re-fetches the same leagues,
so the same events landed in the list repeatedly. Only at the very end were the
events trimmed to the 8 fields anything reads and deduped by id.

Settlement runs this for up to 8 dates per cycle (settle_open_bets looks back
`_days_back`, capped at 7), so the peak was: full raw payloads x duplicates x
dates. Trimming and deduping on ARRIVAL keeps the same output with a fraction
of the peak.

_mem_cache also grew one entry per distinct date for the process lifetime.

Pure-logic tests — no browser, no network.
"""

import importlib

import pytest

ss = importlib.import_module("src.sofascore_results_scraper")


def _raw_event(eid, home="Arsenal", away="Chelsea", hs=2, as_=1, status="finished"):
    """A raw Sofascore event, including the bulk fields nothing downstream reads."""
    return {
        "id": eid,
        "status": {"type": status, "code": 100, "description": "Ended"},
        "homeScore": {"current": hs, "normaltime": hs, "period1": 1, "period2": 1},
        "awayScore": {"current": as_, "normaltime": as_, "period1": 0, "period2": 1},
        "homeTeam": {"name": home, "id": 1, "slug": home.lower(), "colors": {}},
        "awayTeam": {"name": away, "id": 2, "slug": away.lower(), "colors": {}},
        "tournament": {"name": "EPL", "id": 17, "category": {}, "uniqueTournament": {}},
        # bulk the trim is supposed to drop
        "changes": {"changeTimestamp": 1} | {f"pad{i}": "x" * 200 for i in range(40)},
    }


# ---------------------------------------------------------------------------
# collector: trim + dedup on arrival
# ---------------------------------------------------------------------------


def test_collector_dedups_events_repeated_across_responses():
    """Scrolling re-fetches the same leagues; the same ids arrive many times."""
    c = ss._EventCollector()
    for _ in range(5):  # 5 lazy-load rounds returning the same page of events
        c.extend([_raw_event(i) for i in range(20)])
    assert len(c.events()) == 20


def test_collector_trims_bulk_fields_on_arrival():
    c = ss._EventCollector()
    c.extend([_raw_event(1)])
    ev = c.events()[0]
    assert "changes" not in ev, "bulk payload must not be retained"
    assert set(ev) == {
        "id",
        "status",
        "homeScore",
        "awayScore",
        "homeTeam",
        "awayTeam",
        "tournament",
    }


def test_collector_preserves_everything_parse_events_reads():
    c = ss._EventCollector()
    c.extend([_raw_event(7, home="Spurs", away="Everton", hs=3, as_=0)])
    results = ss._parse_events(c.events())
    assert results == {"Spurs vs Everton": (3, 0)}


def test_collector_keeps_unfinished_events_for_the_completion_scan():
    """get_events() returns ALL statuses — settlement filters, not the collector."""
    c = ss._EventCollector()
    c.extend(
        [
            _raw_event(1, home="Live A", away="Live B", status="inprogress"),
            _raw_event(2, home="Done A", away="Done B", hs=1, as_=0, status="finished"),
        ]
    )
    assert len(c.events()) == 2, "both statuses are retained"
    # ...but only the finished one grades.
    assert ss._parse_events(c.events()) == {"Done A vs Done B": (1, 0)}


def test_collector_skips_events_without_an_id():
    c = ss._EventCollector()
    c.extend([{"status": {"type": "finished"}}, _raw_event(3)])
    assert [e["id"] for e in c.events()] == [3]


def test_collector_ignores_non_dict_entries():
    c = ss._EventCollector()
    c.extend(["nope", None, 5, _raw_event(4)])
    assert [e["id"] for e in c.events()] == [4]


def test_collector_peak_is_bounded_by_distinct_ids_not_arrivals():
    c = ss._EventCollector()
    for _ in range(50):
        c.extend([_raw_event(i) for i in range(100)])
    assert len(c.events()) == 100


# ---------------------------------------------------------------------------
# _mem_cache retention
# ---------------------------------------------------------------------------


def test_mem_cache_is_bounded(monkeypatch):
    monkeypatch.setattr(ss, "_mem_cache", {})
    for d in range(ss._MEM_CACHE_MAX + 20):
        ss._mem_cache_put(f"2026-01-{d:02d}", (0.0, {}, []))
    assert len(ss._mem_cache) <= ss._MEM_CACHE_MAX


def test_mem_cache_evicts_oldest_first(monkeypatch):
    monkeypatch.setattr(ss, "_mem_cache", {})
    for i in range(ss._MEM_CACHE_MAX + 1):
        ss._mem_cache_put(f"d{i}", (0.0, {}, []))
    assert "d0" not in ss._mem_cache
    assert f"d{ss._MEM_CACHE_MAX}" in ss._mem_cache


def test_mem_cache_max_covers_the_settlement_lookback():
    """settle_open_bets() asks for up to 8 dates in one pass — all must fit."""
    assert ss._MEM_CACHE_MAX >= 8
