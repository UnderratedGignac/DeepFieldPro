# -*- coding: utf-8 -*-
"""
clv_tracker.py — DeepFieldPro CLV & P&L Logger
===============================================
Tracks Closing Line Value (CLV) and running P&L for paper trading.

NAMING CONVENTIONS:
- Parameters: ProperCase suffix _P
- Variables:  ProperCase suffix _V
- SQL keywords: UPPERCASE
- Comments: single line, max 1 line
"""

import os
import sqlite3
import csv
from datetime import datetime, timezone


DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
BET_LOG_CSV = os.path.join(DATA_DIR, 'bet_log.csv')
DB_ODDS = os.path.join(DATA_DIR, 'odds_stream.db')


def init_bet_log_csv():
    """Initialize bet_log.csv with headers if not exists."""
    if not os.path.exists(BET_LOG_CSV):
        headers = [
            'bet_id', 'timestamp', 'player_name', 'market', 
            'entry_odds', 'stake', 'fair_prob', 'target_threshold',
            'closing_odds', 'clv', 'outcome', 'profit_loss', 'status'
        ]
        with open(BET_LOG_CSV, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
        print(f"[OK] Created bet_log.csv at {BET_LOG_CSV}")


def record_bet(PlayerName_P, Market_P, EntryOdds_P, Stake_P,
               FairProb_P, TargetThreshold_P, bet_id=None):
    """
    Record a new bet to CSV. Status starts as OPEN.
    
    Returns: bet_id string
    """
    init_bet_log_csv()
    
    if bet_id is None:
        timestamp = datetime.now(timezone.utc)
        bet_id = f"BET-{timestamp.strftime('%Y%m%d%H%M%S')}-{os.urandom(4).hex()}"
    
    timestamp_str = datetime.now(timezone.utc).isoformat()
    
    row = [
        bet_id,
        timestamp_str,
        PlayerName_P,
        Market_P,
        EntryOdds_P,
        Stake_P,
        FairProb_P,
        TargetThreshold_P,
        None,  # closing_odds (null until settled)
        None,  # clv (computed at settlement)
        None,  # outcome (WIN/LOSS pending)
        None,  # profit_loss (pending)
        'OPEN'
    ]
    
    with open(BET_LOG_CSV, 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(row)
    
    print(f"[BET RECORDED] {bet_id} | {PlayerName_P} | {Market_P} | "
          f"Stake: ${Stake_P:.2f} @ {EntryOdds_P} | Status: OPEN")
    
    return bet_id


def settle_bet(BetId_P, ClosingOdds_P, Outcome_P):
    """
    Settle a bet: update closing_odds, outcome, profit_loss, status.
    
    Computes CLV_V = (EntryOdds_P / ClosingOdds_P) - 1.0
    Positive CLV = we got better than closing price = real edge
    """
    if not os.path.exists(BET_LOG_CSV):
        print(f"ERROR: bet_log.csv not found")
        return False
    
    rows = []
    found = False
    EntryOdds_V = None
    Stake_V = None
    
    # Read all rows
    with open(BET_LOG_CSV, 'r', newline='') as f:
        reader = csv.reader(f)
        headers = next(reader)
        
        for row in reader:
            if row[0] == BetId_P:  # bet_id column
                found = True
                EntryOdds_V = float(row[4]) if row[4] else None
                Stake_V = float(row[5]) if row[5] else None
                
                # Compute CLV
                if ClosingOdds_P and EntryOdds_V:
                    CLV_V = (EntryOdds_V / ClosingOdds_P) - 1.0
                else:
                    CLV_V = None
                
                # Compute profit/loss
                if Outcome_P == 'WIN':
                    ProfitLoss_V = Stake_V * (EntryOdds_V - 1.0) if Stake_V and EntryOdds_V else 0
                elif Outcome_P == 'LOSS':
                    ProfitLoss_V = -Stake_V if Stake_V else 0
                elif Outcome_P == 'VOID':
                    ProfitLoss_V = 0
                else:
                    ProfitLoss_V = None
                
                # Update row
                row[8] = ClosingOdds_P  # closing_odds
                row[9] = f"{CLV_V:.4f}" if CLV_V is not None else None  # clv
                row[10] = Outcome_P  # outcome
                row[11] = f"{ProfitLoss_V:.2f}" if ProfitLoss_V is not None else None  # profit_loss
                row[12] = 'SETTLED'  # status
            
            rows.append(row)
    
    if not found:
        print(f"ERROR: Bet {BetId_P} not found")
        return False
    
    # Write back
    with open(BET_LOG_CSV, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)
    
    print(f"[BET SETTLED] {BetId_P} | Outcome: {Outcome_P} | "
          f"CLV: {CLV_V:.2%}'" if CLV_V else "CLV: N/A")
    
    return True


def generate_report():
    """
    Generate summary report from bet_log.csv.
    
    Prints:
    - Total bets, Win rate, ROI %, Average CLV
    - Avg entry vs closing odds
    - P&L by market type
    - P&L by competition_type (if available)
    - Rolling 10-bet P&L
    """
    if not os.path.exists(BET_LOG_CSV):
        print("ERROR: bet_log.csv not found")
        return
    
    total_bets = 0
    settled_bets = 0
    wins = 0
    total_pnl = 0.0
    clv_values = []
    entry_odds_list = []
    closing_odds_list = []
    
    market_pnl = {}
    rolling_pnl = []
    
    with open(BET_LOG_CSV, 'r', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            total_bets += 1
            
            if row['status'] == 'SETTLED':
                settled_bets += 1
                
                if row['outcome'] == 'WIN':
                    wins += 1
                
                pnl = float(row['profit_loss']) if row['profit_loss'] else 0
                total_pnl += pnl
                rolling_pnl.append(pnl)
                
                if row['clv']:
                    clv_values.append(float(row['clv']))
                
                market = row['market']
                if market not in market_pnl:
                    market_pnl[market] = 0
                market_pnl[market] += pnl
                
                if row['entry_odds']:
                    entry_odds_list.append(float(row['entry_odds']))
                if row['closing_odds']:
                    closing_odds_list.append(float(row['closing_odds']))
    
    if settled_bets == 0:
        print("\nNo settled bets yet.")
        return
    
    win_rate = wins / settled_bets * 100
    total_staked = sum([float(r['stake']) for r in csv.DictReader(open(BET_LOG_CSV)) if r['status'] == 'SETTLED'])
    roi = (total_pnl / total_staked * 100) if total_staked > 0 else 0
    avg_clv = sum(clv_values) / len(clv_values) * 100 if clv_values else 0
    
    avg_entry = sum(entry_odds_list) / len(entry_odds_list) if entry_odds_list else 0
    avg_closing = sum(closing_odds_list) / len(closing_odds_list) if closing_odds_list else 0
    
    # Rolling 10-bet P&L
    last_10_pnl = sum(rolling_pnl[-10:]) if len(rolling_pnl) >= 10 else sum(rolling_pnl)
    
    print("\n" + "="*60)
    print("CLV & P&L REPORT")
    print("="*60)
    print(f"Total Bets:        {total_bets}")
    print(f"Settled Bets:      {settled_bets}")
    print(f"Win Rate:          {win_rate:.1f}%")
    print(f"ROI:               {roi:.2f}%")
    print(f"Total P&L:         ${total_pnl:+.2f}")
    print(f"Average CLV:       {avg_clv:+.2f}%")
    print(f"Avg Entry Odds:    {avg_entry:.3f}")
    print(f"Avg Closing Odds:  {avg_closing:.3f}")
    print(f"Rolling 10-bet P&L: ${last_10_pnl:+.2f}")
    
    print("\nP&L by Market:")
    for market, pnl in sorted(market_pnl.items(), key=lambda x: x[1], reverse=True):
        print(f"  {market:<25} ${pnl:+.2f}")
    
    print("="*60)


def get_rolling_pnl(n=20):
    """Get rolling P&L over last n bets."""
    if not os.path.exists(BET_LOG_CSV):
        return 0
    
    rolling_pnl = []
    with open(BET_LOG_CSV, 'r', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['status'] == 'SETTLED' and row['profit_loss']:
                rolling_pnl.append(float(row['profit_loss']))
    
    last_n = rolling_pnl[-n:] if len(rolling_pnl) >= n else rolling_pnl
    return sum(last_n)


if __name__ == "__main__":
    print("CLV Tracker Test Mode")
    print("="*50)
    
    # Simulate recording and settling a bet
    bet_id = record_bet(
        PlayerName_P="Mohamed Salah",
        Market_P="sot_over_0.5",
        EntryOdds_P=2.10,
        Stake_P=100.0,
        FairProb_P=0.55,
        TargetThreshold_P=0.50
    )
    
    # Settle the bet
    settle_bet(bet_id, ClosingOdds_P=1.95, Outcome_P='WIN')
    
    # Generate report
    generate_report()
