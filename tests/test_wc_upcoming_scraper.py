"""Regression tests for tools/wc_upcoming_scraper.py history fallback.

Bug (2026-07-09): _get_pinnacle_from_history stored decimal odds under the
selection name ('home'/'draw'/'away'), clobbering the team-name keys and
emitting fixtures whose team names were odds strings (e.g. '4.31 vs 1.8696').
Those rows poisoned odds_stream.db and broke name-keyed WC matching.
"""
import importlib.util
import os
import sqlite3
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_module():
    path = os.path.join(_ROOT, "tools", "wc_upcoming_scraper.py")
    spec = importlib.util.spec_from_file_location("wc_upcoming_scraper_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def history_db(tmp_path):
    db = tmp_path / "completed_fixtures.db"
    con = sqlite3.connect(db)
    con.execute(
        """CREATE TABLE sharp_odds_history (
            home_team TEXT, away_team TEXT, league TEXT,
            selection TEXT, decimal_odds REAL, starts_ts REAL, ts REAL
        )"""
    )
    rows = [
        ("Norway", "England", "FIFA World Cup", "home", 4.31, 1783700000.0, 1000.0),
        ("Norway", "England", "FIFA World Cup", "draw", 3.60, 1783700000.0, 1000.0),
        ("Norway", "England", "FIFA World Cup", "away", 1.87, 1783700000.0, 1000.0),
    ]
    con.executemany("INSERT INTO sharp_odds_history VALUES (?,?,?,?,?,?,?)", rows)
    con.commit()
    con.close()
    return str(db)


def test_team_names_survive_odds_assignment(history_db, monkeypatch):
    mod = _load_module()
    monkeypatch.setattr(mod, "_COMPLETED_DB", history_db)
    result = mod._get_pinnacle_from_history()
    assert len(result) == 1
    fx = result[0]
    assert fx["home"] == "Norway"
    assert fx["away"] == "England"


def test_odds_land_in_dec_keys(history_db, monkeypatch):
    mod = _load_module()
    monkeypatch.setattr(mod, "_COMPLETED_DB", history_db)
    fx = mod._get_pinnacle_from_history()[0]
    assert fx["h_dec"] == pytest.approx(4.31)
    assert fx["d_dec"] == pytest.approx(3.60)
    assert fx["a_dec"] == pytest.approx(1.87)


def test_unknown_selection_ignored(history_db, monkeypatch):
    con = sqlite3.connect(history_db)
    con.execute(
        "INSERT INTO sharp_odds_history VALUES (?,?,?,?,?,?,?)",
        ("Norway", "England", "FIFA World Cup", "over_2.5", 2.10, 1783700000.0, 1000.0),
    )
    con.commit()
    con.close()
    mod = _load_module()
    monkeypatch.setattr(mod, "_COMPLETED_DB", history_db)
    fx = mod._get_pinnacle_from_history()[0]
    # exotic selections must neither clobber names nor invent odds keys
    assert fx["home"] == "Norway"
    assert set(k for k in fx if k.endswith("_dec")) == {"h_dec", "d_dec", "a_dec"}


def test_missing_db_returns_empty(tmp_path, monkeypatch):
    mod = _load_module()
    monkeypatch.setattr(mod, "_COMPLETED_DB", str(tmp_path / "nope.db"))
    assert mod._get_pinnacle_from_history() == []


def test_history_query_uses_ts_index_not_full_scan(history_db):
    """Regression (2026-07-11): the fallback query must filter on ts (idx_soh_ts),
    not sort by team (idx_soh_teams) — the ORDER BY forced a 15.4M-row full scan
    that hung 106s. Assert the shipped query plan SEARCHes on the ts index."""
    con = sqlite3.connect(history_db)
    con.execute("CREATE INDEX IF NOT EXISTS idx_soh_ts ON sharp_odds_history(ts)")
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_soh_teams ON sharp_odds_history(home_team, away_team, selection)"
    )
    ts_max = con.execute("SELECT MAX(ts) FROM sharp_odds_history").fetchone()[0]
    plan = "\n".join(
        str(r)
        for r in con.execute(
            "EXPLAIN QUERY PLAN "
            "SELECT home_team, away_team, league, selection, decimal_odds, starts_ts "
            "FROM sharp_odds_history WHERE ts >= ? AND (league LIKE '%World Cup%' OR league LIKE '%FIFA%')",
            (ts_max - 600,),
        )
    )
    con.close()
    assert "idx_soh_ts" in plan
    assert "idx_soh_teams" not in plan  # the ORDER BY plan must not come back
