"""Predictions must be found whether the fixture id arrives as str or int.

load_predictions_from_db() keys its map by int(fixture_id). Since 2026-08-24 the
Betarabia fixture fallback carries the real Kickertech id straight out of
odds_stream.db, which is a str ("30141288"). update_dashboard_json looked it up
with res_map.get(fid), got None for every Betarabia-sourced fixture, and so
never reached the bet gates: on 2026-10-21 all 163 dashboard fixtures had
prediction=None and the gate telemetry stayed empty while the daemon looked
healthy. The same miss made every cycle re-predict every fixture.

The map itself now normalises keys, so every lookup site agrees.
"""

import importlib
import json
import sqlite3

import pytest

lpd = importlib.import_module("src.live_predictions_daemon")


@pytest.fixture
def preds(tmp_path, monkeypatch):
    con = sqlite3.connect(str(tmp_path / "bet_log.db"))
    con.execute(
        "CREATE TABLE predictions (fixture_id TEXT PRIMARY KEY, match_name TEXT, "
        "league TEXT, kickoff TEXT, prediction TEXT, expected_score TEXT, "
        "home_prob REAL, draw_prob REAL, away_prob REAL, over_prob REAL, "
        "under_prob REAL, btts_yes_prob REAL, btts_no_prob REAL, has_lineup INTEGER, "
        "predicted_at TIMESTAMP, extra_json TEXT)"
    )
    markets = {"Over/Under 2.5": [{"selection": "Over 2.5", "prob": 55.0}]}
    con.execute(
        "INSERT INTO predictions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("30141288", "A vs B", "L", "2026-10-21T18:00:00+00:00", "Home", "1-0",
         40, 30, 30, 55, 45, 50, 50, 0, "2026-10-21T10:00:00",
         json.dumps({"markets": markets})),
    )
    con.commit()
    con.close()
    monkeypatch.setattr(lpd, "DATA_DIR", str(tmp_path))
    return lpd.load_predictions_from_db()


def test_str_fixture_id_finds_its_prediction(preds):
    """Betarabia fixtures carry the Kickertech id as a str."""
    assert preds.get("30141288") is not None
    assert "30141288" in preds
    assert preds["30141288"]["markets"]["Over/Under 2.5"][0]["prob"] == 55.0


def test_int_fixture_id_still_finds_its_prediction(preds):
    """ESPN/Sofascore fixtures carry int ids; they must keep working."""
    assert preds.get(30141288) is not None
    assert 30141288 in preds


def test_unknown_id_misses_cleanly(preds):
    assert preds.get("99999999") is None
    assert "not-a-number" not in preds
