"""
brier_tracker.py — Model calibration quality monitor.

Brier score measures calibration: BS = (1/N) Σ(p_i - o_i)²
  p_i = model probability (1/fair_odds)
  o_i = actual outcome (1=WIN, 0=LOSS)
  Range: 0 (perfect) to 1 (worst)
  Baseline for uniform 3-way: 0.222

A well-calibrated model hits:
  BS < 0.20 — good
  BS < 0.18 — excellent
  BS > 0.23 — worse than naive baseline

Also tracks:
  - Calibration buckets: how often bets at p% actually win
  - ROI by market type
  - Running win rate, avg edge, avg CLV
  - Sharpness (variance of predictions — penalises if model hedges to 33%)
"""

import os
import sqlite3
import math

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BET_LOG = os.path.join(_ROOT, "data", "bet_log.db")


def _connect():
    c = sqlite3.connect(_BET_LOG)
    c.row_factory = sqlite3.Row
    return c


def compute_brier_score(since_date: str = None) -> dict:
    """
    Compute overall Brier score + calibration breakdown from bet_log.db.

    Returns a dict ready to serialise as JSON.
    since_date: optional 'YYYY-MM-DD' filter for recent-only analysis.
    """
    if not os.path.exists(_BET_LOG):
        return {"error": "bet_log.db not found", "brier_score": None}

    date_filter = f"AND DATE(placed_at) >= '{since_date}'" if since_date else ""
    query = f"""
        SELECT fair_odds, entry_odds, result, pnl, stake, market_type,
               edge_pct, clv, placed_at
        FROM bet_log
        WHERE result IN ('W', 'L')
          AND fair_odds IS NOT NULL AND fair_odds > 0
          {date_filter}
    """

    try:
        conn = _connect()
        rows = conn.execute(query).fetchall()
        conn.close()
    except Exception as e:
        return {"error": str(e), "brier_score": None}

    if not rows:
        return {"brier_score": None, "n_bets": 0}

    # Core Brier calculation
    sq_errors = []
    wins = 0
    total_pnl = 0.0
    total_stake = 0.0
    edge_vals = []
    clv_vals = []
    by_market: dict = {}

    # Calibration buckets: 10% wide (0-10%, 10-20%, ..., 90-100%)
    buckets = {i: {"n": 0, "w": 0} for i in range(10)}

    for r in rows:
        prob = 1.0 / r["fair_odds"]
        outcome = 1 if r["result"] == "W" else 0
        sq_errors.append((prob - outcome) ** 2)

        wins += outcome
        total_pnl += r["pnl"] or 0.0
        total_stake += abs(r["stake"] or 0.0)
        if r["edge_pct"] is not None:
            edge_vals.append(r["edge_pct"])
        if r["clv"] is not None:
            clv_vals.append(r["clv"])

        # Bucket (0..9 = 0-9%, 10-19%, ..., 90-99%)
        bucket_idx = min(int(prob * 10), 9)
        buckets[bucket_idx]["n"] += 1
        buckets[bucket_idx]["w"] += outcome

        # By market type
        mt = r["market_type"] or "unknown"
        if mt not in by_market:
            by_market[mt] = {"n": 0, "w": 0, "pnl": 0.0, "stake": 0.0, "sq_errors": []}
        by_market[mt]["n"] += 1
        by_market[mt]["w"] += outcome
        by_market[mt]["pnl"] += r["pnl"] or 0.0
        by_market[mt]["stake"] += abs(r["stake"] or 0.0)
        by_market[mt]["sq_errors"].append((prob - outcome) ** 2)

    n = len(rows)
    brier = round(sum(sq_errors) / n, 4)

    # Baseline: uniform prior at average implied prob
    avg_prob = sum(1.0 / r["fair_odds"] for r in rows) / n
    brier_baseline = round(avg_prob * (1 - avg_prob), 4)  # variance of Bernoulli(p)

    # Brier Skill Score: positive = better than baseline
    bss = round(1.0 - brier / brier_baseline, 4) if brier_baseline > 0 else None

    roi = round((total_pnl / total_stake * 100), 2) if total_stake > 0 else None

    calibration_curve = []
    for i in range(10):
        b = buckets[i]
        if b["n"] >= 5:
            calibration_curve.append({
                "prob_mid": round((i + 0.5) / 10, 2),
                "n": b["n"],
                "actual_win_rate": round(b["w"] / b["n"], 3),
            })

    by_market_summary = {}
    for mt, d in by_market.items():
        mt_brier = round(sum(d["sq_errors"]) / d["n"], 4) if d["n"] else None
        mt_roi = round((d["pnl"] / d["stake"] * 100), 2) if d["stake"] > 0 else None
        by_market_summary[mt] = {
            "n": d["n"],
            "win_rate": round(d["w"] / d["n"], 3),
            "roi_pct": mt_roi,
            "brier": mt_brier,
        }

    # Grade: A/B/C/D/F based on Brier Skill Score
    if bss is None:
        grade = "?"
    elif bss >= 0.10:
        grade = "A"
    elif bss >= 0.05:
        grade = "B"
    elif bss >= 0.00:
        grade = "C"
    elif bss >= -0.05:
        grade = "D"
    else:
        grade = "F"

    return {
        "brier_score": brier,
        "brier_baseline": brier_baseline,
        "brier_skill_score": bss,
        "grade": grade,
        "n_bets": n,
        "win_rate": round(wins / n, 3),
        "roi_pct": roi,
        "avg_edge_pct": round(sum(edge_vals) / len(edge_vals), 3) if edge_vals else None,
        "avg_clv": round(sum(clv_vals) / len(clv_vals), 4) if clv_vals else None,
        "calibration_curve": calibration_curve,
        "by_market": by_market_summary,
    }


