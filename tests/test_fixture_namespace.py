"""fixture_id namespace stamping.

fixture_id was never one id space. Across the verified record: Sofascore
(14-17M) 2451 bets, Betarabia/Kickertech (27-29M) 522, synthetic md5 8-digit
370, non-numeric 95, ESPN 44. Nothing recorded WHICH space an id came from, so
a result keyed by one source's id could never be joined to a bet placed from
another's — every non-Sofascore namespace sat at 0.0% fid-direct settlement.

Worse, the Betarabia fallback builders threw away the real Kickertech event id
(which odds_stream.db already stores) and minted an md5 of "Home vs Away"
instead — an id that by construction can never join to anything.

These tests pin: real ids are preferred over synthetic ones, and every fixture
dict declares its namespace.
"""

import datetime
import importlib
import sqlite3

import pytest

fr = importlib.import_module("src.fixture_results")


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """tmp DATA_DIR with an odds_stream.db carrying real Kickertech ids."""
    d = tmp_path / "data"
    d.mkdir()
    con = sqlite3.connect(str(d / "odds_stream.db"))
    con.execute(
        """CREATE TABLE fixture (
               fixture_id TEXT PRIMARY KEY, home_team TEXT, away_team TEXT,
               kickoff_time TEXT, kickoff_date TEXT, league_id TEXT,
               tournament_name TEXT, scraped_at TEXT)"""
    )
    future = (
        datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)
    ).isoformat()
    con.execute(
        "INSERT INTO fixture (fixture_id, home_team, away_team, kickoff_time, tournament_name) "
        "VALUES (?,?,?,?,?)",
        ("28647082", "Arsenal", "Chelsea", future, "Premier League"),
    )
    con.commit()
    con.close()

    lpd = importlib.import_module("src.live_predictions_daemon")
    monkeypatch.setattr(lpd, "DATA_DIR", str(d))
    return lpd


# ---------------------------------------------------------------------------
# the real Kickertech id must survive
# ---------------------------------------------------------------------------


def test_fetch_betarabia_odds_returns_the_real_fixture_id(data_dir):
    matches, _ = data_dir.fetch_betarabia_odds()
    assert matches["Arsenal vs Chelsea"]["fixture_id"] == "28647082"


def test_fetch_betarabia_odds_keeps_its_existing_fields(data_dir):
    """Additive change only — kickoff/league/status contracts must not move."""
    info = data_dir.fetch_betarabia_odds()[0]["Arsenal vs Chelsea"]
    assert info["league"] == "Premier League"
    assert info["status"] == "NS"
    assert info["kickoff"] is not None


def test_betarabia_fallback_uses_the_real_id_not_an_md5(data_dir, monkeypatch):
    fsm = importlib.import_module("src.free_scraper_module")
    monkeypatch.setattr(fsm, "DATA_DIR", str(data_dir.DATA_DIR), raising=False)
    fixtures = fsm._betarabia_fixture_fallback()
    assert len(fixtures) == 1
    assert str(fixtures[0]["fixture"]["id"]) == "28647082"


def test_betarabia_fallback_stamps_the_betarabia_namespace(data_dir, monkeypatch):
    fsm = importlib.import_module("src.free_scraper_module")
    fixtures = fsm._betarabia_fixture_fallback()
    assert fixtures[0]["fixture_ns"] == fr.NS_BETARABIA


def test_betarabia_fallback_falls_back_to_synthetic_when_id_is_missing(
    data_dir, monkeypatch
):
    """No id in odds_stream.db -> synthetic, but clearly labelled as such."""
    def _no_ids():
        return {"X vs Y": {"kickoff": None, "league": "L", "status": "NS"}}, None

    fsm = importlib.import_module("src.free_scraper_module")
    monkeypatch.setattr(data_dir, "fetch_betarabia_odds", _no_ids)
    fixtures = fsm._betarabia_fixture_fallback()
    assert fixtures[0]["fixture_ns"] == fr.synthetic_ns(fr.NS_BETARABIA)
    assert fixtures[0]["fixture"]["id"]


# ---------------------------------------------------------------------------
# the other sources must declare their namespace too
# ---------------------------------------------------------------------------


def test_sofascore_event_with_a_real_id_is_stamped_sofascore():
    sps = importlib.import_module("src.sofascore_patchright_scraper")
    ev = {
        "id": 16512229,
        "homeTeam": {"name": "Arsenal"},
        "awayTeam": {"name": "Chelsea"},
        "startTimestamp": 1787058000,
        "tournament": {"name": "EPL"},
        "status": {"type": "notstarted"},
    }
    out = sps._parse_event(ev)
    assert out is not None
    assert out["fixture_ns"] == fr.NS_SOFASCORE
    assert out["fixture"]["id"] == 16512229


def test_sofascore_event_without_an_id_is_stamped_synthetic():
    sps = importlib.import_module("src.sofascore_patchright_scraper")
    ev = {
        "homeTeam": {"name": "Arsenal"},
        "awayTeam": {"name": "Chelsea"},
        "startTimestamp": 1787058000,
        "tournament": {"name": "EPL"},
        "status": {"type": "notstarted"},
    }
    out = sps._parse_event(ev)
    assert out is not None
    assert out["fixture_ns"] == fr.synthetic_ns(fr.NS_SOFASCORE)


def test_namespaces_are_distinct_strings():
    """A synthetic id must never be mistaken for a real one."""
    assert fr.synthetic_ns(fr.NS_SOFASCORE) != fr.NS_SOFASCORE
    assert fr.synthetic_ns(fr.NS_BETARABIA) != fr.NS_BETARABIA
    assert len({fr.NS_SOFASCORE, fr.NS_ESPN, fr.NS_BETARABIA, fr.NS_UNKNOWN}) == 4
