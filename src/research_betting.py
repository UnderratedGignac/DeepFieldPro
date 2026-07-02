"""
research_betting.py — Real + paper bet sweep for research data collection.

WC fixtures  → real Stair AI / Polymarket orders (H/D/A) via place_order(),
               Kelly-sized from live wallet balance.
Other leagues → real paper bets (result='OPEN', settle + track P&L),
               Kelly-sized from paper bankroll.
O/U and BTTS → paper only (no Polymarket market), result='OPEN', Kelly-sized.

Markets covered per match:
  1X2  — Home / Draw / Away
  O/U  — Over 2.5 / Under 2.5
  BTTS — Both Teams to Score / Not

Deduplication: data/research_bet_keys.json — never bets same fixture+market+side twice.

Usage:
  from src.research_betting import run_research_sweep
  run_research_sweep()                # all leagues (default)
  run_research_sweep(source='wc')     # WC only
  run_research_sweep(source='both')   # WC real + all leagues paper

API:
  POST /arena/api/research_sweep             → all leagues
  POST /arena/api/research_sweep?source=wc  → WC only
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
# Source A: WC fixtures — real Stair AI orders via place_order()
# ---------------------------------------------------------------------------

def _sweep_wc(existing_keys: set, new_keys: set, verbose: bool) -> tuple:
    """
    Place REAL Stair AI orders for all WC 1X2 outcomes (Kelly-sized from wallet).
    O/U and BTTS have no Polymarket market — logged as settling paper bets.
    """
    new_bets = 0
    skipped = 0
    matches = set()

    try:
        from src.arena_betting import (
            analyze, place_order, get_wallet,
            _wallet_kelly_size, _ap2_set_ctx,
        )
    except Exception as e:
        print(f"[RESEARCH] arena_betting import error: {e}")
        return new_bets, skipped, matches

    # Wallet balance for Kelly sizing
    wallet = get_wallet()
    wallet_balance = float(wallet.get("available_balance_usdc", 0)) if wallet else 0.0

    try:
        candidates = analyze(limit=200, conf_min=0.0, edge_min=-99.0)
    except Exception as e:
        print(f"[RESEARCH] WC analyze() error: {e}")
        return new_bets, skipped, matches

    now_ts = time.time()

    for c in candidates:
        fid = str(c.get("fixture_id") or c.get("sportmonks_fixture_id", ""))
        if not fid:
            continue
        ko = c.get("kickoff_ts", 0)
        if ko and ko <= now_ts:
            continue

        match_name = c.get("match", "")
        outcome = c.get("outcome", "")          # "home" / "draw" / "away"
        market_mid = c.get("market_mid") or 0.0
        model_prob = c.get("model_prob") or 0.0
        edge = c.get("edge_pp", 0.0) / 100.0 if c.get("edge_pp") else c.get("edge", 0.0)
        team_code = c.get("team_code")
        limit_price = c.get("limit_price") or market_mid

        if not outcome or not team_code:
            continue

        # ── 1X2 real order ──────────────────────────────────────────────────
        key = f"{fid}:1X2:{outcome}"
        if key in existing_keys or key in new_keys:
            skipped += 1
            continue

        size = _wallet_kelly_size(edge, market_mid, wallet_balance)

        try:
            _ap2_set_ctx(
                model_prob=model_prob,
                mid=market_mid,
                edge=edge,
                wallet_balance=wallet_balance,
            )
            sc, resp = place_order(fid, team_code, size, limit_price)
            ok = sc in (200, 201)
        except Exception as ex:
            print(f"[RESEARCH] place_order error {match_name} {outcome}: {ex}")
            ok = False

        new_keys.add(key)
        new_bets += 1
        status = "REAL" if ok else "SHADOW"
        if verbose:
            print(
                f"[RESEARCH][WC] {match_name} | 1X2 {outcome} @ {round(1/market_mid,3) if market_mid else '?'}"
                f" | size ${size:.2f} | {status}"
            )

    # ── O/U + BTTS: paper only (no Polymarket market) ───────────────────────
    paper_balance = _paper_bankroll()
    s = _load_settings()
    kelly_mult = float(s.get("kelly_multiplier", 0.15))
    max_exp = float(s.get("max_exposure_pct", 0.02))

    # Collect unique fixtures already seen
    seen_fids: set = set()
    for c in candidates:
        fid = str(c.get("fixture_id") or "")
        ko = c.get("kickoff_ts", 0)
        if not fid or (ko and ko <= now_ts):
            continue
        if fid in seen_fids:
            continue
        seen_fids.add(fid)
        match_name = c.get("match", "")

        ou_pairs = [("Over 2.5", 0.48, "over_25"), ("Under 2.5", 0.52, "under_25")]
        for ou_label, model_ou_p, ou_tag in ou_pairs:
            key = f"{fid}:OU25:{ou_tag}"
            if key in existing_keys or key in new_keys:
                skipped += 1
                continue
            entry_odds_val = round(1.0 / model_ou_p, 3)
            stake = _kelly_stake(model_ou_p, entry_odds_val, paper_balance, kelly_mult, max_exp)
            _log_bet(fid, match_name, ou_label, "Over/Under 2.5",
                     entry_odds_val, entry_odds_val, 0.0, stake,
                     f"research_{ou_tag}", "FIFA World Cup", result="OPEN")
            new_keys.add(key)
            new_bets += 1
            if verbose:
                print(f"[RESEARCH][WC] {match_name} | O/U {ou_label} @ {entry_odds_val} | paper ${stake:.2f}")

        btts_pairs = [("BTTS Yes", 0.44, "btts_yes"), ("BTTS No", 0.56, "btts_no")]
        for btts_label, model_btts_p, btts_tag in btts_pairs:
            key = f"{fid}:BTTS:{btts_tag}"
            if key in existing_keys or key in new_keys:
                skipped += 1
                continue
            entry_odds_val = round(1.0 / model_btts_p, 3)
            stake = _kelly_stake(model_btts_p, entry_odds_val, paper_balance, kelly_mult, max_exp)
            _log_bet(fid, match_name, btts_label, "BTTS",
                     entry_odds_val, entry_odds_val, 0.0, stake,
                     f"research_{btts_tag}", "FIFA World Cup", result="OPEN")
            new_keys.add(key)
            new_bets += 1
            if verbose:
                print(f"[RESEARCH][WC] {match_name} | BTTS {btts_label} @ {entry_odds_val} | paper ${stake:.2f}")

        matches.add(match_name)

    return new_bets, skipped, matches


# ---------------------------------------------------------------------------
# Source B: all leagues from todays_dashboard_state.json (paper, settling)
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


def run_research_sweep(source: str = "all", verbose: bool = True) -> dict:
    """
    Place research bets across upcoming fixtures.

    source: 'all'  — all leagues (paper, settling)
            'wc'   — WC only (real Stair AI orders for 1X2 + paper for O/U/BTTS)
            'both' — WC real + all leagues paper
    """
    existing_keys = _load_keys()
    new_keys: set = set()
    total_new = 0
    total_skip = 0
    all_matches: set = set()

    if source in ("wc", "both"):
        nb, sk, ms = _sweep_wc(existing_keys, new_keys, verbose)
        total_new += nb
        total_skip += sk
        all_matches |= ms

    if source in ("all", "both"):
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
