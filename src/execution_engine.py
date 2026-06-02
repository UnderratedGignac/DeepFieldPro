# -*- coding: utf-8 -*-
import os; os.environ.setdefault('PYTHONUTF8', '1')
"""
execution_engine.py
--------------------
The central execution nervous system for Deep Field Pro.

This is the ONLY file that should place bets. It:
  1. Receives a pricing opportunity (model output)
  2. Validates system status (bankroll HALT check)
  3. Strips vig and calculates true edge
  4. Gates on minimum edge threshold
  5. Sizes the bet via fractional Kelly
  6. Routes to the best available book
  7. Registers the bet with the bankroll tracker
  8. Logs the bet with full metadata
  9. Updates the book account
  10. Fires a Telegram alert

Nothing else in the codebase should call bet_logger, bankroll_tracker,
or account_manager directly. All bets go through here.
"""

import os
import time
from datetime import datetime, timezone
from dotenv import load_dotenv

from bankroll_tracker  import get_status, register_bet, register_settlement, init_bankroll_db
from account_manager   import get_best_book_for_stake, update_account_post_bet, init_account_db
from kelly_calculator  import get_recommended_stake
from bet_logger        import log_bet, init_bet_log_db
from alerter           import alert_bet_placed, alert_pipeline_failure
from utils             import remove_vig, calculate_edge

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

# ─────────────────────────────────────────────────────────
# Minimum thresholds — adjust based on your model's accuracy
# ─────────────────────────────────────────────────────────
MIN_EDGE_PCT          = 0.03   # 3% minimum edge after vig removal
MIN_ODDS              = 1.30   # Don't bet below 1.30 (too little upside)
MAX_ODDS              = 5.00   # Don't bet above 5.00 (too much variance)
KELLY_FRACTION        = 0.25   # Quarter Kelly
PAPER_TRADE_MODE      = True   # ← SET TO False ONLY AFTER BACKTEST VALIDATES EDGE


def place_bet(
    fair_prob:       float,
    market_odds:     float,
    all_outcome_odds: list,   # e.g. [2.10, 1.80] for over/under — needed for vig strip
    match_id:        str,
    player_id:       str,
    market_type:     str,     # e.g. 'passes_over_40.5'
    line:            float,   # e.g. 40.5
    side:            str,     # 'over' or 'under'
    lineup_drop_at:  str,     # ISO timestamp of lineup release
    latency_ms:      int,     # ms from lineup drop to this function call
    regime:          str,     # market regime from Market Regime Intelligence layer
    role_shift_flag: bool     # was a role shift detected for this player?
):
    """
    Attempt to place a bet. Goes through all safety checks before execution.

    fair_prob:        Model's true win probability for this side (e.g. 0.55)
    market_odds:      The odds being offered by the bookmaker (e.g. 2.10)
    all_outcome_odds: All odds for this market (for vig stripping) e.g. [2.10, 1.80]

    Returns: bet_id (str) if placed, None if rejected.
    """
    execution_start = time.time()

    print(f"\n" + "-"*50)
    print(f"Evaluating opportunity: {market_type} | {side} {line} @ {market_odds}")
    print(f"Model fair prob: {fair_prob:.4f} | Market odds: {market_odds}")

    # Guard 0: Survival window check (must be within 90 seconds of lineup drop)
    try:
        drop_time = datetime.fromisoformat(lineup_drop_at)
        seconds_elapsed = (datetime.now(timezone.utc) - drop_time).total_seconds()
        if seconds_elapsed > 90:
            print(f"SKIP: Outside survival window ({seconds_elapsed:.0f}s since lineup drop)")
            return None
    except Exception:
        pass

    # Guard 1: Odds range filter
    if not (MIN_ODDS <= market_odds <= MAX_ODDS):
        print(f"SKIP: Odds {market_odds} outside acceptable range [{MIN_ODDS}, {MAX_ODDS}]")
        return None

    # Guard 2: Vig strip + edge check
    try:
        fair_probs, overround = remove_vig(all_outcome_odds)
        # The vig-stripped market probability for this side
        # (assumes this side is the first element in all_outcome_odds)
        side_index = 0  # Caller must ensure this side's odds is first in all_outcome_odds
        vig_stripped_market_prob = fair_probs[side_index]
    except Exception as e:
        print(f"SKIP: Vig stripping failed - {e}")
        return None

    edge = fair_prob - vig_stripped_market_prob
    print(f"Overround: {(overround-1)*100:.2f}% | Vig-stripped market prob: {vig_stripped_market_prob:.4f}")
    print(f"True edge: {edge*100:.2f}%")

    if edge < MIN_EDGE_PCT:
        print(f"SKIP: Edge {edge*100:.2f}% below minimum {MIN_EDGE_PCT*100:.0f}%")
        return None

    # Guard 3: System HALT check
    status = get_status()
    if status['status'] == 'HALT':
        print(f"SKIP: System is HALTED. Reason in bankroll DB.")
        return None

    # Guard 3.5: Max 2 bets per match to avoid correlated exposure
    import sqlite3
    DB_BETLOG = os.path.join(os.path.dirname(__file__), '..', 'data', 'bet_log.db')
    conn = sqlite3.connect(DB_BETLOG)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM bet_log WHERE match_id = ? AND result IS NULL", (match_id,))
    open_bets = cursor.fetchone()[0]
    conn.close()
    if open_bets >= 2:
        print(f"SKIP: Correlation limit - already {open_bets} open bets on match {match_id}")
        return None

    # Step 4: Calculate stake
    current_bankroll = status['current_balance']
    stake = get_recommended_stake(fair_prob, market_odds, current_bankroll, KELLY_FRACTION)

    if stake <= 0:
        print(f"SKIP: Kelly sizing returned $0 stake.")
        return None

    print(f"Bankroll: ${current_bankroll:.2f} | Recommended stake: ${stake:.2f}")

    # Step 5: Route to best book
    book = get_best_book_for_stake(stake)
    if not book:
        print(f"SKIP: No active bookmaker can accept a ${stake:.2f} stake right now.")
        return None

    print(f"Routing to: {book}")

    # ─── PAPER TRADE MODE ────────────────────────────────────────
    if PAPER_TRADE_MODE:
        import uuid
        paper_id = f"PAPER-{str(uuid.uuid4())[:8]}"
        print(f"[PAPER TRADE] Would bet ${stake:.2f} @ {market_odds} | Edge: {edge*100:.2f}% | ID: {paper_id}")
        alert_bet_placed(paper_id, f"[PAPER] {market_type} {side} {line}", stake, edge)
        return paper_id
    # ─────────────────────────────────────────────────────────────

    # Step 6: Register with bankroll tracker (enforces all limits)
    if not register_bet(stake):
        print(f"SKIP: Bankroll tracker rejected the bet (limit hit or HALT).")
        return None

    # Step 7: Log the bet
    placed_at = datetime.now(timezone.utc).isoformat()
    fair_price = 1.0 / fair_prob  # Convert prob back to decimal odds

    bet_id = log_bet(
        match_id       = match_id,
        player_id      = player_id,
        market_type    = market_type,
        line           = line,
        side           = side,
        entry_odds     = market_odds,
        fair_odds      = fair_price,
        edge_pct       = edge,
        stake          = stake,
        book           = book,
        lineup_drop_at = lineup_drop_at,
        latency_ms     = latency_ms,
        regime         = regime,
        role_shift_flag = role_shift_flag
    )

    # Step 8: Update book account
    update_account_post_bet(book, stake)

    # Step 9: Fire alert
    alert_bet_placed(bet_id, f"{market_type} {side} {line}", stake, edge)

    execution_ms = int((time.time() - execution_start) * 1000)
    print(f"[BET PLACED] ID: {bet_id} | {book} | ${stake:.2f} @ {market_odds} | "
          f"Edge: {edge*100:.2f}% | Execution: {execution_ms}ms")

    return bet_id


