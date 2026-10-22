"""Batched Sofascore stats fetch — one browser session, not one per fixture.

refresh_completed_comparisons() called get_fixture_stats_free(fid) inside its
per-fixture loop. Each call ran `with sync_playwright(): chromium.launch()`,
navigated to sofascore.com and waited 2s — a full Chromium spawn per finished
fixture, ~13 per cycle, on a 45s loop. fetch_api_json() already accepts a LIST
of paths and fetches them all from one session; these tests pin that the batch
helper uses it that way.

No browser, no network — fetch_api_json is stubbed.
"""

import importlib

import pytest

fsm = importlib.import_module("src.free_scraper_module")
sps = importlib.import_module("src.sofascore_patchright_scraper")


@pytest.fixture
def spy(monkeypatch):
    """Record every fetch_api_json call; return canned stats per path."""
    calls = []

    def fake_fetch_api_json(paths, **kw):
        calls.append(list(paths))
        return {p: {"statistics": [{"path": p}]} for p in paths}

    monkeypatch.setattr(sps, "fetch_api_json", fake_fetch_api_json)
    return calls


def test_batch_uses_a_single_browser_session(spy):
    fids = [101, 102, 103, 104, 105]
    out = fsm.get_fixture_stats_free_batch(fids)

    assert len(spy) == 1, f"expected 1 browser session, got {len(spy)}"
    assert len(spy[0]) == 5, "all five paths must go in the one session"
    assert set(out) == set(fids)


def test_batch_maps_results_back_to_fixture_ids(spy):
    out = fsm.get_fixture_stats_free_batch([777, 888])
    assert out[777]["statistics"][0]["path"] == "/api/v1/event/777/statistics"
    assert out[888]["statistics"][0]["path"] == "/api/v1/event/888/statistics"


def test_batch_of_empty_list_makes_no_browser_call(spy):
    assert fsm.get_fixture_stats_free_batch([]) == {}
    assert spy == []


def test_batch_dedups_repeated_ids(spy):
    fsm.get_fixture_stats_free_batch([5, 5, 5, 6])
    assert len(spy) == 1
    assert sorted(spy[0]) == sorted(
        ["/api/v1/event/5/statistics", "/api/v1/event/6/statistics"]
    )


def test_batch_survives_a_failing_session(monkeypatch):
    def boom(paths, **kw):
        raise RuntimeError("chromium launch failed")

    monkeypatch.setattr(sps, "fetch_api_json", boom)
    out = fsm.get_fixture_stats_free_batch([1, 2])
    assert out == {1: None, 2: None}, "a dead session must degrade, not raise"


def test_batch_tolerates_missing_paths_in_response(monkeypatch):
    monkeypatch.setattr(sps, "fetch_api_json", lambda paths, **kw: {})
    assert fsm.get_fixture_stats_free_batch([9]) == {9: None}


def test_single_fetch_still_works_and_uses_one_session(spy):
    """Back-compat: the old single-fixture entry point keeps its contract."""
    got = fsm.get_fixture_stats_free(42)
    assert got["statistics"][0]["path"] == "/api/v1/event/42/statistics"
    assert len(spy) == 1
