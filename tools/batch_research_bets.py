"""
batch_research_bets.py — Place paper bets on ALL markets for ALL upcoming fixtures.
====================================================================================
PAPER / SHADOW mode only. No real money is involved.

Purpose: populate bet_log with a wide coverage of bets across all available fixtures
and markets so CLV tracking, settlement analysis, and edge research have a rich dataset.

Markets covered per fixture:
  - 1X2 (Match Result): Home (1), Draw (X), Away (2)
  - Over/Under 2.5 Goals: Over 2.5, Under 2.5

Flat $5 stake per bet. Uses INSERT OR IGNORE to avoid duplicates.

Run:
    .venv\\Scripts\\python.exe tools\\batch_research_bets.py
"""

import os
import sys
import sqlite3
from datetime import datetime, timezone

# GUARD: places bets on EVERY outcome of EVERY fixture (guaranteed -EV vs the
# vig, floods the ledger). Require an explicit flag so it can't run by accident.
if "--confirm" not in sys.argv:
    print("REFUSED: this bets ALL outcomes of ALL fixtures (hundreds of rows).")
    print("The daemon already places disciplined one-best-pick bets per match.")
    print("If you truly want blanket coverage, run with:  --confirm")
    sys.exit(1)

# ── paths ─────────────────────────────────────────────────────────────────────
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ODDS_DB  = os.path.join(BASE, "data", "odds_stream.db")
BET_DB   = os.path.join(BASE, "data", "bet_log.db")
BANK_DB  = os.path.join(BASE, "data", "bankroll.db")

STAKE = 5.0
BET_SOURCE = "RESEARCH_BATCH"


