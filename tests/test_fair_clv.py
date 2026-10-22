"""Grade closing-line value against Pinnacle's margin-free (fair) closing price.

pinnacle_clv = entry / Pinnacle's RAW closing price - 1. The raw price still
carries Pinnacle's margin, so every bet looks better than it is: on 2026-10-21
VALUE_ONLY read +9.1% against the raw close but +1.4% (95% CI -1.9%..+4.7%)
against the fair one. A gate on the raw number could say GO on an edge that is
not there. pinnacle_fair_clv = entry * Pinnacle's de-vigged closing
probability - 1 is recorded beside it, and the daily report and the edge gate
grade on it. pinnacle_clv keeps its meaning so older rows stay comparable.
"""

import importlib
import sqlite3
import time

import pytest

pv = importlib.import_module("tools.pinnacle_value")
rep = importlib.import_module("tools.value_only_report")
edge = importlib.import_module("tools.edge_status")
backfill = importlib.import_module("tools.backfill_fair_clv")

KO = time.time() + 2 * 3600


@pytest.fixture
def history(tmp_path, monkeypatch):
    db = str(tmp_path / "completed_fixtures.db")
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE sharp_odds_history (match_key TEXT, home_team TEXT, away_team TEXT, league TEXT, "
        "selection TEXT, decimal_odds REAL, devig_prob REAL, ts REAL, starts_ts REAL)"
    )
    now = time.time()
    rows = [("Arsenal vs Chelsea", "Arsenal", "Chelsea", "", sel, dec, p, now - 60, KO)
            for sel, dec, p in (("home", 2.00, 0.48), ("draw", 3.40, 0.28), ("away", 4.00, 0.24),
                                ("under_2.5", 1.90, 0.505), ("btts_no", 2.05, 0.47))]
    con.executemany("INSERT INTO sharp_odds_history VALUES (?,?,?,?,?,?,?,?,?)", rows)
    con.commit()
    con.close()
    monkeypatch.setattr(pv, "_COMPLETED_DB", db)
    monkeypatch.setitem(pv._PIN_PAIRS_CACHE, "ts", 0.0)


@pytest.mark.parametrize("market,side,entry,raw,fair", [
    ("1X2", "Home (1)", 2.20, 2.20 / 2.00 - 1, 2.20 * 0.48 - 1),
    ("Over/Under 2.5", "Under 2.5", 2.00, 2.00 / 1.90 - 1, 2.00 * 0.505 - 1),
    ("BTTS", "No", 2.10, 2.10 / 2.05 - 1, 2.10 * 0.47 - 1),
])
def test_raw_and_fair_clv_from_one_lookup(history, market, side, entry, raw, fair):
    r, f = pv.pinnacle_clvs(market, "Arsenal", "Chelsea", side, entry, kickoff_ts=KO)
    assert r == pytest.approx(raw, abs=1e-4)
    assert f == pytest.approx(fair, abs=1e-4)
    assert f < r, "the fair close never flatters a bet the way the raw close does"


def _ledger(tmp_path, rows, extra_cols=""):
    path = str(tmp_path / "bet_log.db")
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE bet_log (bet_id TEXT, match_id TEXT, bet_source TEXT, market_type TEXT, side TEXT, "
        "entry_odds REAL, stake REAL, result TEXT, pnl REAL, pinnacle_clv REAL, pinnacle_fair_clv REAL, "
        "book TEXT, placed_at TEXT, kickoff_time TEXT, clv REAL" + extra_cols + ")"
    )
    con.executemany(
        "INSERT INTO bet_log (bet_id, match_id, bet_source, market_type, side, entry_odds, stake, result, pnl, "
        "pinnacle_clv, pinnacle_fair_clv, book, placed_at, kickoff_time) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    con.commit()
    con.close()
    return path


def test_daily_report_grades_on_the_fair_close(tmp_path):
    db = _ledger(tmp_path, [
        ("1", "A vs B", "VALUE_ONLY", "1X2", "Away (2)", 6.0, 0.2, "L", -0.2, 0.12, 0.01, "Kambi", "2026-10-22T10:00", None),
        ("2", "C vs D", "VALUE_ONLY", "1X2", "Home (1)", 2.0, 1.0, "W", 1.0, 0.06, -0.01, "Kambi", "2026-10-22T10:00", None),
    ])
    r = rep.build_report(db)
    assert r["clv_mean"] == pytest.approx(0.0)
    assert r["beat_close"] == pytest.approx(0.5)
    assert "fair close" in rep.format_report(r)


def test_edge_gate_grades_value_only_on_the_fair_close(tmp_path, monkeypatch, capsys):
    rows = [(str(i), f"M{i}", "VALUE_ONLY", "1X2", "Away (2)", 5.0, 0.2, "L" if i % 2 else "W", 0.0,
             0.10, (0.02 if i % 2 else 0.04), "Kambi", "2026-10-22T10:00", None) for i in range(110)]
    db = _ledger(tmp_path, rows)
    monkeypatch.setattr(edge, "DB", db)
    edge.main()
    out = capsys.readouterr().out
    block = next(b for b in out.split("\n[") if "(source=VALUE_ONLY)" in b)
    assert block.startswith("GO]")
    assert "avg SHARP CLV ....... +3.00%" in block  # the fair figure, not the raw +10%


def test_backfill_skips_bets_older_than_pinnacle_history_and_dry_run_writes_nothing(tmp_path, monkeypatch):
    """Thousands of settled bets predate the 14-day history; looking each up hung the run."""
    old_ko = str(time.time() - 40 * 86400)
    path = str(tmp_path / "bet_log.db")
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE bet_log (bet_id TEXT, match_id TEXT, market_type TEXT, side TEXT, "
                "entry_odds REAL, result TEXT, kickoff_time TEXT)")
    con.executemany("INSERT INTO bet_log VALUES (?,?,?,?,?,?,?)",
                    [(str(i), "A vs B", "1X2", "Home (1)", 2.0, "W", old_ko) for i in range(50)])
    con.commit()
    con.close()
    calls = []
    monkeypatch.setattr(backfill, "pinnacle_clvs", lambda *a, **k: calls.append(a) or (None, None))
    assert backfill.backfill(path, apply=False) == 0
    assert calls == []
    con = sqlite3.connect(path)
    cols = [r[1] for r in con.execute("PRAGMA table_info(bet_log)")]
    con.close()
    assert "pinnacle_fair_clv" not in cols, "a dry run must not alter the ledger"


def test_backfill_fills_fair_clv_for_settled_bets(tmp_path, history):
    db = _ledger(tmp_path, [
        ("1", "Arsenal vs Chelsea", "VALUE_ONLY", "1X2", "Home (1)", 2.20, 1.0, "W", 1.2, 0.10, None, "Kambi",
         "2026-10-22T10:00", str(KO)),
        ("2", "Arsenal vs Chelsea", "VALUE_ONLY", "1X2", "Draw (X)", 3.60, 1.0, "OPEN", 0.0, None, None, "Kambi",
         "2026-10-22T10:00", str(KO)),
    ])
    assert backfill.backfill(db, apply=True) == 1
    con = sqlite3.connect(db)
    vals = dict(con.execute("SELECT bet_id, pinnacle_fair_clv FROM bet_log").fetchall())
    con.close()
    assert vals["1"] == pytest.approx(2.20 * 0.48 - 1, abs=1e-4)
    assert vals["2"] is None, "open bets have no close yet"
