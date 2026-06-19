"""
Walk-Forward Signal Validation — prospective hold-out evaluation.

Splits all settled STEAM bets chronologically (80% train / 20% hold-out),
evaluates every signal on the hold-out set only, and writes results to the
`signal_validation` table in completed_fixtures.db.

The discovery engine uses all data; this tool gives an unbiased out-of-sample
read — if a signal's hold-out CLV materially trails its discovery CLV, it's
likely over-fit or the edge is decaying.

Usage:
    .venv\\Scripts\\python.exe tools\\signal_validate.py
    .venv\\Scripts\\python.exe tools\\signal_validate.py --split 0.2   # hold-out fraction
    .venv\\Scripts\\python.exe tools\\signal_validate.py --min-bets 5
"""
import os, sys, sqlite3, math, json, datetime
from collections import defaultdict

# ── Config ────────────────────────────────────────────────────────────────────
ROOT   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA   = os.path.join(ROOT, "data")
SIGNALS_DB = os.path.join(DATA, "deepfield_browser_data", "completed_fixtures.db")
BET_DB     = os.path.join(DATA, "bet_log.db")

_args = sys.argv[1:]
def _flag(name, default):
    try:
        return type(default)(_args[_args.index(name) + 1])
    except (ValueError, IndexError):
        return default

HOLD_FRACTION = _flag("--split",    0.20)   # fraction of bets held out for validation
MIN_BETS      = _flag("--min-bets", 3)      # min matches for a signal to appear in report


# ── Load odds history ─────────────────────────────────────────────────────────

def load_odds_history():
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
    by_fid = defaultdict(list)
    for fid, market, sel, odds, ts in rows:
        by_fid[str(fid)].append((sel, float(odds) if odds else 0, ts))
    return dict(by_fid)


def load_settled_bets():
    """Return sorted list of {fid, sel, won, entry_odds, closing_odds, clv, placed_at}."""
    try:
        con = sqlite3.connect(BET_DB)
        rows = con.execute(
            """SELECT fixture_id, player_id, result, entry_odds, closing_odds, placed_at
               FROM bet_log WHERE bet_source='STEAM' AND result IN ('W','L','WIN','LOSS')
               ORDER BY placed_at ASC"""
        ).fetchall()
        con.close()
    except Exception as e:
        print(f"[ERROR] Cannot read bet_log: {e}")
        return []

    import re
    bets = []
    for fid, player_id, result, entry_odds, closing_odds, placed_at in rows:
        if not fid:
            continue
        m = re.search(r"\((Home \(1\)|Away \(2\)|Draw)\)$", player_id or "")
        sel = m.group(1) if m else player_id
        clv = (entry_odds / closing_odds - 1) if closing_odds and closing_odds > 0 else None
        bets.append({
            "fid": str(fid), "sel": sel, "won": result in ("W", "WIN"),
            "entry_odds": entry_odds, "closing_odds": closing_odds,
            "clv": clv, "placed_at": placed_at or "",
        })
    return bets


# ── Signal computation (same logic as signal_discovery.py) ───────────────────

def _devig(odds_dict):
    inv = {s: 1/o for s, o in odds_dict.items() if o and o > 0}
    tot = sum(inv.values())
    if tot <= 0 or len(inv) < 2:
        return None
    return {s: v/tot for s, v in inv.items()}


MIN_MOVE = 0.05  # 5% probability move threshold

