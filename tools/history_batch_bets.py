"""
history_batch_bets.py
---------------------
Insert ~5,000 backdated paper bets from history.db into bet_log.db.
Samples 1,000 historical matches and places up to 5 bets per match
(1X2 Home/Draw/Away + Over 2.5 / Under 2.5) with outcomes pre-settled.
"""

import sqlite3
import datetime
import sys
from pathlib import Path

# GUARD: this injects thousands of synthetic backdated rows into the LIVE bet
# ledger, which poisons ROI/CLV analytics. Require an explicit flag to run.
if "--confirm" not in sys.argv:
    print("REFUSED: this floods bet_log.db with 5,000 synthetic backdated bets.")
    print("These are NOT real bets and corrupt the research ledger.")
    print("If you truly want this, run with:  --confirm")
    sys.exit(1)

BASE = Path(__file__).resolve().parent.parent
HISTORY_DB = BASE / "data" / "history.db"
BET_LOG_DB = BASE / "data" / "bet_log.db"

STAKE = 3.00
BET_SOURCE = "HISTORY_RESEARCH"

# ── helpers ──────────────────────────────────────────────────────────────────

def make_bet_id(league, date, home, side_abbrev):
    """Deterministic ≤50-char bet_id."""
    lg = (league or "UNK")[:3].upper()
    dt = str(date).replace("/", "").replace("-", "")[:8]
    hm = (home or "UNK")[:3].upper()
    sd = side_abbrev[:6].replace(" ", "")
    raw = f"HIST_{lg}_{dt}_{hm}_{sd}"
    return raw[:50]


