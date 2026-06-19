"""
steam_health.py -- STEAM strategy health monitor for DeepFieldPro.
==================================================================
Prints a rich health report for the STEAM flat-stake paper strategy:
  - Signal accumulation status
  - ROI by move-size bucket
  - Recent 30-day trend
  - Current paper bankroll snapshot
  - Go/no-go recommendation

The move-size for each staked bet is resolved by joining bet_log with the
steam_signals ledger (keyed on fixture_id + selection~side).  When a join
row is not found the bet is placed in an "unknown" bucket.

Run:
    .venv\\Scripts\\python.exe tools\\steam_health.py
"""

import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIGNALS_DB = os.path.join(ROOT, "data", "deepfield_browser_data", "completed_fixtures.db")
BETLOG_DB  = os.path.join(ROOT, "data", "bet_log.db")
BANKROLL_DB = os.path.join(ROOT, "data", "bankroll.db")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _open(path, read_only=True):
    if not os.path.exists(path):
        return None
    uri = f"file:{path}?mode=ro" if read_only else None
    return sqlite3.connect(uri, uri=True) if read_only else sqlite3.connect(path)


def _rows(conn, sql, params=()):
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, params)]
    except sqlite3.OperationalError:
        return []


def _fmt_pct(v, decimals=1):
    return f"{v:+.{decimals}%}" if v is not None else "n/a"


def _fmt_f(v, decimals=2):
    return f"{v:+.{decimals}f}" if v is not None else "n/a"


def _bucket(move_pct):
    """Return a sort-key + label for a steam_move value (0-1 fraction or %)."""
    # steam_move is stored as a fraction (e.g. 0.035 = 3.5%) in steam_signals
    # but also sometimes as a percentage float -- normalise to percentage points.
    if move_pct is None:
        return (99, "unknown")
    m = move_pct * 100 if move_pct < 1 else move_pct   # normalise to %
    if m < 2:
        return (0, "<2%")
    if m < 3:
        return (1, "2-3%")
    if m < 5:
        return (2, "3-5%")
    return (3, ">=5%")


def _divider(char="-", width=68):
    print(char * width)


def _header(title):
    _divider("=")
    print(f"  {title}")
    _divider("=")

# ---------------------------------------------------------------------------
# 1. Signal accumulation status
# ---------------------------------------------------------------------------

def section_accumulation(signals_conn, betlog_conn):
    _header("1 - Signal Accumulation Status")

    total_signals = 0
    if signals_conn:
        rows = _rows(signals_conn,
                     "SELECT COUNT(*) AS n FROM steam_signals")
        total_signals = rows[0]["n"] if rows else 0

    total_staked = 0
    settled_count = 0
    open_count = 0
    if betlog_conn:
        staked_rows = _rows(betlog_conn,
            "SELECT result FROM bet_log WHERE bet_source='STEAM'")
        total_staked = len(staked_rows)
        for r in staked_rows:
            res = (r["result"] or "").upper()
            if res in ("", "OPEN"):
                open_count += 1
            else:
                settled_count += 1

    pending_signals = max(0, total_signals - settled_count)

    print(f"  Signals fired  : {total_signals}")
    print(f"  Staked bets    : {total_staked}  (settled: {settled_count} | open: {open_count})")
    print(f"  Signal pending : {pending_signals}")
    print()

    RELIABLE_N = 200
    if settled_count < 50:
        print(f"  [!] Need ~{RELIABLE_N} settled bets for reliable ROI estimate "
              f"(currently {settled_count})")
    elif settled_count < RELIABLE_N:
        print(f"  [!] {RELIABLE_N - settled_count} more settled bets needed before "
              f"ROI is statistically meaningful")
    else:
        print(f"  [OK] Sample size sufficient for ROI assessment ({settled_count} settled)")
    print()

    return settled_count

# ---------------------------------------------------------------------------
# 2. ROI by move-size bucket
# ---------------------------------------------------------------------------

