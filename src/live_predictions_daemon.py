import pandas as pd
import numpy as np
import joblib
import requests
import datetime
import time
import os

import sys
sys.path.insert(0, os.path.dirname(__file__))
from free_scraper_module import get_todays_fixtures_free as get_todays_fixtures
from free_scraper_module import get_fixture_lineups_free as get_fixture_lineups

def load_player_database():
    try:
        df1 = pd.read_csv('data/minor_leagues_2025.csv')
        df2 = pd.read_csv('data/world_cup_players_match_logs.csv')
        df2 = df2.rename(columns={'player_': 'player_name', 'team_': 'team'})
        df = pd.concat([df1, df2], ignore_index=True)
        return df
    except Exception:
        return pd.read_csv('data/minor_leagues_2025.csv')

def get_player_rolling_stats(player_name, df):
    p_data = df[df['player_name'].astype(str).str.contains(player_name, case=False, na=False)]
    if len(p_data) > 0:
        latest = p_data.iloc[-1]
        return {
            'goals_roll': latest.get('goals', 0),
            'assists_roll': latest.get('assists', 0),
            'shots_roll': latest.get('shots', 0),
            'passes_roll': latest.get('passes', 0),
            'rating_roll': latest.get('rating', 6.5)
        }
    else:
        return {
            'goals_roll': 0.1,
            'assists_roll': 0.05,
            'shots_roll': 0.5,
            'passes_roll': 15.0,
            'rating_roll': 6.0
        }

def predict_match(fixture, lineups, player_model, match_model, df):
    home_team = fixture['teams']['home']['name']
    away_team = fixture['teams']['away']['name']
    league_name = fixture['league']['name']
    
    home_players = [p['player']['name'] for p in lineups[0].get('startXI', [])]
    away_players = [p['player']['name'] for p in lineups[1].get('startXI', [])]
        
    home_impact = 0
    away_impact = 0
    
    home_player_stats = []
    for p in home_players:
        stats = get_player_rolling_stats(p, df)
        features = pd.DataFrame([stats])
        impact = player_model.predict(features)[0]
        home_impact += impact
        home_player_stats.append({'name': p, 'impact': round(impact, 2)})
        
    away_player_stats = []
    for p in away_players:
        stats = get_player_rolling_stats(p, df)
        features = pd.DataFrame([stats])
        impact = player_model.predict(features)[0]
        away_impact += impact
        away_player_stats.append({'name': p, 'impact': round(impact, 2)})
        
    league_elo_map = {
        'ENG-Premier League': 1800, 'ENG-Championship': 1550, 'BRA-Serie A': 1600,
        'ARG-Primera': 1550, 'MLS': 1500, 'Saudi Pro League': 1450, 'World Cup': 1900
    }
    
    base_elo = league_elo_map.get(league_name, 1500)
    home_elo = base_elo + (home_impact * 2)
    away_elo = base_elo + (away_impact * 2)
    
    match_features = pd.DataFrame([{
        'team_A_expected_impact': home_impact,
        'team_B_expected_impact': away_impact,
        'impact_diff': home_impact - away_impact,
        'total_expected_impact': home_impact + away_impact,
        'elo_diff': home_elo - away_elo,
        'team_A_elo': home_elo,
        'team_B_elo': away_elo
    }])
    
    outcome_pred = match_model.predict(match_features)[0]
    if outcome_pred == 1:
        winner = f"{home_team} WIN"
        home_g = np.random.poisson(2.1)
        away_g = np.random.poisson(0.8)
    elif outcome_pred == 0:
        winner = f"{away_team} WIN"
        home_g = np.random.poisson(0.8)
        away_g = np.random.poisson(2.1)
    else:
        winner = "DRAW"
        home_g = np.random.poisson(1.2)
        away_g = np.random.poisson(1.2)
        if home_g != away_g: home_g = away_g = max(home_g, away_g)

    intensity_factor = (home_impact + away_impact) / 10.0
    home_corners = int(np.random.poisson(4.5 + (home_impact*0.2)))
    away_corners = int(np.random.poisson(4.5 + (away_impact*0.2)))
    home_fouls = int(np.random.poisson(11.0 + intensity_factor))
    away_fouls = int(np.random.poisson(11.0 + intensity_factor))
    home_yellows = int(np.random.poisson(home_fouls * 0.15))
    away_yellows = int(np.random.poisson(away_fouls * 0.15))

    return {
        'fixture_id': fixture['fixture']['id'],
        'match': f"{home_team} vs {away_team}",
        'league': league_name,
        'prediction': winner,
        'expected_score': f"{home_g} - {away_g}",
        'team_impacts': f"Home: {home_impact:.2f} | Away: {away_impact:.2f}",
        'corners': f"Home: {home_corners} | Away: {away_corners}",
        'fouls': f"Home: {home_fouls} | Away: {away_fouls}",
        'cards': f"Home Yellows: {home_yellows} | Away Yellows: {away_yellows}",
        'home_players': home_player_stats[:3],
        'away_players': away_player_stats[:3]
    }

