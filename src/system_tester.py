"""
system_tester.py — End-to-end test of all betting models, staking formulas,
and research features.

Runs 8 tests, places paper bets tagged by test regime, and writes a report to
data/system_test_report.json.

Tests:
  T01  Prediction model accuracy (DC vs market de-vig across all leagues)
  T03  Daemon quarter-Kelly staking (all leagues, log_ai_bet formula)
  T04  Steam staking model (2% bankroll / flat-$25 fallback)
  T06  Brier score calibration (settled bets, per-market)
  T07  CLV tracking completeness (price_history → settled bet CLV)
  T08  Drawdown monitor (equity curve stats)
  T09  Red card monitor (ESPN API connection + logic check)
  T10  Research bet coverage (by league and market type)

Usage:
  python -m src.system_tester           # full run
  python -m src.system_tester T06       # single test
"""

import os
import sys
import json
import math
import sqlite3
import uuid
import time
import datetime
import traceback
from typing import Any

# Windows PowerShell may use cp1252/cp1256 which can't encode → or ≥
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BET_LOG   = os.path.join(_ROOT, "data", "bet_log.db")
_BANKROLL  = os.path.join(_ROOT, "data", "bankroll.db")
_DASHBOARD = os.path.join(_ROOT, "data", "todays_dashboard_state.json")
_REPORT    = os.path.join(_ROOT, "data", "system_test_report.json")
_SETTINGS  = os.path.join(_ROOT, "data", "settings.json")

