"""Never bet a match that has already kicked off.

Chasing the odds_fresh gate turned up the real hole. The prediction loop only
skips a fixture when BOTH conditions hold:

    status in ("FT", "AET", "PEN")  AND  kickoff more than 12 hours ago

So a match that kicked off 3 hours ago, or one still mis-labelled "NS" because
its source never updated, sails through to the bet gate. On 2026-08-25 that was
17 South American fixtures from the previous day, kicked off 9-13 hours earlier,
carrying 13-hour-old prices.

Nothing rejected them on kickoff. They were caught only by `odds_fresh` — a
staleness guard doing a kickoff guard's job, and the sole thing standing between
the engine and a bet on a finished match. That is far too load-bearing for a
defence-in-depth check, and it fails open whenever the odds happen to be fresh
(a live in-play price is fresh by definition).

_kickoff_passed() makes it explicit.
"""

import datetime
import importlib

import pytest

lpd = importlib.import_module("src.live_predictions_daemon")


def _iso(minutes_from_now):
    return (
        datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(minutes=minutes_from_now)
    ).isoformat()


# ---------------------------------------------------------------------------


def test_future_kickoff_is_bettable():
    assert lpd._kickoff_passed(_iso(120)) is False


def test_kickoff_an_hour_ago_is_not_bettable():
    assert lpd._kickoff_passed(_iso(-60)) is True


def test_yesterdays_match_is_not_bettable():
    """The 2026-08-25 case: kicked off 9-13h earlier, still on the slate."""
    assert lpd._kickoff_passed(_iso(-11 * 60)) is True


def test_just_kicked_off_is_not_bettable():
    assert lpd._kickoff_passed(_iso(-1)) is True


def test_grace_window_allows_a_clock_skew_margin():
    """Feeds disagree by a minute or two; a bet placed seconds before kickoff
    must not be rejected because our clock ran fast."""
    assert lpd._kickoff_passed(_iso(-2), grace_min=5) is False
    assert lpd._kickoff_passed(_iso(-10), grace_min=5) is True


def test_naive_timestamp_is_treated_as_utc():
    naive = (
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=3)
    ).replace(tzinfo=None).isoformat()
    assert lpd._kickoff_passed(naive) is True


def test_zulu_suffix_is_handled():
    z = (
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=3)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert lpd._kickoff_passed(z) is True


@pytest.mark.parametrize("bad", [None, "", "not-a-date", 12345, {}])
def test_unparseable_kickoff_fails_open(bad):
    """An unknown kickoff must not silently block the whole slate — the other
    gates (odds_fresh, ev, prob) still apply."""
    assert lpd._kickoff_passed(bad) is False


def test_status_is_irrelevant():
    """The old filter needed status in (FT, AET, PEN); a stale 'NS' bypassed it.
    Kickoff time alone decides."""
    past = _iso(-180)
    assert lpd._kickoff_passed(past) is True  # regardless of any status field
