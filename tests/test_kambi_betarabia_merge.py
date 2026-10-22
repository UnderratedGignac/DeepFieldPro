"""A Kambi-matched fixture must still carry Betarabia's other markets.

find_betarabia_odds() tries Kambi first and, on a match, returned at once with
Kambi's 1X2 and every other market empty. Kambi only serves 1X2, so for any
fixture Kambi covers, Betarabia's Over/Under 2.5 was never looked at. On
2026-10-21 that was 94 of 163 fixtures, 30 of them with Betarabia O/U prices,
all invisible to MODEL_VALUE_ALIGN (an O/U strategy).

The early return also keyed Kambi's 1X2 as "Home (1)"/"Draw (X)"/"Away (2)",
while the bet loop, the dashboard builder and closing-line capture all read
"Home"/"Draw"/"Away" — so Kambi's 1X2 prices were silently dropped too.

Staleness must stay honest: if a market comes from Betarabia, the age the bet
gate sees has to include Betarabia's scrape age, not just Kambi's 90s cache.
"""

import datetime
import importlib
import sqlite3

import pytest

lpd = importlib.import_module("src.live_predictions_daemon")
kambi = importlib.import_module("src.kambi_scraper")

KAMBI_AGE = 0.5


def _stream_db(data_dir, scraped_at, markets):
    con = sqlite3.connect(str(data_dir / "odds_stream.db"))
    con.execute(
        "CREATE TABLE fixture (fixture_id TEXT PRIMARY KEY, home_team TEXT, "
        "away_team TEXT, kickoff_time TEXT, kickoff_date TEXT, league_id TEXT, "
        "tournament_name TEXT, scraped_at TEXT)"
    )
    con.execute(
        "CREATE TABLE market (market_id TEXT PRIMARY KEY, fixture_id TEXT, "
        "market_name TEXT, selection_name TEXT, raw_odds REAL, prop_player TEXT, "
        "prop_type TEXT, prop_line REAL, scraped_at TEXT)"
    )
    con.execute(
        "INSERT INTO fixture (fixture_id, home_team, away_team, kickoff_time, scraped_at) "
        "VALUES ('1', 'Arsenal', 'Chelsea', ?, ?)",
        (scraped_at, scraped_at),
    )
    con.executemany(
        "INSERT INTO market (market_id, fixture_id, market_name, selection_name, raw_odds) "
        "VALUES (?, '1', ?, ?, ?)",
        [(f"m{i}", m, s, p) for i, (m, s, p) in enumerate(markets)],
    )
    con.commit()
    con.close()


# Betarabia's selection shapes as the scraper stores them (line kept on both sides).
BETARABIA_MARKETS = [
    ("Match Result", "Arsenal", 2.05),
    ("Total Goals", "Total OVER  2.5", 1.90),
    ("Total Goals", "Total UNDER  2.5", 1.95),
]


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    d = tmp_path / "data"
    d.mkdir()
    monkeypatch.setattr(lpd, "DATA_DIR", str(d))
    return d


@pytest.fixture
def kambi_covers(monkeypatch):
    def _cover(home, away):
        monkeypatch.setattr(
            kambi,
            "fetch_kambi_1x2",
            lambda: {
                f"{home} vs {away}": {
                    "home_team": home,
                    "away_team": away,
                    "home": 2.10,
                    "draw": 3.40,
                    "away": 3.60,
                }
            },
        )
        monkeypatch.setattr(kambi, "cache_age_min", lambda: KAMBI_AGE)

    return _cover


def _now(minus_hours=0.0):
    return (
        datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(hours=minus_hours)
    ).isoformat()


def test_kambi_match_keeps_betarabia_over_under(data_dir, kambi_covers):
    _stream_db(data_dir, _now(), BETARABIA_MARKETS)
    kambi_covers("Arsenal", "Chelsea")

    odds = lpd.find_betarabia_odds("Arsenal", "Chelsea")

    assert odds["Over/Under 2.5"] == {"Over": 1.90, "Under": 1.95}


def test_kambi_1x2_uses_the_keys_the_bet_loop_reads(data_dir, kambi_covers):
    _stream_db(data_dir, _now(), BETARABIA_MARKETS)
    kambi_covers("Arsenal", "Chelsea")

    odds = lpd.find_betarabia_odds("Arsenal", "Chelsea")

    assert odds["1X2"] == {"Home": 2.10, "Draw": 3.40, "Away": 3.60}


def test_merged_betarabia_market_carries_betarabia_staleness(data_dir, kambi_covers):
    """A 12h-old Betarabia O/U price must not pass as fresh behind Kambi's age."""
    _stream_db(data_dir, _now(minus_hours=12), BETARABIA_MARKETS)
    kambi_covers("Arsenal", "Chelsea")

    lpd.find_betarabia_odds("Arsenal", "Chelsea")

    assert lpd._betarabia_odds_age_min > 60


def test_kambi_only_fixture_keeps_kambi_age(data_dir, kambi_covers):
    """Betarabia doesn't list the match: Kambi 1X2 alone, at Kambi's own age."""
    _stream_db(data_dir, _now(minus_hours=12), BETARABIA_MARKETS)
    kambi_covers("Lyon", "Nice")

    odds = lpd.find_betarabia_odds("Lyon", "Nice")

    assert odds["1X2"] == {"Home": 2.10, "Draw": 3.40, "Away": 3.60}
    assert odds["Over/Under 2.5"] == {}
    assert lpd._betarabia_odds_age_min == pytest.approx(KAMBI_AGE)