def parse_date(raw):
    """Return a datetime string from various raw date formats."""
    raw = str(raw).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%Y/%m/%d"):
        try:
            return datetime.datetime.strptime(raw, fmt).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    # fallback — keep as-is
    return raw + " 00:00:00"


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    print(f"History DB : {HISTORY_DB}")
    print(f"Bet-log DB : {BET_LOG_DB}")

    # ── 1. pull sample from history.db ──────────────────────────────────────
    hcon = sqlite3.connect(HISTORY_DB)
    hcon.row_factory = sqlite3.Row
    cur = hcon.execute(
        """
        SELECT date, league, season, home, away,
               home_goals, away_goals, result,
               odds_h, odds_d, odds_a,
               odds_ch, odds_cd, odds_ca,
               odds_o25, odds_u25
        FROM matches
        WHERE odds_h  IS NOT NULL
          AND odds_d  IS NOT NULL
          AND odds_a  IS NOT NULL
          AND odds_o25 IS NOT NULL
          AND odds_u25 IS NOT NULL
        ORDER BY RANDOM()
        LIMIT 1000
        """
    )
    matches = cur.fetchall()
    hcon.close()
    print(f"\nMatches sampled: {len(matches)}")

    # ── 2. build bet rows ────────────────────────────────────────────────────
    BET_DEFS = [
        # (market_type, line,    side_label,  side_abbrev, key_entry, key_close, win_fn)
        ("1X2", "1X2",   "Home (1)",   "HOM", "odds_h",   "odds_ch",  lambda r, m: m["result"] == "H"),
        ("1X2", "1X2",   "Draw (X)",   "DRW", "odds_d",   "odds_cd",  lambda r, m: m["result"] == "D"),
        ("1X2", "1X2",   "Away (2)",   "AWY", "odds_a",   "odds_ca",  lambda r, m: m["result"] == "A"),
        ("O/U", "2.5",   "Over 2.5",   "OVR", "odds_o25", "odds_o25", lambda r, m: (m["home_goals"] or 0) + (m["away_goals"] or 0) > 2.5),
        ("O/U", "2.5",   "Under 2.5",  "UND", "odds_u25", "odds_u25", lambda r, m: (m["home_goals"] or 0) + (m["away_goals"] or 0) < 2.5),
    ]

    rows = []
    skipped = 0

    for m in matches:
        placed_at = parse_date(m["date"])

        for (mtype, line, side_label, side_abbrev, key_entry, key_close, win_fn) in BET_DEFS:
            entry_odds = m[key_entry]
            close_odds = m[key_close]

            if entry_odds is None or entry_odds <= 1.0:
                skipped += 1
                continue

            # outcome
            try:
                won = win_fn(None, m)
            except Exception:
                won = None

            if won is None:
                skipped += 1
                continue

            result_str = "W" if won else "L"
            pnl = round(STAKE * (entry_odds - 1), 4) if won else -STAKE

            # CLV
            clv = None
            if close_odds and close_odds > 1.0:
                clv = round(entry_odds / close_odds - 1, 6)

            bet_id = make_bet_id(m["league"], m["date"], m["home"], side_abbrev)

            rows.append({
                "bet_id":        bet_id,
                "match_id":      None,
                "player_id":     None,
                "market_type":   mtype,
                "line":          line,
                "side":          side_label,
                "entry_odds":    entry_odds,
                "fair_odds":     None,
                "edge_pct":      None,
                "stake":         STAKE,
                "book":          "Pinnacle",
                "placed_at":     placed_at,
                "lineup_drop_at":None,
                "latency_ms":    None,
                "closing_odds":  close_odds,
                "clv":           clv,
                "result":        result_str,
                "pnl":           pnl,
                "regime":        None,
                "role_shift_flag": 0,
                "bet_source":    BET_SOURCE,
                "is_recommended": 0,
                "model_version": None,
                "fixture_id":    None,
                "league":        m["league"],
                "clv_sharp":     None,
                "best_odds":     entry_odds,
                "best_book":     "Pinnacle",
                "signal_name":   "HISTORY_RESEARCH",
                "move_size":     None,
                "monotonicity":  None,
                "pinnacle_clv":  clv,
            })

    print(f"Bets built : {len(rows)}  (skipped {skipped} due to null/bad odds)")

    # ── 3. insert ────────────────────────────────────────────────────────────
    bcon = sqlite3.connect(BET_LOG_DB)
    cols = [
        "bet_id","match_id","player_id","market_type","line","side",
        "entry_odds","fair_odds","edge_pct","stake","book","placed_at",
        "lineup_drop_at","latency_ms","closing_odds","clv","result","pnl",
        "regime","role_shift_flag","bet_source","is_recommended","model_version",
        "fixture_id","league","clv_sharp","best_odds","best_book","signal_name",
        "move_size","monotonicity","pinnacle_clv",
    ]
    placeholders = ",".join("?" * len(cols))
    sql = f"INSERT OR IGNORE INTO bet_log ({','.join(cols)}) VALUES ({placeholders})"

    inserted = 0
    ignored  = 0
    for r in rows:
        vals = [r[c] for c in cols]
        cur = bcon.execute(sql, vals)
        if cur.rowcount:
            inserted += 1
        else:
            ignored += 1

    bcon.commit()
    bcon.close()

    print(f"\nInserted : {inserted}")
    print(f"Ignored  : {ignored}  (duplicates)")

    # ── 4. summary stats ────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("SUMMARY STATS")
    print("=" * 60)

    settled = [r for r in rows if r["result"] in ("W", "L")]

    def stats(subset, label):
        if not subset:
            print(f"\n{label}: no data")
            return
        wins  = [r for r in subset if r["result"] == "W"]
        total = len(subset)
        wr    = len(wins) / total * 100
        total_pnl  = sum(r["pnl"] for r in subset)
        total_staked = sum(r["stake"] for r in subset)
        roi   = total_pnl / total_staked * 100

        clv_vals = [r["clv"] for r in subset if r["clv"] is not None]
        avg_clv  = sum(clv_vals) / len(clv_vals) * 100 if clv_vals else None

        print(f"\n{label}")
        print(f"  Bets       : {total}")
        print(f"  Win rate   : {wr:.1f}%")
        print(f"  Total P&L  : ${total_pnl:+.2f}")
        print(f"  ROI        : {roi:+.2f}%")
        if avg_clv is not None:
            print(f"  Avg CLV    : {avg_clv:+.3f}%  (n={len(clv_vals)})")
        else:
            print(f"  Avg CLV    : N/A")

    stats(settled,                                 "ALL BETS")
    stats([r for r in settled if r["market_type"] == "1X2"], "1X2 market")
    stats([r for r in settled if r["market_type"] == "O/U"], "O/U market")

    # per side
    for side in ["Home (1)", "Draw (X)", "Away (2)", "Over 2.5", "Under 2.5"]:
        stats([r for r in settled if r["side"] == side], f"  {side}")

    print("\nDone.")


if __name__ == "__main__":
    main()
