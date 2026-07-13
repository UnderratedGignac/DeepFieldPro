"""
research_betting.py — Paper bet sweep for research data collection.

All leagues → paper bets (result='OPEN', settle + track P&L),
              Kelly-sized from paper bankroll.

Markets covered per match:
  1X2  — Home / Draw / Away
  O/U  — Over 2.5 / Under 2.5
  BTTS — Both Teams to Score / Not

Deduplication: data/research_bet_keys.json — never bets same fixture+market+side twice.

Usage:
  from src.research_betting import run_research_sweep
  run_research_sweep()
"""

import os
import json
import sqlite3
import uuid
import time
import datetime

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BET_LOG = os.path.join(_ROOT, "data", "bet_log.db")
_KEYS_FILE = os.path.join(_ROOT, "data", "research_bet_keys.json")
_DASHBOARD_STATE = os.path.join(_ROOT, "data", "todays_dashboard_state.json")
_SETTINGS_FILE = os.path.join(_ROOT, "data", "settings.json")
_BANKROLL_DB = os.path.join(_ROOT, "data", "bankroll.db")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_keys() -> set:
    try:
        with open(_KEYS_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def _save_keys(keys: set):
    with open(_KEYS_FILE, "w", encoding="utf-8") as f:
        json.dump(list(keys), f)


def _load_settings() -> dict:
    try:
        with open(_SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _paper_bankroll() -> float:
    """Return current paper bankroll balance."""
    try:
        conn = sqlite3.connect(_BANKROLL_DB)
        bal = conn.execute(
            "SELECT current_balance FROM bankroll ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        if bal:
            return float(bal[0])
    except Exception:
        pass
    # Fallback: use last bet_log balance-adjacent estimate
    try:
        conn = sqlite3.connect(_BET_LOG)
        row = conn.execute(
            "SELECT SUM(pnl) FROM bet_log WHERE result NOT IN ('OPEN','VOID')"
        ).fetchone()
        conn.close()
        return max(100.0, 5000.0 + (row[0] or 0.0))
    except Exception:
        return 1000.0


def _kelly_stake(prob: float, odds: float, balance: float,
                 kelly_mult: float = 0.15, max_exp_pct: float = 0.02) -> float:
    """Quarter-Kelly stake capped at max_exp_pct of balance."""
    if odds <= 1.0 or prob <= 0 or balance <= 0:
        return 1.0
    kelly_f = max(0.0, (prob * odds - 1.0) / (odds - 1.0))
    stake = kelly_f * kelly_mult * balance
    cap = balance * max_exp_pct
    return round(max(1.0, min(stake, cap)), 2)


# ---------------------------------------------------------------------------
# DB writer — paper bets that settle and track P&L
# DISABLED: research sweep bets pollute the bet log with all-outcome batches.
# Real paper bets are placed by log_ai_bet() in the daemon (one best pick/match).
# ---------------------------------------------------------------------------

_BET_LOG_ENABLED = False  # set True only for deliberate research runs


def _log_bet(fixture_id, match_name, side, market_type, entry_odds,
             fair_odds, edge_pct, stake, signal_name, league="",
             regime="research", result="OPEN"):
    if not _BET_LOG_ENABLED:
        return
    conn = sqlite3.connect(_BET_LOG)
    line_val = 2.5 if "2.5" in str(market_type) else (3.0 if "3.0" in str(market_type) else None)
    conn.execute("""
        INSERT OR REPLACE INTO bet_log
          (bet_id, match_id, player_id, market_type, line, side,
           entry_odds, fair_odds, edge_pct, stake, book,
           placed_at, result, pnl, regime, bet_source, signal_name, league)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,datetime('now'),?,?,?,?,?,?)
    """, (
        str(uuid.uuid4()),
        str(fixture_id),
        side,
        market_type,
        line_val,
        side,
        entry_odds,
        fair_odds,
        edge_pct,
        stake,
        "PAPER",
        result,
        0.0,
        regime,
        "RESEARCH",
        signal_name,
        league,
    ))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# All leagues from todays_dashboard_state.json (paper, settling)
# ---------------------------------------------------------------------------

def _sweep_dashboard(existing_keys: set, new_keys: set, verbose: bool) -> tuple:
    """
    Place real settling paper bets across all leagues.
    result='OPEN' — settlement engine picks these up and tracks P&L.
    Stakes are Kelly-sized from paper bankroll.
    """
    new_bets = 0
    skipped = 0
    matches = set()

    try:
        with open(_DASHBOARD_STATE, "r", encoding="utf-8") as f:
            state = json.load(f)
    except Exception as e:
        print(f"[RESEARCH] Cannot read dashboard state: {e}")
        return new_bets, skipped, matches

    s = _load_settings()
    kelly_mult = float(s.get("kelly_multiplier", 0.15))
    max_exp = float(s.get("max_exposure_pct", 0.02))
    balance = _paper_bankroll()

    now_ts = time.time()

    for entry in state:
        fid = str(entry.get("fixture_id", ""))
        match_name = entry.get("match", "")
        league = entry.get("league", "")
        kickoff_str = entry.get("kickoff", "")

        if not fid or not match_name:
            continue

        if kickoff_str:
            try:
                ko_ts = datetime.datetime.fromisoformat(
                    kickoff_str.replace("Z", "+00:00")
                ).timestamp()
                if ko_ts <= now_ts:
                    continue
            except Exception:
                pass

        prediction = entry.get("prediction") or {}
        markets = prediction.get("markets") or {}

        # ── 1X2 ──────────────────────────────────────────────────────────────
        for sel in markets.get("1X2", []):
            raw_sel = sel.get("selection", "")
            prob_pct = sel.get("prob", 0)
            odds = sel.get("odds") or sel.get("best_odds")
            ev = sel.get("ev") or sel.get("ev_best") or 0.0

            if not raw_sel or not prob_pct or not odds:
                continue

            side = raw_sel.lower().split("(")[0].strip()
            if "home" in side:
                side = "home"
            elif "draw" in side:
                side = "draw"
            elif "away" in side:
                side = "away"

            key = f"{fid}:1X2:{side}"
            if key in existing_keys or key in new_keys:
                skipped += 1
                continue

            model_p = prob_pct / 100.0
            entry_odds = round(float(odds), 3)
            fair_odds_val = round(1.0 / model_p, 3) if model_p > 0 else entry_odds
            edge_pct = round(ev * 100, 2) if abs(ev) < 1 else round(ev, 2)
            stake = _kelly_stake(model_p, entry_odds, balance, kelly_mult, max_exp)

            _log_bet(fid, match_name, side, "1X2",
                     entry_odds, fair_odds_val, edge_pct, stake,
                     f"research_1x2_{side}", league, result="OPEN")
            new_keys.add(key)
            new_bets += 1
            if verbose:
                print(
                    f"[RESEARCH] {match_name} ({league}) | 1X2 {side} @ {entry_odds}"
                    f" (EV {edge_pct:+.1f}%) | paper ${stake:.2f}"
                )

        # ── O/U 2.5 ──────────────────────────────────────────────────────────
        for sel in markets.get("Over/Under 2.5", []):
            raw_sel = sel.get("selection", "")
            prob_pct = sel.get("prob", 0)
            odds = sel.get("odds") or sel.get("best_odds")
            ev = sel.get("ev") or sel.get("ev_best") or 0.0

            if not raw_sel or not prob_pct:
                continue

            side = "over_25" if "over" in raw_sel.lower() else "under_25"
            key = f"{fid}:OU25:{side}"
            if key in existing_keys or key in new_keys:
                skipped += 1
                continue

            model_p = prob_pct / 100.0
            entry_odds_val = round(float(odds), 3) if odds else round(1.0 / model_p, 3)
            fair_odds_val = round(1.0 / model_p, 3) if model_p > 0 else entry_odds_val
            edge_pct = round(ev * 100, 2) if abs(ev) < 1 else round(ev, 2)
            stake = _kelly_stake(model_p, entry_odds_val, balance, kelly_mult, max_exp)

            _log_bet(fid, match_name, raw_sel, "Over/Under 2.5",
                     entry_odds_val, fair_odds_val, edge_pct, stake,
                     f"research_{side}", league, result="OPEN")
            new_keys.add(key)
            new_bets += 1
            if verbose:
                print(f"[RESEARCH] {match_name} ({league}) | O/U {raw_sel} @ {entry_odds_val} | paper ${stake:.2f}")

        # ── BTTS ─────────────────────────────────────────────────────────────
        for sel in markets.get("BTTS", []):
            raw_sel = sel.get("selection", "")
            prob_pct = sel.get("prob", 0)
            odds = sel.get("odds")
            ev = sel.get("ev") or 0.0

            if not raw_sel or not prob_pct:
                continue

            side = "btts_yes" if "yes" in raw_sel.lower() else "btts_no"
            key = f"{fid}:BTTS:{side}"
            if key in existing_keys or key in new_keys:
                skipped += 1
                continue

            model_p = prob_pct / 100.0
            entry_odds_val = round(float(odds), 3) if odds else round(1.0 / model_p, 3)
            fair_odds_val = round(1.0 / model_p, 3) if model_p > 0 else entry_odds_val
            edge_pct = round(ev * 100, 2) if abs(ev) < 1 else round(ev, 2)
            stake = _kelly_stake(model_p, entry_odds_val, balance, kelly_mult, max_exp)

            _log_bet(fid, match_name, raw_sel, "BTTS",
                     entry_odds_val, fair_odds_val, edge_pct, stake,
                     f"research_{side}", league, result="OPEN")
            new_keys.add(key)
            new_bets += 1
            if verbose:
                print(f"[RESEARCH] {match_name} ({league}) | BTTS {raw_sel} @ {entry_odds_val} | paper ${stake:.2f}")

        matches.add(f"{match_name} ({league})")

    return new_bets, skipped, matches


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def clear_keys():
    """Wipe the dedup key file so the next sweep re-places all bets."""
    _save_keys(set())
    print("[RESEARCH] Dedup keys cleared.")


def run_research_sweep(verbose: bool = True) -> dict:
    """Place paper research bets across upcoming fixtures (all leagues)."""
    existing_keys = _load_keys()
    new_keys: set = set()
    total_new = 0
    total_skip = 0
    all_matches: set = set()

    nb, sk, ms = _sweep_dashboard(existing_keys, new_keys, verbose)
    total_new += nb
    total_skip += sk
    all_matches |= ms

    _save_keys(existing_keys | new_keys)

    result = {
        "new_bets": total_new,
        "skipped": total_skip,
        "matches": sorted(all_matches),
        "total_keys_tracked": len(existing_keys) + len(new_keys),
    }
    print(f"[RESEARCH] Sweep complete: {total_new} new bets, {total_skip} skipped")
    return result
