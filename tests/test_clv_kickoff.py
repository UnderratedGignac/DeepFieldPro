"""Closing-line value must be measured against THIS fixture's Pinnacle close.

The daily VALUE_ONLY report judges the strategy on pinnacle_clv, recorded at
settlement from the last Pinnacle snapshot. clv_from_pinnacle() and
clv_from_pinnacle_ou25() looked rows up by team names alone, so a same-name
youth game (Pinnacle lists them under the senior names) could stand in for the
real close; the O/U one had no fuzzy fallback at all ("Inter Milan" vs
"Internazionale" recorded nothing). Both now take the bet's kickoff and go
through get_pinnacle_latest(). BTTS had no Pinnacle history and so no CLV:
the feed now writes btts_yes/btts_no rows and clv_from_pinnacle_btts() reads them.
"""

import importlib
import sqlite3
import time

import pytest

pv = importlib.import_module("tools.pinnacle_value")
pf = importlib.import_module("src.pinnacle_feed")

SENIOR_KO = time.time() + 6 * 3600
YOUTH_KO = time.time() + 1 * 3600


@pytest.fixture
def history(tmp_path, monkeypatch):
    db = str(tmp_path / "completed_fixtures.db")
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE sharp_odds_history (match_key TEXT, home_team TEXT, away_team TEXT, league TEXT, "
        "selection TEXT, decimal_odds REAL, devig_prob REAL, ts REAL, starts_ts REAL)"
    )
    now = time.time()
    rows = []
    for i in range(3):
        rows += [("Bayern Munich vs Arsenal", "Bayern Munich", "Arsenal", "", "under_2.5", 2.47, 0.39, now - 600 + i, SENIOR_KO),
                 ("Bayern Munich vs Arsenal", "Bayern Munich", "Arsenal", "", "under_2.5", 3.30, 0.29, now - 60 + i, YOUTH_KO)]
    con.executemany("INSERT INTO sharp_odds_history VALUES (?,?,?,?,?,?,?,?,?)", rows)
    con.commit()
    con.close()
    monkeypatch.setattr(pv, "_COMPLETED_DB", db)
    monkeypatch.setattr(pf, "_COMPLETED_DB", db)
    monkeypatch.setitem(pv._PIN_PAIRS_CACHE, "ts", 0.0)
    return db


def test_ou25_clv_uses_the_fixtures_own_close(history):
    clv = pv.clv_from_pinnacle_ou25("Bayern Munich", "Arsenal", "Under 2.5", 2.60, kickoff_ts=SENIOR_KO)
    assert clv == pytest.approx(2.60 / 2.47 - 1, abs=1e-4)


def test_ou25_clv_falls_back_to_fuzzy_names(history):
    clv = pv.clv_from_pinnacle_ou25("Bayern München", "Arsenal FC", "Under 2.5", 2.60, kickoff_ts=SENIOR_KO)
    assert clv == pytest.approx(2.60 / 2.47 - 1, abs=1e-4)


def test_btts_snapshot_and_clv(history):
    n = pf.write_btts_snapshot({"Bayern Munich vs Arsenal": {
        "yes": 1.80, "no": 2.05, "p_yes": 0.53, "p_no": 0.47, "starts_ts": SENIOR_KO,
        "_home": "Bayern Munich", "_away": "Arsenal"}})
    assert n == 1
    clv = pv.clv_from_pinnacle_btts("Bayern Munich", "Arsenal", "No", 2.20, kickoff_ts=SENIOR_KO)
    assert clv == pytest.approx(2.20 / 2.05 - 1, abs=1e-4)
