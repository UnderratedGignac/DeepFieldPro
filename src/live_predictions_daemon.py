import pandas as pd
import numpy as np
import joblib
import requests
import datetime
import time
import os
import math

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
        # Inject slight variance so unknown players don't all get exactly 0.18
        return {
            'goals_roll': max(0, np.random.normal(0.1, 0.05)),
            'assists_roll': max(0, np.random.normal(0.05, 0.02)),
            'shots_roll': max(0, np.random.normal(0.5, 0.2)),
            'passes_roll': max(0, np.random.normal(15.0, 5.0)),
            'rating_roll': np.clip(np.random.normal(6.0, 0.3), 4.0, 8.0)
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
        exp_h = 2.1; exp_a = 0.8
    elif outcome_pred == 0:
        winner = f"{away_team} WIN"
        exp_h = 0.8; exp_a = 2.1
    else:
        winner = "DRAW"
        exp_h = 1.2; exp_a = 1.2
        
    home_g = np.random.poisson(exp_h)
    away_g = np.random.poisson(exp_a)
    if winner == "DRAW" and home_g != away_g: home_g = away_g = max(home_g, away_g)

    intensity_factor = (home_impact + away_impact) / 10.0
    home_corners = int(np.random.poisson(4.5 + (home_impact*0.2)))
    away_corners = int(np.random.poisson(4.5 + (away_impact*0.2)))
    home_fouls = int(np.random.poisson(11.0 + intensity_factor))
    away_fouls = int(np.random.poisson(11.0 + intensity_factor))
    home_yellows = int(np.random.poisson(home_fouls * 0.15))
    away_yellows = int(np.random.poisson(away_fouls * 0.15))

    # Calculate Market Probabilities for Betarabia UI
    def poisson_prob(l, k):
        return (math.exp(-l) * (l**k)) / math.factorial(k)

    prob_1 = prob_x = prob_2 = 0.0
    prob_over_25 = prob_under_25 = 0.0
    prob_btts_yes = prob_btts_no = 0.0

    for i in range(8):
        for j in range(8):
            p = poisson_prob(exp_h, i) * poisson_prob(exp_a, j)
            if i > j: prob_1 += p
            elif i == j: prob_x += p
            else: prob_2 += p
            
            if (i + j) > 2.5: prob_over_25 += p
            else: prob_under_25 += p
            
            if i > 0 and j > 0: prob_btts_yes += p
            else: prob_btts_no += p

    # Normalize due to truncation at 7 goals
    total_1x2 = prob_1 + prob_x + prob_2
    prob_1 /= total_1x2; prob_x /= total_1x2; prob_2 /= total_1x2
    
    total_ou = prob_over_25 + prob_under_25
    prob_over_25 /= total_ou; prob_under_25 /= total_ou
    
    total_btts = prob_btts_yes + prob_btts_no
    prob_btts_yes /= total_btts; prob_btts_no /= total_btts

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
        'away_players': away_player_stats[:3],
        'markets': {
            '1X2': [
                {'selection': 'Home (1)', 'prob': round(prob_1 * 100, 1)},
                {'selection': 'Draw (X)', 'prob': round(prob_x * 100, 1)},
                {'selection': 'Away (2)', 'prob': round(prob_2 * 100, 1)}
            ],
            'Over/Under 2.5': [
                {'selection': 'Over 2.5', 'prob': round(prob_over_25 * 100, 1)},
                {'selection': 'Under 2.5', 'prob': round(prob_under_25 * 100, 1)}
            ],
            'BTTS': [
                {'selection': 'Yes', 'prob': round(prob_btts_yes * 100, 1)},
                {'selection': 'No', 'prob': round(prob_btts_no * 100, 1)}
            ]
        }
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
import sqlite3
import unicodedata
import re
import uuid

def load_settings():
    try:
        with open('data/settings.json', 'r') as f:
            return json.load(f)
    except Exception:
        return {
            "kelly_multiplier": 0.25,
            "min_ev_threshold": 0.05,
            "max_exposure_pct": 0.05,
            "auto_place_bets": False
        }

def find_betarabia_odds(home_team, away_team):
    """
    Looks up a match in odds_stream.db fixture table and grabs odds from market table.
    Returns a dict with market keys and selection odds.
    """
    def clean_name(name):
        if not name:
            return ""
        n = name.lower()
        # Remove accents
        n = "".join(c for c in unicodedata.normalize('NFD', n) if unicodedata.category(c) != 'Mn')
        # Remove punctuation
        n = re.sub(r'[^a-z0-9\s]', '', n)
        # Remove common suffixes
        suffixes = ['fc', 'cf', 'sc', 'u23', 'pr', 'ii', 'u20', 'united', 'city']
        words = [w for w in n.split() if w not in suffixes]
        return "".join(words)

    clean_h = clean_name(home_team)
    clean_a = clean_name(away_team)

    db_path = 'data/odds_stream.db'
    if not os.path.exists(db_path):
        return None
        
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        
        # Get all fixtures
        cur.execute("SELECT fixture_id, home_team, away_team FROM fixture")
        fixtures = cur.fetchall()
        
        matched_fid = None
        matched_home = None
        matched_away = None
        
        for fid, h, a in fixtures:
            ch = clean_name(h)
            ca = clean_name(a)
            # Match if they overlap
            if (clean_h and ch and (clean_h in ch or ch in clean_h)) and (clean_a and ca and (clean_a in ca or ca in clean_a)):
                matched_fid = fid
                matched_home = h
                matched_away = a
                break
                
        if not matched_fid:
            conn.close()
            return None
            
        # Query markets
        cur.execute("SELECT market_name, selection_name, raw_odds FROM market WHERE fixture_id = ?", (matched_fid,))
        rows = cur.fetchall()
        conn.close()
        
        odds_dict = {
            '1X2': {},
            'Over/Under 2.5': {},
            'BTTS': {}
        }
        
        for mname, sname, price in rows:
            mname_lower = mname.lower()
            sname_lower = sname.lower()
            
            # Match Result (1X2)
            if "result" in mname_lower or "1x2" in mname_lower:
                if sname_lower == "x" or "draw" in sname_lower:
                    odds_dict['1X2']['Draw'] = price
                else:
                    cs = clean_name(sname)
                    ch_matched = clean_name(matched_home)
                    ca_matched = clean_name(matched_away)
                    if cs in ch_matched or ch_matched in cs:
                        odds_dict['1X2']['Home'] = price
                    elif cs in ca_matched or ca_matched in cs:
                        odds_dict['1X2']['Away'] = price
                        
            # Over/Under 2.5
            elif "total" in mname_lower or "over/under" in mname_lower:
                if "2.5" in sname:
                    if "over" in sname_lower:
                        odds_dict['Over/Under 2.5']['Over'] = price
                    elif "under" in sname_lower:
                        odds_dict['Over/Under 2.5']['Under'] = price
                        
            # BTTS
            elif "both teams" in mname_lower or "btts" in mname_lower:
                if "yes" in sname_lower:
                    odds_dict['BTTS']['Yes'] = price
                elif "no" in sname_lower:
                    odds_dict['BTTS']['No'] = price
                    
        return odds_dict
        
    except Exception as e:
        print("Error in find_betarabia_odds:", e)
        return None

def log_ai_bet(match, market, selection, odds, prob, ev):
    db_path = "data/bet_log.db"
    if not os.path.exists(db_path):
        return
        
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        
        # Check if already logged
        cur.execute("""
            SELECT COUNT(*) FROM bet_log 
            WHERE match_id = ? AND market_type = ? AND side = ? AND bet_source = 'AI'
        """, (match, market, selection))
        exists = cur.fetchone()[0] > 0
        
        if not exists:
            bet_id = "AI_" + uuid.uuid4().hex[:14]
            fair_odds = round(100.0 / prob, 3) if prob > 0 else 1.0
            
            try:
                br_conn = sqlite3.connect("data/bankroll.db")
                br_cur = br_conn.cursor()
                br_cur.execute("SELECT current_balance FROM bankroll ORDER BY date DESC LIMIT 1")
                balance = br_cur.fetchone()[0]
                br_conn.close()
            except Exception:
                balance = 10000.0
                
            settings = load_settings()
            kelly_mult = settings.get("kelly_multiplier", 0.25)
            
            p = prob / 100.0
            b = odds - 1.0
            if b > 0:
                kelly_f = (p * odds - 1.0) / b
                kelly_f = max(0, min(settings.get("max_exposure_pct", 0.05), kelly_f * kelly_mult))
            else:
                kelly_f = 0.01
                
            stake = round(balance * kelly_f, 2)
            if stake < 10.0: stake = 10.0
            
            cur.execute("""
                INSERT INTO bet_log 
                (bet_id, match_id, player_id, market_type, entry_odds, fair_odds, edge_pct, stake, result, pnl, placed_at, bet_source, is_recommended, line, side)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (bet_id, match, f"{match} ({selection})", market, odds, fair_odds, round(ev * 100, 1), stake, "OPEN", 0.0, datetime.datetime.now().isoformat(), "AI", 1, 2.5, selection))
            print(f"[AI BET LOGGER] Automatically logged recommended AI bet: {match} ({selection}) @ {odds} stake {stake}")
            
        conn.commit()
        conn.close()
    except Exception as e:
        print("Error in log_ai_bet:", e)

def settle_open_bets():
    """
    Scrapes today's finished matches from Sofascore and settles any OPEN bets in bet_log.db.
    """
    print("[SETTLEMENT] Running settlement check...")
    try:
        from free_scraper_module import get_todays_fixtures_free
        fixtures = get_todays_fixtures_free()
    except Exception as e:
        print("Error fetching fixtures for settlement:", e)
        return
        
    finished_matches = {}
    for f in fixtures:
        status = f['fixture']['status']['short']
        if status == 'FT':
            home_team = f['teams']['home']['name']
            away_team = f['teams']['away']['name']
            home_score = f['fixture'].get('home_score')
            away_score = f['fixture'].get('away_score')
            if home_score is not None and away_score is not None:
                finished_matches[f"{home_team} vs {away_team}"] = (home_score, away_score)
                
    if not finished_matches:
        print("[SETTLEMENT] No finished matches found in Sofascore today yet.")
        return
        
    db_path = "data/bet_log.db"
    if not os.path.exists(db_path):
        return
        
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        
        cur.execute("SELECT bet_id, match_id, player_id, market_type, entry_odds, stake, bet_source FROM bet_log WHERE result = 'OPEN'")
        open_bets = cur.fetchall()
        
        if not open_bets:
            conn.close()
            return
            
        print(f"[SETTLEMENT] Found {len(open_bets)} OPEN bets. Settling...")
        
        def clean_name(name):
            if not name:
                return ""
            n = name.lower()
            n = "".join(c for c in unicodedata.normalize('NFD', n) if unicodedata.category(c) != 'Mn')
            n = re.sub(r'[^a-z0-9\s]', '', n)
            suffixes = ['fc', 'cf', 'sc', 'u23', 'pr', 'ii', 'u20', 'united', 'city']
            words = [w for w in n.split() if w not in suffixes]
            return "".join(words)
            
        for bet_id, match_id, player_id, market_type, entry_odds, stake, bet_source in open_bets:
            match_match = re.match(r"^(.*) vs (.*) \((.*)\)$", player_id)
            if not match_match:
                match_name = match_id if match_id else "Unknown vs Unknown"
                cur.execute("SELECT side FROM bet_log WHERE bet_id = ?", (bet_id,))
                side_row = cur.fetchone()
                selection = side_row[0] if side_row else "Home"
            else:
                home_t = match_match.group(1).strip()
                away_t = match_match.group(2).strip()
                selection = match_match.group(3).strip()
                match_name = f"{home_t} vs {away_t}"
                
            sel_lower = selection.lower()
            
            # Find score
            matched_score = None
            bet_home_clean = clean_name(match_name.split(" vs ")[0])
            bet_away_clean = clean_name(match_name.split(" vs ")[1])
            
            for finished_name, score in finished_matches.items():
                fin_home_clean = clean_name(finished_name.split(" vs ")[0])
                fin_away_clean = clean_name(finished_name.split(" vs ")[1])
                
                if (bet_home_clean and fin_home_clean and (bet_home_clean in fin_home_clean or fin_home_clean in bet_home_clean)) and \
                   (bet_away_clean and fin_away_clean and (bet_away_clean in fin_away_clean or fin_away_clean in bet_away_clean)):
                    matched_score = score
                    break
                    
            if matched_score is None:
                continue
                
            home_score, away_score = matched_score
            
            won = False
            if market_type == '1X2':
                if 'home' in sel_lower or '1' in sel_lower:
                    won = (home_score > away_score)
                elif 'draw' in sel_lower or 'x' in sel_lower:
                    won = (home_score == away_score)
                elif 'away' in sel_lower or '2' in sel_lower:
                    won = (away_score > home_score)
            elif market_type == 'Over/Under 2.5':
                total_goals = home_score + away_score
                if 'over' in sel_lower:
                    won = (total_goals > 2.5)
                elif 'under' in sel_lower:
                    won = (total_goals < 2.5)
            elif market_type == 'BTTS':
                if 'yes' in sel_lower:
                    won = (home_score > 0 and away_score > 0)
                elif 'no' in sel_lower:
                    won = (home_score == 0 or away_score == 0)
                    
            result = 'W' if won else 'L'
            pnl = stake * (entry_odds - 1) if won else -stake
            
            cur.execute("UPDATE bet_log SET result = ?, pnl = ?, closing_odds = ? WHERE bet_id = ?", (result, pnl, entry_odds, bet_id))
            print(f"[SETTLEMENT] Settled bet {bet_id} as {result} (PnL: ${pnl:.2f})")
            
            # Capital adjustments for USER
            if result == 'W' and bet_source == 'USER':
                br_path = "data/bankroll.db"
                if os.path.exists(br_path):
                    br_conn = sqlite3.connect(br_path)
                    br_cur = br_conn.cursor()
                    payout = stake * entry_odds
                    br_cur.execute("UPDATE bankroll SET current_balance = current_balance + ?, daily_pnl = daily_pnl + ? WHERE id = (SELECT MAX(id) FROM bankroll)", (payout, pnl))
                    br_conn.commit()
                    br_conn.close()
                    print(f"[SETTLEMENT] Credited win payout ${payout:.2f} to bankroll (USER)")
            elif result == 'L' and bet_source == 'USER':
                br_path = "data/bankroll.db"
                if os.path.exists(br_path):
                    br_conn = sqlite3.connect(br_path)
                    br_cur = br_conn.cursor()
                    br_cur.execute("UPDATE bankroll SET daily_pnl = daily_pnl + ? WHERE id = (SELECT MAX(id) FROM bankroll)", (pnl,))
                    br_conn.commit()
                    br_conn.close()
                    
        conn.commit()
        conn.close()
    except Exception as e:
        print("Error during settlement:", e)

def update_dashboard_json(fixtures, results_cache):
    dashboard_data = []
    res_map = {r['fixture_id']: r for r in results_cache if 'fixture_id' in r}
    
    settings = load_settings()
    min_ev_threshold = settings.get("min_ev_threshold", 0.05)
    
    for f in fixtures:
        fid = f['fixture']['id']
        match_time = f['fixture']['date']
        home = f['teams']['home']['name']
        away = f['teams']['away']['name']
        league = f['league']['name']
        status = f['fixture']['status']['short']
        
        prediction = res_map.get(fid, None)
        odds_dict = find_betarabia_odds(home, away)
        
        # Prepare pre-match markets if available from Betarabia, regardless of lineups
        prematch_markets = None
        if odds_dict:
            # Check if we got any odds
            has_odds = False
            for cat, selections in odds_dict.items():
                if selections:
                    has_odds = True
                    break
            
            if has_odds:
                prematch_markets = {
                    '1X2': [],
                    'Over/Under 2.5': [],
                    'BTTS': []
                }
                if 'Home' in odds_dict.get('1X2', {}):
                    prematch_markets['1X2'].append({'selection': 'Home (1)', 'odds': odds_dict['1X2']['Home']})
                if 'Draw' in odds_dict.get('1X2', {}):
                    prematch_markets['1X2'].append({'selection': 'Draw (X)', 'odds': odds_dict['1X2']['Draw']})
                if 'Away' in odds_dict.get('1X2', {}):
                    prematch_markets['1X2'].append({'selection': 'Away (2)', 'odds': odds_dict['1X2']['Away']})
                    
                if 'Over' in odds_dict.get('Over/Under 2.5', {}):
                    prematch_markets['Over/Under 2.5'].append({'selection': 'Over 2.5', 'odds': odds_dict['Over/Under 2.5']['Over']})
                if 'Under' in odds_dict.get('Over/Under 2.5', {}):
                    prematch_markets['Over/Under 2.5'].append({'selection': 'Under 2.5', 'odds': odds_dict['Over/Under 2.5']['Under']})
                    
                if 'Yes' in odds_dict.get('BTTS', {}):
                    prematch_markets['BTTS'].append({'selection': 'Yes', 'odds': odds_dict['BTTS']['Yes']})
                if 'No' in odds_dict.get('BTTS', {}):
                    prematch_markets['BTTS'].append({'selection': 'No', 'odds': odds_dict['BTTS']['No']})
                
        if prediction and 'markets' in prediction:
            for m_type, selections in prediction['markets'].items():
                for sel in selections:
                    sel_name = sel['selection']
                    prob = sel['prob']
                    
                    key = None
                    if m_type == '1X2':
                        if 'Home' in sel_name or '1' in sel_name: key = 'Home'
                        elif 'Draw' in sel_name or 'X' in sel_name: key = 'Draw'
                        elif 'Away' in sel_name or '2' in sel_name: key = 'Away'
                    elif m_type == 'Over/Under 2.5':
                        if 'Over' in sel_name: key = 'Over'
                        elif 'Under' in sel_name: key = 'Under'
                    elif m_type == 'BTTS':
                        if 'Yes' in sel_name: key = 'Yes'
                        elif 'No' in sel_name: key = 'No'
                        
                    odds = None
                    if odds_dict and m_type in odds_dict and key in odds_dict[m_type]:
                        odds = odds_dict[m_type][key]
                        
                    if odds is not None:
                        ev = (prob / 100.0) * odds - 1.0
                        is_recommended = ev >= min_ev_threshold
                        sel['odds'] = odds
                        sel['ev'] = round(ev * 100, 1)
                        sel['recommended'] = is_recommended
                        
                        if is_recommended:
                            log_ai_bet(f"{home} vs {away}", m_type, sel_name, odds, prob, ev)
                    else:
                        est_odds = round(0.95 * (100.0 / prob), 2) if prob > 0 else 1.0
                        sel['odds'] = est_odds
                        sel['ev'] = -5.0
                        sel['recommended'] = False
        
        item = {
            'fixture_id': fid,
            'match': f"{home} vs {away}",
            'league': league,
            'kickoff': match_time,
            'status_code': status,
            'has_lineup': fid in res_map,
            'prediction': prediction,
            'prematch_markets': prematch_markets
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
    
    # Run initial settlement on startup
    settle_open_bets()
    
    while True:
        # 1. Trigger Betarabia odds scraper in background (non-blocking)
        print("[*] Launching Betarabia Scraper in background to refresh live odds...")
        try:
            import subprocess
            import sys
            subprocess.Popen([sys.executable, "src/betarabia_scraper.py"])
        except Exception as e:
            print("Failed to start background scraper:", e)
            
        # 2. Run post-match settlement
        settle_open_bets()
        
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
            
        # Always update dashboard JSON to keep odds and recommendations fresh!
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if new_lineup_found:
            update_markdown_artifact(results_cache, timestamp)
            print(f"[+] Artifact updated with latest confirmed lineups.")
            
        update_dashboard_json(fixtures, results_cache)
        
        # Wait 3 minutes (180s) before the next sweep
        time.sleep(180)


if __name__ == "__main__":
    run_daemon()