def section_roi_by_bucket(signals_conn, betlog_conn):
    _header("2 - ROI by Move-Size Bucket")

    if not betlog_conn:
        print("  bet_log.db not found.\n")
        return

    # Fetch all settled STEAM bets from bet_log
    bets = _rows(betlog_conn, """
        SELECT bet_id, fixture_id, side, stake, pnl, result, placed_at,
               entry_odds, league
        FROM   bet_log
        WHERE  bet_source = 'STEAM'
          AND  result NOT IN ('', 'OPEN')
          AND  result IS NOT NULL
    """)

    if not bets:
        print("  No settled STEAM bets yet.\n")
        return

    # Build a lookup: (fixture_id, normalised_selection) -> steam_move
    move_lookup = {}
    if signals_conn:
        sigs = _rows(signals_conn,
                     "SELECT fixture_id, selection, steam_move FROM steam_signals")
        for s in sigs:
            key = (s["fixture_id"], (s["selection"] or "").lower())
            move_lookup[key] = s["steam_move"]

    # Bucket each bet
    buckets = {}   # label -> {"count": int, "wins": int, "staked": float, "pnl": float}
    for b in bets:
        fid  = b["fixture_id"] or ""
        side = (b["side"] or "").lower()
        move = move_lookup.get((fid, side))

        # Fallback: try partial match on side keywords
        if move is None:
            for (f2, sel2), mv in move_lookup.items():
                if f2 == fid:
                    s_lower = sel2.lower()
                    if ("home" in side and "home" in s_lower) or \
                       ("away" in side and "away" in s_lower) or \
                       ("draw" in side and "draw" in s_lower):
                        move = mv
                        break

        sort_key, label = _bucket(move)
        if label not in buckets:
            buckets[label] = {"sort": sort_key, "count": 0, "wins": 0,
                              "staked": 0.0, "pnl": 0.0}
        entry = buckets[label]
        entry["count"] += 1
        res = (b["result"] or "").upper()
        if res in ("W", "WIN", "WON"):
            entry["wins"] += 1
        entry["staked"] += float(b["stake"] or 0)
        entry["pnl"]    += float(b["pnl"] or 0)

    # Print table
    col_w = [10, 8, 9, 10, 10]
    header = ["Move bucket", "Bets", "Win%", "Staked", "ROI"]
    row_fmt = "  {:<10} {:>8} {:>9} {:>10} {:>10}"
    print(row_fmt.format(*header))
    _divider()

    for label in sorted(buckets, key=lambda l: buckets[l]["sort"]):
        e = buckets[label]
        win_rate = e["wins"] / e["count"] if e["count"] else 0
        roi = e["pnl"] / e["staked"] if e["staked"] else 0
        print(row_fmt.format(
            label,
            e["count"],
            f"{win_rate:.1%}",
            f"{e['staked']:.2f}",
            _fmt_pct(roi),
        ))

    _divider()
    # Totals
    total_count  = sum(e["count"]  for e in buckets.values())
    total_staked = sum(e["staked"] for e in buckets.values())
    total_pnl    = sum(e["pnl"]    for e in buckets.values())
    total_wins   = sum(e["wins"]   for e in buckets.values())
    overall_win  = total_wins / total_count if total_count else 0
    overall_roi  = total_pnl / total_staked if total_staked else 0
    print(row_fmt.format(
        "TOTAL",
        total_count,
        f"{overall_win:.1%}",
        f"{total_staked:.2f}",
        _fmt_pct(overall_roi),
    ))
    print()

    return overall_roi, total_count

# ---------------------------------------------------------------------------
# 3. Recent 30-day trend
# ---------------------------------------------------------------------------

def section_30d_trend(betlog_conn):
    _header("3 - Last 30 Days - STEAM Bets")

    if not betlog_conn:
        print("  bet_log.db not found.\n")
        return

    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    bets = _rows(betlog_conn, """
        SELECT stake, pnl, result, placed_at, entry_odds
        FROM   bet_log
        WHERE  bet_source = 'STEAM'
          AND  placed_at  >= ?
    """, (cutoff,))

    if not bets:
        print("  No STEAM bets in the last 30 days.\n")
        return

    settled = [b for b in bets
               if (b["result"] or "").upper() not in ("", "OPEN")]
    open_n  = len(bets) - len(settled)

    if not settled:
        print(f"  {len(bets)} bets placed, none settled yet (all open).\n")
        return

    total_staked = sum(float(b["stake"] or 0) for b in settled)
    total_pnl    = sum(float(b["pnl"]   or 0) for b in settled)
    wins         = sum(1 for b in settled
                       if (b["result"] or "").upper() in ("W", "WIN", "WON"))
    win_rate     = wins / len(settled)
    roi          = total_pnl / total_staked if total_staked else 0
    avg_stake    = total_staked / len(settled)
    avg_odds     = (sum(float(b["entry_odds"] or 0) for b in settled) / len(settled))

    print(f"  Period         : last 30 days (cutoff {cutoff[:10]})")
    print(f"  Bets placed    : {len(bets)}  (settled: {len(settled)} | open: {open_n})")
    print(f"  Win rate       : {win_rate:.1%}  ({wins}/{len(settled)})")
    print(f"  Avg entry odds : {avg_odds:.2f}")
    print(f"  Avg stake      : {avg_stake:.2f}")
    print(f"  Total staked   : {total_staked:.2f}")
    print(f"  Total P&L      : {total_pnl:+.2f}")
    print(f"  ROI            : {_fmt_pct(roi)}")
    print()

