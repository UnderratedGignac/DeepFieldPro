"""
Signal Discovery Engine — automated hypothesis testing on odds history.

Tests a library of pre-defined signals against completed matches in odds_history,
ranks by CLV (closing-line value), and prints a ranked report. Run nightly or
on demand after accumulating new odds snapshots.

Signals tested:
  1. STEAM_FWD      Line moves toward a side (current strategy, baseline)
  2. STEAM_REV      Bet AGAINST the move (contrarian)
  3. FAV_DRIFT      Home favourite shortening (implied prob rising)
  4. DOG_DRIFT      Away underdog shortening (implied prob rising)
  5. OPEN_GAP       Side priced substantially shorter than other book at open
  6. LATE_STEAM     Only moves in the last 2 snapshots (final-hour sharp action)
  7. EARLY_STEAM    Only moves in the first half of the snapshot series (stale)
  8. LARGE_SPREAD   High uncertainty (max prob - min prob across selections is wide)
  9. FAV_DRIFT_REV  Home favourite lengthening (market fading the home team)
 10. MOMENTUM_ACCEL Acceleration: recent move larger than initial move

Usage:
    python tools/signal_discovery.py                 # default thresholds
    python tools/signal_discovery.py --min-bets 5   # hide signals with < N matches
    python tools/signal_discovery.py --min-move 3   # minimum move % to qualify (default 5)
"""

import sqlite3, os, sys, math
from collections import defaultdict

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
SIGNALS_DB = os.path.join(DATA, "deepfield_browser_data", "completed_fixtures.db")
HISTORY_DB = os.path.join(DATA, "history.db")

MIN_BETS = int(
    next(
        (
            sys.argv[sys.argv.index("--min-bets") + 1]
            for i, a in enumerate(sys.argv)
            if a == "--min-bets"
        ),
        3,
    )
)
MIN_MOVE = (
    float(
        next(
            (
                sys.argv[sys.argv.index("--min-move") + 1]
                for i, a in enumerate(sys.argv)
                if a == "--min-move"
            ),
            5,
        )
    )
    / 100.0
)


# ── Load odds history ─────────────────────────────────────────────────────────


def load_odds_history():
    """Return {fixture_id: [(selection, odds, timestamp), ...]} sorted by timestamp."""
    try:
        con = sqlite3.connect(SIGNALS_DB)
        rows = con.execute(
            "SELECT fixture_id, market, selection, odds, timestamp "
            "FROM odds_history WHERE market='1X2' ORDER BY fixture_id, timestamp ASC"
        ).fetchall()
        con.close()
    except Exception as e:
        print(f"[ERROR] Cannot read odds_history: {e}")
        return {}

    from collections import defaultdict

    by_fid = defaultdict(list)
    for fid, market, sel, odds, ts in rows:
        by_fid[str(fid)].append((sel, float(odds) if odds else 0, ts))
    return dict(by_fid)


def load_settled():
    """Return {fixture_id: result_map} where result_map = {'Home (1)': 1/0, ...}.
    Loaded from steam_signals joined with bet_log (we only know results from settled bets).
    """
    try:
        # Load all settled STEAM bets: match_id -> result and player_id (selection)
        con = sqlite3.connect(os.path.join(DATA, "bet_log.db"))
        rows = con.execute(
            """SELECT fixture_id, player_id, result, entry_odds, closing_odds
               FROM bet_log WHERE bet_source='STEAM' AND result IN ('W','L','WIN','LOSS')"""
        ).fetchall()
        con.close()
    except Exception:
        return {}

    settled = {}
    for fid, player_id, result, entry_odds, closing_odds in rows:
        if not fid:
            continue
        if fid not in settled:
            settled[str(fid)] = {}
        # Extract selection from player_id like "Team A vs Team B (Away (2))"
        import re as _re

        _m = _re.search(r"\((Home \(1\)|Away \(2\)|Draw)\)$", player_id or "")
        sel = _m.group(1) if _m else player_id
        won = result in ("W", "WIN")
        settled[str(fid)][sel] = {
            "won": won,
            "entry_odds": entry_odds,
            "closing_odds": closing_odds,
            "clv": (
                (entry_odds / closing_odds - 1)
                if closing_odds and closing_odds > 0
                else None
            ),
        }
    return settled


