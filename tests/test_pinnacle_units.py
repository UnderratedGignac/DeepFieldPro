"""Only Pinnacle's real goals matchups may feed goals totals and 1X2.

Pinnacle publishes cards and corners as separate matchups of the same
type="matchup", told apart only by `units` ("Regular" / "Bookings" /
"Corners") and renamed participants ("Aston Villa (Bookings)"). On 2026-10-21
the feed held 1048 Regular, 87 Corners and 29 Bookings matchups, and both
fetch_pinnacle_totals() and fetch_1x2_snapshot() took all of them: a cards
line at 2.5 sat in the goals O/U 2.5 universe, the only Pinnacle entry for
Aston Villa vs Viking and Real Madrid vs Leipzig.

The totals line was also matched with key.count("2.5"), so a 12.5 line
(corners territory) read as 2.5. It now compares the price's exact points.
"""

import importlib
import time

import pytest

pf = importlib.import_module("src.pinnacle_feed")

SOON = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 3 * 3600))


def _matchup(mid, home, away, units):
    return {
        "id": mid,
        "type": "matchup",
        "units": units,
        "startTime": SOON,
        "league": {"name": "UEFA - Champions League"},
        "participants": [
            {"alignment": "home", "name": home},
            {"alignment": "away", "name": away},
        ],
    }


def _total(mid, points, over=-110, under=-110):
    return {
        "matchupId": mid,
        "type": "total",
        "period": 0,
        "key": f"s;0;ou;{points}",
        "prices": [
            {"designation": "over", "points": points, "price": over},
            {"designation": "under", "points": points, "price": under},
        ],
    }


def _moneyline(mid):
    return {
        "matchupId": mid,
        "type": "moneyline",
        "period": 0,
        "prices": [
            {"designation": "home", "price": 150},
            {"designation": "draw", "price": 240},
            {"designation": "away", "price": 180},
        ],
    }


@pytest.fixture
def feed(monkeypatch):
    matchups = [
        _matchup(1, "Arsenal", "Chelsea", "Regular"),
        _matchup(2, "Arsenal (Bookings)", "Chelsea (Bookings)", "Bookings"),
        _matchup(3, "Arsenal (Corners)", "Chelsea (Corners)", "Corners"),
        _matchup(4, "Lyon", "Nice", "Regular"),
    ]
    markets = [
        _total(1, 2.5), _total(2, 2.5), _total(3, 2.5), _total(4, 12.5),
        _moneyline(1), _moneyline(2), _moneyline(3),
    ]

    def _cached(path, params=None, timeout=15):
        return matchups if path.endswith("/matchups") else markets

    monkeypatch.setattr(pf, "_get_cached", _cached)


def test_totals_hold_regular_goals_matchups_only(feed):
    assert set(pf.fetch_pinnacle_totals(line=2.5)) == {"Arsenal vs Chelsea"}


def test_a_12_5_line_is_not_read_as_2_5(feed):
    assert "Lyon vs Nice" not in pf.fetch_pinnacle_totals(line=2.5)


def test_1x2_snapshot_skips_bookings_and_corners(feed):
    keys = {r["match_key"] for r in pf.fetch_1x2_snapshot()}
    assert keys == {"Arsenal vs Chelsea"}
