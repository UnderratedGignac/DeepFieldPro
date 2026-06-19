"""
Counterfactual Engine — re-evaluate historical STEAM signals at different thresholds.

Answers: "If we had used threshold X instead of Y, what CLV would we have seen?"

Loads all 1X2 odds history and settled bet records, then re-fires the STEAM_FWD
signal at every threshold in the sweep — without re-running the daemon or scraper.

Usage:
    .venv\\Scripts\\python.exe tools\\counterfactual.py
    .venv\\Scripts\\python.exe tools\\counterfactual.py --thresholds 3,5,7,10,15
    .venv\\Scripts\\python.exe tools\\counterfactual.py --signal LATE_STEAM --thresholds 3,5,7

Output:
    Threshold  N bets  Hit%  Avg CLV%  CLV n  Verdict
    ---------------------------------------------------------------
    3%         182     52.7  +2.1%     140    weak
    5%          98     54.1  +4.8%      81    STRONG
    7%          47     57.4  +7.3%      39    STRONG
    10%         18     55.6  +2.9%      15    weak
    15%          4      —     —          0    marginal

Also writes data/counterfactual_results.json for dashboard consumption.
"""

import os, sys, sqlite3, json
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
SIGNALS_DB = os.path.join(DATA, "deepfield_browser_data", "completed_fixtures.db")
BET_DB = os.path.join(DATA, "bet_log.db")

_args = sys.argv[1:]


def _flag(name, default):
    try:
        idx = _args.index(name)
        return type(default)(_args[idx + 1])
    except (ValueError, IndexError):
        return default


THRESHOLDS_RAW = _flag("--thresholds", "3,5,7,10,15")
THRESHOLDS = [float(t) / 100.0 for t in THRESHOLDS_RAW.split(",")]
SIGNAL_TYPE = _flag("--signal", "STEAM_FWD")  # which signal to sweep


# ── Shared loaders ────────────────────────────────────────────────────────────


def load_odds_history():
    """Return {fixture_id: [(sel, odds, ts), ...]} sorted ascending."""
    try:
        con = sqlite3.connect(SIGNALS_DB)
        rows = con.execute(
            "SELECT fixture_id, selection, odds, timestamp "
            "FROM odds_history WHERE market='1X2' ORDER BY fixture_id, timestamp ASC"
        ).fetchall()
        con.close()
    except Exception as e:
        print(f"[ERROR] odds_history: {e}")
        return {}
    by_fid = defaultdict(list)
    for fid, sel, odds, ts in rows:
        by_fid[str(fid)].append((sel, float(odds) if odds else 0, ts))
    return dict(by_fid)


def load_settled():
    """Return {fid: {sel: {won, entry_odds, closing_odds, clv}}}."""
    try:
        con = sqlite3.connect(BET_DB)
        rows = con.execute(
            "SELECT fixture_id, player_id, result, entry_odds, closing_odds "
            "FROM bet_log WHERE bet_source='STEAM' AND result IN ('W','L','WIN','LOSS')"
        ).fetchall()
        con.close()
    except Exception as e:
        print(f"[ERROR] bet_log: {e}")
        return {}
    import re as _re

    settled = {}
    for fid, pid, result, eo, co in rows:
        if not fid:
            continue
        m = _re.search(r"\((Home \(1\)|Away \(2\)|Draw)\)$", pid or "")
        sel = m.group(1) if m else pid
        clv = (eo / co - 1) if co and co > 0 else None
        settled.setdefault(str(fid), {})[sel] = {
            "won": result in ("W", "WIN"),
            "entry_odds": eo,
            "closing_odds": co,
            "clv": clv,
        }
    return settled


def _devig(odds_dict):
    inv = {s: 1 / o for s, o in odds_dict.items() if o and o > 0}
    tot = sum(inv.values())
    if tot <= 0 or len(inv) < 2:
        return None
    return {s: v / tot for s, v in inv.items()}


# ── Signal computers at a given threshold ────────────────────────────────────


def fire_steam_fwd(snap_list, threshold):
    """Return (selection, move) if STEAM_FWD fires at this threshold, else None."""
    by_ts = defaultdict(dict)
    for sel, odds, ts in snap_list:
        if odds > 0:
            by_ts[ts][sel] = odds
    prob_series = {ts: _devig(by_ts[ts]) for ts in sorted(by_ts) if _devig(by_ts[ts])}
    ts_list = sorted(prob_series)
    if len(ts_list) < 2:
        return None
    first, last = prob_series[ts_list[0]], prob_series[ts_list[-1]]
    best = max(
        ((sel, last[sel] - first[sel]) for sel in set(first) & set(last)),
        key=lambda x: x[1],
        default=None,
    )
    if best and best[1] >= threshold:
        series = [
            prob_series[ts].get(best[0], 0)
            for ts in ts_list
            if best[0] in prob_series[ts]
        ]
        steps = [series[i + 1] - series[i] for i in range(len(series) - 1)]
        mono = sum(1 for s in steps if s > 0) / len(steps) if steps else 0.5
        return (best[0], best[1] * mono)
    return None


