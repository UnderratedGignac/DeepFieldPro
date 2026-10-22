"""Both Teams To Score as a VALUE_ONLY market: Kambi + Betarabia prices vs Pinnacle.

Kambi publishes BTTS for its whole listing in one request (listView
category 11942, criterion 1001642858, outcomes OT_YES/OT_NO in thousandths);
the feed also lists in-play events and e-football ("Roma (Taz)"), which must
be dropped. Each BTTS side takes the better of Kambi and Betarabia, with the
book recorded. Pinnacle prices BTTS as a special keyed by the parent match's
names, so youth games collide with the senior match exactly like 1X2/O/U did;
the special's own league carries the level.
"""

import datetime
import importlib
import sqlite3
import time

import pytest

kambi = importlib.import_module("src.kambi_scraper")
lpd = importlib.import_module("src.live_predictions_daemon")
pf = importlib.import_module("src.pinnacle_feed")

SOON = time.time() + 3 * 3600


def _iso(ts):
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _kevent(eid, home, away, start, yes, no, state="NOT_STARTED", group="Premier League"):
    return {
        "event": {"id": eid, "homeName": home, "awayName": away, "start": _iso(start),
                  "state": state, "group": group},
        "betOffers": [{"criterion": {"id": 1001642858, "label": "Both Teams To Score"},
                       "outcomes": [{"label": "Yes", "type": "OT_YES", "odds": yes},
                                    {"label": "No", "type": "OT_NO", "odds": no}]}],
    }


def test_parse_btts_keeps_real_pre_match_events_only():
    events = [
        _kevent(1, "Arsenal", "Chelsea", SOON, 1720, 2100),
        _kevent(2, "Lyon", "Nice", SOON - 7200, 1500, 2500, state="STARTED"),
        _kevent(3, "Roma (Taz)", "Sassuolo (Pavlinho19)", SOON, 1800, 1900),
        _kevent(4, "Porto", "Benfica", SOON, None, 1900),  # suspended side
    ]
    out = kambi.parse_btts(events, now_ts=time.time())
    assert list(out) == ["Arsenal vs Chelsea"]
    assert (out["Arsenal vs Chelsea"]["yes"], out["Arsenal vs Chelsea"]["no"]) == (1.72, 2.1)


@pytest.fixture
def books(tmp_path, monkeypatch):
    d = tmp_path / "data"
    d.mkdir()
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    con = sqlite3.connect(str(d / "odds_stream.db"))
    con.execute("CREATE TABLE fixture (fixture_id TEXT, home_team TEXT, away_team TEXT, "
                "kickoff_time TEXT, kickoff_date TEXT, league_id TEXT, tournament_name TEXT, scraped_at TEXT)")
    con.execute("CREATE TABLE market (market_id TEXT, fixture_id TEXT, market_name TEXT, selection_name TEXT, "
                "raw_odds REAL, prop_player TEXT, prop_type TEXT, prop_line REAL, scraped_at TEXT)")
    con.execute("INSERT INTO fixture (fixture_id, home_team, away_team, kickoff_time, scraped_at) "
                "VALUES ('1','Arsenal','Chelsea',?,?)", (now, now))
    con.executemany("INSERT INTO market (market_id, fixture_id, market_name, selection_name, raw_odds) "
                    "VALUES (?, '1', 'Both teams to score', ?, ?)",
                    [("m1", "Both teams to score - YES", 1.80), ("m2", "Both teams to score - NO", 1.95)])
    con.commit()
    con.close()
    monkeypatch.setattr(lpd, "DATA_DIR", str(d))
    monkeypatch.setattr(kambi, "fetch_kambi_1x2", lambda: {})
    monkeypatch.setattr(kambi, "fetch_kambi_ou25", lambda: {})
    monkeypatch.setattr(kambi, "fetch_kambi_btts", lambda: {"Arsenal vs Chelsea": {
        "home_team": "Arsenal", "away_team": "Chelsea", "yes": 1.72, "no": 2.10}})
    monkeypatch.setattr(kambi, "btts_cache_age_min", lambda: 1.0)


def test_btts_takes_the_better_price_from_either_book(books):
    odds = lpd.find_betarabia_odds("Arsenal", "Chelsea")
    assert odds["BTTS"] == {"Yes": 1.80, "No": 2.10}
    assert odds.books[("BTTS", "Yes")] == "Betarabia"
    assert odds.books[("BTTS", "No")] == "Kambi"


def test_pinnacle_btts_labels_youth_games_from_the_league(monkeypatch):
    def special(sid, parent_id, league, start):
        return {"id": sid, "type": "special", "league": {"name": league},
                "special": {"description": "Both Teams To Score?"},
                "parent": {"id": parent_id, "startTime": _iso(start), "participants": [
                    {"alignment": "home", "name": "Bayern Munich"}, {"alignment": "away", "name": "Arsenal"}]},
                "participants": [{"id": sid * 10 + 1, "name": "Yes"}, {"id": sid * 10 + 2, "name": "No"}]}

    def ml(sid, yes, no):
        return {"matchupId": sid, "type": "moneyline", "period": 0, "prices": [
            {"participantId": sid * 10 + 1, "price": yes}, {"participantId": sid * 10 + 2, "price": no}]}

    matchups = [special(1, 100, "UEFA - Champions League", SOON),
                special(2, 200, "UEFA - Youth League U19", SOON - 2 * 3600)]
    markets = [ml(1, -130, 110), ml(2, -200, 160)]
    monkeypatch.setattr(pf, "_get_cached",
                        lambda path, params=None, timeout=15: matchups if path.endswith("/matchups") else markets)
    assert set(pf.fetch_pinnacle_btts()) == {"Bayern Munich vs Arsenal", "Bayern Munich U19 vs Arsenal U19"}
