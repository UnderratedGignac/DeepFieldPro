"""
reporting.py — Phase 12 (Reporting) for DeepFieldPro.

Two pure, testable time-window helpers (filter_by_period, capital_curve)
used by tools/period_report.py to stitch together daily/weekly/monthly
reports from the per-phase modules already built (Phases 2-9): ROI/CLV
(clv_analysis, attribution_engine), slippage (execution_analytics),
calibration (calibration_metrics), Forebet segmentation
(forebet_segmentation), feature importance (feature_importance).

Deliberately does NOT reimplement any of those — this module's own logic is
just "which records fall in this time window" and "cumulative P&L over
time," the two genuinely new pieces Phase 12 needs.
"""

PERIOD_SECONDS = {
    "daily": 1 * 86400,
    "weekly": 7 * 86400,
    "monthly": 30 * 86400,
}


def filter_by_period(records, ts_key, period, now_ts):
    """
    Records whose record[ts_key] falls within `period` ("daily"/"weekly"/
    "monthly") before `now_ts`. Records with a missing/non-numeric ts_key are
    excluded (can't place them in time, so they can't honestly be included in
    a time-windowed report) rather than silently assumed to be "recent."
    """
    window = PERIOD_SECONDS.get(period)
    if window is None:
        raise ValueError(f"unknown period {period!r}; expected one of {list(PERIOD_SECONDS)}")
    cutoff = now_ts - window
    out = []
    for r in records:
        ts = r.get(ts_key)
        if not isinstance(ts, (int, float)):
            continue
        if ts >= cutoff:
            out.append(r)
    return out


def capital_curve(records, ts_key="ts", pnl_key="pnl"):
    """
    Chronologically-sorted cumulative P&L series: [{"ts":..., "cumulative_pnl":...}, ...].
    Records missing either key are excluded. Empty input -> empty list (a
    valid "no data yet" result, not an error).
    """
    usable = [r for r in records if isinstance(r.get(ts_key), (int, float)) and r.get(pnl_key) is not None]
    usable.sort(key=lambda r: r[ts_key])
    curve = []
    running = 0.0
    for r in usable:
        running += float(r[pnl_key])
        curve.append({"ts": r[ts_key], "cumulative_pnl": round(running, 2)})
    return curve
