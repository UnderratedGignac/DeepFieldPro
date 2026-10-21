"""Kambi (Unibet) Over/Under 2.5 as a second price source, best price wins.

Betarabia only carried O/U for the ~50 fixtures its scraper could open per run;
Kambi publishes full-time totals for every pre-match event it lists. Each O/U
side now takes the better of the two books, and the bet records WHICH book the
price came from — a Kambi price is only real at a Kambi-powered bookmaker.

Kambi detail: full-time totals are criterion 1001159926 ("Total Goals");
first-half (1001159532) and team totals use other criteria. Lines and odds are
in thousandths (line 2500 = 2.5, odds 1900 = 1.90). The listView feed only
carries 1X2, so totals come from betoffer/event/{id,id,...}.json in batches,
pre-match events only (the feed also lists in-play events).
"""

import datetime
import importlib
import sqlite3
import time

import pytest

kambi = importlib.import_module("src.kambi_scraper")
lpd = importlib.import_module("src.live_predictions_daemon")
alerting = importlib.import_module("src.services.alerting")

FT_TOTAL, HT_TOTAL, TEAM_TOTAL = 1001159926, 1001159532, 1001159967


def _ou_offer(event_id, crit, line, over, under):
    return {
        "eventId": event_id,
        "criterion": {"id": crit, "label": "Total Goals"},
        "outcomes": [
            {"label": "Over", "type": "OT_OVER", "line": line, "odds": over},
            {"label": "Under", "type": "OT_UNDER", "line": line, "odds": under},
        ],
    }


# ---------------------------------------------------------------------------
# kambi_scraper: parse and fetch
# ---------------------------------------------------------------------------


def test_parse_keeps_only_the_full_time_25_line():
    offers = [
        _ou_offer(1, FT_TOTAL, 1500, 1250, 3700),
        _ou_offer(1, FT_TOTAL, 2500, 1900, 1950),
        _ou_offer(1, HT_TOTAL, 2500, 4100, 1200),
        _ou_offer(1, TEAM_TOTAL, 2500, 3300, 1300),
        _ou_offer(2, FT_TOTAL, 3500, 3000, 1350),
    ]
    assert kambi.parse_ou25(offers) == {1: {"over": 1.9, "under": 1.95}}


class _Resp:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_listview_rows_carry_event_id_and_state(monkeypatch):
    feed = {
        "events": [
            {
                "event": {"id": 77, "homeName": "Arsenal", "awayName": "Chelsea",
                          "start": "2026-10-21T19:00:00Z", "group": "Premier League",
                          "state": "NOT_STARTED"},
                "betOffers": [{"criterion": {"label": "Full Time"}, "outcomes": [
                    {"type": "OT_ONE", "odds": 2100}, {"type": "OT_CROSS", "odds": 3400},
                    {"type": "OT_TWO", "odds": 3600}]}],
            }
        ]
    }
    monkeypatch.setattr(kambi.requests, "get", lambda *a, **k: _Resp(feed))
    monkeypatch.setitem(kambi._cache, "ts", 0.0)
    monkeypatch.setitem(kambi._cache, "data", {})

    row = kambi.fetch_kambi_1x2()["Arsenal vs Chelsea"]
    assert row["event_id"] == 77 and row["state"] == "NOT_STARTED"


def test_fetch_ou25_queries_pre_match_events_only(monkeypatch):
    soon = time.time() + 3600
    monkeypatch.setattr(
        kambi,
        "fetch_kambi_1x2",
        lambda: {
            "Arsenal vs Chelsea": {"event_id": 1, "state": "NOT_STARTED", "starts_ts": soon,
                                   "home_team": "Arsenal", "away_team": "Chelsea", "league": "PL"},
            "Lyon vs Nice": {"event_id": 2, "state": "STARTED", "starts_ts": soon - 7200,
                             "home_team": "Lyon", "away_team": "Nice", "league": "L1"},
        },
    )
    asked = []

    def _get(url, **_kw):
        asked.append(url)
        return _Resp({"betOffers": [_ou_offer(1, FT_TOTAL, 2500, 1900, 1950),
                                    _ou_offer(2, FT_TOTAL, 2500, 1100, 6000)]})

    monkeypatch.setattr(kambi.requests, "get", _get)
    monkeypatch.setitem(kambi._ou_cache, "ts", 0.0)
    monkeypatch.setitem(kambi._ou_cache, "data", {})

    out = kambi.fetch_kambi_ou25()

    assert list(out) == ["Arsenal vs Chelsea"]
    assert out["Arsenal vs Chelsea"]["over"] == 1.9
    assert len(asked) == 1 and "/betoffer/event/1.json" in asked[0]


