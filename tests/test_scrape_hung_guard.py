"""A scrape still in progress must not be killed as "hung".

The daemon launches the Betarabia scraper BECAUSE odds are stale, and odds only
refresh when the scrape finishes. The hung-scrape guard treated "process alive
and odds stale" as hung, so any scrape outliving one daemon cycle was killed
before it could write. Once each event page waited for its deep-markets file
(~4-5 min per scrape), that became a kill/relaunch loop (2026-10-21).

Hung now means: stale odds AND running longer than a scrape can take.
"""

import importlib

lpd = importlib.import_module("src.live_predictions_daemon")


def test_scrape_in_progress_with_stale_odds_is_not_hung():
    assert lpd._scrape_is_hung(running_for_sec=5 * 60, odds_stale=True) is False


def test_scrape_far_past_its_runtime_with_stale_odds_is_hung():
    assert lpd._scrape_is_hung(running_for_sec=40 * 60, odds_stale=True) is True


def test_long_scrape_with_fresh_odds_is_not_hung():
    assert lpd._scrape_is_hung(running_for_sec=40 * 60, odds_stale=False) is False


def test_limit_leaves_room_for_a_full_scrape():
    """50 event pages at up to the deep-file timeout each must fit comfortably."""
    assert lpd._SCRAPE_MAX_RUNTIME_SEC >= 10 * 60