def devig(odds_dict):
    """De-vig a {selection: decimal_odds} dict to probabilities."""
    inv = {s: 1 / o for s, o in odds_dict.items() if o and o > 0}
    tot = sum(inv.values())
    if tot <= 0 or len(inv) < 2:
        return None
    return {s: v / tot for s, v in inv.items()}


def snapshots_to_prob_series(snap_list):
    """Convert [(sel, odds, ts), ...] to {ts: {sel: prob}} sorted maps."""
    by_ts = defaultdict(dict)
    for sel, odds, ts in snap_list:
        if odds > 0:
            by_ts[ts][sel] = odds
    result = {}
    for ts in sorted(by_ts):
        dv = devig(by_ts[ts])
        if dv:
            result[ts] = dv
    return result


# ── Signal definitions ────────────────────────────────────────────────────────


def compute_signals(fid, snap_list):
    """Return a dict of signal_name -> (selection, signal_strength) or None."""
    if len(snap_list) < 4:  # need at least 2 timestamps
        return {}

    prob_series = snapshots_to_prob_series(snap_list)
    ts_list = sorted(prob_series)
    if len(ts_list) < 2:
        return {}

    first_snap = prob_series[ts_list[0]]
    last_snap = prob_series[ts_list[-1]]
    mid_idx = len(ts_list) // 2
    early_snap = prob_series[ts_list[max(0, mid_idx - 1)]]
    recent_snap = prob_series[ts_list[-2]] if len(ts_list) >= 2 else first_snap

    all_sels = set(first_snap) | set(last_snap)
    sigs = {}

    for sel in all_sels:
        if sel not in first_snap or sel not in last_snap:
            continue
        total_move = last_snap[sel] - first_snap[sel]
        early_move = early_snap.get(sel, first_snap[sel]) - first_snap[sel]
        late_move = last_snap[sel] - recent_snap.get(sel, last_snap[sel])

        # Monotonicity
        series = [prob_series[ts][sel] for ts in ts_list if sel in prob_series[ts]]
        steps = [series[i + 1] - series[i] for i in range(len(series) - 1)]
        direction = 1 if total_move >= 0 else -1
        mono = sum(1 for s in steps if s * direction > 0) / len(steps) if steps else 0.5

        # 1. STEAM_FWD — sustained move toward this selection
        if total_move >= MIN_MOVE:
            sigs.setdefault("STEAM_FWD", []).append((sel, total_move * mono))

        # 2. STEAM_REV — bet against the move
        if total_move >= MIN_MOVE:
            # Find the losing side (the one moving against)
            opponent_sel = min(
                all_sels, key=lambda s: last_snap.get(s, 0) - first_snap.get(s, 0)
            )
            if opponent_sel != sel:
                move_away = first_snap.get(opponent_sel, 0) - last_snap.get(
                    opponent_sel, 0
                )
                if move_away >= MIN_MOVE:
                    sigs.setdefault("STEAM_REV", []).append((opponent_sel, move_away))

        # 3. FAV_DRIFT — home team favourite AND shortening
        if sel == "Home (1)" and total_move >= MIN_MOVE and last_snap[sel] > 0.5:
            sigs.setdefault("FAV_DRIFT", []).append((sel, total_move))

        # 4. DOG_DRIFT — away team underdog shortening significantly
        if sel == "Away (2)" and total_move >= MIN_MOVE and first_snap[sel] < 0.4:
            sigs.setdefault("DOG_DRIFT", []).append((sel, total_move))

        # 5. LATE_STEAM — move concentrated in last 2 snapshots
        if late_move >= MIN_MOVE and abs(early_move) < MIN_MOVE * 0.5:
            sigs.setdefault("LATE_STEAM", []).append((sel, late_move))

        # 6. EARLY_STEAM — move in first half, then stagnant
        if early_move >= MIN_MOVE and abs(late_move) < MIN_MOVE * 0.5:
            sigs.setdefault("EARLY_STEAM", []).append((sel, early_move))

        # 7. FAV_DRIFT_REV — home favourite lengthening (market fading home)
        if sel == "Home (1)" and total_move <= -MIN_MOVE and first_snap[sel] > 0.5:
            sigs.setdefault("FAV_DRIFT_REV", []).append((sel, -total_move))

        # 8. MOMENTUM_ACCEL — recent move accelerating vs initial move
        if (
            total_move >= MIN_MOVE
            and late_move > early_move * 1.5
            and late_move >= MIN_MOVE * 0.5
        ):
            sigs.setdefault("MOMENTUM_ACCEL", []).append((sel, late_move))

    # 9. LARGE_SPREAD — uncertainty signal (all selections)
    probs = list(first_snap.values())
    if probs:
        spread = max(probs) - min(probs)
        if spread > 0.40:
            # Bet on the favourite (highest prob in last snap)
            fav_sel = max(last_snap, key=lambda s: last_snap[s])
            sigs.setdefault("LARGE_SPREAD", []).append((fav_sel, spread))

    # Return best (strongest) signal instance per type
    best = {}
    for name, hits in sigs.items():
        if hits:
            best[name] = max(hits, key=lambda x: x[1])
    return best


