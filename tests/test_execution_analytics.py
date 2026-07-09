"""Unit tests for Phase 2 (Execution Quality) — src/execution_analytics.py."""

import pytest

from src import execution_analytics as ea

SAMPLE_BOOK = {
    "bids": [{"price": "0.48", "size": "100"}, {"price": "0.47", "size": "200"}],
    "asks": [
        {"price": "0.50", "size": "50"},
        {"price": "0.505", "size": "80"},
        {"price": "0.51", "size": "150"},
        {"price": "0.55", "size": "1000"},
    ],
}


def test_best_bid_ask():
    bid, ask = ea.best_bid_ask(SAMPLE_BOOK)
    assert bid == 0.48
    assert ask == 0.50


def test_best_bid_ask_handles_missing_book():
    assert ea.best_bid_ask(None) == (None, None)
    assert ea.best_bid_ask({}) == (None, None)


def test_compute_liquidity_metrics_bands():
    mid = 0.50
    metrics = ea.compute_liquidity_metrics(SAMPLE_BOOK, mid)
    # 0.5% band -> ceiling 0.5025 -> only the $0.50 level (50 * 0.50 = 25)
    assert metrics["liq_0.5pct"] == pytest.approx(25.0)
    # 1% band -> ceiling 0.505 -> $0.50 + $0.505 levels (25 + 40.4)
    assert metrics["liq_1pct"] == pytest.approx(25.0 + 80 * 0.505)
    # 3% band -> ceiling 0.515 -> excludes the $0.55 level
    assert metrics["liq_3pct"] == pytest.approx(25.0 + 80 * 0.505 + 150 * 0.51)


def test_compute_liquidity_metrics_handles_bad_input():
    assert ea.compute_liquidity_metrics(None, 0.5) == {
        "liq_0.5pct": 0.0, "liq_1pct": 0.0, "liq_2pct": 0.0, "liq_3pct": 0.0,
    }
    assert ea.compute_liquidity_metrics(SAMPLE_BOOK, 0) == {
        "liq_0.5pct": 0.0, "liq_1pct": 0.0, "liq_2pct": 0.0, "liq_3pct": 0.0,
    }


def test_liquidity_gate_ok_passes_with_sufficient_depth():
    # 1% band has ~$65.40 available; want $10 with 3x multiple -> need $30 -> OK
    ok, metrics = ea.liquidity_gate_ok(SAMPLE_BOOK, 0.50, desired_usd=10.0, required_multiple=3, band_pct=0.01)
    assert ok is True
    assert metrics["liq_1pct"] > 30.0


def test_liquidity_gate_ok_rejects_thin_book():
    # Want $50 with 3x multiple -> need $150, but 1% band only has ~$65.40
    ok, metrics = ea.liquidity_gate_ok(SAMPLE_BOOK, 0.50, desired_usd=50.0, required_multiple=3, band_pct=0.01)
    assert ok is False


def test_liquidity_gate_fails_open_on_missing_book():
    """A missing/unreachable order book must NOT block betting entirely."""
    ok, metrics = ea.liquidity_gate_ok(None, 0.50, desired_usd=1000.0, required_multiple=3)
    assert ok is True
    assert metrics["liq_1pct"] == 0.0  # visible in the record as a real data gap


def test_log_signal_and_update_fill_roundtrip(tmp_path):
    db_path = str(tmp_path / "execution_log.db")
    row_id = ea.log_signal(
        {
            "order_id": "abc-123",
            "signal_ts": 1000.0,
            "fixture_id": "WC2026-GS-M1",
            "match": "France vs Morocco",
            "outcome": "home",
            "model_prob": 0.80,
            "fair_prob": 0.75,
            "market_mid": 0.604,
            "best_bid": 0.60,
            "best_ask": 0.61,
            "spread": 0.01,
            "requested_size": 14.04,
            "limit_price": 0.624,
            "liquidity_depth": {"liq_1pct": 65.4},
            "ev_at_signal": 0.196,
            "kickoff_ts": 5200.0,
        },
        db_path=db_path,
    )
    assert row_id == 1

    ea.update_fill(
        "abc-123", filled_size=14.04, fill_price=0.63, fill_observed_at=1004.2,
        ev_at_fill=0.176, db_path=db_path,
    )
    ea.update_settlement("abc-123", "home", db_path=db_path)

    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM execution_log WHERE order_id = ?", ("abc-123",)).fetchone()
    conn.close()

    assert row["filled_size"] == 14.04
    assert row["fill_price"] == 0.63
    assert row["slippage"] == pytest.approx((0.63 - 0.624) / 0.624, abs=1e-5)
    assert row["execution_delay_sec"] == pytest.approx(4.2, abs=1e-3)
    assert row["final_settlement"] == "home"


def test_slippage_report_empty_is_valid_not_error(tmp_path):
    db_path = str(tmp_path / "execution_log.db")
    report = ea.slippage_report(db_path=db_path)
    assert report["n"] == 0
    assert report["avg_slippage"] is None
    assert report["by_liquidity_bucket"] == {}


def test_slippage_report_aggregates(tmp_path):
    db_path = str(tmp_path / "execution_log.db")
    for i, (fid, liq, slip, ttk_hrs) in enumerate(
        [
            ("WC-1", 600, 0.01, 0.5),
            ("WC-1", 600, -0.02, 2.0),
            ("WC-2", 50, 0.05, 30.0),
        ]
    ):
        ea.log_signal(
            {
                "order_id": f"o{i}",
                "signal_ts": 1000.0,
                "fixture_id": fid,
                "match": fid,
                "outcome": "home",
                "limit_price": 0.5,
                "liquidity_depth": {"liq_1pct": liq},
                "kickoff_ts": 1000.0 + ttk_hrs * 3600.0,
            },
            db_path=db_path,
        )
        ea.update_fill(f"o{i}", filled_size=10, fill_price=0.5 * (1 + slip), fill_observed_at=1001.0, db_path=db_path)

    report = ea.slippage_report(db_path=db_path)
    assert report["n"] == 3
    assert "deep (>=$500)" in report["by_liquidity_bucket"]
    assert report["by_liquidity_bucket"]["deep (>=$500)"]["n"] == 2
    assert "thin (<$100)" in report["by_liquidity_bucket"]
    assert report["by_market"]["WC-1"]["n"] == 2
    assert report["by_market"]["WC-2"]["n"] == 1
    assert "<1h to kickoff" in report["by_time_to_kickoff"]
    assert ">24h to kickoff" in report["by_time_to_kickoff"]
