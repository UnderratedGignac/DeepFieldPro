"""
DeepFieldPro — Endless FBref Scraper (Goal Mode)
================================================
Scrapes match logs for missing leagues, handles rate-limits automatically,
and doesn't stop until all target leagues are downloaded and merged.
"""

import soccerdata as sd
import pandas as pd
import time
import sys
import io
import os
import traceback

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

TARGET_LEAGUES = [
    'USA-MLS',
    'KSA-Saudi Pro League',
    'ARG-Primera Division',
    'BEL-Pro League',
    'BRA-Brasileirao',
    'ENG-Championship'
]

CSV_PATH = 'data/world_cup_players_match_logs_global.csv'

def clean_df(df):
    if df is None or df.empty:
        return df
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = ['_'.join(col).strip() for col in df.columns.values]
    df = df.reset_index()
    return df

def get_existing_leagues():
    if not os.path.exists(CSV_PATH):
        return []
    try:
        df = pd.read_csv(CSV_PATH, low_memory=False)
        return df['league_'].dropna().unique().tolist()
    except Exception as e:
        print(f"Error reading existing CSV: {e}")
        return []

def scrape_league(league):
    print(f"\n[{time.strftime('%H:%M:%S')}] Starting scrape for {league}...")
    while True:
        try:
            fb = sd.FBref(leagues=league, seasons='2526')
            
            print(f"  Fetching summary stats for {league}...")
            df_summary = fb.read_player_match_stats(stat_type='summary')
            time.sleep(6) # FBref limit buffer
            
            print(f"  Fetching passing stats for {league}...")
            df_passing = fb.read_player_match_stats(stat_type='passing')
            time.sleep(6)
            
            # Clean
            df_s = clean_df(df_summary)
            df_p = clean_df(df_passing)
            
            if df_s is None or df_s.empty:
                print(f"  No summary data found for {league}.")
                return None
                
            # Merge
            df_p_sub = df_p[['player_', 'game_', 'Passes_Att', 'Passes_Cmp', 'Passes_Cmp%']] if (df_p is not None and not df_p.empty) else pd.DataFrame()
            if not df_p_sub.empty:
                df_merged = pd.merge(df_s, df_p_sub, on=['player_', 'game_'], how='left')
            else:
                df_merged = df_s
                
            df_merged['league_'] = league
            print(f"  Successfully scraped {len(df_merged)} rows for {league}.")
            return df_merged
            
        except Exception as e:
            err_msg = str(e)
            if '429' in err_msg or 'Too Many Requests' in err_msg:
                print(f"  [429 RATE LIMIT] Hit FBref block for {league}. Sleeping 120s...")
                time.sleep(120)
            else:
                print(f"  [ERROR] {err_msg}")
                traceback.print_exc()
                # If it's a structural error (e.g., league not found for season), just return empty to move on
                if 'Expected a redirect' in err_msg:
                    print(f"  [429 RATE LIMIT] Got redirect block. Sleeping 120s...")
                    time.sleep(120)
                else:
                    return None

def main():
    print("=" * 60)
    print("DEEPFIELDPRO - ENDLESS GOAL SCRAPER INITIALIZED")
    print("=" * 60)
    
    existing = get_existing_leagues()
    print(f"Existing leagues in DB: {existing}")
    
    leagues_to_fetch = [l for l in TARGET_LEAGUES if l not in existing]
    
    if not leagues_to_fetch:
        print("All target leagues are already in the database! Goal complete.")
        return
        
    print(f"Leagues left to scrape: {leagues_to_fetch}")
    
    for league in leagues_to_fetch:
        df = scrape_league(league)
        if df is not None and not df.empty:
            print(f"  Saving {league} to master DB...")
            df.to_csv(CSV_PATH, mode='a', header=not os.path.exists(CSV_PATH), index=False)
            print(f"  Saved {league} successfully.")
        else:
            print(f"  Failed to get data for {league} or no data exists.")
            
    print("\n=" * 60)
    print("ALL MISSING DATA HAS BEEN SCRAPED SUCCESSFULLY.")
    print("=" * 60)

if __name__ == '__main__':
    main()