def update_markdown_artifact(results, timestamp):
    out_text = f"===========================================\n"
    out_text += f" LIVE BOTTOM-UP MATCH PREDICTIONS\n"
    out_text += f" Last Updated: {timestamp}\n"
    out_text += f" *Only matches with official starting lineups shown*\n"
    out_text += f"===========================================\n\n"
    
    if not results:
        out_text += "*No official lineups have been announced for any matches yet. Waiting for updates...*\n"
        
    for r in results:
        out_text += f"### [{r['league']}] {r['match']}\n"
        out_text += f"- **Predicted Outcome:** {r['prediction']}\n"
        out_text += f"- **Expected Score:** {r['expected_score']}\n"
        out_text += f"- **Team Strengths (Aggregated Impact):** {r['team_impacts']}\n"
        out_text += f"- **Match Stats:** Corners ({r['corners']}) | Fouls ({r['fouls']}) | Cards ({r['cards']})\n"
        out_text += "- **Top Impact Players (Home):** " + ", ".join([f"{p['name']} ({p['impact']})" for p in r['home_players']]) + "\n"
        out_text += "- **Top Impact Players (Away):** " + ", ".join([f"{p['name']} ({p['impact']})" for p in r['away_players']]) + "\n\n"
        out_text += "---\n\n"
        
    # Write to artifact dir directly if possible, or data dir
    artifact_path = r'C:\Users\Elie\.gemini\antigravity-cli\brain\92df1273-9456-4c34-be82-7b0f28f9a507\todays_live_predictions.md'
    try:
        with open(artifact_path, 'w', encoding='utf-8') as f:
            f.write(out_text)
    except Exception:
        with open('data/todays_live_predictions.md', 'w', encoding='utf-8') as f:
            f.write(out_text)

import json
def update_dashboard_json(fixtures, results_cache):
    dashboard_data = []
    # Map results by fixture id
    res_map = {r['fixture_id']: r for r in results_cache if 'fixture_id' in r}
    
    for f in fixtures:
        fid = f['fixture']['id']
        match_time = f['fixture']['date']
        home = f['teams']['home']['name']
        away = f['teams']['away']['name']
        league = f['league']['name']
        status = f['fixture']['status']['short']
        
        item = {
            'fixture_id': fid,
            'match': f"{home} vs {away}",
            'league': league,
            'kickoff': match_time,
            'status_code': status,
            'has_lineup': fid in res_map,
            'prediction': res_map.get(fid, None)
        }
        dashboard_data.append(item)
        
    with open('data/todays_dashboard_state.json', 'w', encoding='utf-8') as f:
        json.dump(dashboard_data, f, indent=4)

def run_daemon():
    print("[*] Starting Smart Live Predictions Daemon...")
    player_model = joblib.load('models/player_impact_model.pkl')
    match_model = joblib.load('models/bottom_up_match_model.pkl')
    df = load_player_database()
    
    processed_fixtures = set()
    results_cache = []
    
    while True:
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Scanning fixtures for upcoming kickoffs (T-45m window)...")
        fixtures = get_todays_fixtures()
        new_lineup_found = False
        
        for f in fixtures:
            fid = f['fixture']['id']
            if fid in processed_fixtures:
                continue # Already predicted this match
                
            status = f['fixture']['status']['short']
            if status in ['FT', 'AET', 'PEN', 'PST', 'CANC', 'ABD', '1H', '2H', 'HT']:
                continue # Match is already running, over, or cancelled
                
            # Check Match Time
            match_time_str = f['fixture']['date']
            try:
                # Parse ISO format string from API (e.g., '2026-06-05T15:00:00+00:00')
                kickoff_time = datetime.datetime.fromisoformat(match_time_str.replace('Z', '+00:00'))
                time_to_kickoff = (kickoff_time - now_utc).total_seconds() / 60.0
            except Exception:
                time_to_kickoff = 999
                
            # SMART LOGIC: Only query lineups if we are between 0 and 45 minutes before kickoff
            if 0 < time_to_kickoff <= 45:
                print(f"[~] {f['teams']['home']['name']} vs {f['teams']['away']['name']} kicks off in {int(time_to_kickoff)} mins. Checking for lineups...")
                lineups = get_fixture_lineups(fid)
                
                if len(lineups) == 2 and len(lineups[0].get('startXI', [])) == 11:
                    print(f"[!] Official lineup confirmed for: {f['teams']['home']['name']} vs {f['teams']['away']['name']}!")
                    res = predict_match(f, lineups, player_model, match_model, df)
                    results_cache.append(res)
                    processed_fixtures.add(fid)
                    new_lineup_found = True
                else:
                    print(f"    -> Lineups not officially posted yet. Will retry soon.")
            
        if new_lineup_found or len(results_cache) == 0:
            timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            update_markdown_artifact(results_cache, timestamp)
            update_dashboard_json(fixtures, results_cache)
            if new_lineup_found:
                print(f"[+] Artifact updated with latest confirmed lineups.")
            
        # Wait 5 minutes before the next sweep
        time.sleep(300)

if __name__ == "__main__":
    run_daemon()