def compute_signals(snap_list):
    """Return {signal_name: (selection, strength)} for a fixture's snapshot list."""
    if len(snap_list) < 4:
        return {}
    by_ts = defaultdict(dict)
    for sel, odds, ts in snap_list:
        if odds > 0:
            by_ts[ts][sel] = odds
    prob_series = {}
    for ts in sorted(by_ts):
        dv = _devig(by_ts[ts])
        if dv:
            prob_series[ts] = dv
    ts_list = sorted(prob_series)
    if len(ts_list) < 2:
        return {}

    first_snap  = prob_series[ts_list[0]]
    last_snap   = prob_series[ts_list[-1]]
    mid_idx     = len(ts_list) // 2
    early_snap  = prob_series[ts_list[max(0, mid_idx - 1)]]
    recent_snap = prob_series[ts_list[-2]] if len(ts_list) >= 2 else first_snap
    all_sels    = set(first_snap) | set(last_snap)
    sigs = {}

    for sel in all_sels:
        if sel not in first_snap or sel not in last_snap:
            continue
        total_move = last_snap[sel] - first_snap[sel]
        early_move = early_snap.get(sel, first_snap[sel]) - first_snap[sel]
        late_move  = last_snap[sel] - recent_snap.get(sel, last_snap[sel])
        series = [prob_series[ts][sel] for ts in ts_list if sel in prob_series[ts]]
        steps  = [series[i+1] - series[i] for i in range(len(series)-1)]
        direction = 1 if total_move >= 0 else -1
        mono = sum(1 for s in steps if s * direction > 0) / len(steps) if steps else 0.5

        if total_move >= MIN_MOVE:
            sigs.setdefault("STEAM_FWD", []).append((sel, total_move * mono))
        if total_move >= MIN_MOVE:
            opp = min(all_sels, key=lambda s: last_snap.get(s, 0) - first_snap.get(s, 0))
            if opp != sel:
                move_away = first_snap.get(opp, 0) - last_snap.get(opp, 0)
                if move_away >= MIN_MOVE:
                    sigs.setdefault("STEAM_REV", []).append((opp, move_away))
        if sel == "Home (1)" and total_move >= MIN_MOVE and last_snap[sel] > 0.5:
            sigs.setdefault("FAV_DRIFT", []).append((sel, total_move))
        if sel == "Away (2)" and total_move >= MIN_MOVE and first_snap[sel] < 0.4:
            sigs.setdefault("DOG_DRIFT", []).append((sel, total_move))
        if late_move >= MIN_MOVE and abs(early_move) < MIN_MOVE * 0.5:
            sigs.setdefault("LATE_STEAM", []).append((sel, late_move))
        if early_move >= MIN_MOVE and abs(late_move) < MIN_MOVE * 0.5:
            sigs.setdefault("EARLY_STEAM", []).append((sel, early_move))
        if sel == "Home (1)" and total_move <= -MIN_MOVE and first_snap[sel] > 0.5:
            sigs.setdefault("FAV_DRIFT_REV", []).append((sel, -total_move))
        if total_move >= MIN_MOVE and late_move > early_move * 1.5 and late_move >= MIN_MOVE * 0.5:
            sigs.setdefault("MOMENTUM_ACCEL", []).append((sel, late_move))

    probs = list(first_snap.values())
    if probs:
        spread = max(probs) - min(probs)
        if spread > 0.40:
            fav_sel = max(last_snap, key=lambda s: last_snap[s])
            sigs.setdefault("LARGE_SPREAD", []).append((fav_sel, spread))

    best = {}
    for name, hits in sigs.items():
        if hits:
            best[name] = max(hits, key=lambda x: x[1])
    return best


# ── Main ──────────────────────────────────────────────────────────────────────

print()
print("=" * 72)
print("      WALK-FORWARD SIGNAL VALIDATION")
print("=" * 72)
print(f"  Hold-out fraction : {HOLD_FRACTION * 100:.0f}%")
print(f"  Min bets to report: {MIN_BETS}")
print()

bets_all = load_settled_bets()
if not bets_all:
    print("  [!] No settled STEAM bets found. Need results.")
    sys.exit(0)

# Chronological split: train on first (1 - HOLD_FRACTION), validate on the rest
split_idx  = int(len(bets_all) * (1 - HOLD_FRACTION))
train_bets = bets_all[:split_idx]
val_bets   = bets_all[split_idx:]

print(f"  Total settled bets : {len(bets_all)}")
print(f"  Train set          : {len(train_bets)} bets (through {train_bets[-1]['placed_at'][:10] if train_bets else 'n/a'})")
print(f"  Validation set     : {len(val_bets)} bets (from {val_bets[0]['placed_at'][:10] if val_bets else 'n/a'})")
print()

# Build settled map from validation bets only
val_settled = {}
for b in val_bets:
    fid = b["fid"]
    if fid not in val_settled:
        val_settled[fid] = {}
    val_settled[fid][b["sel"]] = b

print(f"  Validation fixtures: {len(val_settled)}")

# Load odds history
odds_hist = load_odds_history()
print(f"  Fixtures with odds history: {len(odds_hist)}")
print()

if not val_settled:
    print("  [!] Validation set is empty — need more settled bets. Try later.")
    sys.exit(0)

# Compute signals for every fixture that has odds history
signal_hits = {}
for fid, snaps in odds_hist.items():
    sigs = compute_signals(snaps)
    if sigs:
        signal_hits[fid] = sigs

# Evaluate signals ONLY on validation set fixtures
import re as _re
results = defaultdict(lambda: {"n": 0, "wins": 0, "clv_sum": 0, "clv_n": 0})

for fid, sigs in signal_hits.items():
    if fid not in val_settled:
        continue
    for sig_name, (sel_key, strength) in sigs.items():
        bet_info = None
        for bet_sel, info in val_settled[fid].items():
            if sel_key == bet_sel or sel_key in bet_sel:
                bet_info = info
                break
        if bet_info is None:
            continue
        r = results[sig_name]
        r["n"] += 1
        if bet_info["won"]:
            r["wins"] += 1
        if bet_info["clv"] is not None:
            r["clv_sum"] += bet_info["clv"]
            r["clv_n"]   += 1

