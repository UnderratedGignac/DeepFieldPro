"""
DeepFieldPro - 2025 Minor Leagues Scraper
=========================================
Bypasses API rate limits and paywalls by directly querying the Sofascore API 
via SeleniumBase (Undetected ChromeDriver).

This script targets the 2025 season data for leagues that FBref and API-Football 
(Free) do not provide.
"""

import os
import json
import time
import pandas as pd
from seleniumbase import SB

# Target Leagues mapping (Sofascore Unique Tournament IDs)
# 11365: Saudi Pro League
# 242: MLS
# 17: English Championship
# 268: Argentina Liga Profesional
# 325: Brazil Serie A
TARGET_LEAGUES = {
    11365: 'Saudi Pro League',
    242: 'MLS',
    17: 'ENG-Championship',
    268: 'ARG-Primera',
    325: 'BRA-Serie A'
}

DATA_DIR = os.path.join(os.path.dirname(__file__), '../data')
os.makedirs(DATA_DIR, exist_ok=True)
OUT_CSV = os.path.join(DATA_DIR, 'minor_leagues_2025.csv')

def extract_json(sb, url):
    """Load an API URL and parse the JSON payload from the browser."""
    sb.open(url)
    try:
        # Give Cloudflare a moment if it challenges
        time.sleep(2)
        text = sb.execute_script('return document.body.innerText;')
        return json.loads(text)
    except Exception:
        print(f"    [!] Failed to parse JSON from {url}")
        return None

def get_2025_season_id(sb, tournament_id):
    """Find the specific season ID corresponding to the 2025 season."""
    url = f"https://api.sofascore.com/api/v1/unique-tournament/{tournament_id}/seasons"
    data = extract_json(sb, url)
    if not data or 'seasons' not in data:
        return None
        
    for s in data['seasons']:
        # Match '2025' or '24/25' or '2025/2026'
        year_label = str(s.get('year', ''))
        name_label = str(s.get('name', ''))
        if '2025' in year_label or '25' in year_label or '25' in name_label:
            return s['id']
            
    # Fallback to the latest season if 2025 explicitly isn't found
    return data['seasons'][0]['id']

def get_events_for_season(sb, tournament_id, season_id):
    """Get all match event IDs for the season."""
    url = f"https://api.sofascore.com/api/v1/unique-tournament/{tournament_id}/season/{season_id}/events/last/0"
    data = extract_json(sb, url)
    if not data or 'events' not in data:
        return []
    return [event['id'] for event in data['events'] if event.get('status', {}).get('type') == 'finished']

def get_player_statistics_for_event(sb, event_id):
    """Get player match logs for a single game."""
    # Fetch team names from the event details
    event_url = f"https://api.sofascore.com/api/v1/event/{event_id}"
    event_data = extract_json(sb, event_url)
    
    team_names = {'home': 'Home', 'away': 'Away'}
    if event_data and 'event' in event_data:
        team_names['home'] = event_data['event'].get('homeTeam', {}).get('name', 'Home')
        team_names['away'] = event_data['event'].get('awayTeam', {}).get('name', 'Away')

    url = f"https://api.sofascore.com/api/v1/event/{event_id}/lineups"
    data = extract_json(sb, url)
    
    rows = []
    if not data:
        return rows
        
    for team_key in ['home', 'away']:
        team_data = data.get(team_key, {})
        team_name = team_names[team_key]
        players = team_data.get('players', [])
        
        for p in players:
            p_info = p.get('player', {})
            stats = p.get('statistics', {})
            
            if not stats or stats.get('minutesPlayed', 0) == 0:
                continue
                
            rows.append({
                'player_name': p_info.get('name'),
                'player_id': p_info.get('id'),
                'team': team_name,
                'minutes': stats.get('minutesPlayed', 0),
                'goals': stats.get('goals', 0),
                'assists': stats.get('assists', 0),
                'shots': stats.get('totalShots', 0),
                'shots_on_target': stats.get('shotsOnTarget', 0),
                'passes': stats.get('totalPasses', 0),
                'passes_acc': stats.get('accuratePasses', 0),
                'rating': stats.get('rating', 0.0),
                'event_id': event_id
            })
    return rows

def main():
    print("=============================================")
    print(" DEEPFIELDPRO 2025 MINOR LEAGUES SCRAPER")
    print("=============================================")
    
    all_rows = []
    
    # uc=True uses Undetected ChromeDriver to bypass Cloudflare
    with SB(uc=True, headless=True) as sb:
        print("[+] Initializing Undetected Browser...")
        
        for tourney_id, league_name in TARGET_LEAGUES.items():
            print(f"\n[*] Processing {league_name} (ID: {tourney_id})")
            
            # 1. Get 2025 Season ID
            season_id = get_2025_season_id(sb, tourney_id)
            if not season_id:
                print("    [-] Could not find season ID. Skipping.")
                continue
            print(f"    [+] Found 2025 Season ID: {season_id}")
            
            # 2. Get Matches
            event_ids = get_events_for_season(sb, tourney_id, season_id)
            print(f"    [+] Found {len(event_ids)} finished matches.")
            
            # 3. Scrape Matches
            for i, eid in enumerate(event_ids):
                print(f"        -> Fetching stats for match {eid} ({i+1}/{len(event_ids)})...")
                match_stats = get_player_statistics_for_event(sb, eid)
                for row in match_stats:
                    row['league'] = league_name
                    row['season'] = '2025'
                all_rows.extend(match_stats)
                time.sleep(2) # Politeness delay
                
    if all_rows:
        df = pd.DataFrame(all_rows)
        # Save or append
        header = not os.path.exists(OUT_CSV)
        df.to_csv(OUT_CSV, mode='a', header=header, index=False)
        print(f"\n[OK] Successfully saved {len(df)} 2025 player stat rows to {OUT_CSV}")
    else:
        print("\n[-] No data was scraped.")

if __name__ == "__main__":
    main()
