"""
worldcup_analysis.py -- World Cup 2026 Pinnacle sharp-money analysis.

Shows live Pinnacle odds for upcoming WC matches and identifies
which matches have seen the largest line movements (sharp money signals).

Run: .venv/Scripts/python.exe tools/worldcup_analysis.py
"""

import os
import sqlite3
import time
import datetime

DB = os.path.join(
    os.path.dirname(__file__), "..", "data", "deepfield_browser_data", "completed_fixtures.db"
)


def _dt(ts):
    if not ts:
        return "?"
    try:
        return datetime.datetime.utcfromtimestamp(ts).strftime("%m-%d %H:%M UTC")
    except Exception:
        return "?"


def main():
    if not os.path.exists(DB):
        print("completed_fixtures.db not found")
        return

    con = sqlite3.connect(DB, timeout=5)
    now = time.time()

    # ── 1. All World Cup matches with current (latest) Pinnacle odds ──────────
    latest = con.execute(
        """
        SELECT match_key, home_team, away_team, starts_ts,
               MAX(CASE WHEN selection='home' THEN decimal_odds END) as h_odds,
               MAX(CASE WHEN selection='draw' THEN decimal_odds END) as d_odds,
               MAX(CASE WHEN selection='away' THEN decimal_odds END) as a_odds,
               MAX(CASE WHEN selection='home' THEN devig_prob END) as p_home,
               MAX(CASE WHEN selection='draw' THEN devig_prob END) as p_draw,
               MAX(CASE WHEN selection='away' THEN devig_prob END) as p_away,
               MAX(ts) as last_snap
        FROM (
          SELECT match_key, home_team, away_team, starts_ts, selection,
                 decimal_odds, devig_prob, ts,
                 ROW_NUMBER() OVER (PARTITION BY match_key, selection ORDER BY ts DESC) as rn
          FROM sharp_odds_history
          WHERE league LIKE '%World Cup%' OR league LIKE '%world cup%'
        )
        WHERE rn = 1
        GROUP BY match_key, home_team, away_team, starts_ts
        ORDER BY starts_ts ASC
        """
    ).fetchall()

    upcoming = [r for r in latest if r[3] and r[3] > now]
    past = [r for r in latest if not r[3] or r[3] <= now]

    print("\n=== WORLD CUP 2026 — PINNACLE LIVE ODDS ===\n")
    print(f"Matches in DB : {len(latest)} total, {len(upcoming)} upcoming, {len(past)} completed/started")

    if not upcoming:
        print("\nNo upcoming WC matches found in sharp_odds_history.")
        print("(Either the Pinnacle feed hasn't captured them yet, or all matches started.)")
    else:
        print(f"\n{'Match':<40} {'Kickoff':>16}  {'H':>5} {'D':>5} {'A':>5}  {'pHome':>6} {'pAway':>6}")
        print("-" * 93)
        for row in upcoming:
            mk, h, a, sts, ho, do_, ao, ph, pd, pa, last = row
            stale_min = (now - last) / 60 if last else 999
            stale_str = f"  [stale {stale_min:.0f}m]" if stale_min > 5 else ""
            h_str = f"{ho:.2f}" if ho else "  N/A"
            d_str = f"{do_:.2f}" if do_ else "  N/A"
            a_str = f"{ao:.2f}" if ao else "  N/A"
            ph_str = f"{ph:.1%}" if ph else "  N/A"
            pa_str = f"{pa:.1%}" if pa else "  N/A"
            print(f"  {mk[:38]:<38} {_dt(sts):>16}  {h_str:>5} {d_str:>5} {a_str:>5}  {ph_str:>6} {pa_str:>6}{stale_str}")

    # ── 2. Biggest Pinnacle line movements (sharp money signal) ───────────────

    print("\n\n=== TOP LINE MOVEMENTS (Sharp Money Signal) ===\n")
    print("Comparing earliest vs latest Pinnacle snapshot per WC match.\n")

    moves_data = con.execute(
        """
        SELECT match_key, home_team, away_team, starts_ts, selection,
               MIN(devig_prob) as min_prob, MAX(devig_prob) as max_prob,
               (SELECT devig_prob FROM sharp_odds_history s2
                WHERE s2.match_key = s.match_key AND s2.selection = s.selection
                ORDER BY ts ASC LIMIT 1) as earliest_prob,
               (SELECT devig_prob FROM sharp_odds_history s2
                WHERE s2.match_key = s.match_key AND s2.selection = s.selection
                ORDER BY ts DESC LIMIT 1) as latest_prob,
               COUNT(*) as snaps,
               MIN(ts) as first_ts,
               MAX(ts) as last_ts
        FROM sharp_odds_history s
        WHERE (league LIKE '%World Cup%' OR league LIKE '%world cup%')
        GROUP BY match_key, home_team, away_team, starts_ts, selection
        """
    ).fetchall()

    # Compute move per match/selection
    move_rows = []
    for row in moves_data:
        mk, h, a, sts, sel, mn, mx, ep, lp, snaps, ft, lt = row
        if ep is None or lp is None:
            continue
        move = lp - ep  # positive = market moved toward this selection (sharps back it)
        span_h = round((lt - ft) / 3600, 1) if ft and lt else 0
        move_rows.append((abs(move), move, mk, h, a, sts, sel, ep, lp, snaps, span_h))

    move_rows.sort(reverse=True)

    print(f"  {'Match':<38} {'Sel':>5} {'Earliest':>9} {'Latest':>9} {'Move':>8} {'Snaps':>6} {'Span':>8}")
    print("  " + "-" * 88)
    for _, move, mk, h, a, sts, sel, ep, lp, snaps, span_h in move_rows[:15]:
        direction = "^" if move > 0 else "v"
        upcoming_flag = " [UPCOMING]" if sts and sts > now else ""
        print(
            f"  {mk[:38]:<38} {sel:>5}  {ep:>8.3f}  {lp:>8.3f}  "
            f"{move*100:>+7.2f}pp  {snaps:>6}  {span_h:>6.1f}h{upcoming_flag}"
        )

    # ── 3. WC upcoming — biggest moves only ──────────────────────────────────

    upcoming_moves = [(abs_m, mv, mk, h, a, sts, sel, ep, lp, sn, sp)
                      for abs_m, mv, mk, h, a, sts, sel, ep, lp, sn, sp in move_rows
                      if sts and sts > now]

    if upcoming_moves:
        print("\n\n=== UPCOMING WC MATCHES — BIGGEST PINNACLE MOVES ===\n")
        print("These are the sharp-money signals worth monitoring:\n")
        print(f"  {'Match':<38} {'Sel':>5} {'Move':>8} {'Snaps':>6} {'Kickoff'}")
        print("  " + "-" * 80)
        for _, move, mk, h, a, sts, sel, ep, lp, sn, sp in upcoming_moves[:10]:
            direction = "SHARP^" if move > 0 else "dump v"
            print(
                f"  {mk[:38]:<38} {sel:>5}  {move*100:>+7.2f}pp  {sn:>5}   {_dt(sts)}  [{direction}]"
            )

    con.close()
    print()


if __name__ == "__main__":
    main()