@pytest.fixture
def two_events(monkeypatch):
    soon = time.time() + 3600
    monkeypatch.setattr(
        kambi,
        "fetch_kambi_1x2",
        lambda: {
            "Bayern Munich vs Arsenal": {"event_id": 1, "state": "NOT_STARTED", "starts_ts": soon,
                                         "home_team": "Bayern Munich", "away_team": "Arsenal", "league": "CL"},
            "Real Madrid vs RB Leipzig": {"event_id": 2, "state": "NOT_STARTED", "starts_ts": soon,
                                          "home_team": "Real Madrid", "away_team": "RB Leipzig", "league": "CL"},
        },
    )
    monkeypatch.setitem(kambi._ou_cache, "ts", 0.0)
    monkeypatch.setitem(kambi._ou_cache, "data", {})


def test_requests_over_under_offers_only(two_events, monkeypatch):
    """Unfiltered, one batch of big matches held 8182 offers; type=6 keeps O/U only."""
    asked = []

    def _get(url, **_kw):
        asked.append(url)
        return _Resp({"betOffers": [_ou_offer(1, FT_TOTAL, 2500, 1550, 2450)]})

    monkeypatch.setattr(kambi.requests, "get", _get)
    kambi.fetch_kambi_ou25()
    assert asked and all("type=6" in u for u in asked)


def test_follows_range_pages_until_total(two_events, monkeypatch):
    """Replies stop at a page cap; an event on page 2 must not be dropped.

    On 2026-10-21 the senior Bayern vs Arsenal and Real Madrid vs Leipzig 2.5
    lines sat past the first 2000 offers and never reached the bet gate.
    """
    def _get(url, **_kw):
        if "range_start=1" in url:
            return _Resp({"betOffers": [_ou_offer(2, FT_TOTAL, 2500, 1180, 4900)],
                          "range": {"start": 1, "size": 1, "total": 2}})
        return _Resp({"betOffers": [_ou_offer(1, FT_TOTAL, 2500, 1550, 2450)],
                      "range": {"start": 0, "size": 1, "total": 2}})

    monkeypatch.setattr(kambi.requests, "get", _get)
    out = kambi.fetch_kambi_ou25()
    assert set(out) == {"Bayern Munich vs Arsenal", "Real Madrid vs RB Leipzig"}
    assert out["Real Madrid vs RB Leipzig"]["under"] == 4.9


# ---------------------------------------------------------------------------
# daemon: best price across books, with the book recorded
# ---------------------------------------------------------------------------

KAMBI_AGE, KAMBI_OU_AGE = 0.5, 2.0


