"""
STEAM Monitor ? comprehensive performance analysis for the STEAM strategy.

Joins bet_log (results + CLV) with steam_signals (move size) to give a full
picture broken down by move bucket, league, and odds range.

Usage:
    python tools/steam_monitor.py
    python tools/steam_monitor.py --min-bets 2   # hide buckets with < N bets
"""

import sqlite3, os, sys, math

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
BET_DB = os.path.join(DATA, "bet_log.db")
SIGNALS_DB = os.path.join(DATA, "deepfield_browser_data", "completed_fixtures.db")

MIN_BETS = int(
    next(
        (
            sys.argv[sys.argv.index("--min-bets") + 1]
            for i, a in enumerate(sys.argv)
            if a == "--min-bets"
        ),
        1,
    )
)


def roi(pnl, staked):
    return (pnl / staked * 100) if staked > 0 else 0.0


def fmt(val, suffix="", plus=False):
    if val is None:
        return "  --  "
    s = f"{val:+.1f}" if plus else f"{val:.1f}"
    return f"{s}{suffix}"


def hr(char="-", width=90):
    print(char * width)


def section(title):
    hr()
    print(f"  {title}")
    hr()


# ?? Load data ?????????????????????????????????????????????????????????????????

con = sqlite3.connect(BET_DB)
con.execute(f"ATTACH DATABASE '{SIGNALS_DB}' AS sig")

# Join bet_log STEAM bets with steam_signals on fixture_id.
# steam_move comes from steam_signals (fraction ? multiply ?100 for %).
rows = con.execute(
    """
    SELECT
        b.bet_id,
        b.match_id,
        b.league,
        b.entry_odds,
        b.stake,
        b.result,
        b.pnl,
        b.clv,
        b.closing_odds,
        b.placed_at,
        s.steam_move
    FROM bet_log b
    LEFT JOIN sig.steam_signals s
        ON b.fixture_id = s.fixture_id
        AND b.market_type = s.market
    WHERE b.bet_source = 'STEAM'
    ORDER BY b.placed_at ASC
"""
).fetchall()
con.close()

settled = [r for r in rows if r[5] in ("W", "L", "WIN", "LOSS")]
has_clv = [r for r in settled if r[7] is not None]


# ?? Helper: bucket stats ??????????????????????????????????????????????????????


def bucket_stats(bets):
    n = len(bets)
    if n == 0:
        return None
    wins = sum(1 for b in bets if b[5] in ("W", "WIN"))
    staked = sum(b[4] or 0 for b in bets)
    pnl = sum(b[6] or 0 for b in bets)
    clv_vals = [b[7] for b in bets if b[7] is not None]
    avg_clv = sum(clv_vals) / len(clv_vals) * 100 if clv_vals else None
    avg_odds = sum(b[3] for b in bets if b[3]) / n
    return dict(
        n=n,
        wins=wins,
        hit=wins / n * 100,
        staked=staked,
        pnl=pnl,
        roi=roi(pnl, staked),
        avg_clv=avg_clv,
        avg_odds=avg_odds,
        clv_n=len(clv_vals),
    )


def print_table(header, rows_data, col_widths):
    fmt_str = "  " + "  ".join(f"{{:<{w}}}" for w in col_widths)
    print(fmt_str.format(*header))
    print("  " + "  ".join("-" * w for w in col_widths))
    for row in rows_data:
        print(fmt_str.format(*row))


# ??????????????????????????????????????????????????????????????????????????????
# 1. OVERALL SUMMARY
# ??????????????????????????????????????????????????????????????????????????????

print()
print("=" * 72)
print("                    STEAM MONITOR -- FULL REPORT")
print("=" * 72)
print()

s = bucket_stats(settled)
total_bets = len(rows)
open_bets = sum(1 for r in rows if r[5] == "OPEN")

print(f"  Total STEAM bets logged : {total_bets}")
print(f"  Settled                 : {s['n']} (W={s['wins']} / L={s['n']-s['wins']})")
print(f"  Open                    : {open_bets}")
print(f"  Hit rate                : {s['hit']:.1f}%")
print(f"  Total staked (paper $)  : ${s['staked']:.2f}")
print(f"  Net P&L                 : ${s['pnl']:+.2f}")
print(f"  ROI                     : {s['roi']:+.1f}%")
if s["avg_clv"] is not None:
    print(f"  Avg CLV ({s['clv_n']} bets)      : {s['avg_clv']:+.2f}%  <-- key metric")
