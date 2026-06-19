"""
clv_tracker.py — Closing Line Value (CLV) performance report.

CLV = (entry_odds / closing_odds) - 1

Positive CLV means you took a better price than where the market settled.
Consistently positive CLV is the single strongest predictor of long-term
profitability — it means the market moved AWAY from your position after
you bet (confirming you had value).

Closing line proxy (best available):
  1. Pinnacle snapshot from sharp_history (most accurate)
  2. Last Betarabia price in odds_history before kickoff (weaker proxy)
  3. N/A (bet excluded from CLV stats but still shown for ROI)

Run:
    .venv\Scripts\python.exe tools\clv_tracker.py
"""
import os
import sys
import sqlite3
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
BET_LOG = os.path.join(DATA, "bet_log.db")
SNAP_DB = os.path.join(DATA, "deepfield_browser_data", "completed_fixtures.db")


def _closing_price(fixture_id, market, selection) -> float | None:
    """Best closing price from sharp_history (Pinnacle) then odds_history fallback."""
    if not fixture_id:
        return None
    fid = str(fixture_id)

    try:
        conn = sqlite3.connect(SNAP_DB)
        cur = conn.cursor()

        # Try Pinnacle snapshots first
        cur.execute("""
            SELECT odds FROM sharp_history
            WHERE fixture_id=? AND market=? AND selection=?
            ORDER BY ts DESC LIMIT 1
        """, (fid, market, selection))
        row = cur.fetchone()
        if row:
            conn.close()
            return float(row[0])

        # Fallback: last Betarabia snapshot before kickoff
        cur.execute("""
            SELECT odds FROM odds_history
            WHERE fixture_id=? AND market=? AND selection=?
            ORDER BY timestamp DESC LIMIT 1
        """, (fid, market, selection))
        row = cur.fetchone()
        conn.close()
        return float(row[0]) if row else None

    except Exception:
        return None