def _stream_db(data_dir, scraped_at, markets):
    con = sqlite3.connect(str(data_dir / "odds_stream.db"))
    con.execute(
        "CREATE TABLE fixture (fixture_id TEXT PRIMARY KEY, home_team TEXT, away_team TEXT, "
        "kickoff_time TEXT, kickoff_date TEXT, league_id TEXT, tournament_name TEXT, scraped_at TEXT)"
    )
    con.execute(
        "CREATE TABLE market (market_id TEXT PRIMARY KEY, fixture_id TEXT, market_name TEXT, "
        "selection_name TEXT, raw_odds REAL, prop_player TEXT, prop_type TEXT, prop_line REAL, scraped_at TEXT)"
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


def _now(minus_hours=0.0):
    return (datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(hours=minus_hours)).isoformat()


@pytest.fixture
def books(tmp_path, monkeypatch):
    d = tmp_path / "data"
    d.mkdir()
    monkeypatch.setattr(lpd, "DATA_DIR", str(d))
    monkeypatch.setattr(kambi, "fetch_kambi_1x2", lambda: {
        "Arsenal vs Chelsea": {"home_team": "Arsenal", "away_team": "Chelsea",
                               "home": 2.10, "draw": 3.40, "away": 3.60}})
    monkeypatch.setattr(kambi, "cache_age_min", lambda: KAMBI_AGE)
    monkeypatch.setattr(kambi, "fetch_kambi_ou25", lambda: {
        "Arsenal vs Chelsea": {"home_team": "Arsenal", "away_team": "Chelsea",
                               "over": 2.05, "under": 1.80}})
    monkeypatch.setattr(kambi, "ou_cache_age_min", lambda: KAMBI_OU_AGE)
    return d


BETARABIA_OU = [("Total Goals", "Total OVER  2.5", 1.90), ("Total Goals", "Total UNDER  2.5", 1.95)]


def test_each_side_takes_the_better_book(books):
    _stream_db(books, _now(), BETARABIA_OU)
    odds = lpd.find_betarabia_odds("Arsenal", "Chelsea")
    assert odds["Over/Under 2.5"] == {"Over": 2.05, "Under": 1.95}
    assert odds.books[("Over/Under 2.5", "Over")] == "Kambi"
    assert odds.books[("Over/Under 2.5", "Under")] == "Betarabia"
    assert odds.books[("1X2", "Home")] == "Kambi"


def test_kambi_alone_prices_over_under_when_betarabia_lacks_the_match(books):
    _stream_db(books, _now(), [])  # Betarabia lists the fixture, no markets
    odds = lpd.find_betarabia_odds("Arsenal", "Chelsea")
    assert odds["Over/Under 2.5"] == {"Over": 2.05, "Under": 1.80}
    assert lpd._betarabia_odds_age_min == pytest.approx(KAMBI_OU_AGE)


def test_stale_betarabia_price_still_flags_stale(books):
    """A 12h-old Betarabia Under in the mix must not pass as fresh."""
    _stream_db(books, _now(minus_hours=12), BETARABIA_OU)
    lpd.find_betarabia_odds("Arsenal", "Chelsea")
    assert lpd._betarabia_odds_age_min > 60


# ---------------------------------------------------------------------------
# the bet row and the alert name the bookmaker
# ---------------------------------------------------------------------------


@pytest.fixture
def bet_env(tmp_path, monkeypatch):
    d = tmp_path / "data"
    d.mkdir()
    con = sqlite3.connect(str(d / "bet_log.db"))
    con.execute(
        "CREATE TABLE bet_log (bet_id TEXT, match_id TEXT, player_id TEXT, market_type TEXT, "
        "entry_odds REAL, fair_odds REAL, edge_pct REAL, stake REAL, result TEXT, pnl REAL, "
        "placed_at TEXT, bet_source TEXT, is_recommended INT, line REAL, side TEXT, "
        "fixture_id TEXT, league TEXT, kickoff_time TEXT, fixture_ns TEXT, book TEXT)"
    )
    con.commit()
    con.close()
    monkeypatch.setattr(lpd, "DATA_DIR", str(d))
    monkeypatch.setattr(lpd, "load_settings", lambda: {
        "model_predictions_disabled": False, "ai_real_staking_enabled": False})
    monkeypatch.setattr(lpd, "_CLV_TRACKER_OK", False)
    sent = []
    monkeypatch.setattr(alerting.notifier, "_notify", lambda msg, **kw: sent.append(msg))
    return d, sent


def test_bet_row_records_the_book(bet_env):
    d, _ = bet_env
    lpd.log_ai_bet("Arsenal vs Chelsea", "Over/Under 2.5", "Over 2.5", 2.05, 55.0, 0.10,
                   fixture_id=1, league="PL", source="MODEL_VALUE_ALIGN", book="Kambi")
    con = sqlite3.connect(str(d / "bet_log.db"))
    assert con.execute("SELECT book FROM bet_log").fetchone()[0] == "Kambi"
    con.close()


def test_alert_names_the_book_to_bet_at(bet_env):
    _, sent = bet_env
    lpd.log_ai_bet("Arsenal vs Chelsea", "Over/Under 2.5", "Over 2.5", 2.05, 55.0, 0.10,
                   fixture_id=1, league="PL", source="MODEL_VALUE_ALIGN", book="Kambi")
    assert sent and "(Kambi)" in sent[0] and "Betarabia" not in sent[0]
