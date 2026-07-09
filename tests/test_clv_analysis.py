"""Unit tests for Phase 7 (Closing Line Value) — src/clv_analysis.py."""

import sqlite3

import pytest

from src import clv_analysis as clv


def _make_price_db(tmp_path, rows):
    """rows: list of (fixture_id, outcome, mid, recorded_at)."""
    db_path = str(tmp_path / "polymarket_steam.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE price_history (id INTEGER PRIMARY KEY, fixture_id TEXT, "
        "match_name TEXT, outcome TEXT, mid REAL, recorded_at REAL)"
    )
    for fid, outcome, mid, ts in rows:
        conn.execute(
            "INSERT INTO price_history (fixture_id, outcome, mid, recorded_at) VALUES (?,?,?,?)",
            (fid, outcome, mid, ts),
        )
    conn.commit()
    conn.close()
    return db_path


def test_compute_clv_basic():
    # Bought at 0.50, closed at 0.60 -> we got a better (cheaper) price -> positive CLV
    assert clv.compute_clv(0.50, 0.60) == pytest.approx(0.50 / 0.60 - 1.0, abs=1e-5)


def test_compute_clv_none_on_missing_or_zero_price():
    assert clv.compute_clv(None, 0.5) is None
    assert clv.compute_clv(0.5, None) is None
    assert clv.compute_clv(0.5, 0.0) is None


def test_fetch_price_snapshots_finds_closest_within_window(tmp_path):
    db_path = _make_price_db(
        tmp_path,
        [
            ("F1", "home", 0.50, 1000.0),      # signal time
            ("F1", "home", 0.55, 1000.0 + 1800),  # +30 min
            ("F1", "home", 0.60, 1000.0 + 3600),  # +1hr
            ("F1", "home", 0.65, 5000.0),       # last before kickoff
        ],
    )
    snaps = clv.fetch_price_snapshots("F1", "home", signal_ts=1000.0, kickoff_ts=6000.0, db_path=db_path)
    assert snaps["signal_price"] == 0.50
    assert snaps["price_30min"] == 0.55
    assert snaps["price_1hr"] == 0.60
    assert snaps["price_pre_kickoff"] == 0.65


def test_fetch_price_snapshots_missing_window_returns_none(tmp_path):
    # Only snapshot on record is at ts=1000 -- a signal at ts=100000 has
    # nothing within any of the snapshot windows (all well beyond their
    # max_gap_sec tolerances), so every field should come back None.
    db_path = _make_price_db(tmp_path, [("F1", "home", 0.50, 1000.0)])
    snaps = clv.fetch_price_snapshots("F1", "home", signal_ts=100000.0, kickoff_ts=None, db_path=db_path)
    assert snaps["signal_price"] is None
    assert snaps["price_30min"] is None
    assert snaps["price_1hr"] is None
    assert snaps["price_pre_kickoff"] is None  # no kickoff_ts supplied


def test_summarize_clv_excludes_missing_and_computes_stats():
    records = [
        {"clv": 0.05, "strategy": "tipster_confirmed"},
        {"clv": -0.02, "strategy": "tipster_confirmed"},
        {"clv": None, "strategy": "tipster_confirmed"},  # excluded
        {"clv": 0.10, "strategy": "real_arb"},
    ]
    summary = clv.summarize_clv(records)
    assert summary["n"] == 3
    assert summary["avg_clv"] == pytest.approx((0.05 - 0.02 + 0.10) / 3, abs=1e-5)
    assert summary["positive_clv_pct"] == pytest.approx(2 / 3, abs=1e-4)
    assert summary["by_strategy"]["tipster_confirmed"]["n"] == 2
    assert summary["by_strategy"]["real_arb"]["n"] == 1


def test_summarize_clv_empty_is_valid_not_error():
    summary = clv.summarize_clv([])
    assert summary["n"] == 0
    assert summary["avg_clv"] is None
    assert summary["by_strategy"] == {}


def test_build_clv_report_end_to_end(tmp_path):
    db_path = _make_price_db(
        tmp_path,
        [
            ("F1", "home", 0.50, 1000.0),
            ("F1", "home", 0.60, 5000.0),  # pre-kickoff / closing
        ],
    )
    bets = [
        {
            "fixture_id": "F1", "outcome": "home", "signal_ts": 1000.0,
            "kickoff_ts": 6000.0, "price_taken": 0.52, "strategy": "tipster_confirmed",
            "settlement": "home",
        }
    ]
    report = clv.build_clv_report(bets, db_path=db_path)
    assert report["detail"][0]["price_pre_kickoff"] == 0.60
    assert report["detail"][0]["clv"] == pytest.approx(0.52 / 0.60 - 1.0, abs=1e-5)
    assert report["summary"]["n"] == 1
