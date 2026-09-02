"""Betarabia scraper API-capture memory bounds.

run_full_probe() registers a page.on("response") handler that called
`await response.json()` on EVERY JSON response and appended it to an unbounded
list, then drove the SAME page through 50 event navigations. Each navigation
re-fetches the same boilerplate (init.json, bundles, translations/sportSymbol,
cache/version), so the list held ~50 copies of payloads the parsers never read.
Measured cost: a single chrome-headless-shell renderer at 1.34 GB.

parse_kickertech_events() / parse_kickertech_odds() only ever read the top-level
keys "events", "odds" and "data". _ResponseStore keeps exactly those, deduped by
URL, so repeated boilerplate collapses to nothing.

Pure-logic tests — no browser, no network.
"""

import importlib

import pytest

bs = importlib.import_module("src.betarabia_scraper")


@pytest.fixture
def store():
    return bs._ResponseStore()


# ---------------------------------------------------------------------------
# what gets kept
# ---------------------------------------------------------------------------


def test_keeps_payload_with_events_key(store):
    store.add("https://pre-88o-sp.websbkt.com/88/en/events", {"events": {"1": {}}})
    assert len(store.as_list()) == 1


def test_keeps_payload_with_odds_key(store):
    store.add("https://pre-88o-sp.websbkt.com/88/en/odds", {"odds": {"a": 1}})
    assert len(store.as_list()) == 1


def test_keeps_event_detail_payload_under_data_key(store):
    store.add(
        "https://api-m-sp-cdl.websbkt.com/event/28647082",
        {"data": {"groups": [], "info": {}, "odds": {}}},
    )
    assert len(store.as_list()) == 1


@pytest.mark.parametrize(
    "url",
    [
        "https://pre-88o-sp.websbkt.com/88/en/init.json",
        "https://auth-88o-sp.websbkt.com/bundles",
        "https://live-88o-sp.websbkt.com/bundles",
        "https://pre-88o-sp.websbkt.com/cache/version/88",
        "https://api-m-sp-cdl.websbkt.com/translations/sportSymbol?frId=88&lang=en",
    ],
)
def test_drops_boilerplate_payloads_the_parsers_never_read(store, url):
    """These are re-fetched on every one of the 50 event navigations."""
    store.add(url, {"version": 3, "symbols": ["a"] * 5000})
    assert store.as_list() == []


def test_drops_non_sbtech_domains(store):
    store.add("https://www.betarabia.com/whatever.json", {"events": {"1": {}}})
    assert store.as_list() == []


def test_drops_non_dict_payloads(store):
    store.add("https://pre-88o-sp.websbkt.com/x", None)
    store.add("https://pre-88o-sp.websbkt.com/y", ["a", "b"])
    assert store.as_list() == []


# ---------------------------------------------------------------------------
# dedup — the actual leak
# ---------------------------------------------------------------------------


def test_repeated_url_does_not_accumulate(store):
    """50 event navigations re-fetch the same URL; we keep one copy."""
    for i in range(50):
        store.add(
            "https://pre-88o-sp.websbkt.com/88/en/events",
            {"events": {"1": {"seq": i}}},
        )
    kept = store.as_list()
    assert len(kept) == 1
    assert kept[0]["data"]["events"]["1"]["seq"] == 49, "latest payload wins"


def test_distinct_event_urls_are_all_kept(store):
    """Per-event odds payloads have distinct URLs and must all survive."""
    for eid in range(30):
        store.add(
            f"https://api-m-sp-cdl.websbkt.com/event/{eid}",
            {"data": {"groups": [], "info": {}, "odds": {}}},
        )
    assert len(store.as_list()) == 30


def test_store_has_a_hard_cap(store):
    """Backstop so a pathological page can never grow the store without bound."""
    for i in range(bs._MAX_CAPTURED_RESPONSES + 250):
        store.add(
            f"https://api-m-sp-cdl.websbkt.com/event/{i}",
            {"data": {"groups": [], "info": {}, "odds": {}}},
        )
    assert len(store.as_list()) <= bs._MAX_CAPTURED_RESPONSES


# ---------------------------------------------------------------------------
# output shape must stay exactly what the parsers expect
# ---------------------------------------------------------------------------


def test_as_list_shape_is_url_data_dicts(store):
    store.add("https://pre-88o-sp.websbkt.com/e", {"events": {"1": {"id": 1}}})
    item = store.as_list()[0]
    assert set(item) == {"url", "data"}
    assert item["url"].endswith("/e")


def test_parsers_accept_store_output(store):
    """End-to-end shape check against the real parser."""
    store.add(
        "https://pre-88o-sp.websbkt.com/88/en/events",
        {
            "events": {
                "111": {
                    "id": "111",
                    "teams": {"home": "Arsenal", "away": "Chelsea"},
                    "dateStart": "2026-08-24T18:00:00Z",
                    "tournamentName": "EPL",
                    "sportId": 88,
                }
            }
        },
    )
    events = bs.parse_kickertech_events(store.as_list())
    assert "111" in events or 111 in events


def test_page_recycle_interval_is_set_and_sane():
    """The renderer heap is reset by recycling the page mid-crawl."""
    assert 1 <= bs._PAGE_RECYCLE_EVERY <= 25
