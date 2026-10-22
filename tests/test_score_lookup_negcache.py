"""Negative-result cache for the deep settlement score lookup.

lookup_score() is the last-resort settlement path: Flashscore team search +
results-page scrape for BOTH teams, then a Google fallback — each of those
launches its own headless Chromium. One observed daemon cycle did 10 lookups =
18 FS-SCRAPE launches + 9 Google launches = 27 Chromium spawns.

Nothing cached the misses, so the same obscure fixtures (reserve sides, minor
leagues that Flashscore simply does not carry) were re-attempted on every
settlement pass — every ~45 seconds, indefinitely. This pins the negative cache
that stops the retry storm while leaving successful lookups untouched.

No browser, no network — the strategy layers are stubbed.
"""

import importlib

import pytest

sl = importlib.import_module("tools.score_lookup")


@pytest.fixture(autouse=True)
def clean_cache():
    sl.clear_lookup_cache()
    yield
    sl.clear_lookup_cache()


@pytest.fixture
def no_strategies(monkeypatch):
    """Make every lookup strategy fail, counting attempts."""
    calls = {"n": 0}

    def fail(*a, **kw):
        calls["n"] += 1
        return None

    monkeypatch.setattr(sl, "_fs_feed_fuzzy", fail)
    monkeypatch.setattr(sl, "_fs_search_team", fail)
    monkeypatch.setattr(sl, "_google_score", fail)
    return calls


@pytest.fixture
def winning_strategy(monkeypatch):
    calls = {"n": 0}

    def hit(home, away, *a, **kw):
        calls["n"] += 1
        return (2, 1)

    monkeypatch.setattr(sl, "_fs_feed_fuzzy", hit)
    return calls


# ---------------------------------------------------------------------------


def test_failed_lookup_is_not_retried_within_ttl(no_strategies):
    """The whole point: one miss must not become a browser launch every cycle."""
    assert sl.lookup_score("Selwyn United FC", "Nelson Suburbs") is None
    first = no_strategies["n"]
    assert first > 0

    for _ in range(20):  # 20 more settlement passes
        assert sl.lookup_score("Selwyn United FC", "Nelson Suburbs") is None

    assert no_strategies["n"] == first, "cached miss must not re-run any strategy"


def test_retry_resumes_after_ttl_expires(no_strategies, monkeypatch):
    sl.lookup_score("A", "B")
    first = no_strategies["n"]

    real = sl.time.time
    monkeypatch.setattr(sl.time, "time", lambda: real() + sl.NEG_CACHE_TTL + 1)

    sl.lookup_score("A", "B")
    assert no_strategies["n"] > first, "the fixture must be retried once TTL lapses"


def test_successful_lookup_is_never_suppressed(winning_strategy):
    for _ in range(5):
        got = sl.lookup_score("Chicago Fire", "Vancouver Whitecaps")
        assert got is not None and got[:2] == (2, 1)
    assert winning_strategy["n"] == 5, "hits must not be served from the miss cache"


def test_cache_is_per_fixture(no_strategies):
    sl.lookup_score("A", "B")
    n_after_first = no_strategies["n"]

    sl.lookup_score("C", "D")  # different fixture -> must actually try
    assert no_strategies["n"] > n_after_first


def test_cache_is_direction_sensitive(no_strategies):
    """'A vs B' and 'B vs A' are different fixtures in this codebase."""
    sl.lookup_score("A", "B")
    n = no_strategies["n"]
    sl.lookup_score("B", "A")
    assert no_strategies["n"] > n


def test_cache_key_is_case_and_whitespace_insensitive(no_strategies):
    sl.lookup_score("Real Madrid", "Barcelona")
    n = no_strategies["n"]
    sl.lookup_score("  real madrid ", "BARCELONA")
    assert no_strategies["n"] == n


def test_cache_is_bounded(no_strategies):
    for i in range(sl.NEG_CACHE_MAX + 100):
        sl.lookup_score(f"Home{i}", f"Away{i}")
    assert len(sl._NEG_CACHE) <= sl.NEG_CACHE_MAX


def test_clear_lookup_cache_forces_a_retry(no_strategies):
    sl.lookup_score("A", "B")
    n = no_strategies["n"]
    sl.lookup_score("A", "B")
    assert no_strategies["n"] == n

    sl.clear_lookup_cache()
    sl.lookup_score("A", "B")
    assert no_strategies["n"] > n


def test_ttl_exceeds_the_daemons_own_deep_lookup_throttle():
    """The daemon already gates the deep lookup behind _DEEP_LOOKUP_INTERVAL
    (1800s). A cache TTL at or below that expires exactly when the throttle
    lifts, so it would suppress nothing — the cache must outlive the throttle."""
    from tests._daemon_test_utils import import_daemon

    throttle = import_daemon()._DEEP_LOOKUP_INTERVAL
    assert sl.NEG_CACHE_TTL > throttle, (
        f"TTL {sl.NEG_CACHE_TTL}s <= throttle {throttle}s makes the cache a no-op"
    )


def test_ttl_is_long_enough_to_matter_but_not_stale():
    """Long enough to collapse the retry storm, short enough that a genuinely
    late result still gets picked up the same day."""
    assert 1800 < sl.NEG_CACHE_TTL <= 6 * 3600