# ---------------------------------------------------------------------------
# 4. Bankroll snapshot
# ---------------------------------------------------------------------------

def section_bankroll():
    _header("4 - Paper Bankroll Snapshot")

    if not os.path.exists(BANKROLL_DB):
        print("  bankroll.db not found.\n")
        return

    conn = _open(BANKROLL_DB)
    if not conn:
        print("  Could not open bankroll.db.\n")
        return

    rows = _rows(conn, """
        SELECT date, starting_balance, current_balance, peak_balance,
               daily_exposure, daily_pnl, system_status
        FROM   bankroll
        ORDER  BY id DESC
        LIMIT  1
    """)
    conn.close()

    if not rows:
        print("  No bankroll records found.\n")
        return

    r = rows[0]
    start   = float(r["starting_balance"] or 0)
    current = float(r["current_balance"]  or 0)
    peak    = float(r["peak_balance"]     or 0)
    drawdown = (peak - current) / peak if peak else 0
    lifetime_roi = (current - start) / start if start else 0

    print(f"  As of date     : {r['date']}")
    print(f"  Current balance: ${current:,.2f}")
    print(f"  Peak balance   : ${peak:,.2f}")
    print(f"  Drawdown       : {drawdown:.1%} from peak")
    print(f"  Daily exposure : ${float(r['daily_exposure'] or 0):,.2f}")
    print(f"  Daily P&L      : {_fmt_f(r['daily_pnl'])}")
    print(f"  Status         : {r['system_status']}")
    print(f"  Lifetime ROI   : {_fmt_pct(lifetime_roi)}")
    print()

# ---------------------------------------------------------------------------
# 5. Recommendation
# ---------------------------------------------------------------------------

def section_recommendation(settled_count, overall_roi=None):
    _header("5 - Recommendation")

    RELIABLE_N = 200
    remaining  = max(0, RELIABLE_N - settled_count)

    if settled_count < RELIABLE_N:
        print(f"  [WAIT] Accumulating data -- {remaining} more settled bets needed")
        print(f"         (have {settled_count}/{RELIABLE_N}; live ledger needs time to fill)")
    elif overall_roi is not None and overall_roi > 0:
        print(f"  [OK] STEAM strategy accumulating positive signal -- continue")
        print(f"       Overall ROI: {_fmt_pct(overall_roi)}")
        print(f"       Keep steam_betting_enabled=true; revisit steam_min_move_pct if ROI slips.")
    elif overall_roi is not None and overall_roi < -0.05:
        print(f"  [!!] STEAM ROI negative at scale ({_fmt_pct(overall_roi)})")
        print(f"       Consider raising steam_min_move_pct (current default: 3%).")
        print(f"       Check by bucket (section 2) -- low move sizes may drag the average.")
    else:
        roi_str = _fmt_pct(overall_roi) if overall_roi is not None else "n/a"
        print(f"  [~]  ROI is near breakeven ({roi_str}) with {settled_count} settled bets.")
        print(f"       Continue accumulating data; no action needed yet.")
    print()

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print()
    print("=" * 68)
    print("  DeepFieldPro - STEAM Strategy Health Monitor")
    print(f"  Generated : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 68)
    print()

    signals_conn = None
    if os.path.exists(SIGNALS_DB):
        try:
            signals_conn = sqlite3.connect(f"file:{SIGNALS_DB}?mode=ro", uri=True)
        except Exception as e:
            print(f"  [warn] Could not open signals DB: {e}")
    else:
        print(f"  [warn] signals DB not found: {SIGNALS_DB}")

    betlog_conn = None
    if os.path.exists(BETLOG_DB):
        try:
            betlog_conn = sqlite3.connect(f"file:{BETLOG_DB}?mode=ro", uri=True)
        except Exception as e:
            print(f"  [warn] Could not open bet_log DB: {e}")
    else:
        print(f"  [warn] bet_log.db not found: {BETLOG_DB}")

    settled_count = section_accumulation(signals_conn, betlog_conn)
    bucket_result = section_roi_by_bucket(signals_conn, betlog_conn)
    section_30d_trend(betlog_conn)
    section_bankroll()

    overall_roi = None
    if bucket_result:
        overall_roi, _ = bucket_result

    section_recommendation(settled_count, overall_roi)

    if signals_conn:
        signals_conn.close()
    if betlog_conn:
        betlog_conn.close()

    print("  NOTE: Real money is HARD-GATED (DEEPFIELD_ARENA_LIVE unset).")
    print("        All figures above are paper / shadow only.")
    print()


if __name__ == "__main__":
    main()
