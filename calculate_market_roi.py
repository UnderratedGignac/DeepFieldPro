import sqlite3
import pandas as pd
import os

DB_PATH = 'data/bet_log.db'

def calculate_market_roi():
    conn = sqlite3.connect(DB_PATH)
    
    # Query settled bets
    query = "SELECT market_type, stake, pnl FROM bet_log WHERE result IS NOT NULL"
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    if df.empty:
        print("No settled bets found to calculate ROI.")
        return

    # Aggregate by market
    market_stats = df.groupby('market_type').agg({
        'stake': 'sum',
        'pnl': 'sum'
    })
    
    market_stats['roi'] = (market_stats['pnl'] / market_stats['stake']) * 100
    
    print("\n--- Market ROI Report ---")
    print(market_stats.sort_values(by='roi', ascending=False).to_string())
    
    # Optional: Save for engine usage
    market_stats.to_csv('data/market_roi.csv')
    print("\nROI data saved to data/market_roi.csv")

if __name__ == "__main__":
    calculate_market_roi()