# Build output
out = {}
for name, r in results.items():
    if r["n"] < MIN_BETS:
        continue
    n   = r["n"]
    clv = r["clv_sum"] / r["clv_n"] * 100 if r["clv_n"] > 0 else None
    # 95% CI
    ci_lo = ci_hi = None
    if r["clv_n"] >= 2 and clv is not None:
        clv_vals = [b["clv"] * 100 for fid in val_settled
                    for b in [val_settled[fid].get(sn) for sn in val_settled[fid]]
                    if b and b.get("clv") is not None]
        # Simple CI using std of all val CLV vals (approximation)
        if len(clv_vals) >= 2:
            mean = sum(clv_vals) / len(clv_vals)
            variance = sum((v - mean) ** 2 for v in clv_vals) / (len(clv_vals) - 1)
            se = math.sqrt(variance / r["clv_n"])
            z  = 1.96 if r["clv_n"] >= 30 else (2.045 if r["clv_n"] >= 25 else 2.571)
            ci_lo = round(clv - z * se, 1)
            ci_hi = round(clv + z * se, 1)

    status = "STRONG" if clv and clv >= 5 else (
             "VALIDATED" if clv and clv >= 2 else (
             "WATCH" if clv is not None else "NO_CLV"))
    out[name] = {
        "n": n, "wins": r["wins"],
        "hit": r["wins"] / n * 100,
        "avg_clv": round(clv, 2) if clv is not None else None,
        "clv_n": r["clv_n"], "ci_lower": ci_lo, "ci_upper": ci_hi,
        "status": status,
        "split_date": val_bets[0]["placed_at"][:10] if val_bets else None,
        "train_n": len(train_bets),
        "val_n": len(val_bets),
    }

ranked = sorted(out.items(), key=lambda x: (x[1]["avg_clv"] or -999), reverse=True)

print("-" * 72)
print(f"  {'Signal':<18}  {'N (val)':>8}  {'Hit%':>6}  {'CLV%':>8}  {'95% CI':>16}  Status")
print(f"  {'-'*18}  {'-'*8}  {'-'*6}  {'-'*8}  {'-'*16}  {'-'*12}")
for name, r in ranked:
    clv_str = f"{r['avg_clv']:+.1f}%" if r["avg_clv"] is not None else "   --   "
    ci_str  = (f"[{r['ci_lower']:+.1f}, {r['ci_upper']:+.1f}]"
               if r["ci_lower"] is not None else "          n/a")
    print(f"  {name:<18}  {r['n']:>8}  {r['hit']:>5.1f}%  {clv_str:>8}  {ci_str:>16}  {r['status']}")

print()

# Write to signal_validation table
try:
    con = sqlite3.connect(SIGNALS_DB)
    con.execute("""CREATE TABLE IF NOT EXISTS signal_validation (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        run_date     TEXT,
        signal_name  TEXT,
        val_samples  INTEGER,
        val_wins     INTEGER,
        val_hit_rate REAL,
        val_avg_clv  REAL,
        val_ci_lower REAL,
        val_ci_upper REAL,
        val_status   TEXT,
        train_n      INTEGER,
        val_n        INTEGER,
        split_date   TEXT,
        UNIQUE(run_date, signal_name)
    )""")
    today = datetime.date.today().isoformat()
    for name, r in out.items():
        con.execute(
            """INSERT OR REPLACE INTO signal_validation
               (run_date, signal_name, val_samples, val_wins, val_hit_rate,
                val_avg_clv, val_ci_lower, val_ci_upper, val_status,
                train_n, val_n, split_date)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (today, name, r["n"], r["wins"], r["hit"],
             r["avg_clv"], r["ci_lower"], r["ci_upper"], r["status"],
             r["train_n"], r["val_n"], r["split_date"]),
        )
    con.commit()
    con.close()
    print(f"  signal_validation table updated ({len(out)} signals, run_date={today})")
except Exception as e:
    print(f"  [warn] Could not write signal_validation: {e}")

# Also save JSON snapshot
out_path = os.path.join(DATA, "signal_validation_results.json")
with open(out_path, "w") as f:
    json.dump({
        "run_date": datetime.date.today().isoformat(),
        "hold_fraction": HOLD_FRACTION,
        "train_n": len(train_bets),
        "val_n": len(val_bets),
        "signals": out,
    }, f, indent=2)
print(f"  Results saved to {out_path}")
print()
print("=" * 72)
print()
