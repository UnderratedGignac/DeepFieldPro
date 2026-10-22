"""Odds-staleness must describe THIS fixture, not the previous one.

`_betarabia_odds_age_min` is a module-level global that find_betarabia_odds()
sets, and the bet gate reads as `odds_fresh` (reject if older than
settings.max_odds_staleness_min, default 60).

It was only ever assigned on the Betarabia branch, near the END of the function.
The Tier-1 Kambi branch returns early — and Kambi serves the majority of the
slate (164 fixtures in a live check) — so every Kambi-priced fixture inherited
whatever staleness the last Betarabia-matched fixture happened to leave behind.

Live gate telemetry showed the damage: `odds_fresh` rejected 54 of 127
selections (43%) while only 9% of fixtures in odds_stream.db were actually
older than 60 minutes. Fixtures whose odds came fresh from a live API were
being thrown away as stale.
"""

import datetime
import importlib
import sqlite3

import pytest

lpd = importlib.import_module("src.live_predictions_daemon")
kambi = importlib.import_module("src.kambi_scraper")

STALE = 999.0  # minutes — well past any sane gate


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """tmp DATA_DIR with an odds_stream.db holding one freshly-scraped fixture."""
    d = tmp_path / "data"
    d.mkdir()
    con = sqlite3.connect(str(d / "odds_stream.db"))
    con.execute(
        """CREATE TABLE fixture (
               fixture_id TEXT PRIMARY KEY, home_team TEXT, away_team TEXT,
               kickoff_time TEXT, kickoff_date TEXT, league_id TEXT,
               tournament_name TEXT, scraped_at TEXT)"""
    )
    con.execute(
        """CREATE TABLE market (
               market_id TEXT PRIMARY KEY, fixture_id TEXT, market_name TEXT,
               selection_name TEXT, raw_odds REAL, prop_player TEXT,
               prop_type TEXT, prop_line REAL, scraped_at TEXT)"""
    )
    now = datetime.datetime.now(datetime.timezone.utc)
    con.execute(
        "INSERT INTO fixture (fixture_id, home_team, away_team, kickoff_time, scraped_at) "
        "VALUES (?,?,?,?,?)",
        ("1", "Arsenal", "Chelsea", now.isoformat(), now.isoformat()),
    )
    con.execute(
        "INSERT INTO market (market_id, fixture_id, market_name, selection_name, raw_odds) "
        "VALUES (?,?,?,?,?)",
        ("m1", "1", "Match Result", "Arsenal", 2.10),
    )
    con.commit()
    con.close()
    monkeypatch.setattr(lpd, "DATA_DIR", str(d))
    return d


@pytest.fixture
def no_kambi(monkeypatch):
    monkeypatch.setattr(kambi, "fetch_kambi_1x2", lambda: {})


@pytest.fixture
def with_kambi(monkeypatch):
    """Kambi covers Arsenal vs Chelsea, freshly fetched."""
    monkeypatch.setattr(
        kambi,
        "fetch_kambi_1x2",
        lambda: {
            "Arsenal vs Chelsea": {
                "home_team": "Arsenal",
                "away_team": "Chelsea",
                "home": 2.10,
                "draw": 3.40,
                "away": 3.60,
            }
        },
    )
    monkeypatch.setattr(kambi, "cache_age_min", lambda: 0.5)


# ---------------------------------------------------------------------------
# the leak
# ---------------------------------------------------------------------------


def test_kambi_priced_fixture_is_not_marked_stale(data_dir, with_kambi, monkeypatch):
    """The bug: a live-API price inherited the previous fixture's staleness."""
    monkeypatch.setattr(lpd, "_betarabia_odds_age_min", STALE, raising=False)

    odds = lpd.find_betarabia_odds("Arsenal", "Chelsea")

    assert odds and odds["1X2"]["Home"] == 2.10, "Kambi should have served this"
    age = lpd._betarabia_odds_age_min
    assert age != STALE, "stale value from a previous fixture leaked through"
    assert age is None or age <= 60, f"Kambi-priced fixture reported as {age} min old"


def test_kambi_age_comes_from_its_own_cache(data_dir, with_kambi, monkeypatch):
    monkeypatch.setattr(lpd, "_betarabia_odds_age_min", STALE, raising=False)
    lpd.find_betarabia_odds("Arsenal", "Chelsea")
    assert lpd._betarabia_odds_age_min == pytest.approx(0.5)


def test_no_match_does_not_leave_the_previous_fixtures_age(data_dir, no_kambi, monkeypatch):
    """An unmatched fixture must not inherit the last one's freshness either."""
    monkeypatch.setattr(lpd, "_betarabia_odds_age_min", STALE, raising=False)
    lpd.find_betarabia_odds("Nonexistent United", "Nowhere City")
    assert lpd._betarabia_odds_age_min != STALE


def test_missing_db_does_not_leave_a_stale_age(tmp_path, no_kambi, monkeypatch):
    monkeypatch.setattr(lpd, "DATA_DIR", str(tmp_path / "nope"))
    monkeypatch.setattr(lpd, "_betarabia_odds_age_min", STALE, raising=False)
    lpd.find_betarabia_odds("Arsenal", "Chelsea")
    assert lpd._betarabia_odds_age_min != STALE


# ---------------------------------------------------------------------------
# the Betarabia branch must keep working exactly as before
# ---------------------------------------------------------------------------


def test_betarabia_branch_still_reports_real_age(data_dir, no_kambi, monkeypatch):
    monkeypatch.setattr(lpd, "_betarabia_odds_age_min", STALE, raising=False)
    odds = lpd.find_betarabia_odds("Arsenal", "Chelsea")
    assert odds is not None
    age = lpd._betarabia_odds_age_min
    assert age is not None and age < 5, f"freshly scraped fixture reported {age} min old"


def test_betarabia_branch_flags_genuinely_old_odds(data_dir, no_kambi, monkeypatch):
    old = (
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=12)
    ).isoformat()
    con = sqlite3.connect(str(data_dir / "odds_stream.db"))
    con.execute("UPDATE fixture SET scraped_at=? WHERE fixture_id='1'", (old,))
    con.commit()
    con.close()

    lpd.find_betarabia_odds("Arsenal", "Chelsea")
    age = lpd._betarabia_odds_age_min
    assert age is not None and age > 60, "a 12h-old scrape must still be caught"


# ---------------------------------------------------------------------------
# kambi cache age helper
# ---------------------------------------------------------------------------


def test_kambi_cache_age_is_none_before_any_fetch(monkeypatch):
    monkeypatch.setattr(kambi, "_cache", {"ts": 0.0, "data": {}})
    assert kambi.cache_age_min() is None


def test_kambi_cache_age_tracks_the_fetch_time(monkeypatch):
    import time as _t

    monkeypatch.setattr(kambi, "_cache", {"ts": _t.time() - 120, "data": {"x": 1}})
    assert kambi.cache_age_min() == pytest.approx(2.0, abs=0.1)


def test_kambi_cache_age_stays_inside_the_staleness_gate(monkeypatch):
    """Kambi's own TTL is 90s, so it can never legitimately look stale."""
    assert kambi._TTL / 60.0 < 60