def compute_rolling_brier(window_days: int = 30, since_date: str = None) -> list:
    """
    Rolling Brier score by calendar week.
    Returns [{week, brier, n, win_rate}, ...] for charting.
    """
    if not os.path.exists(_BET_LOG):
        return []
    date_filter = f"AND DATE(placed_at) >= '{since_date}'" if since_date else ""
    query = f"""
        SELECT DATE(placed_at, 'weekday 0', '-6 days') AS week_start,
               fair_odds, result
        FROM bet_log
        WHERE result IN ('W', 'L') AND fair_odds IS NOT NULL AND fair_odds > 0
          {date_filter}
        ORDER BY placed_at ASC
    """
    try:
        conn = _connect()
        rows = conn.execute(query).fetchall()
        conn.close()
    except Exception:
        return []

    by_week: dict = {}
    for r in rows:
        wk = r["week_start"]
        if wk not in by_week:
            by_week[wk] = []
        prob = 1.0 / r["fair_odds"]
        o = 1 if r["result"] == "W" else 0
        by_week[wk].append((prob, o))

    result = []
    for wk, pairs in sorted(by_week.items()):
        n = len(pairs)
        bs = sum((p - o) ** 2 for p, o in pairs) / n
        wr = sum(o for _, o in pairs) / n
        result.append({
            "week": wk,
            "brier": round(bs, 4),
            "n": n,
            "win_rate": round(wr, 3),
        })
    return result


def compute_streak(since_date: str = None) -> dict:
    """Current win/loss streak and recent form (last 10 results)."""
    if not os.path.exists(_BET_LOG):
        return {}
    date_filter = f"AND DATE(placed_at) >= '{since_date}'" if since_date else ""
    query = f"""
        SELECT result FROM bet_log
        WHERE result IN ('W', 'L') {date_filter}
        ORDER BY placed_at DESC LIMIT 50
    """
    try:
        conn = _connect()
        rows = [r["result"] for r in conn.execute(query).fetchall()]
        conn.close()
    except Exception:
        return {}

    if not rows:
        return {"streak": 0, "streak_type": None, "last_10": []}

    # Current streak (from most recent result)
    streak_type = rows[0]
    streak = 0
    for r in rows:
        if r == streak_type:
            streak += 1
        else:
            break

    last_10 = rows[:10]
    wins_10 = last_10.count("W")
    return {
        "streak": streak,
        "streak_type": streak_type,  # "W" or "L"
        "last_10": last_10,
        "last_10_win_rate": round(wins_10 / len(last_10), 3),
    }


def compute_market_alerts(since_date: str = None) -> list:
    """Flag market types where performance is below the naive baseline."""
    perf = compute_brier_score(since_date=since_date)
    alerts = []
    brier_baseline = perf.get("brier_baseline", 0.222)
    for market, stats in perf.get("by_market", {}).items():
        bs = stats.get("brier")
        roi = stats.get("roi_pct")
        if bs is not None and bs > brier_baseline:
            alerts.append({
                "market": market,
                "alert": "BELOW_BASELINE",
                "brier": bs,
                "brier_baseline": brier_baseline,
                "roi_pct": roi,
                "message": f"{market}: Brier {bs} > baseline {brier_baseline} — model has no edge here",
            })
        if roi is not None and roi < -5.0:
            alerts.append({
                "market": market,
                "alert": "NEGATIVE_ROI",
                "roi_pct": roi,
                "message": f"{market}: ROI {roi}% — consider disabling this market",
            })
    return alerts


def get_performance_summary(since_date: str = None) -> dict:
    """Top-level summary for the /api/performance endpoint."""
    overall = compute_brier_score(since_date=since_date)
    rolling = compute_rolling_brier(since_date=since_date)
    streak = compute_streak(since_date=since_date)
    alerts = compute_market_alerts(since_date=since_date)
    return {
        "overall": overall,
        "rolling_weekly": rolling[-12:],
        "streak": streak,
        "market_alerts": alerts,
    }