print(f"  Avg entry odds          : {s['avg_odds']:.2f}")
print()

# CLV interpretation
if s["avg_clv"] is not None:
    if s["avg_clv"] >= 5:
        verdict = "POSITIVE EDGE SIGNAL ? CLV suggests genuine line-shopping advantage"
        color = "[OK]"
    elif s["avg_clv"] >= 0:
        verdict = "MARGINAL ? accumulate more bets before drawing conclusions"
        color = "[~]"
    else:
        verdict = "NEGATIVE CLV ? strategy may be dead; investigate move quality"
        color = "[X]"
    print(f"  {color}  {verdict}")
    print()

target = 300
remaining = max(0, target - s["n"])
bar_fill = min(40, int(s["n"] / target * 40))
bar = "#" * bar_fill + "." * (40 - bar_fill)
print(f"  Sample progress to 300-bet confidence threshold:")
print(f"  [{bar}] {s['n']}/300  ({remaining} more bets needed)")
print()


# ??????????????????????????????????????????????????????????????????????????????
# 2. BY MOVE SIZE BUCKET
# ??????????????????????????????????????????????????????????????????????????????

section("ROI & CLV BY MOVE SIZE BUCKET")

move_buckets = [
    ("5 ? 8%", 0.05, 0.08),
    ("8 ? 12%", 0.08, 0.12),
    ("12 ? 20%", 0.12, 0.20),
    ("20%+", 0.20, 9.99),
    ("(unknown)", None, None),
]

header = ["Move bucket", "Bets", "Hit%", "Staked", "P&L", "ROI%", "CLV%", "Avg odds"]
widths = [12, 5, 7, 9, 9, 8, 8, 9]
print_table(header, [], widths)

for label, lo, hi in move_buckets:
    if lo is None:
        bucket = [r for r in settled if r[10] is None]
    else:
        bucket = [r for r in settled if r[10] is not None and lo <= r[10] < hi]
    if len(bucket) < MIN_BETS:
        continue
    st = bucket_stats(bucket)
    print(
        "  "
        + "  ".join(
            [
                f"{label:<12}",
                f"{st['n']:<5}",
                f"{st['hit']:>5.1f}%",
                f"${st['staked']:>7.2f}",
                f"${st['pnl']:>+7.2f}",
                f"{st['roi']:>+6.1f}%",
                fmt(st["avg_clv"], "%", plus=True).rjust(8),
                f"{st['avg_odds']:>7.2f}",
            ]
        )
    )

print()
print("  Note: backtested edge at ?5% move was +20.9% ROI (2,386-bet held-out season).")
print("  Splits above require 50+ bets each to be reliable.")
print()


# ??????????????????????????????????????????????????????????????????????????????
# 3. BY LEAGUE
# ??????????????????????????????????????????????????????????????????????????????

section("ROI & CLV BY LEAGUE  (min 1 bet; ?2 needed for any signal)")

leagues = {}
for r in settled:
    lg = r[2] or "(none)"
    leagues.setdefault(lg, []).append(r)

league_rows = []
for lg, bets in sorted(leagues.items(), key=lambda x: -len(x[1])):
    st = bucket_stats(bets)
    league_rows.append(
        (
            lg[:32],
            f"{st['n']}",
            f"{st['hit']:.0f}%",
            f"${st['staked']:.0f}",
            f"${st['pnl']:+.2f}",
            f"{st['roi']:+.1f}%",
            fmt(st["avg_clv"], "%", plus=True),
        )
    )

print_table(
    ["League", "N", "Hit%", "Staked", "P&L", "ROI%", "CLV%"],
    league_rows,
    [32, 4, 5, 7, 9, 8, 8],
)
print()
print("  Leagues with negative CLV AND ?3 bets are blacklist candidates.")
print('  Add them to  data/settings.json ? "league_blocklist".')
print()


# ??????????????????????????????????????????????????????????????????????????????
# 4. BY ODDS RANGE
# ??????????????????????????????????????????????????????????????????????????????

section("ROI & CLV BY ODDS RANGE")

odds_buckets = [
    ("1.50 ? 2.00", 1.50, 2.00),
    ("2.00 ? 2.50", 2.00, 2.50),
    ("2.50 ? 3.50", 2.50, 3.50),
    ("3.50+", 3.50, 99.0),
]

header2 = ["Odds range", "Bets", "Hit%", "Staked", "P&L", "ROI%", "CLV%"]
widths2 = [14, 5, 7, 9, 9, 8, 8]
print_table(header2, [], widths2)

