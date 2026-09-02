"""Pinnacle raw-response cache tests.

The public Pinnacle endpoint is Cloudflare-cached and advertises it:

    cache-control: public, max-age=905, must-revalidate
    cf-cache-status: HIT
    age: 809

So the underlying data only changes about every 15 minutes, but the feed
polled it every POLL_INTERVAL (45s) and BOTH the feed loop and the daemon
called fetch_* helpers that each re-request the SAME two endpoints:

    /sports/29/matchups          (fetch_1x2_snapshot, _totals, _btts)
    /sports/29/markets/straight  (fetch_1x2_snapshot, _totals, _btts)

/sports/29/markets/straight alone is ~24MB, so that is tens of GB/day of
re-downloading byte-identical cached responses.

These tests pin the fix: a shared, TTL-aware in-process cache keyed on the
request path, whose TTL is derived from the CDN's OWN remaining freshness
(max-age minus age). Deriving it that way is what makes this safe — the
cache can never serve data staler than what the CDN was already going to
serve, so it adds no staleness to the edge calculation.

No real network — the HTTP layer is stubbed.
"""

import importlib

import pytest


class _FakeResponse:
    def __init__(self, payload, headers=None):
        self._payload = payload
        self.headers = headers or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


@pytest.fixture
def feed(monkeypatch):
    pf = importlib.import_module("src.pinnacle_feed")
    pf._cache_clear()
    yield pf
    pf._cache_clear()


@pytest.fixture
def http(monkeypatch, feed):
    """Stub the raw HTTP layer and count calls per path."""
    calls = []

    def fake_get_raw(path, params=None, timeout=15):
        calls.append(path)
        return _FakeResponse(
            [{"path": path, "n": len(calls)}],
            {"cache-control": "public, max-age=905, must-revalidate", "age": "809"},
        )

    monkeypatch.setattr(feed, "_get_raw", fake_get_raw)
    return calls


def test_repeat_fetch_within_ttl_makes_one_http_call(feed, http):
    a = feed._get_cached("/sports/29/markets/straight")
    b = feed._get_cached("/sports/29/markets/straight")
    assert a == b
    assert len(http) == 1, "second call within TTL must be served from cache"


def test_distinct_paths_cached_independently(feed, http):
    feed._get_cached("/sports/29/matchups")
    feed._get_cached("/sports/29/markets/straight")
    feed._get_cached("/sports/29/matchups")
    feed._get_cached("/sports/29/markets/straight")
    assert len(http) == 2, "each path fetched once, then cached"


def test_cache_expires_and_refetches(feed, http, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(feed.time, "time", lambda: now[0])
    feed._get_cached("/sports/29/matchups")
    assert len(http) == 1
    now[0] += 10_000  # well past any TTL
    feed._get_cached("/sports/29/matchups")
    assert len(http) == 2, "expired entry must be refetched"


def test_ttl_derived_from_cdn_remaining_freshness(feed):
    """max-age=905 with age=809 leaves 96s of CDN freshness."""
    ttl = feed._cache_ttl_from_headers(
        {"cache-control": "public, max-age=905, must-revalidate", "age": "809"}
    )
    assert ttl == pytest.approx(96.0, abs=1.0)


def test_ttl_never_exceeds_cdn_max_age(feed):
    ttl = feed._cache_ttl_from_headers({"cache-control": "public, max-age=905"})
    assert ttl <= 905.0


def test_ttl_falls_back_when_headers_absent(feed):
    ttl = feed._cache_ttl_from_headers({})
    assert ttl > 0, "a missing cache-control must not disable caching entirely"
    assert ttl <= feed._MAX_CACHE_SEC


def test_ttl_is_floored_so_a_nearly_expired_cdn_copy_still_dedups(feed):
    """age >= max-age would give ttl<=0 and defeat the cache for a whole cycle."""
    ttl = feed._cache_ttl_from_headers(
        {"cache-control": "public, max-age=905", "age": "905"}
    )
    assert ttl >= feed._MIN_CACHE_SEC


def test_all_three_fetchers_share_one_pair_of_requests(feed, monkeypatch):
    """The headline fix: 3 fetchers previously issued 6 requests, now 2.

    fetch_1x2_snapshot, fetch_pinnacle_totals and fetch_pinnacle_btts each
    request /sports/29/matchups AND /sports/29/markets/straight. Sharing the
    cache collapses six round-trips (of a ~24MB payload) into two.
    """
    calls = []

    def fake_get_raw(path, params=None, timeout=15):
        calls.append(path)
        return _FakeResponse(
            [],  # empty payload: parsing yields no matches, which is fine here
            {"cache-control": "public, max-age=905", "age": "0"},
        )

    monkeypatch.setattr(feed, "_get_raw", fake_get_raw)

    feed.fetch_1x2_snapshot()
    feed.fetch_pinnacle_totals(line=2.5)
    feed.fetch_pinnacle_btts()

    assert sorted(set(calls)) == [
        "/sports/29/markets/straight",
        "/sports/29/matchups",
    ]
    assert len(calls) == 2, f"expected 2 shared requests, got {len(calls)}: {calls}"


def test_poll_interval_is_not_wildly_faster_than_the_data_changes(feed):
    """A 45s poll against a ~905s TTL re-read identical bytes ~20x over.

    The cache makes the poll cheap, but the interval should still be in the
    same order of magnitude as the CDN window so the loop is not spinning.
    """
    assert feed.POLL_INTERVAL >= 120, (
        "POLL_INTERVAL should not be an order of magnitude below the CDN's "
        "~905s cache TTL"
    )