def _parse_kickoff(kt: str) -> datetime:
    """Parse ISO kickoff string (handles trailing Z or +00:00)."""
    if kt.endswith("Z"):
        kt = kt[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(kt)
    except ValueError:
        # Fallback: truncate to seconds
        return datetime.fromisoformat(kt[:19] + "+00:00")


def main():
    now_utc = datetime.now(timezone.utc)
    print(f"Batch research bets — {now_utc.isoformat()}")
    print(f"Stake per bet: ${STAKE:.2f}")
    print()

    odds_conn = sqlite3.connect(ODDS_DB)
    odds_conn.row_factory = sqlite3.Row

    bet_conn = sqlite3.connect(BET_DB)

    # ── 1. Load all fixtures ───────────────────────────────────────────────────
    all_fixtures = odds_conn.execute(
        "SELECT fixture_id, home_team, away_team, kickoff_time, tournament_name FROM fixture"
    ).fetchall()
    print(f"Total fixtures in odds_stream.db: {len(all_fixtures)}")

    # Filter to upcoming only (kickoff in the future)
    future_fixtures = []
    for f in all_fixtures:
        kt = f["kickoff_time"]
        if not kt:
            continue
        try:
            ko = _parse_kickoff(kt)
            # Ensure timezone-aware comparison
            if ko.tzinfo is None:
                ko = ko.replace(tzinfo=timezone.utc)
            if ko > now_utc:
                future_fixtures.append(dict(f))
        except Exception as e:
            # If we can't parse, include it (safer to over-include than miss)
            future_fixtures.append(dict(f))

    print(f"Upcoming fixtures (kickoff > now): {len(future_fixtures)}")

    # ── 2. Fixtures already with OPEN bets — skip them ────────────────────────
    open_fids = set(
        r[0]
        for r in bet_conn.execute(
            "SELECT DISTINCT fixture_id FROM bet_log WHERE result='OPEN'"
        ).fetchall()
        if r[0]
    )
    print(f"Fixture IDs with existing OPEN bets: {len(open_fids)}")

    to_bet = [f for f in future_fixtures if f["fixture_id"] not in open_fids]
    print(f"New fixtures to process: {len(to_bet)}")
    print()

    # ── 3. Process each fixture ────────────────────────────────────────────────
    placed_at = datetime.utcnow().isoformat()
    total_inserted = 0
    skipped_no_odds = 0
    counts = {"1X2": 0, "Over/Under 2.5": 0}

    bets_to_insert = []

    for fix in to_bet:
        fid        = fix["fixture_id"]
        home_team  = fix["home_team"]
        away_team  = fix["away_team"]
        league     = fix["tournament_name"] or ""
        match_id   = f"{home_team} vs {away_team}"

        markets = odds_conn.execute(
            "SELECT market_name, selection_name, raw_odds FROM market WHERE fixture_id = ?",
            (fid,)
        ).fetchall()

        if not markets:
            skipped_no_odds += 1
            continue

        # Build lookup: market_name → {selection_name: raw_odds}
        mkt_map = {}
        for m in markets:
            mn = m["market_name"]
            sn = m["selection_name"]
            ro = m["raw_odds"]
            if mn not in mkt_map:
                mkt_map[mn] = {}
            mkt_map[mn][sn] = ro

        fixture_bets = []

        # ── 1X2 (Match Result) ─────────────────────────────────────────────
        if "Match Result" in mkt_map:
            mr = mkt_map["Match Result"]
            # Map selections: home_team → Home (1), X → Draw (X), away_team → Away (2)
            outcomes = [
                (home_team, "Home (1)"),
                ("X",       "Draw (X)"),
                (away_team, "Away (2)"),
            ]
            for sel_name, side in outcomes:
                odds = mr.get(sel_name)
                if odds is None:
                    # Try case-insensitive fallback
                    for k, v in mr.items():
                        if k.strip().lower() == sel_name.strip().lower():
                            odds = v
                            break
                if odds is None:
                    continue
                market_type = "1X2"
                bet_id = f"RESEARCH_{market_type[:3].upper()}_{fid}_{side[:3].replace(' ', '')}"
                fixture_bets.append({
                    "bet_id":       bet_id,
                    "match_id":     match_id,
                    "player_id":    None,
                    "market_type":  market_type,
                    "line":         None,
                    "side":         side,
                    "entry_odds":   odds,
                    "fair_odds":    None,
                    "edge_pct":     None,
                    "stake":        STAKE,
                    "book":         None,
                    "placed_at":    placed_at,
                    "lineup_drop_at": None,
                    "latency_ms":   None,
                    "closing_odds": None,
                    "clv":          None,
                    "result":       "OPEN",
                    "pnl":          0,
                    "regime":       None,
                    "role_shift_flag": None,
                    "bet_source":   BET_SOURCE,
                    "is_recommended": 0,
                    "model_version": None,
                    "fixture_id":   fid,
                    "league":       league,
                    "clv_sharp":    None,
                    "best_odds":    None,
                    "best_book":    None,
                    "signal_name":  None,
                    "move_size":    None,
                    "monotonicity": None,
                    "pinnacle_clv": None,
                })

        # ── Over/Under 2.5 (Total Goals) ──────────────────────────────────
        if "Total Goals" in mkt_map:
            tg = mkt_map["Total Goals"]
            ou_outcomes = [
                ("Total OVER 2.5",  "Over 2.5"),
                ("Total UNDER 2.5", "Under 2.5"),
            ]
            for sel_name, side in ou_outcomes:
                odds = tg.get(sel_name)
                if odds is None:
                    continue
                market_type = "Over/Under 2.5"
                bet_id = f"RESEARCH_{market_type[:3].upper()}_{fid}_{side[:3].replace(' ', '')}"
                fixture_bets.append({
                    "bet_id":       bet_id,
                    "match_id":     match_id,
                    "player_id":    None,
                    "market_type":  market_type,
                    "line":         2.5,
                    "side":         side,
                    "entry_odds":   odds,
                    "fair_odds":    None,
                    "edge_pct":     None,
                    "stake":        STAKE,
                    "book":         None,
                    "placed_at":    placed_at,
                    "lineup_drop_at": None,
                    "latency_ms":   None,
                    "closing_odds": None,
                    "clv":          None,
                    "result":       "OPEN",
                    "pnl":          0,
                    "regime":       None,
                    "role_shift_flag": None,
                    "bet_source":   BET_SOURCE,
                    "is_recommended": 0,
                    "model_version": None,
                    "fixture_id":   fid,
                    "league":       league,
                    "clv_sharp":    None,
                    "best_odds":    None,
                    "best_book":    None,
                    "signal_name":  None,
                    "move_size":    None,
                    "monotonicity": None,
                    "pinnacle_clv": None,
                })

        bets_to_insert.extend(fixture_bets)

    # ── 4. Insert bets into bet_log ────────────────────────────────────────────
    insert_sql = """
        INSERT OR IGNORE INTO bet_log (
            bet_id, match_id, player_id, market_type, line, side,
            entry_odds, fair_odds, edge_pct, stake, book, placed_at,
            lineup_drop_at, latency_ms, closing_odds, clv, result, pnl,
            regime, role_shift_flag, bet_source, is_recommended, model_version,
            fixture_id, league, clv_sharp, best_odds, best_book,
            signal_name, move_size, monotonicity, pinnacle_clv
        ) VALUES (
            :bet_id, :match_id, :player_id, :market_type, :line, :side,
            :entry_odds, :fair_odds, :edge_pct, :stake, :book, :placed_at,
            :lineup_drop_at, :latency_ms, :closing_odds, :clv, :result, :pnl,
            :regime, :role_shift_flag, :bet_source, :is_recommended, :model_version,
            :fixture_id, :league, :clv_sharp, :best_odds, :best_book,
            :signal_name, :move_size, :monotonicity, :pinnacle_clv
        )
    """

    for bet in bets_to_insert:
        cur = bet_conn.execute(insert_sql, bet)
        if cur.rowcount > 0:
            total_inserted += 1
            counts[bet["market_type"]] += 1

    bet_conn.commit()

    total_staked = total_inserted * STAKE

    # ── 5. Update bankroll ────────────────────────────────────────────────────
    bank_conn = sqlite3.connect(BANK_DB)
    bank_row = bank_conn.execute(
        "SELECT id, current_balance, daily_exposure FROM bankroll ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if bank_row:
        row_id      = bank_row[0]
        old_balance = bank_row[1]
        old_exposure = bank_row[2] or 0.0
        new_balance  = old_balance - total_staked
        new_exposure = old_exposure + total_staked
        bank_conn.execute(
            "UPDATE bankroll SET current_balance = ?, daily_exposure = ? WHERE id = ?",
            (new_balance, new_exposure, row_id)
        )
        bank_conn.commit()
        print(f"Bankroll updated: ${old_balance:.2f} -> ${new_balance:.2f}  (deducted ${total_staked:.2f})")
    bank_conn.close()

    # ── 6. Summary ────────────────────────────────────────────────────────────
    print()
    print("=" * 55)
    print("BATCH RESEARCH BETS — SUMMARY")
    print("=" * 55)
    print(f"  Fixtures processed:          {len(to_bet)}")
    print(f"  Fixtures skipped (no odds):  {skipped_no_odds}")
    print(f"  Bets inserted:")
    print(f"    1X2 bets:                  {counts['1X2']}")
    print(f"    Over/Under 2.5 bets:       {counts['Over/Under 2.5']}")
    print(f"    TOTAL:                     {total_inserted}")
    print(f"  Total staked:                ${total_staked:.2f}")
    print("=" * 55)

    odds_conn.close()
    bet_conn.close()


if __name__ == "__main__":
    main()