def fire_late_steam(snap_list, threshold):
    by_ts = defaultdict(dict)
    for sel, odds, ts in snap_list:
        if odds > 0:
            by_ts[ts][sel] = odds
    prob_series = {ts: _devig(by_ts[ts]) for ts in sorted(by_ts) if _devig(by_ts[ts])}
    ts_list = sorted(prob_series)
    if len(ts_list) < 3:
        return None
    first = prob_series[ts_list[0]]
    recent = prob_series[ts_list[-2]]
    last = prob_series[ts_list[-1]]
    mid = prob_series[ts_list[len(ts_list) // 2]]
    best = None
    for sel in set(first) & set(last):
        late_move = last[sel] - recent.get(sel, last[sel])
        early_move = mid.get(sel, first[sel]) - first[sel]
        if late_move >= threshold and abs(early_move) < threshold * 0.5:
            if best is None or late_move > best[1]:
                best = (sel, late_move)
    return best


SIGNAL_COMPUTERS = {
    "STEAM_FWD": fire_steam_fwd,
    "LATE_STEAM": fire_late_steam,
}


# ── Evaluate one threshold ────────────────────────────────────────────────────


def evaluate_threshold(odds_hist, settled, threshold, signal_type):
    computer = SIGNAL_COMPUTERS.get(signal_type, fire_steam_fwd)
    n = wins = clv_sum = clv_n = 0
    for fid, snaps in odds_hist.items():
        if fid not in settled:
            continue
        hit = computer(snaps, threshold)
        if hit is None:
            continue
        sel_key, strength = hit
        bet_info = None
        for bet_sel, info in settled[fid].items():
            if sel_key == bet_sel or sel_key in bet_sel:
                bet_info = info
                break
        if bet_info is None:
            continue
        n += 1
        if bet_info["won"]:
            wins += 1
        if bet_info["clv"] is not None:
            clv_sum += bet_info["clv"]
            clv_n += 1

    avg_clv = round(clv_sum / clv_n * 100, 2) if clv_n > 0 else None
    return {
        "threshold_pct": round(threshold * 100, 1),
        "n": n,
        "wins": wins,
        "hit": round(wins / n * 100, 1) if n else 0,
        "avg_clv": avg_clv,
        "clv_n": clv_n,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

import datetime as _dt

print()
print("=" * 72)
print(f"  COUNTERFACTUAL ENGINE — signal: {SIGNAL_TYPE}")
print(f"  Thresholds: {THRESHOLDS_RAW}%")
print("=" * 72)

odds_hist = load_odds_history()
settled = load_settled()
print(f"  Fixtures with odds history : {len(odds_hist)}")
print(f"  Fixtures with settled bets : {len(settled)}")
overlap = set(odds_hist) & set(settled)
print(f"  Overlap (evaluable)        : {len(overlap)}")
print()

if not overlap:
    print("  [!] No evaluable fixtures. Accumulate more data and try again.")
    sys.exit(0)

results = []
for thr in THRESHOLDS:
    r = evaluate_threshold(odds_hist, settled, thr, SIGNAL_TYPE)
    results.append(r)

print(
    f"  {'Threshold':>10}  {'N bets':>7}  {'Hit%':>6}  {'Avg CLV%':>9}  {'CLV n':>6}  Verdict"
)
print(f"  {'-'*10}  {'-'*7}  {'-'*6}  {'-'*9}  {'-'*6}  {'-'*12}")
for r in results:
    clv_str = f"{r['avg_clv']:+.1f}%" if r["avg_clv"] is not None else "   —   "
    hit_str = f"{r['hit']:.1f}%" if r["n"] > 0 else "  —   "
    verdict = (
        "STRONG"
        if r["avg_clv"] and r["avg_clv"] >= 5
        else (
            "weak"
            if r["avg_clv"] and r["avg_clv"] >= 0
            else (
                "DEAD"
                if r["avg_clv"] and r["avg_clv"] < -5
                else "marginal" if r["n"] >= 3 else "no data"
            )
        )
    )
    print(
        f"  {r['threshold_pct']:>9.1f}%  {r['n']:>7}  {hit_str:>6}  {clv_str:>9}  {r['clv_n']:>6}  {verdict}"
    )

print()
# Highlight the optimal threshold
scored = [(r, r["avg_clv"] or -999) for r in results if r["n"] >= 5]
if scored:
    best = max(scored, key=lambda x: x[1])[0]
    print(
        f"  Optimal threshold: {best['threshold_pct']:.0f}% (CLV={best['avg_clv']:+.1f}%, n={best['n']})"
    )
    print()
    print(
        "  NOTE: Selectivity check — does higher threshold improve CLV? (healthy edge: YES)"
    )
    thr_clv = [
        (r["threshold_pct"], r["avg_clv"])
        for r in results
        if r["avg_clv"] is not None and r["n"] >= 5
    ]
    if len(thr_clv) >= 2:
        first_clv = thr_clv[0][1]
        last_clv = thr_clv[-1][1]
        if last_clv > first_clv:
            print(
                f"  ✅ CLV improves with selectivity (+{last_clv - first_clv:.1f}pp) — edge is real."
            )
        else:
            print(
                f"  ⚠️  CLV degrades with selectivity ({last_clv - first_clv:+.1f}pp) — model disagreements = model error."
            )
print()
print("=" * 72)

# Save results
out_path = os.path.join(DATA, "counterfactual_results.json")
payload = {
    "run_date": _dt.date.today().isoformat(),
    "signal_type": SIGNAL_TYPE,
    "thresholds_pct": THRESHOLDS_RAW,
    "results": results,
    "optimal": scored and max(scored, key=lambda x: x[1])[0] or None,
}
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(payload, f, indent=2)
print(f"  Results saved to {out_path}")
print()