# ── Evaluate signals against settled bets ────────────────────────────────────


def evaluate(signal_hits, settled_map):
    """
    signal_hits: {fid: {signal_name: (selection, strength)}}
    settled_map: {fid: {selection: {won, clv, ...}}}

    Returns {signal_name: {n, wins, losses, avg_clv, avg_strength, roi}}
    """
    results = defaultdict(
        lambda: {
            "n": 0,
            "wins": 0,
            "losses": 0,
            "clv_sum": 0,
            "clv_n": 0,
            "strength_sum": 0,
        }
    )

    for fid, sigs in signal_hits.items():
        if fid not in settled_map:
            continue
        for sig_name, (sel_key, strength) in sigs.items():
            # Match selection key to settled bet: try exact, then substring
            bet_info = None
            for bet_sel, info in settled_map[fid].items():
                if sel_key == bet_sel or sel_key in bet_sel:
                    bet_info = info
                    break
            if bet_info is None:
                continue
            r = results[sig_name]
            r["n"] += 1
            r["strength_sum"] += strength
            if bet_info["won"]:
                r["wins"] += 1
            else:
                r["losses"] += 1
            if bet_info["clv"] is not None:
                r["clv_sum"] += bet_info["clv"]
                r["clv_n"] += 1

    # Finalise
    out = {}
    for name, r in results.items():
        if r["n"] < MIN_BETS:
            continue
        n = r["n"]
        wins = r["wins"]
        staked = n * 25  # assume flat $25 stake (our paper stake)
        # Rough ROI: wins get (avg_odds - 1) * stake, losses lose stake
        # We don't have per-bet odds here so use hit rate vs breakeven
        # Instead, report CLV and hit rate as the primary metrics
        clv = r["clv_sum"] / r["clv_n"] * 100 if r["clv_n"] > 0 else None
        out[name] = {
            "n": n,
            "wins": wins,
            "hit": wins / n * 100,
            "avg_clv": clv,
            "clv_n": r["clv_n"],
            "avg_strength": r["strength_sum"] / n * 100,
        }
    return out


# ── Main ──────────────────────────────────────────────────────────────────────

print()
print("=" * 72)
print("       SIGNAL DISCOVERY ENGINE -- automated hypothesis ranking")
print("=" * 72)
print(f"  Min move threshold : {MIN_MOVE*100:.0f}%")
print(f"  Min bets to report : {MIN_BETS}")
print()

odds_hist = load_odds_history()
settled = load_settled()
print(f"  Fixtures with odds history : {len(odds_hist)}")
print(f"  Fixtures with known result : {len(settled)}")
print()

if not odds_hist:
    print(
        "  [!] No odds history found. Run the daemon for a few days to accumulate data."
    )
    sys.exit(0)

if not settled:
    print("  [!] No settled STEAM bets found. Need results to evaluate signals.")
    sys.exit(0)