for label, lo, hi in odds_buckets:
    bucket = [r for r in settled if r[3] and lo <= r[3] < hi]
    if len(bucket) < MIN_BETS:
        continue
    st = bucket_stats(bucket)
    print(
        "  "
        + "  ".join(
            [
                f"{label:<14}",
                f"{st['n']:<5}",
                f"{st['hit']:>5.1f}%",
                f"${st['staked']:>7.2f}",
                f"${st['pnl']:>+7.2f}",
                f"{st['roi']:>+6.1f}%",
                fmt(st["avg_clv"], "%", plus=True).rjust(8),
            ]
        )
    )
print()


# ??????????????????????????????????????????????????????????????????????????????
# 5. CLV TREND OVER TIME (weekly)
# ??????????????????????????????????????????????????????????????????????????????

section("CLV TREND BY WEEK  (shows whether edge is improving or decaying)")

from collections import defaultdict

weekly: dict = defaultdict(list)
for r in has_clv:
    placed = r[9]  # placed_at string
    if placed:
        # ISO week
        try:
            import datetime

            d = datetime.date.fromisoformat(placed[:10])
            week = f"{d.isocalendar()[0]}-W{d.isocalendar()[1]:02d}"
        except Exception:
            week = placed[:7]
        weekly[week].append(r)

if weekly:
    header3 = ["Week", "Bets (CLV)", "Avg CLV%", "ROI%"]
    widths3 = [10, 12, 10, 8]
    print_table(header3, [], widths3)
    for week in sorted(weekly):
        bets = weekly[week]
        clv_vals = [b[7] * 100 for b in bets if b[7] is not None]
        avg_c = sum(clv_vals) / len(clv_vals) if clv_vals else None
        pnl_w = sum(b[6] or 0 for b in bets)
        stk_w = sum(b[4] or 0 for b in bets)
        roi_w = roi(pnl_w, stk_w)
        print(
            "  "
            + "  ".join(
                [
                    f"{week:<10}",
                    f"{len(bets):<12}",
                    fmt(avg_c, "%", plus=True).rjust(10),
                    f"{roi_w:>+6.1f}%",
                ]
            )
        )
else:
    print("  No CLV data yet ? settlement needs to populate closing_odds.")
print()


# ??????????????????????????????????????????????????????????????????????????????
# 6. RECOMMENDATIONS
# ??????????????????????????????????????????????????????????????????????????????

section("RECOMMENDATIONS")

if s["avg_clv"] is not None and s["avg_clv"] >= 5:
    print("  [OK]  CLV is positive. The strategy is worth continuing.")
    print(f"      Confidence is LOW at {s['n']} settled bets. Target: 300+.")
    print("      Do NOT raise stakes until sample is ? 200 bets.")

# Negative-CLV leagues to flag
bad_leagues = [
    (lg, bucket_stats(bets))
    for lg, bets in leagues.items()
    if len(bets) >= 3
    and (st := bucket_stats(bets))
    and st["avg_clv"] is not None
    and st["avg_clv"] < 0
]
if bad_leagues:
    print()
    print("  [!]   Leagues with negative CLV and ?3 bets (consider blacklisting):")
    for lg, st in bad_leagues:
        print(
            f"        {lg}: CLV={st['avg_clv']:+.1f}%  ROI={st['roi']:+.1f}%  n={st['n']}"
        )

# Move threshold suggestion
hi_move = [r for r in settled if r[10] is not None and r[10] >= 0.10]
lo_move = [r for r in settled if r[10] is not None and r[10] < 0.10]
if hi_move and lo_move:
    hi_st, lo_st = bucket_stats(hi_move), bucket_stats(lo_move)
    print()
    if hi_st["avg_clv"] and lo_st["avg_clv"] and hi_st["avg_clv"] > lo_st["avg_clv"]:
        print(
            f"  [^]  Larger moves (?10%) show higher CLV ({hi_st['avg_clv']:+.1f}%) "
            f"vs smaller moves ({lo_st['avg_clv']:+.1f}%)."
        )
        print(
            "      Consider raising steam_min_move_pct to 10% once you have ?100 bets."
        )

print()
print("  Next milestones:")
milestones = [50, 100, 200, 300, 500]
for m in milestones:
    remaining_m = max(0, m - s["n"])
    status = "[OK] DONE" if remaining_m == 0 else f"  {remaining_m} more bets"
    print(f"    {m:>4} bets ? {status}")

print()
hr("=")
print()
