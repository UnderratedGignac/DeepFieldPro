"""A Pinnacle price must belong to the same match, not just the same names.

Two collisions produced 1X2 "edges" of +16% to +104% on 2026-10-21:

1. Pinnacle lists youth games under the senior team names; only the league
   says so ("UEFA - Youth League U19", "Mexico - U21 League"). The senior
   Bayern Munich vs Arsenal (19:00) shared sharp_odds_history rows with the
   U19 game (14:00), and the "latest" price was the U19 one. Fix at the
   source: youth participants carry the league's level ("Bayern Munich U19"),
   and a lookup given a kickoff only accepts rows starting within 3h of it.
2. Fuzzy pair resolution scored the whole "home vs away" string, so
   "Independiente Santa Fe vs Once Caldas" resolved to Santa Fe vs
   Corinthians on the strength of the long home name. Each side must now
   match on its own.
"""

import datetime
import importlib
import sqlite3
import time

import pytest

pf = importlib.import_module("src.pinnacle_feed")
pv = importlib.import_module("tools.pinnacle_value")

SENIOR_KO = time.time() + 6 * 3600
YOUTH_KO = time.time() + 1 * 3600


def _iso(ts):
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _matchup(mid, league, ko):
    return {
        "id": mid, "type": "matchup", "units": "Regular", "startTime": _iso(ko),
        "league": {"name": league},
        "participants": [{"alignment": "home", "name": "Bayern Munich"},
                         {"alignment": "away", "name": "Arsenal"}],
    }


@pytest.fixture
def feed(monkeypatch):
    matchups = [_matchup(1, "UEFA - Champions League", SENIOR_KO),
                _matchup(2, "UEFA - Youth League U19", YOUTH_KO)]
    markets = [
        {"matchupId": 1, "type": "moneyline", "period": 0, "prices": [
            {"designation": "home", "price": 126}, {"designation": "draw", "price": 282},
            {"designation": "away", "price": 210}]},
        {"matchupId": 2, "type": "moneyline", "period": 0, "prices": [
            {"designation": "home", "price": -149}, {"designation": "draw", "price": 381},
            {"designation": "away", "price": 249}]},
        {"matchupId": 1, "type": "total", "period": 0, "key": "s;0;ou;2.5", "prices": [
            {"designation": "over", "points": 2.5, "price": -170},
            {"designation": "under", "points": 2.5, "price": 147}]},
        {"matchupId": 2, "type": "total", "period": 0, "key": "s;0;ou;2.5", "prices": [
            {"designation": "over", "points": 2.5, "price": -250},
            {"designation": "under", "points": 2.5, "price": 200}]},
    ]
    monkeypatch.setattr(pf, "_get_cached",
                        lambda path, params=None, timeout=15: matchups if path.endswith("/matchups") else markets)


def test_1x2_snapshot_labels_youth_teams_from_the_league(feed):
    keys = {r["match_key"] for r in pf.fetch_1x2_snapshot()}
    assert keys == {"Bayern Munich vs Arsenal", "Bayern Munich U19 vs Arsenal U19"}


def test_totals_keep_senior_and_youth_apart(feed):
    tot = pf.fetch_pinnacle_totals(line=2.5)
    assert set(tot) == {"Bayern Munich vs Arsenal", "Bayern Munich U19 vs Arsenal U19"}
    assert tot["Bayern Munich vs Arsenal"]["starts_ts"] == pytest.approx(SENIOR_KO, abs=1)


@pytest.fixture
def history(tmp_path, monkeypatch):
    db = tmp_path / "completed_fixtures.db"
    con = sqlite3.connect(str(db))
    con.execute(
        "CREATE TABLE sharp_odds_history (match_key TEXT, home_team TEXT, away_team TEXT, league TEXT, "
        "selection TEXT, decimal_odds REAL, devig_prob REAL, ts REAL, starts_ts REAL)"
    )
    now = time.time()
    rows = []
    for i in range(12):  # senior: older snapshots
        rows.append(("Bayern Munich vs Arsenal", "Bayern Munich", "Arsenal", "CL", "home", 2.26, 0.43, now - 600 + i, SENIOR_KO))
    for i in range(12):  # legacy un-labelled U19 rows: newer
        rows.append(("Bayern Munich vs Arsenal", "Bayern Munich", "Arsenal", "U19", "home", 1.67, 0.55, now - 60 + i, YOUTH_KO))
    con.executemany("INSERT INTO sharp_odds_history VALUES (?,?,?,?,?,?,?,?,?)", rows)
    con.commit()
    con.close()
    monkeypatch.setattr(pv, "_COMPLETED_DB", str(db))


def test_latest_price_belongs_to_the_fixtures_kickoff(history):
    p = pv.get_pinnacle_latest("Bayern Munich", "Arsenal", "Home (1)", kickoff_ts=_iso(SENIOR_KO))
    assert p["decimal_odds"] == 2.26


def test_pair_resolution_requires_both_teams(monkeypatch):
    monkeypatch.setitem(pv._PIN_PAIRS_CACHE, "ts", time.time())
    monkeypatch.setitem(pv._PIN_PAIRS_CACHE, "pairs", [
        ("Independiente Santa Fe", "Corinthians"),
        ("Internazionale", "Shakhtar Donetsk"),
        ("Alo Egypt", "Al Qanater Al Khayreyah"),
    ])
    assert pv._fuzzy_resolve_pair("Independiente Santa Fe", "Once Caldas Manizales") is None
    assert pv._fuzzy_resolve_pair("Inter Milan", "Shakhtar Donetsk") == ("Internazionale", "Shakhtar Donetsk")
    assert pv._fuzzy_resolve_pair("Alo Egypt", "Al Qanater") == ("Alo Egypt", "Al Qanater Al Khayreyah")


def test_ou25_match_requires_both_teams():
    cands = {"Independiente Santa Fe vs Corinthians": {"p_over": 0.5}}
    assert pv._fuzzy_match_ou25("Independiente Santa Fe", "Once Caldas Manizales", cands) is None


def test_ou25_for_fixture_rejects_a_same_name_game_at_another_kickoff():
    cands = {"Bayern Munich vs Arsenal": {"p_over": 0.71, "starts_ts": YOUTH_KO}}
    assert pv.ou25_for_fixture("Bayern Munich", "Arsenal", _iso(SENIOR_KO), cands) is None
    cands["Bayern Munich vs Arsenal"]["starts_ts"] = SENIOR_KO
    assert pv.ou25_for_fixture("Bayern Munich", "Arsenal", _iso(SENIOR_KO), cands)["p_over"] == 0.71