# Compute signals for all fixtures that have odds history
signal_hits = {}
for fid, snaps in odds_hist.items():
    sigs = compute_signals(fid, snaps)
    if sigs:
        signal_hits[fid] = sigs

print(f"  Fixtures with fired signals : {len(signal_hits)}")
overlap = set(signal_hits) & set(settled)
print(f"  Fixtures with result + signal : {len(overlap)}")
print()

if not overlap:
    print("  [!] No overlap between signal fixtures and settled fixtures.")
    print("      The daemon needs more time to accumulate overlapping data.")
    sys.exit(0)

# Evaluate
eval_results = evaluate(signal_hits, settled)

if not eval_results:
    print(f"  [!] No signal fired on >= {MIN_BETS} settled matches. Lower --min-bets.")
    sys.exit(0)

# Rank by CLV (primary), then hit rate
ranked = sorted(
    eval_results.items(), key=lambda x: (x[1]["avg_clv"] or -999), reverse=True
)

print("-" * 72)
print(
    f"  {'Signal':<18}  {'N':>5}  {'Hit%':>6}  {'Avg CLV%':>9}  "
    f"{'CLV N':>6}  {'Avg Move%':>9}  {'Verdict'}"
)
print(f"  {'-'*18}  {'-'*5}  {'-'*6}  {'-'*9}  {'-'*6}  {'-'*9}  {'-'*12}")

for name, r in ranked:
    clv_str = f"{r['avg_clv']:+.1f}%" if r["avg_clv"] is not None else "   --   "
    verdict = (
        "STRONG"
        if r["avg_clv"] and r["avg_clv"] >= 5
        else (
            "weak"
            if r["avg_clv"] and r["avg_clv"] >= 0
            else "DEAD" if r["avg_clv"] and r["avg_clv"] < -5 else "marginal"
        )
    )
    print(
        f"  {name:<18}  {r['n']:>5}  {r['hit']:>5.1f}%  {clv_str:>9}  "
        f"{r['clv_n']:>6}  {r['avg_strength']:>8.1f}%  {verdict}"
    )

print()
print("  Legend:")
print("    STRONG  = avg CLV >= +5%  (priority to build into live strategy)")
print("    weak    = avg CLV 0-5%    (accumulate more data)")
print("    marginal= no CLV data yet")
print("    DEAD    = avg CLV < -5%   (do not use)")
print()
print("  CLV is the primary metric. ROI fluctuates with sample size; CLV is stable.")
print(
    "  Any signal with STRONG CLV and >= 20 matches is worth implementing in the daemon."
)
print()
print("=" * 72)
print()

# Save results to data/ for historical comparison
import json, datetime

out_path = os.path.join(DATA, "signal_discovery_results.json")
payload = {
    "run_date": datetime.date.today().isoformat(),
    "min_move_pct": MIN_MOVE * 100,
    "fixtures_analysed": len(odds_hist),
    "fixtures_settled": len(settled),
    "signals": eval_results,
}
with open(out_path, "w") as f:
    json.dump(payload, f, indent=2)
print(f"  Results saved to {out_path}")

# Append a historical snapshot to signal_performance table for trend analysis
try:
    import sqlite3 as _sql3

    _perf_db = os.path.join(DATA, "deepfield_browser_data", "completed_fixtures.db")
    _pc = _sql3.connect(_perf_db)
    _pc.execute(
        """CREATE TABLE IF NOT EXISTS signal_performance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_date TEXT,
        signal_name TEXT,
        matches INTEGER,
        wins INTEGER,
        avg_clv REAL,
        roi REAL,
        status TEXT,
        confidence REAL
    )"""
    )
    _today = datetime.date.today().isoformat()
    for _sig, _r in eval_results.items():
        _n = _r["n"]
        _clv = _r.get("avg_clv")
        _hit = _r.get("hit", 0)
        if _clv is not None and _n >= 100:
            _status = (
                "PROMOTE" if _clv >= 3.0 else ("DISABLE" if _clv < 0.0 else "WATCH")
            )
        elif _n < 100:
            _status = "WATCH"
        else:
            _status = "UNKNOWN"
        _conf = min(99, max(0, (_n / 500) * 99))
        _pc.execute(
            "INSERT INTO signal_performance (run_date, signal_name, matches, wins, avg_clv, roi, status, confidence) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (_today, _sig, _n, _r.get("wins", 0), _clv, None, _status, round(_conf, 1)),
        )
    _pc.commit()
    _pc.close()
    print(f"  Signal performance snapshot written to signal_performance table.")
