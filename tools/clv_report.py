"""
clv_report.py -- Closing Line Value performance tracker.

CLV = entry_odds / closing_odds - 1.
  Positive = you beat the closing price = provably good bet in expectation.
  50+ settled bets at avg CLV > +2% = statistically significant edge.

Pinnacle CLV (vs sharp Pinnacle close) is the gold standard.
Betarabia CLV (vs own soft book close) is secondary.

Run: .venv/Scripts/python.exe tools/clv_report.py
"""

import os
import sqlite3

DB = os.path.join(os.path.dirname(__file__), "..", "data", "bet_log.db")


def pct(v):
    return f"{v*100:+.2f}%" if v is not None else "N/A"


def _has_col(con, table, col):
    cols = [r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()]
    return col in cols


def main():
    if not os.path.exists(DB):
        print("bet_log.db not found — daemon hasn't placed any bets yet.")
        return

    con = sqlite3.connect(DB, timeout=5)
    con.row_factory = sqlite3.Row

    has_pinnacle_clv = _has_col(con, "bet_log", "pinnacle_clv")
    has_league = _has_col(con, "bet_log", "league")
    has_move = _has_col(con, "bet_log", "move_size")
    has_source = _has_col(con, "bet_log", "bet_source")

    all_bets = [dict(r) for r in con.execute("SELECT * FROM bet_log ORDER BY placed_at DESC").fetchall()]
    con.close()

    if not all_bets:
        print("bet_log is empty — no bets placed yet.")
        return

    settled = [r for r in all_bets if r.get("result") in ("W", "L")]
    open_bets = [r for r in all_bets if r.get("result") == "OPEN"]
    voided = [r for r in all_bets if r.get("result") == "VOID"]

    # ─── 1. OVERALL SUMMARY ──────────────────────────────────────────────────

    print("\n" + "=" * 62)
    print("  CLV PERFORMANCE REPORT")
    print("=" * 62)
    print(f"  Total bets placed : {len(all_bets)}")
    print(f"  Open              : {len(open_bets)}")
    print(f"  Settled (W/L)     : {len(settled)}")
    print(f"  Voided            : {len(voided)}")

    if settled:
        wins = [r for r in settled if r.get("result") == "W"]
        losses = [r for r in settled if r.get("result") == "L"]
        total_staked = sum(r.get("stake", 0) or 0 for r in settled)
        total_pnl = sum(r.get("pnl", 0) or 0 for r in settled)
        hit_rate = len(wins) / len(settled)
        roi = total_pnl / total_staked if total_staked else 0
        print(f"\n  Hit rate          : {hit_rate:.1%}  ({len(wins)}W / {len(losses)}L)")
        print(f"  Total staked      : ${total_staked:.2f}")
        print(f"  Net P&L           : ${total_pnl:+.2f}")
        print(f"  ROI               : {roi:+.2%}")

    # Betarabia CLV
    with_clv = [r for r in settled if r.get("clv") is not None]
    if with_clv:
        avg_clv = sum(r["clv"] for r in with_clv) / len(with_clv)
        beat_close = sum(1 for r in with_clv if r["clv"] > 0)
        print(f"\n  Betarabia CLV     : {pct(avg_clv)} avg  "
              f"({beat_close}/{len(with_clv)} beat close = {beat_close/len(with_clv):.0%})")
    else:
        print(f"\n  Betarabia CLV     : no data yet (CLV captured at settlement)")

    # Pinnacle CLV
    if has_pinnacle_clv:
        with_pclv = [r for r in settled if r.get("pinnacle_clv") is not None]
        if with_pclv:
            avg_pclv = sum(r["pinnacle_clv"] for r in with_pclv) / len(with_pclv)
            beat_pin = sum(1 for r in with_pclv if r["pinnacle_clv"] > 0)
            print(f"  Pinnacle CLV (*)  : {pct(avg_pclv)} avg  "
                  f"({beat_pin}/{len(with_pclv)} beat Pinnacle = {beat_pin/len(with_pclv):.0%})")
            print("  (*) Gold standard: consistently >+2% CLV = statistically significant edge")
        else:
            print("  Pinnacle CLV (*)  : no data yet (recorded at settlement via live feed)")
    else:
        print("  Pinnacle CLV      : column not yet in schema (run a settlement cycle)")

    need = max(0, 50 - len(settled))
    if need:
        print(f"\n  Note: {need} more settled bets needed for 80% statistical confidence.")

    # ─── 2. BY BET SOURCE ────────────────────────────────────────────────────

    if has_source and settled:
        print("\n\n--- BY BET SOURCE " + "-" * 44)
        print(f"  {'Source':<16} {'Bets':>5} {'Hit':>6} {'ROI':>8} {'Betarabia CLV':>14} {'Pinnacle CLV':>13}")
        print("  " + "-" * 66)

        sources = {}
        for r in settled:
            src = r.get("bet_source") or "unknown"
            sources.setdefault(src, []).append(r)

        for src, grp in sorted(sources.items(), key=lambda kv: -len(kv[1])):
            n = len(grp)
            wins_n = sum(1 for r in grp if r.get("result") == "W")
            staked = sum(r.get("stake", 0) or 0 for r in grp)
            pnl_sum = sum(r.get("pnl", 0) or 0 for r in grp)
            roi_val = pnl_sum / staked if staked else 0
            hit = wins_n / n

            clv_g = [r["clv"] for r in grp if r.get("clv") is not None]
            clv_str = pct(sum(clv_g) / len(clv_g)) if clv_g else "N/A"

            pclv_str = "N/A"
            if has_pinnacle_clv:
                pclv_g = [r["pinnacle_clv"] for r in grp if r.get("pinnacle_clv") is not None]
                if pclv_g:
                    pclv_str = pct(sum(pclv_g) / len(pclv_g))

            print(f"  {src:<16} {n:>5} {hit:>5.1%} {roi_val:>+7.2%} {clv_str:>14} {pclv_str:>13}")

    # ─── 3. BY LEAGUE (top 10) ────────────────────────────────────────────────

    if has_league and settled:
        print("\n\n--- BY LEAGUE (top 10 by count) " + "-" * 30)
        print(f"  {'League':<30} {'Bets':>5} {'Hit':>6} {'ROI':>8} {'Pin CLV':>10}")
        print("  " + "-" * 62)

        leagues = {}
        for r in settled:
            lg = r.get("league") or "Unknown"
            leagues.setdefault(lg, []).append(r)

        for lg, grp in sorted(leagues.items(), key=lambda kv: -len(kv[1]))[:10]:
            n = len(grp)
            wins_n = sum(1 for r in grp if r.get("result") == "W")
            staked = sum(r.get("stake", 0) or 0 for r in grp)
            pnl_sum = sum(r.get("pnl", 0) or 0 for r in grp)
            roi_val = pnl_sum / staked if staked else 0

            pclv_str = "N/A"
            if has_pinnacle_clv:
                pclv_g = [r["pinnacle_clv"] for r in grp if r.get("pinnacle_clv") is not None]
                if pclv_g:
                    pclv_str = pct(sum(pclv_g) / len(pclv_g))

            print(f"  {lg[:30]:<30} {n:>5} {wins_n/n:>5.1%} {roi_val:>+7.2%} {pclv_str:>10}")

    # ─── 4. STEAM MOVE SIZE ANALYSIS ─────────────────────────────────────────

    steam_bets = [r for r in settled if (r.get("bet_source") or "") == "STEAM"]
    if has_move and steam_bets:
        print("\n\n--- STEAM: CLV BY MOVE SIZE " + "-" * 35)
        print(f"  {'Bucket':<12} {'Bets':>5} {'Hit':>6} {'ROI':>8} {'Betarabia CLV':>14} {'Pinnacle CLV':>13}")
        print("  " + "-" * 62)

        buckets = [("<5%", 0, 5), ("5-10%", 5, 10), ("10-20%", 10, 20), (">20%", 20, 9999)]
        for label, lo, hi in buckets:
            grp = [r for r in steam_bets
                   if lo <= (r.get("move_size") or 0) < hi]
            if not grp:
                continue
            n = len(grp)
            wins_n = sum(1 for r in grp if r.get("result") == "W")
            staked = sum(r.get("stake", 0) or 0 for r in grp)
            pnl_sum = sum(r.get("pnl", 0) or 0 for r in grp)
            roi_val = pnl_sum / staked if staked else 0

            clv_g = [r["clv"] for r in grp if r.get("clv") is not None]
            clv_str = pct(sum(clv_g) / len(clv_g)) if clv_g else "N/A"

            pclv_str = "N/A"
            if has_pinnacle_clv:
                pclv_g = [r["pinnacle_clv"] for r in grp if r.get("pinnacle_clv") is not None]
                if pclv_g:
                    pclv_str = pct(sum(pclv_g) / len(pclv_g))

            print(f"  {label:<12} {n:>5} {wins_n/n:>5.1%} {roi_val:>+7.2%} {clv_str:>14} {pclv_str:>13}")

    # ─── 5. RECENT 20 BETS ───────────────────────────────────────────────────

    print("\n\n--- RECENT 20 BETS " + "-" * 43)
    print(f"  {'Match':<28} {'Src':<6} {'Odds':>5} {'Res':>4} {'PnL':>7} {'BCLV':>7} {'PCLV':>7}")
    print("  " + "-" * 68)

    for r in all_bets[:20]:
        match = (r.get("match_id") or "")[:28]
        src = (r.get("bet_source") or "?")[:6]
        odds = r.get("entry_odds", 0) or 0
        res = r.get("result") or "?"
        pnl_val = r.get("pnl", 0) or 0
        clv_val = r.get("clv")
        pclv_val = r.get("pinnacle_clv") if has_pinnacle_clv else None
        clv_s = f"{clv_val*100:+.1f}%" if clv_val is not None else "  N/A"
        pclv_s = f"{pclv_val*100:+.1f}%" if pclv_val is not None else "  N/A"
        print(f"  {match:<28} {src:<6} {odds:>5.2f} {res:>4} {pnl_val:>+6.2f} {clv_s:>7} {pclv_s:>7}")

    # ─── 6. CLV TREND ────────────────────────────────────────────────────────

    if len(settled) >= 20:
        half = len(settled) // 2
        old_half = settled[half:]   # older bets (list is DESC by placed_at)
        new_half = settled[:half]   # newer bets

        def avg_pclv(grp):
            v = [r["pinnacle_clv"] for r in grp if r.get("pinnacle_clv") is not None]
            return sum(v) / len(v) if v else None

        def avg_clv(grp):
            v = [r["clv"] for r in grp if r.get("clv") is not None]
            return sum(v) / len(v) if v else None

        print("\n\n--- CLV TREND (first half vs second half) " + "-" * 20)
        old_clv = avg_clv(old_half)
        new_clv = avg_clv(new_half)
        print(f"  Earlier bets : Betarabia CLV = {pct(old_clv)}   n={len(old_half)}")
        print(f"  Recent bets  : Betarabia CLV = {pct(new_clv)}   n={len(new_half)}")
        if has_pinnacle_clv:
            old_pclv = avg_pclv(old_half)
            new_pclv = avg_pclv(new_half)
            print(f"  Earlier bets : Pinnacle CLV  = {pct(old_pclv)}")
            print(f"  Recent bets  : Pinnacle CLV  = {pct(new_pclv)}")
            if old_pclv is not None and new_pclv is not None:
                trend = "improving" if new_pclv > old_pclv else "degrading"
                print(f"  Trend: {trend} ({pct(new_pclv - old_pclv)} change)")

    print()


if __name__ == "__main__":
    main()
