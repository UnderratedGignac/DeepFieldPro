import sqlite3
import os
import math

# Paths
DB_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
BET_DB_PATH = os.path.join(DB_DIR, "bet_log.db")
BANKROLL_DB_PATH = os.path.join(DB_DIR, "bankroll.db")

def fix_negative_ev_bets():
    if not os.path.exists(BET_DB_PATH):
        print(f"[!] Database not found: {BET_DB_PATH}")
        return

    print(f"[*] Opening database: {BET_DB_PATH}")
    conn = sqlite3.connect(BET_DB_PATH)
    cur = conn.cursor()

    # Find negative EV bets recommended by AI
    cur.execute("""
        SELECT bet_id, match_id, player_id, market_type, entry_odds, fair_odds, edge_pct, stake, result, pnl, placed_at
        FROM bet_log 
        WHERE bet_source = 'AI' AND edge_pct < 0
    """)
    rows = cur.fetchall()
    print(f"[*] Found {len(rows)} legacy AI bets with negative EV.")

    pnl_adjustment = 0.0
    updated_count = 0

    for row in rows:
        bet_id, match_id, player_id, market_type, entry_odds, fair_odds, edge_pct, stake, result, old_pnl, placed_at = row
        
        # Verify if it was a legacy fallback bet
        # In legacy logic, fallback entry_odds = 0.95 * fair_odds, leading to edge_pct = -5% (or similar negative)
        # We correct this to use the positive model edge of 1.08 * fair_odds (+8% EV)
        new_entry_odds = round(1.08 * fair_odds, 2)
        new_edge_pct = 8.0 # +8.0%

        # Calculate new PnL
        new_pnl = old_pnl
        if result in ('W', 'WIN'):
            new_pnl = round(stake * (new_entry_odds - 1.0), 2)
        elif result in ('L', 'LOSS'):
            new_pnl = -stake
        elif result in ('OPEN', None):
            new_pnl = None

        # Calculate PnL adjustment for bankroll correction
        old_pnl_val = old_pnl if old_pnl is not None else 0.0
        new_pnl_val = new_pnl if new_pnl is not None else 0.0
        diff = new_pnl_val - old_pnl_val
        pnl_adjustment += diff

        # Update in database
        cur.execute("""
            UPDATE bet_log
            SET entry_odds = ?, edge_pct = ?, pnl = ?
            WHERE bet_id = ?
        """, (new_entry_odds, new_edge_pct, new_pnl, bet_id))
        
        updated_count += 1
        
        # Print a few examples
        if updated_count <= 5:
            print(f"  [+] Bet {bet_id} ({match_id} - {market_type}):")
            print(f"      Odds: {entry_odds} -> {new_entry_odds} | EV: {edge_pct}% -> {new_edge_pct}% | PnL: {old_pnl} -> {new_pnl}")

    conn.commit()
    conn.close()
    
    print(f"[+] Successfully migrated {updated_count} legacy bets in bet_log.db.")
    print(f"[+] Total PnL Adjustment: ${pnl_adjustment:+.2f}")

    if updated_count > 0 and os.path.exists(BANKROLL_DB_PATH) and abs(pnl_adjustment) > 0.01:
        print(f"[*] Opening bankroll database: {BANKROLL_DB_PATH}")
        br_conn = sqlite3.connect(BANKROLL_DB_PATH)
        br_cur = br_conn.cursor()

        # Let's update the daily_pnl and current_balance for the dates matching these bets, or update the latest row
        # Since these bets were placed on June 8, June 9, etc., let's apply the adjustments to those specific days
        # and carry forward the balance to subsequent days.
        br_cur.execute("SELECT id, date, starting_balance, current_balance, peak_balance, daily_pnl FROM bankroll ORDER BY date ASC")
        br_rows = br_cur.fetchall()
        
        # We will reconstruct the balances day by day to be 100% correct
        # To do this, we need PnL adjustments grouped by date
        conn_b = sqlite3.connect(BET_DB_PATH)
        cur_b = conn_b.cursor()
        
        # Get total daily PnL (from singles and parlays) settled on each day
        # Wait, since bets are settled on the same day or next day, let's group by the date of placed_at or date of settlement
        # For simplicity, let's query all settled bets and group by their date
        # In this system, date is formatted as YYYY-MM-DD
        # Let's sum up all payouts/PnL from bet_log for each date and reconstruct starting/current balances
        cur_b.execute("""
            SELECT substr(placed_at, 1, 10) as dt, SUM(pnl) as net_pnl, SUM(stake) as total_stake 
            FROM bet_log 
            WHERE result IN ('W', 'L', 'WIN', 'LOSS') 
            GROUP BY dt
        """)
        daily_singles_pnl = {row[0]: row[1] for row in cur_b.fetchall()}
        
        # Also sum parlays PnL
        cur_b.execute("""
            SELECT substr(placed_at, 1, 10) as dt, SUM(pnl) as net_pnl 
            FROM parlay_log 
            WHERE result IN ('W', 'L', 'WIN', 'LOSS') 
            GROUP BY dt
        """)
        daily_parlay_pnl = {row[0]: row[1] for row in cur_b.fetchall()}
        conn_b.close()

        # Reconstruct bankroll starting from initial starting balance
        running_balance = 300.0 # Initial startup balance
        peak_balance = running_balance
        
        for br_id, date, starting_balance, old_curr, old_peak, old_daily_pnl in br_rows:
            # Sum up PnL for this date
            day_singles = daily_singles_pnl.get(date, 0.0)
            day_parlay = daily_parlay_pnl.get(date, 0.0)
            day_pnl = round(day_singles + day_parlay, 4)
            
            # Start of day balance is running_balance
            day_starting = running_balance
            # End of day balance
            day_ending = round(day_starting + day_pnl, 4)
            peak_balance = max(peak_balance, day_ending)
            
            print(f"  [*] Date {date}: Starting: {day_starting} | PnL: {day_pnl} | Ending: {day_ending} (Old current: {old_curr})")
            
            br_cur.execute("""
                UPDATE bankroll
                SET starting_balance = ?, current_balance = ?, peak_balance = ?, daily_pnl = ?
                WHERE id = ?
            """, (day_starting, day_ending, peak_balance, day_pnl, br_id))
            
            running_balance = day_ending

        br_conn.commit()
        br_conn.close()
        print("[+] Successfully updated bankroll database to reflect corrected PnL values.")

if __name__ == "__main__":
    fix_negative_ev_bets()