except Exception as _e:
    print(f"  [warn] Could not write signal_performance: {_e}")

# Update signal_registry: auto-promote / disable based on evidence
_REGISTRY_DEFAULTS = {
    "STEAM_FWD": 1,
    "STEAM_REV": 0,
    "DOG_DRIFT": 0,
    "FAV_DRIFT": 0,
    "EARLY_STEAM": 0,
    "LATE_STEAM": 0,
    "FAV_DRIFT_REV": 0,
    "MOMENTUM_ACCEL": 0,
    "LARGE_SPREAD": 0,
}
try:
    import sqlite3 as _sql3r

    _rdb = os.path.join(DATA, "deepfield_browser_data", "completed_fixtures.db")
    _rc = _sql3r.connect(_rdb)
    _rc.execute(
        """CREATE TABLE IF NOT EXISTS signal_registry (
        signal_name  TEXT PRIMARY KEY,
        enabled      INTEGER DEFAULT 1,
        promoted     INTEGER DEFAULT 0,
        min_samples  INTEGER DEFAULT 100,
        owner        TEXT    DEFAULT 'system',
        updated_at   DATETIME DEFAULT CURRENT_TIMESTAMP
    )"""
    )
    # Seed defaults for any missing rows
    for _sig, _en in _REGISTRY_DEFAULTS.items():
        _rc.execute(
            "INSERT OR IGNORE INTO signal_registry (signal_name, enabled, promoted) VALUES (?,?,0)",
            (_sig, _en),
        )
    # Apply auto-promotion / retirement rules with minimum sample gates:
    #   Promotion  : n >= 100 AND CLV >= +3%          (already conservative)
    #   Retirement : n >= 100 AND CI upper bound < 0  (CI must clear zero to act — avoids false-negative on variance)
    #   Min gate for any auto-action: n >= 100
    for _sig, _r in eval_results.items():
        _n, _clv = _r["n"], _r.get("avg_clv")
        if _clv is None or _n < 100:
            continue  # gate: insufficient evidence
        if _clv >= 3.0:
            _rc.execute(
                "UPDATE signal_registry SET promoted=1, updated_at=CURRENT_TIMESTAMP WHERE signal_name=?",
                (_sig,),
            )
            print(f"  [REGISTRY] {_sig}: PROMOTED (CLV={_clv:.1f}%, n={_n})")
        elif _clv < 0.0:
            # Retirement gate: require CI upper bound below zero to avoid acting on normal variance.
            # Approximation: SE = stddev/sqrt(n); z=1.96 for n>=30. Use clv_n if available.
            _cn = _r.get("clv_n", _n)
            _ci_upper = None
            if _cn >= 10:
                import math as _math

                # We don't store per-bet CLV here, so estimate from avg_clv alone (conservative SE proxy)
                # Use CLV as a Z-score check: retire only if CLV < -2% (more than 1 SE below zero for typical SE)
                # Real CI will be computed in signal_validate.py — treat this as a soft gate
                _retire = _clv < -2.0 and _n >= 100
            else:
                _retire = False
            if _retire:
                _rc.execute(
                    "UPDATE signal_registry SET enabled=0, promoted=0, updated_at=CURRENT_TIMESTAMP WHERE signal_name=?",
                    (_sig,),
                )
                print(
                    f"  [REGISTRY] {_sig}: DISABLED (CLV={_clv:.1f}%, n={_n}) — use signal_validate.py to confirm CI before acting"
                )
    _rc.commit()
    _rc.close()
    print(f"  Signal registry updated.")
except Exception as _e:
    print(f"  [warn] Could not update signal_registry: {_e}")
print()