def settle_bet(bet_id: str, result: str, closing_odds: float, stake: float, odds: float):
    """
    Call after a match finishes to settle a bet.

    result:       'win', 'loss', or 'void'
    closing_odds: Pre-kickoff closing line for CLV tracking
    stake:        Original stake placed (same as logged)
    odds:         Entry odds (same as logged)

    pnl convention:
      win  → stake * (odds - 1)    ← profit only
      loss → 0                      ← stake already gone from register_bet
      void → stake                  ← full refund
    """
    import sqlite3
    from clv_updater import update_clv

    if result == 'win':
        pnl = stake * (odds - 1.0)
    elif result == 'loss':
        pnl = 0.0
    elif result == 'void':
        pnl = stake
    else:
        print(f"Unknown result '{result}' for bet {bet_id}. Settlement skipped.")
        return

    # Update bankroll with profit/refund
    register_settlement(pnl)

    # Mark result in bet log
    DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'bet_log.db')
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    net_pnl = pnl if result != 'loss' else -stake  # True P&L including stake cost
    cursor.execute('''
        UPDATE bet_log SET result = ?, pnl = ?, closing_odds = ? WHERE bet_id = ?
    ''', (result, net_pnl, closing_odds, bet_id))
    conn.commit()
    conn.close()

    print(f"Bet {bet_id} settled: {result.upper()} | P&L: ${net_pnl:+.2f}")

    # Trigger CLV update
    update_clv()


def initialize_all():
    """Run this once on first startup to create all required databases."""
    print("Initializing all databases...")
    init_bankroll_db()
    init_account_db()
    init_bet_log_db()
    from lineup_parser       import init_db as init_lineups
    from role_baseline_builder import init_history_db
    from odds_feed           import init_db as init_odds, start_db_writer
    init_lineups()
    init_history_db()
    init_odds()
    start_db_writer()
    print("[OK] All systems initialized and ready.")


if __name__ == "__main__":
    initialize_all()

    # --- Example: Simulate a bet being evaluated ---
    print("\n--- Test: Simulating a bet opportunity ---")
    result = place_bet(
        fair_prob        = 0.54,          # Model says 54% chance
        market_odds      = 2.00,          # Book is offering 2.00 (50% implied)
        all_outcome_odds = [2.00, 1.90],  # Over and Under odds
        match_id         = 'TEST_MATCH_001',
        player_id        = 'PLAYER_123',
        market_type      = 'passes_over_40.5',
        line             = 40.5,
        side             = 'over',
        lineup_drop_at   = datetime.now(timezone.utc).isoformat(),
        latency_ms       = 3200,
        regime           = 'lineup_adjustment_window',
        role_shift_flag  = False
    )
    if result:
        print(f"\nResult: Bet placed - ID: {result}")
    else:
        print("\nResult: No bet placed (check guards above)")

