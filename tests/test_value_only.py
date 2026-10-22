"""VALUE_ONLY: bet any price that beats Pinnacle's fair price, no model check.

1X2 and Over/Under 2.5, best price across Betarabia and Kambi, draws allowed
(the draw exclusion protects the model, and this strategy has no model). It
keeps its own switch, dedup and ledger (bet_source='VALUE_ONLY'), its own edge
cap, and records which bookmaker each price came from — a Kambi price is only
real at a Kambi-powered book.
"""

import datetime
import importlib
import sqlite3

import pytest

lpd = importlib.import_module("src.live_predictions_daemon")
kambi = importlib.import_module("src.kambi_scraper")
bt = importlib.import_module("src.bankroll_tracker")
alerting = importlib.import_module("src.services.alerting")


# ---------------------------------------------------------------------------
# 1X2 best price across books
# ---------------------------------------------------------------------------


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
                    "VALUES (?, '1', 'Match Result', ?, ?)",
                    [("m1", "Arsenal", 2.20), ("m2", "X", 3.30), ("m3", "Chelsea", 3.50)])
    con.commit()
    con.close()
    monkeypatch.setattr(lpd, "DATA_DIR", str(d))
    monkeypatch.setattr(kambi, "fetch_kambi_1x2", lambda: {"Arsenal vs Chelsea": {
        "home_team": "Arsenal", "away_team": "Chelsea", "home": 2.10, "draw": 3.40, "away": 3.60}})
    monkeypatch.setattr(kambi, "cache_age_min", lambda: 0.5)
    monkeypatch.setattr(kambi, "fetch_kambi_ou25", lambda: {})


def test_1x2_takes_the_better_price_from_either_book(books):
    odds = lpd.find_betarabia_odds("Arsenal", "Chelsea")
    assert odds["1X2"] == {"Home": 2.20, "Draw": 3.40, "Away": 3.60}
    assert odds.books[("1X2", "Home")] == "Betarabia"
    assert odds.books[("1X2", "Draw")] == "Kambi"


# ---------------------------------------------------------------------------
# the VALUE_ONLY bet logger
# ---------------------------------------------------------------------------

BASE_SETTINGS = {"value_only_betting_enabled": True, "pinnacle_value_betting_enabled": False,
                 "value_only_max_edge_pct": 15.0, "stake_min": 1.0, "stake_max": 5.0}


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    d = tmp_path / "data"
    d.mkdir()
    con = sqlite3.connect(str(d / "bet_log.db"))
    con.execute(
        "CREATE TABLE bet_log (bet_id TEXT, match_id TEXT, player_id TEXT, market_type TEXT, entry_odds REAL, "
        "fair_odds REAL, edge_pct REAL, stake REAL, result TEXT, pnl REAL, placed_at TEXT, bet_source TEXT, "
        "is_recommended INT, line REAL, side TEXT, fixture_id TEXT, league TEXT, best_odds REAL, best_book TEXT)"
    )
    con.commit()
    con.close()
    monkeypatch.setattr(lpd, "DATA_DIR", str(d))
    settings = dict(BASE_SETTINGS)
    monkeypatch.setattr(lpd, "load_settings", lambda: settings)
    monkeypatch.setattr(bt, "register_bet", lambda stake, db_path=None: True)
    sent = []
    monkeypatch.setattr(alerting.notifier, "_notify", lambda msg, **kw: sent.append(msg))
    return d, settings, sent


def _bet(**kw):
    args = dict(match="Toluca vs Tijuana", market="1X2", selection="Draw (X)", odds=5.0,
                pinnacle_edge_pct=6.0, fixture_id=7, league="Liga MX",
                pinnacle_data={"fair_odds": 4.72}, bet_source="VALUE_ONLY", book="Kambi",
                fixture_ns="betarabia", kickoff_time="2026-10-22T01:00:00+00:00")
    args.update(kw)
    lpd.log_pinnacle_value_bet(**args)


def _rows(d):
    con = sqlite3.connect(str(d / "bet_log.db"))
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT * FROM bet_log")]
    con.close()
    return rows


def test_records_its_own_source_and_the_book(ledger):
    d, _, sent = ledger
    _bet()
    (row,) = _rows(d)
    assert row["bet_source"] == "VALUE_ONLY"
    assert row["book"] == "Kambi"
    assert row["fixture_ns"] == "betarabia"
    assert row["kickoff_time"] == "2026-10-22T01:00:00+00:00"
    assert sent and "(Kambi)" in sent[0] and "VALUE_ONLY" in sent[0]


def test_runs_on_its_own_switch(ledger):
    d, settings, _ = ledger
    settings["value_only_betting_enabled"] = False
    _bet()
    assert _rows(d) == []


def test_dedup_is_per_strategy(ledger):
    """An existing PINNACLE_VALUE bet must not block the separate VALUE_ONLY record."""
    d, _, _ = ledger
    con = sqlite3.connect(str(d / "bet_log.db"))
    con.execute("INSERT INTO bet_log (match_id, market_type, side, bet_source, result) "
                "VALUES ('Toluca vs Tijuana', '1X2', 'Draw (X)', 'PINNACLE_VALUE', 'OPEN')")
    con.commit()
    con.close()
    _bet()
    _bet()  # a repeat of its own bet is still deduped
    assert [r["bet_source"] for r in _rows(d)].count("VALUE_ONLY") == 1


def test_edge_above_its_cap_is_skipped(ledger):
    d, _, _ = ledger
    _bet(pinnacle_edge_pct=16.0)
    assert _rows(d) == []
