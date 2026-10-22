"""edge_milestone_check.py — "can I place real bets yet?" milestone checker.

Evaluates ONLY verified-provenance settles (result_verified=1, i.e. every grade
produced by the post-2026-07-11 settlement pipeline or the 2026-07-12 audit
repairs — the trustworthy record). Legacy unverified grades are excluded: the
2026-07-12 audit proved ~29% of the externally-checkable ones were wrong.

Milestone (per strategy): N >= 300 verified settles AND the fixture-clustered
t-statistic of per-bet ROI >= 2.0 AND ROI > 0. That is roughly a 95% CI above
zero — the same bar as the project's STEAM_FWD validation ladder.

Also emits an engine-stall warning when no new verified settle has landed in
48h (accumulation stopped -> the milestone can never trigger).

Output: one line per strategy + a final MILESTONE_MET / MILESTONE_NOT_MET /
ENGINE_STALLED verdict line (machine-parseable for the daily cron).
Read-only; safe to run any time.
"""
import datetime
import math
import os
import sqlite3
import statistics
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "data", "bet_log.db")

N_MIN = 300
T_MIN = 2.0
CLUSTER_HAIRCUT = 0.75  # 1X2 + O/U on the same fixture are correlated

# Every strategy that writes to bet_log. This list was hand-maintained inside
# main() and had drifted: MODEL_VALUE_ALIGN — the only strategy in the whole
# verified record with a clustered t above the 2.0 bar (t=+3.52, n=190,
# +43.5% ROI) — was never tracked, so every run reported MILESTONE_NOT_MET
# while the best signal went unmeasured. PINNACLE_VALUE (+$134.98) and
# STAIR_AI (-$142.63) were missing too.
#
# Adding a bet_source to the daemon means adding it here. Steam variants and
# CONSENSUS use the STEAM_FWD ladder's 100-sample bar rather than the 300-bet
# tipster bar: they are flat-staked signal bets and 100 was the pre-agreed
# milestone. An early crossing at 100 is weaker evidence than one at 300 —
# more tracked strategies means more lottery tickets, so treat a 100-bar
# crossing with extra skepticism.
TRACKED = [
    ("FOREBET", "TIPSTER_FOREBET", N_MIN),
    ("APIFB", "TIPSTER_APIFB", N_MIN),
    ("CONSENSUS", "TIPSTER_CONSENSUS", 100),
    ("STEAM", "STEAM", 100),
    ("STEAM_LL", "STEAM_LL", 100),
    ("PIN_STEAM", "PINNACLE_STEAM", 100),
    ("SHARP_ST", "SHARP_STEAM", 100),
    ("AI", "AI", N_MIN),
    ("MODEL_VAL", "MODEL_VALUE_ALIGN", N_MIN),
    ("PIN_VALUE", "PINNACLE_VALUE", N_MIN),
    ("VAL_ONLY", "VALUE_ONLY", N_MIN),
    ("STAIR_AI", "STAIR_AI", N_MIN),
    ("ALL", "%", N_MIN),
]


def strategy_stats(cur, source_like):
    rows = cur.execute(
        "SELECT pnl, stake, fixture_id FROM bet_log "
        "WHERE result IN ('W','L') AND result_verified=1 AND stake > 0 "
        "AND bet_source LIKE ?",
        (source_like,),
    ).fetchall()
    n = len(rows)
    if n < 2:
        return {"n": n, "net": 0.0, "roi": 0.0, "t": 0.0, "fixtures": 0}
    net = sum(r[0] for r in rows)
    staked = sum(r[1] for r in rows)
    rois = [r[0] / r[1] for r in rows]
    mean = statistics.mean(rois)
    sd = statistics.stdev(rois)
    t = (mean * math.sqrt(n) / sd) * CLUSTER_HAIRCUT if sd > 0 else 0.0
    return {
        "n": n,
        "net": round(net, 2),
        "staked": round(staked, 2),
        "roi": round(net / staked * 100, 1) if staked else 0.0,
        "t": round(t, 2),
        "fixtures": len({r[2] for r in rows}),
    }


def main():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    # Engine-stall check: newest verified settle timestamp.
    last = cur.execute(
        "SELECT MAX(settle_checked_at) FROM bet_log WHERE result_verified=1"
    ).fetchone()[0]
    stalled = True
    if last:
        try:
            last_dt = datetime.datetime.fromisoformat(str(last).replace("Z", "+00:00"))
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=datetime.timezone.utc)
            age_h = (
                datetime.datetime.now(datetime.timezone.utc) - last_dt
            ).total_seconds() / 3600
            stalled = age_h > 48
            print(f"last verified settle: {last} ({age_h:.1f}h ago)")
        except ValueError:
            pass

    met = []
    for name, like, n_min in TRACKED:
        s = strategy_stats(cur, like)
        ok = s["n"] >= n_min and s["t"] >= T_MIN and s["net"] > 0
        print(
            f"{name:9} n={s['n']:4}/{n_min} verified  net={s['net']:+9.2f}  "
            f"roi={s.get('roi', 0):+6.1f}%  t(clustered)={s['t']:+5.2f}/{T_MIN}  "
            f"-> {'EDGE VALIDATED' if ok else 'not yet'}"
        )
        if ok:
            met.append(name)
    conn.close()

    if met:
        print(f"MILESTONE_MET: {','.join(met)}")
        return 0
    if stalled:
        print("ENGINE_STALLED: no verified settle in >48h — daemon down or feeds broken")
        return 2
    print("MILESTONE_NOT_MET")
    return 1


if __name__ == "__main__":
    sys.exit(main())