def run():
    if not os.path.exists(BET_LOG):
        print("bet_log.db not found.")
        return

    conn = sqlite3.connect(BET_LOG)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT id, match, market, selection, odds, stake, result,
                   bet_source, fixture_id, created_at
            FROM bets
            WHERE result IN ('WON', 'LOST', 'VOID', 'PUSH')
            ORDER BY created_at DESC
        """)
    except Exception as e:
        print(f"Error reading bets: {e}")
        conn.close()
        return

    rows = cur.fetchall()
    conn.close()

    if not rows:
        print("No settled bets yet.")
        return

    stats = defaultdict(lambda: {
        "bets": 0, "roi_num": 0.0, "roi_den": 0.0,
        "clv_sum": 0.0, "clv_n": 0, "beat_close": 0,
    })
    all_rows = []

    for r in rows:
        source = r["bet_source"] or "AI"
        entry  = float(r["odds"] or 0)
        stake  = float(r["stake"] or 1)
        result = r["result"]

        if result == "WON":
            pnl = stake * (entry - 1)
        elif result == "LOST":
            pnl = -stake
        else:
            pnl = 0.0  # VOID / PUSH
        roi = pnl / stake if stake > 0 else 0.0

        closing = _closing_price(r["fixture_id"], r["market"], r["selection"])
        clv = ((entry / closing) - 1.0) if (closing and entry > 0) else None

        s = stats[source]
        s["bets"] += 1
        s["roi_num"] += pnl
        s["roi_den"] += stake
        if clv is not None:
            s["clv_sum"] += clv
            s["clv_n"] += 1
            if clv > 0:
                s["beat_close"] += 1

        all_rows.append({
            "match": r["match"] or "",
            "market": r["market"] or "",
            "sel": r["selection"] or "",
            "entry": entry,
            "closing": closing,
            "clv": clv,
            "result": result,
            "pnl": pnl,
            "source": source,
            "date": (r["created_at"] or "")[:10],
        })

    # ── Summary table ────────────────────────────────────────────────────────
    print()
    print("=" * 70)
    print("  CLOSING LINE VALUE (CLV) REPORT")
    print("=" * 70)
    print(f"  {'Source':<10} {'Bets':>5}  {'Avg CLV':>8}  {'Beat%':>7}  {'ROI':>8}")
    print("  " + "-" * 50)

    overall = {"bets": 0, "roi_num": 0.0, "roi_den": 0.0,
               "clv_sum": 0.0, "clv_n": 0, "beat_close": 0}

    for src, s in sorted(stats.items(),
                          key=lambda x: -(x[1]["clv_sum"] / max(x[1]["clv_n"], 1))):
        avg_clv  = (s["clv_sum"] / s["clv_n"] * 100) if s["clv_n"] else None
        beat_pct = (s["beat_close"] / s["clv_n"] * 100) if s["clv_n"] else None
        roi_pct  = (s["roi_num"] / s["roi_den"] * 100) if s["roi_den"] else 0.0
        clv_s    = f"{avg_clv:+.1f}%" if avg_clv is not None else "    N/A"
        beat_s   = f"{beat_pct:.0f}%" if beat_pct is not None else "  N/A"
        print(f"  {src:<10} {s['bets']:>5}  {clv_s:>8}  {beat_s:>7}  {roi_pct:>+7.1f}%")

        for k in ("bets", "roi_num", "roi_den", "clv_sum", "clv_n", "beat_close"):
            overall[k] += s[k]

    if len(stats) > 1:
        avg_clv  = (overall["clv_sum"] / overall["clv_n"] * 100) if overall["clv_n"] else None
        beat_pct = (overall["beat_close"] / overall["clv_n"] * 100) if overall["clv_n"] else None
        roi_pct  = (overall["roi_num"] / overall["roi_den"] * 100) if overall["roi_den"] else 0.0
        clv_s    = f"{avg_clv:+.1f}%" if avg_clv is not None else "    N/A"
        beat_s   = f"{beat_pct:.0f}%" if beat_pct is not None else "  N/A"
        print("  " + "-" * 50)
        print(f"  {'ALL':<10} {overall['bets']:>5}  {clv_s:>8}  {beat_s:>7}  {roi_pct:>+7.1f}%")

    print("=" * 70)

    # ── Interpretation ───────────────────────────────────────────────────────
    print()
    print("  Interpretation:")
    print("    CLV > 0%   — you took a better price than the market settled at")
    print("    Beat% > 50% — majority of bets had value vs the closing line")
    print("    Positive CLV reliably predicts long-term profit regardless of W/L")
    print()
    print("  Closing line source: sharp_history (Pinnacle) → odds_history (Betarabia)")
    print("  No closing data = bet excluded from CLV stats (still counted in ROI)")

    # ── Recent bets with CLV ─────────────────────────────────────────────────
    clv_rows = [b for b in all_rows if b["clv"] is not None]
    if clv_rows:
        print()
        print(f"  {'Date':<11} {'Match':<33} {'Mkt':<7} {'Entry':>6} {'Close':>6} {'CLV':>7} {'Res':<5}")
        print("  " + "-" * 78)
        for b in clv_rows[:25]:
            entry_s  = f"{b['entry']:.2f}"
            close_s  = f"{b['closing']:.2f}" if b["closing"] else "  N/A"
            clv_s    = f"{b['clv']*100:+.1f}%"
            flag     = " ✓" if b["clv"] > 0 else ""
            print(f"  {b['date']:<11} {b['match'][:33]:<33} {b['market'][:6]:<7} "
                  f"{entry_s:>6} {close_s:>6} {clv_s:>7} {b['result']:<5}{flag}")
    else:
        print()
        print("  No CLV data yet — needs Pinnacle/odds_history closing snapshots.")
        print("  Let the daemon run for a full matchday and re-run this report.")

    print()


if __name__ == "__main__":
    run()
