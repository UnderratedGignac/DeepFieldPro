"""Unit tests for Phase 12 (Reporting) — src/reporting.py."""

import pytest

from src import reporting as rpt

NOW = 1_000_000.0
DAY = 86400


def test_filter_by_period_daily_excludes_older_records():
    records = [
        {"ts": NOW - 1 * 3600, "v": "recent"},       # 1 hour ago -> in daily window
        {"ts": NOW - 2 * DAY, "v": "two_days_ago"},  # outside daily window
    ]
    out = rpt.filter_by_period(records, "ts", "daily", now_ts=NOW)
    assert [r["v"] for r in out] == ["recent"]


def test_filter_by_period_weekly_includes_daily_range_too():
    records = [
        {"ts": NOW - 1 * DAY, "v": "one_day"},
        {"ts": NOW - 6 * DAY, "v": "six_days"},
        {"ts": NOW - 8 * DAY, "v": "eight_days"},  # outside weekly window
    ]
    out = rpt.filter_by_period(records, "ts", "weekly", now_ts=NOW)
    assert {r["v"] for r in out} == {"one_day", "six_days"}


def test_filter_by_period_monthly():
    records = [
        {"ts": NOW - 20 * DAY, "v": "in"},
        {"ts": NOW - 40 * DAY, "v": "out"},
    ]
    out = rpt.filter_by_period(records, "ts", "monthly", now_ts=NOW)
    assert [r["v"] for r in out] == ["in"]


def test_filter_by_period_unknown_period_raises():
    with pytest.raises(ValueError):
        rpt.filter_by_period([], "ts", "yearly", now_ts=NOW)


def test_filter_by_period_excludes_missing_or_non_numeric_ts():
    records = [
        {"ts": None, "v": "missing"},
        {"v": "no_key_at_all"},
        {"ts": "not-a-number", "v": "bad_type"},
        {"ts": NOW, "v": "valid"},
    ]
    out = rpt.filter_by_period(records, "ts", "daily", now_ts=NOW)
    assert [r["v"] for r in out] == ["valid"]


def test_capital_curve_empty_is_valid():
    assert rpt.capital_curve([]) == []


def test_capital_curve_sorts_chronologically_and_cumulates():
    records = [
        {"ts": 300, "pnl": 5.0},
        {"ts": 100, "pnl": 10.0},
        {"ts": 200, "pnl": -3.0},
    ]
    curve = rpt.capital_curve(records)
    assert [c["ts"] for c in curve] == [100, 200, 300]
    assert curve[0]["cumulative_pnl"] == 10.0
    assert curve[1]["cumulative_pnl"] == 7.0
    assert curve[2]["cumulative_pnl"] == 12.0


def test_capital_curve_excludes_records_missing_keys():
    records = [
        {"ts": 100, "pnl": 5.0},
        {"ts": 200},  # missing pnl
        {"pnl": 5.0},  # missing ts
    ]
    curve = rpt.capital_curve(records)
    assert len(curve) == 1
    assert curve[0]["cumulative_pnl"] == 5.0
