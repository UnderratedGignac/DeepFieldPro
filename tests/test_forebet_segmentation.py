"""Unit tests for Phase 6 (Forebet Analysis) — src/forebet_segmentation.py."""

import sqlite3

import pytest

from src import forebet_segmentation as fs


def _make_db(tmp_path, rows, market_type="1X2"):
    """rows: list of (bet_source, stake, pnl, edge_pct, fair_odds, result)."""
    db_path = str(tmp_path / "bet_log.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE bet_log (
            bet_id TEXT, stake REAL, pnl REAL, edge_pct REAL,
            fair_odds REAL, result TEXT, bet_source TEXT, market_type TEXT
        )
        """
    )
    for i, (src, stake, pnl, edge, fo, result) in enumerate(rows):
        conn.execute(
            "INSERT INTO bet_log (bet_id, stake, pnl, edge_pct, fair_odds, result, bet_source, market_type) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (f"b{i}", stake, pnl, edge, fo, result, src, market_type),
        )
    conn.commit()
    conn.close()
    return db_path


def test_empty_db_returns_valid_zero_segments(tmp_path):
    db_path = _make_db(tmp_path, [])
    report = fs.build_forebet_segmentation_report(db_path=db_path)
    assert report["forebet_confirmed"]["n"] == 0
    assert report["non_confirmed"]["n"] == 0
    assert report["arbitrage"]["n"] == 0


def test_void_bets_excluded_from_segments(tmp_path):
    rows = [
        ("TIPSTER_FOREBET", 5.0, 0.0, 0.0, 2.0, "VOID"),
        ("TIPSTER_FOREBET", 5.0, 5.0, 0.0, 2.0, "W"),
    ]
    db_path = _make_db(tmp_path, rows)
    report = fs.build_forebet_segmentation_report(db_path=db_path)
    assert report["forebet_confirmed"]["n"] == 1  # VOID excluded


def test_forebet_confirmed_vs_non_confirmed_separated_by_source(tmp_path):
    rows = [
        ("TIPSTER_FOREBET", 10.0, 5.0, 0.0, 2.5, "W"),
        ("TIPSTER_FOREBET", 10.0, -10.0, 0.0, 2.5, "L"),
        ("AI", 10.0, -10.0, 0.0, 2.0, "L"),
        ("AI", 10.0, -10.0, 0.0, 2.0, "L"),
        ("OTHER_SOURCE", 10.0, 10.0, 0.0, 2.0, "W"),
    ]
    db_path = _make_db(tmp_path, rows)
    report = fs.build_forebet_segmentation_report(db_path=db_path)
    assert report["forebet_confirmed"]["n"] == 2
    assert report["non_confirmed"]["n"] == 2
    # OTHER_SOURCE isn't counted in either bucket
    assert report["forebet_confirmed"]["total_pnl"] == pytest.approx(-5.0)
    assert report["non_confirmed"]["total_pnl"] == pytest.approx(-20.0)


def test_roi_and_win_rate_computed_correctly(tmp_path):
    rows = [
        ("TIPSTER_FOREBET", 10.0, 15.0, 0.0, 2.5, "W"),  # win, profit 15
        ("TIPSTER_FOREBET", 10.0, -10.0, 0.0, 2.5, "L"),  # loss, -10
    ]
    db_path = _make_db(tmp_path, rows)
    report = fs.build_forebet_segmentation_report(db_path=db_path)
    seg = report["forebet_confirmed"]
    assert seg["win_rate"] == 0.5
    assert seg["roi"] == pytest.approx(5.0 / 20.0)  # total_pnl=5, total_staked=20


def test_edge_segmentation_splits_by_threshold(tmp_path):
    rows = [
        ("TIPSTER_FOREBET", 10.0, 5.0, 8.0, 2.0, "W"),   # high edge (>=5)
        ("TIPSTER_FOREBET", 10.0, -10.0, 2.0, 2.0, "L"),  # low edge (<5)
    ]
    db_path = _make_db(tmp_path, rows)
    report = fs.build_forebet_segmentation_report(db_path=db_path, edge_threshold_pct=5.0)
    assert report["forebet_high_edge"]["n"] == 1
    assert report["forebet_low_edge"]["n"] == 1


def test_confidence_segmentation_splits_by_implied_prob(tmp_path):
    # fair_odds=1.5 -> implied prob = 0.667 (high conf); fair_odds=4.0 -> 0.25 (low conf)
    rows = [
        ("TIPSTER_FOREBET", 10.0, 5.0, 0.0, 1.5, "W"),
        ("TIPSTER_FOREBET", 10.0, -10.0, 0.0, 4.0, "L"),
    ]
    db_path = _make_db(tmp_path, rows)
    report = fs.build_forebet_segmentation_report(db_path=db_path, confidence_threshold=0.50)
    assert report["forebet_high_confidence"]["n"] == 1
    assert report["forebet_low_confidence"]["n"] == 1


def test_missing_fair_odds_excluded_from_confidence_buckets_not_crashed(tmp_path):
    rows = [("TIPSTER_FOREBET", 10.0, 5.0, 0.0, None, "W")]
    db_path = _make_db(tmp_path, rows)
    report = fs.build_forebet_segmentation_report(db_path=db_path)
    assert report["forebet_confirmed"]["n"] == 1
    assert report["forebet_high_confidence"]["n"] == 0
    assert report["forebet_low_confidence"]["n"] == 0


def test_market_type_filter_excludes_other_markets(tmp_path):
    db_path = str(tmp_path / "bet_log.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE bet_log (bet_id TEXT, stake REAL, pnl REAL, edge_pct REAL, "
        "fair_odds REAL, result TEXT, bet_source TEXT, market_type TEXT)"
    )
    conn.execute(
        "INSERT INTO bet_log VALUES ('b1', 10.0, 5.0, 0.0, 2.0, 'W', 'TIPSTER_FOREBET', '1X2')"
    )
    conn.execute(
        "INSERT INTO bet_log VALUES ('b2', 10.0, -10.0, 0.0, 2.0, 'L', 'TIPSTER_FOREBET', 'Over/Under 2.5')"
    )
    conn.commit()
    conn.close()

    report_1x2 = fs.build_forebet_segmentation_report(db_path=db_path, market_type="1X2")
    assert report_1x2["forebet_confirmed"]["n"] == 1
    assert report_1x2["forebet_confirmed"]["total_pnl"] == pytest.approx(5.0)

    report_all = fs.build_forebet_segmentation_report(db_path=db_path, market_type=None)
    assert report_all["forebet_confirmed"]["n"] == 2