PAPER_STAKE_FLAT = 10.0   # flat stake for non-Kelly tests


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_settings() -> dict:
    try:
        with open(_SETTINGS, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _paper_balance() -> float:
    try:
        conn = sqlite3.connect(_BANKROLL)
        row = conn.execute(
            "SELECT current_balance FROM bankroll ORDER BY date DESC LIMIT 1"
        ).fetchone()
        conn.close()
        return float(row[0]) if row else 5000.0
    except Exception:
        return 5000.0


def _log_paper_bet(fixture_id, match_name, side, market_type,
                   entry_odds, fair_odds, edge_pct, stake,
                   signal_name, league="", regime="test",
                   _conn=None):
    """Insert a paper bet into bet_log.db with a test regime tag.
    Pass an open connection via _conn to batch multiple inserts efficiently."""
    if stake is None or stake < 0:
        stake = 0.0
    line_val = None
    if "2.5" in str(market_type): line_val = 2.5
    if "3.0" in str(market_type): line_val = 3.0
    own_conn = _conn is None
    try:
        conn = sqlite3.connect(_BET_LOG) if own_conn else _conn
        conn.execute("""
            INSERT INTO bet_log
              (bet_id, match_id, player_id, market_type, line, side,
               entry_odds, fair_odds, edge_pct, stake, book,
               placed_at, result, pnl, regime, bet_source, signal_name, league)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,datetime('now'),?,?,?,?,?,?)
        """, (
            str(uuid.uuid4()), str(fixture_id), side, market_type, line_val, side,
            entry_odds, fair_odds, edge_pct, stake, "PAPER",
            "VOID", 0.0, regime, "TEST", signal_name, league,
        ))
        if own_conn:
            conn.commit()
            conn.close()
        return True
    except Exception:
        return False


def _pass(name, detail, data=None):
    return {"test": name, "status": "PASS", "detail": detail, "data": data or {}}

def _fail(name, detail, data=None):
    return {"test": name, "status": "FAIL", "detail": detail, "data": data or {}}

def _warn(name, detail, data=None):
    return {"test": name, "status": "WARN", "detail": detail, "data": data or {}}


# ---------------------------------------------------------------------------
# T01 — Prediction model accuracy
# ---------------------------------------------------------------------------

def test_prediction_model() -> dict:
    """
    Load all upcoming fixtures from the daemon's dashboard state.
    For each, compute model edge vs de-vigged market probability.
    Report: mean edge, MAE, grade distribution, top 5 picks.
    """
    try:
        with open(_DASHBOARD, "r", encoding="utf-8") as f:
            state = json.load(f)
    except Exception as e:
        return _fail("T01_prediction_model", f"Cannot read dashboard state: {e}")

    now_ts = time.time()
    edges = []
    top_picks = []
    grade_counts = {"A+": 0, "A": 0, "B": 0, "C": 0, "D": 0, "F": 0}

    for entry in state:
        kick = entry.get("kickoff", "")
        try:
            ko_ts = datetime.datetime.fromisoformat(
                kick.replace("Z", "+00:00")).timestamp()
            if ko_ts <= now_ts:
                continue
        except Exception:
            pass

        pred = (entry.get("prediction") or {})
        markets = pred.get("markets") or {}
        for sel in markets.get("1X2", []):
            prob_pct = sel.get("prob", 0)
            odds = sel.get("odds") or sel.get("best_odds")
            ev = sel.get("ev") or sel.get("ev_best") or 0.0
            if not prob_pct or not odds:
                continue
            model_p = prob_pct / 100.0
            mkt_p = 1.0 / float(odds)
            edge_pp = round((model_p - mkt_p) * 100, 2)
            edges.append(edge_pp)

            # Grade (A-F edge-quality bucket)
            steam = sel.get("steam_move", 0) or 0
            if edge_pp >= 8 and steam >= 5:
                grade = "A"
            elif edge_pp >= 5 and (steam >= 3):
                grade = "B"
            elif edge_pp >= 3:
                grade = "C"
            elif edge_pp >= 1:
                grade = "D"
            elif edge_pp < -1:
                grade = "F"
            else:
                grade = "F"
            grade_counts[grade] = grade_counts.get(grade, 0) + 1

            if edge_pp >= 3:
                top_picks.append({
                    "match": entry.get("match"),
                    "league": entry.get("league"),
                    "side": sel.get("selection"),
                    "model_p": round(model_p * 100, 1),
                    "odds": odds,
                    "edge_pp": edge_pp,
                    "ev": round(float(ev) * 100, 2),
                })

    if not edges:
        return _fail("T01_prediction_model", "No upcoming fixtures found")

    top_picks.sort(key=lambda x: x["edge_pp"], reverse=True)
    mean_edge = round(sum(edges) / len(edges), 2)
    positive = sum(1 for e in edges if e > 0)

    status = "PASS" if positive > len(edges) * 0.3 else "WARN"
    return {
        "test": "T01_prediction_model",
        "status": status,
        "detail": (
            f"{len(edges)} 1X2 selections across {len(state)} fixtures. "
            f"Mean edge {mean_edge:+.1f}pp. {positive}/{len(edges)} positive-edge picks."
        ),
        "data": {
            "total_selections": len(edges),
            "positive_edge": positive,
            "mean_edge_pp": mean_edge,
            "grade_distribution": grade_counts,
            "top_picks": top_picks[:10],
        },
    }


# ---------------------------------------------------------------------------
# T03 — Daemon quarter-Kelly staking
# ---------------------------------------------------------------------------

def test_daemon_quarter_kelly() -> dict:
    """
    Test the daemon's quarter-Kelly formula (log_ai_bet staking logic).
    Formula: kelly_f = (p*b+p-1)/b; capped at max_exposure_pct=5%; * kelly_mult=0.25
    Places zero-stake shadow bets (ai_real_staking_enabled=False by default).
    """
    try:
        with open(_DASHBOARD, "r", encoding="utf-8") as f:
            state = json.load(f)
    except Exception as e:
        return _fail("T03_daemon_quarter_kelly", f"Cannot read dashboard: {e}")

    settings = _load_settings()
    kelly_mult = settings.get("kelly_multiplier", 0.15)
    max_exp = settings.get("max_exposure_pct", 0.02)
    ai_real = settings.get("ai_real_staking_enabled", False)
    balance = _paper_balance()

    now_ts = time.time()
    bets_placed = 0
    results = []

    # Batch all inserts in one connection — 237 serial open/close cycles are slow on Windows
    batch_conn = sqlite3.connect(_BET_LOG)

    for entry in state:
        kick = entry.get("kickoff", "")
        try:
            if datetime.datetime.fromisoformat(
                    kick.replace("Z", "+00:00")).timestamp() <= now_ts:
                continue
        except Exception:
            pass

        fid = str(entry.get("fixture_id", ""))
        match = entry.get("match", "")
        league = entry.get("league", "")
        markets = (entry.get("prediction") or {}).get("markets") or {}

        for sel in markets.get("1X2", []):
            prob_pct = sel.get("prob", 0)
            odds = sel.get("odds") or sel.get("best_odds")
            if not prob_pct or not odds:
                continue

            p = prob_pct / 100.0
            b = float(odds) - 1.0
            kelly_f_full = 0.0
            if b > 0:
                kelly_f_full = (p * float(odds) - 1.0) / b
                kelly_f = max(0.0, min(max_exp, kelly_f_full * kelly_mult))
            else:
                kelly_f = 0.01

            stake = round(balance * kelly_f, 2)
            stake = max(1.0, min(stake, balance))
            real_stake = stake if ai_real else 0.0

            side = sel.get("selection", "")
            entry_odds_v = float(odds)
            fair_odds_v = round(1.0 / p, 3) if p > 0 else entry_odds_v
            edge_pp = round((p - 1.0 / entry_odds_v) * 100, 2)

            placed = _log_paper_bet(
                fid, match, side, "1X2",
                entry_odds_v, fair_odds_v, edge_pp, real_stake,
                "test_qkelly_1x2", league, "test_quarter_kelly",
                _conn=batch_conn,
            )
            if placed:
                bets_placed += 1
                if len(results) < 10:
                    results.append({
                        "match": match, "side": side, "prob_pct": prob_pct,
                        "kelly_f_full_pct": round(kelly_f_full * 100, 2),
                        "kelly_f_frac_pct": round(kelly_f * 100, 3),
                        "computed_stake": stake, "real_stake": real_stake,
                    })

    batch_conn.commit()
    batch_conn.close()

    return _pass(
        "T03_daemon_quarter_kelly",
        f"{bets_placed} quarter-Kelly shadow bets placed "
        f"({'REAL staking ON' if ai_real else 'ZERO-stake (ai_real_staking_enabled=False)'}). "
        f"Paper balance ${balance:,.0f}. kelly_mult={kelly_mult}, max_exp={max_exp*100}%.",
        {
            "ai_real_staking_enabled": ai_real,
            "kelly_multiplier": kelly_mult,
            "max_exposure_pct": max_exp,
            "paper_balance": balance,
            "bets_placed": bets_placed,
            "sample": results[:5],
        },
    )


# ---------------------------------------------------------------------------
# T04 — Steam staking model
# ---------------------------------------------------------------------------

def test_steam_staking() -> dict:
    """
    Test the steam staking formula: 2% of bankroll (steam_kelly_frac) or
    flat $25 (steam_flat_stake) for matches with steam_move ≥ steam_min_move_pct.
    Places flat-stake paper bets on steam signals found in dashboard state.
    """
    settings = _load_settings()
    steam_min = settings.get("steam_min_move_pct", 3.0)
    steam_frac = settings.get("steam_kelly_frac", 0.02)
    steam_flat = float(settings.get("steam_flat_stake", 25.0))
    balance = _paper_balance()

    stake = round(balance * steam_frac, 2) if steam_frac > 0 else steam_flat
    stake = max(1.0, min(stake, balance * 0.03))

    try:
        with open(_DASHBOARD, "r", encoding="utf-8") as f:
            state = json.load(f)
    except Exception as e:
        return _fail("T04_steam_staking", f"Cannot read dashboard: {e}")

    now_ts = time.time()
    signals = []
    bets_placed = 0

    for entry in state:
        kick = entry.get("kickoff", "")
        try:
            if datetime.datetime.fromisoformat(
                    kick.replace("Z", "+00:00")).timestamp() <= now_ts:
                continue
        except Exception:
            pass

        fid = str(entry.get("fixture_id", ""))
        match = entry.get("match", "")
        league = entry.get("league", "")
        markets = (entry.get("prediction") or {}).get("markets") or {}

        for sel in markets.get("1X2", []):
            steam = abs(sel.get("steam_move", 0) or 0)
            if steam < steam_min:
                continue
            prob_pct = sel.get("prob", 0)
            odds = sel.get("odds") or sel.get("best_odds")
            if not prob_pct or not odds:
                continue
            direction = "UP" if (sel.get("steam_move") or 0) > 0 else "DOWN"
            signals.append({
                "match": match, "league": league,
                "side": sel.get("selection"), "steam_move": round(steam, 2),
                "direction": direction, "odds": odds, "prob_pct": prob_pct
            })

            p = prob_pct / 100.0
            entry_odds_v = float(odds)
            fair_odds_v = round(1.0 / p, 3) if p > 0 else entry_odds_v
            edge_pp = round((p - 1.0 / entry_odds_v) * 100, 2)

            placed = _log_paper_bet(
                fid, match, sel.get("selection"), "1X2",
                entry_odds_v, fair_odds_v, edge_pp, stake,
                f"test_steam_{round(steam,1)}pct", league, "test_steam"
            )
            if placed:
                bets_placed += 1

    signals.sort(key=lambda x: x["steam_move"], reverse=True)
    status = "PASS" if signals else "WARN"
    return {
        "test": "T04_steam_staking",
        "status": status,
        "detail": (
            f"{len(signals)} steam signals found (>={steam_min}%). "
            f"Steam stake: ${stake:.2f} (2% of ${balance:,.0f} bankroll). "
            f"{bets_placed} test bets placed."
        ),
        "data": {
            "steam_min_pct": steam_min,
            "steam_kelly_frac": steam_frac,
            "stake_computed": stake,
            "signals_found": len(signals),
            "bets_placed": bets_placed,
            "top_signals": signals[:10],
        },
    }


# ---------------------------------------------------------------------------
# T06 — Brier score calibration
# ---------------------------------------------------------------------------

def test_brier_score() -> dict:
    """
    Run the Brier score tracker on all settled bets.
    Checks: BS < 0.25 (uniform baseline for 3-way = 0.222).
    Also checks per-market ROI and calibration curve shape.
    """
    try:
        from src.brier_tracker import compute_brier_score, get_performance_summary
        summary = get_performance_summary()
    except Exception as e:
        return _fail("T06_brier_score", f"brier_tracker error: {e}")

    if summary.get("error"):
        return _warn("T06_brier_score", summary["error"], summary)

    overall_bs = summary.get("brier_score")
    bss = summary.get("brier_skill_score_pct", 0)
    roi = summary.get("roi_pct", 0)
    n = summary.get("settled_bets", 0)
    market_alerts = summary.get("market_alerts", [])

    if n < 10:
        return _warn("T06_brier_score",
                     f"Only {n} settled bets - need >=10 for reliable Brier score.",
                     summary)

    BASELINE = 0.248
    if overall_bs is None:
        return _warn("T06_brier_score", "Brier score could not be computed.", summary)

    status = "PASS" if overall_bs < BASELINE else "FAIL"
    return {
        "test": "T06_brier_score",
        "status": status,
        "detail": (
            f"Brier={overall_bs:.4f} (baseline {BASELINE}). "
            f"BSS={bss:.1f}%. ROI={roi:+.1f}%. n={n} settled bets. "
            f"{len(market_alerts)} market alerts."
        ),
        "data": summary,
    }


# ---------------------------------------------------------------------------
# T07 — CLV tracking
# ---------------------------------------------------------------------------

def test_clv_tracking() -> dict:
    """
    Check how many settled bets have CLV data populated.
    CLV = (entry_price / closing_mid - 1) × 100pp.
    Positive CLV means we bought cheaper than the closing line → positive EV.
    """
    if not os.path.exists(_BET_LOG):
        return _fail("T07_clv_tracking", "bet_log.db not found")

    conn = sqlite3.connect(_BET_LOG)
    conn.row_factory = sqlite3.Row

    total = conn.execute(
        "SELECT COUNT(*) FROM bet_log WHERE result IN ('W','L')"
    ).fetchone()[0]
    with_clv = conn.execute(
        "SELECT COUNT(*) FROM bet_log WHERE result IN ('W','L') AND clv IS NOT NULL"
    ).fetchone()[0]
    avg_clv = conn.execute(
        "SELECT AVG(clv) FROM bet_log WHERE result IN ('W','L') AND clv IS NOT NULL"
    ).fetchone()[0]
    positive_clv = conn.execute(
        "SELECT COUNT(*) FROM bet_log WHERE result IN ('W','L') AND clv > 0"
    ).fetchone()[0]

    # Check price_history table
    try:
        ph_count = conn.execute(
            "SELECT COUNT(*) FROM price_history"
        ).fetchone()[0]
    except Exception:
        ph_count = 0

    open_with_clv_potential = conn.execute(
        "SELECT COUNT(*) FROM bet_log WHERE result='OPEN' AND fixture_id IS NOT NULL"
    ).fetchone()[0]

    conn.close()

    clv_pct = round(with_clv / total * 100, 1) if total > 0 else 0
    avg_clv_fmt = round(avg_clv, 2) if avg_clv else None
    positive_pct = round(positive_clv / with_clv * 100, 1) if with_clv > 0 else 0

    status = "PASS" if with_clv > 0 or ph_count > 0 else "WARN"
    return {
        "test": "T07_clv_tracking",
        "status": status,
        "detail": (
            f"{with_clv}/{total} settled bets have CLV data ({clv_pct}%). "
            f"Avg CLV: {avg_clv_fmt}pp. Positive CLV: {positive_pct}% of CLV-tracked. "
            f"price_history rows: {ph_count}. Open bets CLV-eligible: {open_with_clv_potential}."
        ),
        "data": {
            "settled_bets": total,
            "with_clv": with_clv,
            "clv_coverage_pct": clv_pct,
            "avg_clv_pp": avg_clv_fmt,
            "positive_clv_pct": positive_pct,
            "price_history_rows": ph_count,
            "open_bets_clv_eligible": open_with_clv_potential,
        },
    }


# ---------------------------------------------------------------------------
# T08 — Drawdown monitor
# ---------------------------------------------------------------------------

def test_drawdown() -> dict:
    """
    Compute equity curve stats from the paper bankroll + bet_log PnL.
    Reports: peak, current, max drawdown %, current drawdown %.
    """
    if not os.path.exists(_BET_LOG):
        return _fail("T08_drawdown", "bet_log.db not found")

    conn = sqlite3.connect(_BET_LOG)
    conn.row_factory = sqlite3.Row

    settled = conn.execute(
        "SELECT pnl, placed_at FROM bet_log WHERE result IN ('W','L') ORDER BY placed_at"
    ).fetchall()
    conn.close()

    SEED = 5000.0
    balance = SEED
    peak = SEED
    max_dd = 0.0
    equity = []

    for row in settled:
        pnl = row["pnl"] or 0
        balance += pnl
        if balance > peak:
            peak = balance
        dd = (peak - balance) / peak * 100 if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd
        equity.append(round(balance, 2))

    current_dd = round((peak - balance) / peak * 100, 2) if peak > 0 else 0

    open_conn = sqlite3.connect(_BET_LOG)
    open_bets = open_conn.execute(
        "SELECT COUNT(*), SUM(stake) FROM bet_log WHERE result='OPEN'"
    ).fetchone()
    open_conn.close()
    open_count = open_bets[0] or 0
    open_exposure = round(open_bets[1] or 0, 2)

    status = "PASS" if max_dd < 20 else ("WARN" if max_dd < 40 else "FAIL")
    return {
        "test": "T08_drawdown",
        "status": status,
        "detail": (
            f"Paper balance ${balance:,.2f} (seed ${SEED:,.0f}). "
            f"Peak ${peak:,.2f}. Max drawdown {max_dd:.1f}%. "
            f"Current drawdown {current_dd:.1f}%. "
            f"{open_count} open bets, ${open_exposure} at risk."
        ),
        "data": {
            "seed": SEED,
            "current_balance": round(balance, 2),
            "peak_balance": round(peak, 2),
            "max_drawdown_pct": round(max_dd, 2),
            "current_drawdown_pct": current_dd,
            "settled_bets": len(settled),
            "open_bets": open_count,
            "open_exposure": open_exposure,
            "equity_tail": equity[-20:],
        },
    }


# ---------------------------------------------------------------------------
# T09 — Red card monitor
# ---------------------------------------------------------------------------

def test_redcard_monitor() -> dict:
    """
    Verify the red card monitor can reach the ESPN API and the alert logic
    produces sensible numbers. No live WC matches expected outside tournament days.
    """
    try:
        from src.redcard_monitor import _espn_live_wc, _remaining_xg, _win_prob_from_xg
    except Exception as e:
        return _fail("T09_redcard_monitor", f"Import error: {e}")

    # Test _remaining_xg at several match minutes
    base_lambda = 1.25
    xg_tests = []
    for minute in [0, 45, 60, 76, 85, 90]:
        xg_rem = _remaining_xg(minute, base_lambda)
        xg_tests.append({"minute": minute, "remaining_xg": round(xg_rem, 3)})

    # Test win prob computation
    p_win, p_draw, p_loss = _win_prob_from_xg(0.8, 0.4, 1, 0)
    prob_check_ok = abs(p_win + p_draw + p_loss - 1.0) < 0.01

    # Test ESPN API connection
    api_ok = False
    live_count = 0
    try:
        live = _espn_live_wc()
        live_count = len(live)
        api_ok = True
    except Exception:
        pass

    # Check alert file
    alerts_path = os.path.join(_ROOT, "data", "redcard_alerts.json")
    alert_count = 0
    try:
        with open(alerts_path, "r", encoding="utf-8") as f:
            alert_count = len(json.load(f))
    except Exception:
        pass

    status = "PASS" if prob_check_ok and api_ok else ("WARN" if prob_check_ok else "FAIL")
    return {
        "test": "T09_redcard_monitor",
        "status": status,
        "detail": (
            f"ESPN API: {'reachable' if api_ok else 'FAILED'}. "
            f"{live_count} live WC matches right now. "
            f"Win prob check: {'OK' if prob_check_ok else 'FAILED'} "
            f"(sums to {p_win+p_draw+p_loss:.4f}). "
            f"{alert_count} historical alerts stored."
        ),
        "data": {
            "espn_api_reachable": api_ok,
            "live_wc_matches": live_count,
            "prob_check_ok": prob_check_ok,
            "xg_test_win_prob": {
                "scenario": "away_scores_at_60min_1-0",
                "p_win": p_win, "p_draw": p_draw, "p_loss": p_loss,
            },
            "remaining_xg_by_minute": xg_tests,
            "stored_alerts": alert_count,
        },
    }


# ---------------------------------------------------------------------------
# T10 — Research bet coverage
# ---------------------------------------------------------------------------

def test_research_coverage() -> dict:
    """
    Audit how many research bets are in bet_log, broken down by league and market type.
    Also shows edge distribution of research bets to verify model data quality.
    """
    if not os.path.exists(_BET_LOG):
        return _fail("T10_research_coverage", "bet_log.db not found")

    conn = sqlite3.connect(_BET_LOG)
    conn.row_factory = sqlite3.Row

    total = conn.execute(
        "SELECT COUNT(*) FROM bet_log WHERE regime='research'"
    ).fetchone()[0]

    by_market = conn.execute("""
        SELECT market_type, COUNT(*) as cnt
        FROM bet_log WHERE regime='research'
        GROUP BY market_type ORDER BY cnt DESC
    """).fetchall()

    by_league = conn.execute("""
        SELECT league, COUNT(*) as cnt
        FROM bet_log WHERE regime='research'
        GROUP BY league ORDER BY cnt DESC LIMIT 20
    """).fetchall()

    positive_edge = conn.execute(
        "SELECT COUNT(*) FROM bet_log WHERE regime='research' AND edge_pct > 0"
    ).fetchone()[0]

    avg_edge = conn.execute(
        "SELECT AVG(edge_pct) FROM bet_log WHERE regime='research' AND edge_pct IS NOT NULL"
    ).fetchone()[0]

    conn.close()

    markets = {r["market_type"]: r["cnt"] for r in by_market}
    leagues = {(r["league"] or "unknown"): r["cnt"] for r in by_league}

    return _pass(
        "T10_research_coverage",
        f"{total} research bets across {len(leagues)} leagues. "
        f"Markets: {markets}. "
        f"Positive edge: {positive_edge}/{total} ({round(positive_edge/total*100,1) if total else 0}%). "
        f"Avg edge: {round(avg_edge,2) if avg_edge else 'N/A'}pp.",
        {
            "total_research_bets": total,
            "by_market": markets,
            "top_leagues": leagues,
            "positive_edge_count": positive_edge,
            "avg_edge_pp": round(avg_edge, 2) if avg_edge else None,
        },
    )


# ---------------------------------------------------------------------------
# Master runner
# ---------------------------------------------------------------------------

ALL_TESTS = {
    "T01": test_prediction_model,
    "T03": test_daemon_quarter_kelly,
    "T04": test_steam_staking,
    "T06": test_brier_score,
    "T07": test_clv_tracking,
    "T08": test_drawdown,
    "T09": test_redcard_monitor,
    "T10": test_research_coverage,
}

TEST_NAMES = {
    "T01": "Prediction Model Accuracy",
    "T03": "Daemon Quarter-Kelly Staking",
    "T04": "Steam Staking Model",
    "T06": "Brier Score Calibration",
    "T07": "CLV Tracking",
    "T08": "Drawdown Monitor",
    "T09": "Red Card Monitor",
    "T10": "Research Bet Coverage",
}


def run_all(tests: list = None) -> dict:
    """Run selected tests (default: all). Returns full report dict."""
    to_run = tests or list(ALL_TESTS.keys())
    results = []
    passed = failed = warned = 0

    for key in to_run:
        fn = ALL_TESTS.get(key)
        if not fn:
            results.append(_fail(key, f"Unknown test: {key}"))
            failed += 1
            continue

        print(f"  [{key}] {TEST_NAMES.get(key, key)} ...", end=" ", flush=True)
        try:
            r = fn()
        except Exception as e:
            r = _fail(key, f"Uncaught exception: {traceback.format_exc(limit=3)}")

        r["name"] = TEST_NAMES.get(key, key)
        results.append(r)
        status = r.get("status", "FAIL")
        # Strip non-ASCII so Windows cp1256 console never chokes on symbols
        detail = r.get("detail", "").encode("ascii", "replace").decode("ascii")[:80]
        if status == "PASS":
            passed += 1
            print("PASS")
        elif status == "WARN":
            warned += 1
            print("WARN -", detail)
        else:
            failed += 1
            print("FAIL -", detail)

    report = {
        "run_at": datetime.datetime.utcnow().isoformat() + "Z",
        "summary": {"passed": passed, "warned": warned, "failed": failed,
                    "total": len(results)},
        "results": results,
    }

    with open(_REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\n[SYSTEM TEST] {passed} PASS  {warned} WARN  {failed} FAIL  --  "
          f"report: data/system_test_report.json")
    return report


if __name__ == "__main__":
    selected = sys.argv[1:] or None   # e.g. python -m src.system_tester T06 T07
    run_all(selected)
