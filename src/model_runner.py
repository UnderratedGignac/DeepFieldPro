import os
import sys
import sqlite3
import time
import math
import pandas as pd
import lightgbm as lgb
from datetime import datetime, timezone
from dotenv import load_dotenv

from pricing_engine  import calculate_over_prob
from execution_engine import place_bet

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

BASE_DIR    = os.path.join(os.path.dirname(__file__), '..')
MODEL_DIR   = os.path.join(BASE_DIR, 'models')
DATA_DIR    = os.path.join(BASE_DIR, 'data')
DB_ODDS     = os.path.join(DATA_DIR, 'odds_stream.db')
DB_OPP      = os.path.join(DATA_DIR, 'opponent_profiles.db')
DB_LINEUPS  = os.path.join(DATA_DIR, 'parsed_lineups.db')
PLAYER_CSV  = 'C:/Users/Elie/data/csv/FULL_PLAYER_DATABASE_2026.csv'

def load_models():
    """Load pre-trained LightGBM models into memory."""
    try:
        models = {
            'start_clf': lgb.Booster(model_file=os.path.join(MODEL_DIR, 'minutes_start_classifier.txt')),
            'min_p10': lgb.Booster(model_file=os.path.join(MODEL_DIR, 'minutes_p10_regressor.txt')),
            'min_p50': lgb.Booster(model_file=os.path.join(MODEL_DIR, 'minutes_p50_regressor.txt')),
            'min_p90': lgb.Booster(model_file=os.path.join(MODEL_DIR, 'minutes_p90_regressor.txt')),
            'sot_club': lgb.Booster(model_file=os.path.join(MODEL_DIR, 'lgbm_sot_club_v1.pkl')),
            'sot_intl': lgb.Booster(model_file=os.path.join(MODEL_DIR, 'lgbm_sot_international_v2.pkl')),
            # Fallback mock for the quantiles we don't have separate models for yet
            'sot_p10': lgb.Booster(model_file=os.path.join(MODEL_DIR, 'sot_p10.txt')),
            'sot_p50': lgb.Booster(model_file=os.path.join(MODEL_DIR, 'sot_p50.txt')),
            'sot_p90': lgb.Booster(model_file=os.path.join(MODEL_DIR, 'sot_p90.txt')),
            'pass_p10': lgb.Booster(model_file=os.path.join(MODEL_DIR, 'passes_p10.txt')),
            'pass_p50': lgb.Booster(model_file=os.path.join(MODEL_DIR, 'passes_p50.txt')),
            'pass_p90': lgb.Booster(model_file=os.path.join(MODEL_DIR, 'passes_p90.txt')),
            'shots_p10': lgb.Booster(model_file=os.path.join(MODEL_DIR, 'shots_p10.txt')),
            'shots_p50': lgb.Booster(model_file=os.path.join(MODEL_DIR, 'shots_p50.txt')),
            'shots_p90': lgb.Booster(model_file=os.path.join(MODEL_DIR, 'shots_p90.txt')),
            'goals_mean': lgb.Booster(model_file=os.path.join(MODEL_DIR, 'goals_mean.txt')),
            'cards_mean': lgb.Booster(model_file=os.path.join(MODEL_DIR, 'cards_mean.txt')),
            'offsides_mean': lgb.Booster(model_file=os.path.join(MODEL_DIR, 'offsides_mean.txt'))
        }
    except Exception as e:
        print(f"Error loading models: {e}")
        print("Please run python src/train_models.py first.")
        sys.exit(1)
        
    print(f"[OK] All {len(models)} models loaded.")
    return models

def get_player_historical_stats(player_name, FallbackPosition_P=None, FallbackLeague_P=None):
    df = pd.read_csv(PLAYER_CSV)
    from unidecode import unidecode
    df['name_clean'] = df['Player Name'].apply(lambda x: unidecode(str(x)).lower().strip())
    name_clean = unidecode(str(player_name)).lower().strip()
    matches = df[df['name_clean'] == name_clean]
    if matches.empty:
        matches = df[df['name_clean'].str.contains(name_clean[:10], na=False)]
    if matches.empty:
        # Log missing player
        log_path = os.path.join(DATA_DIR, 'missing_players.log')
        with open(log_path, 'a') as f:
            f.write(f"{datetime.now(timezone.utc).isoformat()} - MISSING: {player_name}\n")
            
        if FallbackPosition_P and FallbackLeague_P:
            league_pos = df[(df['league'] == FallbackLeague_P) & (df['Position'].str.contains(FallbackPosition_P, na=False))]
            if not league_pos.empty:
                mean_row = league_pos.mean(numeric_only=True).to_dict()
                mean_row['Player Name'] = f"{FallbackPosition_P} Average ({FallbackLeague_P})"
                mean_row['Position'] = FallbackPosition_P
                mean_row['is_fallback'] = True
                return pd.Series(mean_row)
        return None
        
    row = matches.sort_values('season', ascending=False).iloc[0].copy()
    row['is_fallback'] = False
    return row

def get_opponent_profile(opponent_team_name):
    if not os.path.exists(DB_OPP):
        return {'ppda': 12.0, 'opp_possession_allowed': 50.0}  
    conn = sqlite3.connect(DB_OPP)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT ppda, opp_possession_allowed FROM opponent_profiles "
        "WHERE team_name LIKE ? ORDER BY match_week DESC LIMIT 1",
        (f'%{opponent_team_name}%',)
    )
    row = cursor.fetchone()
    conn.close()
    if row:
        return {'ppda': row[0], 'opp_possession_allowed': row[1]}
    return {'ppda': 12.0, 'opp_possession_allowed': 50.0}

def get_current_odds(match_id, player_name, market_type, line):
    if not os.path.exists(DB_ODDS):
        return None, None
    conn = sqlite3.connect(DB_ODDS)
    cursor = conn.cursor()
    # Check selection name containing player name and appropriate line/type
    if line is not None:
        line_str = f'%{line}%'
    else:
        line_str = '%%'
    cursor.execute("""
        SELECT price FROM odds_feed
        WHERE match_id = ?
          AND market_type = ?
          AND (selection_name LIKE ? AND selection_name LIKE ?)
        ORDER BY timestamp DESC LIMIT 2
    """, (match_id, market_type, line_str, f'%{player_name}%'))
    rows = cursor.fetchall()
    conn.close()
    if len(rows) >= 2:
        return rows[0][0], rows[1][0]  
    elif len(rows) == 1:
        return rows[0][0], None
    return None, None

def safe_float(val, default):
    try:
        if isinstance(val, str) and '-' in val:
            return float(val.split('-')[0])
        return float(val)
    except:
        return float(default)

def build_feature_vector(stats, opp_profile):
    position_map = {'MF': 3, 'DF': 2, 'FW': 1, 'GK': 0, 'MF,FW': 2, 'DF,MF': 2}
    pos_encoded = position_map.get(str(stats.get('Position', 'MF')), 2)

    return {
        'Age':                         safe_float(stats.get('Age', 25), 25),
        'Position_encoded':            pos_encoded,
        'Minutes Played':              safe_float(stats.get('Minutes Played', 900), 900),
        'Starts':                      safe_float(stats.get('Starts', 10), 10),
        'Percentage of Minutes Played': safe_float(stats.get('Min%', 0.7), 0.7),
        'Mn/Start':                    safe_float(stats.get('Mn/Start', 75), 75),
        'Mn/MP':                       safe_float(stats.get('Mn/MP', 70), 70),
        'PPM':                         safe_float(stats.get('PPM', 1.5), 1.5),
        'Crs':                         safe_float(stats.get('Crs', 1.0), 1.0),
        'Interceptions':               safe_float(stats.get('Interceptions', 1.0), 1.0),
        'Tackles Won':                 safe_float(stats.get('Tackles Won', 1.0), 1.0),
        'ppda':                        safe_float(opp_profile['ppda'], 12.0),
        'opp_possession_allowed':      safe_float(opp_profile['opp_possession_allowed'], 50.0),
        'sample_weight':               1.0   
    }

def poisson_prob_ge(lam, k):
    """Probability of Poisson variable being >= k."""
    if lam <= 0:
        return 0.0
    prob_lt_k = 0.0
    for i in range(k):
        prob_lt_k += (lam ** i) * math.exp(-lam) / math.factorial(i)
    return max(0.0, min(1.0, 1.0 - prob_lt_k))

def run_for_match(fixture_id, opponent_team, lineup_drop_at, latency_ms,
                  role_shifts, regime='lineup_adjustment_window'):
    print(f"\n=== MODEL RUNNER STARTING | Fixture: {fixture_id} ===")
    start_time = time.time()

    models = load_models()
    opp_profile = get_opponent_profile(opponent_team)
    print(f"Opponent: {opponent_team} | PPDA: {opp_profile['ppda']} | "
          f"Possession Allowed: {opp_profile['opp_possession_allowed']}%")

    conn = sqlite3.connect(DB_LINEUPS)
    starters_df = pd.read_sql_query(
        "SELECT player_id, player_name, expected_role FROM parsed_lineups "
        "WHERE match_id = ? AND is_starter = 1",
        conn, params=(str(fixture_id),)
    )
    conn.close()

    if starters_df.empty:
        print("ERROR: No starters found in DB. Did lineup_parser run?")
        return []

    {s['player_id']: s for s in role_shifts}
    bets_placed = []

    # 1. First Pass: Predict features and calculate sum of goals/cards for relative pricing
    player_data = []
    sum_goal_prob = 0.0
    sum_card_prob = 0.0

    for _, player_row in starters_df.iterrows():
        player_name = player_row['player_name']
        player_id   = player_row['player_id']
        role        = player_row['expected_role']

        if role == 'goalkeeper':
            continue

        stats = get_player_historical_stats(player_name)
        if stats is None:
            continue

        features = build_feature_vector(stats, opp_profile)
        MINUTES_FEATURES = ['Age', 'Starts', 'Percentage of Minutes Played', 'Mn/Start', 'Mn/MP', 'PPM', 'ppda', 'opp_possession_allowed', 'sample_weight']
        PASSES_FEATURES = ['Age', 'Position_encoded', 'Minutes Played', 'Mn/Start', 'Percentage of Minutes Played', 'Crs', 'Interceptions', 'Tackles Won', 'ppda', 'opp_possession_allowed', 'sample_weight']

        X_minutes = pd.DataFrame([features], columns=MINUTES_FEATURES)
        X_passes = pd.DataFrame([features], columns=PASSES_FEATURES)

        start_prob  = float(models['start_clf'].predict(X_minutes)[0])
        if start_prob < 0.50:
            continue

        min_p10     = float(models['min_p10'].predict(X_minutes)[0])
        min_p50     = float(models['min_p50'].predict(X_minutes)[0])
        min_p90     = float(models['min_p90'].predict(X_minutes)[0])

        shots_p10   = float(models['shots_p10'].predict(X_passes)[0])
        shots_p50   = float(models['shots_p50'].predict(X_passes)[0])
        shots_p90   = float(models['shots_p90'].predict(X_passes)[0])

        sot_p10     = float(models['sot_p10'].predict(X_passes)[0])
        sot_p50     = float(models['sot_p50'].predict(X_passes)[0])
        sot_p90     = float(models['sot_p90'].predict(X_passes)[0])

        goals_rate  = float(models['goals_mean'].predict(X_passes)[0])
        cards_rate  = float(models['cards_mean'].predict(X_passes)[0])
        off_rate    = float(models['offsides_mean'].predict(X_passes)[0])

        # Poisson Lambdas scaled to expected minutes
        lam_goals = max(0.001, goals_rate * min_p50 / 90.0)
        lam_cards = max(0.001, cards_rate * min_p50 / 90.0)
        lam_offsides = max(0.001, off_rate * min_p50 / 90.0)

        anytime_goal = 1.0 - math.exp(-lam_goals)
        card_prob = 1.0 - math.exp(-lam_cards)

        sum_goal_prob += anytime_goal
        sum_card_prob += card_prob

        player_data.append({
            'player_name': player_name,
            'player_id': player_id,
            'role': role,
            'min_p10': min_p10, 'min_p50': min_p50, 'min_p90': min_p90,
            'shots_p10': shots_p10, 'shots_p50': shots_p50, 'shots_p90': shots_p90,
            'sot_p10': sot_p10, 'sot_p50': sot_p50, 'sot_p90': sot_p90,
            'lam_goals': lam_goals, 'lam_cards': lam_cards, 'lam_offsides': lam_offsides,
            'anytime_goal': anytime_goal, 'card_prob': card_prob
        })

    # Avoid divide-by-zero
    sum_goal_prob = max(0.1, sum_goal_prob)
    sum_card_prob = max(0.1, sum_card_prob)

    # 2. Second Pass: Price all 14 Betarabia prop markets
    for p in player_data:
        p_name = p['player_name']
        print(f"\n  {p_name} | Role: {p['role']}")
        print(f"    Expected goals/match: {p['lam_goals']:.3f} | cards/match: {p['lam_cards']:.3f} | offsides/match: {p['lam_offsides']:.3f}")

        # Construct the 14 potential markets
        markets = []

        # 1. Player will score a goal (Anytime Goalscorer)
        markets.append({
            'market_type': 'goals_anytime',
            'line': None,
            'fair_prob': p['anytime_goal']
        })

        # 2. 1st Goalscorer (relative to match goals)
        markets.append({
            'market_type': 'goals_first',
            'line': None,
            'fair_prob': (p['anytime_goal'] / sum_goal_prob) * 0.90 # 90% chance match has at least 1 goal
        })

        # 3. Player will score twice or more (Brace)
        markets.append({
            'market_type': 'goals_brace',
            'line': None,
            'fair_prob': poisson_prob_ge(p['lam_goals'], 2)
        })

        # 4. Player will score hat trick or more
        markets.append({
            'market_type': 'goals_hattrick',
            'line': None,
            'fair_prob': poisson_prob_ge(p['lam_goals'], 3)
        })

        # 5. Player to score in both halves
        p_half = 1.0 - math.exp(-p['lam_goals'] / 2.0)
        markets.append({
            'market_type': 'goals_both_halves',
            'line': None,
            'fair_prob': p_half * p_half
        })

        # 6. Player to score in first 10 minutes
        lam_10 = p['lam_goals'] * (10.0 / p['min_p50'])
        markets.append({
            'market_type': 'goals_first_10',
            'line': None,
            'fair_prob': 1.0 - math.exp(-lam_10)
        })

        # 7. Player to Receive A Yellow Card (approx 95% of cards)
        markets.append({
            'market_type': 'cards_yellow',
            'line': None,
            'fair_prob': 1.0 - math.exp(-p['lam_cards'] * 0.95)
        })

        # 8. Player to be Carded (Yellow or Red)
        markets.append({
            'market_type': 'cards_any',
            'line': None,
            'fair_prob': p['card_prob']
        })

        # 9. First Player to be Carded
        markets.append({
            'market_type': 'cards_first',
            'line': None,
            'fair_prob': (p['card_prob'] / sum_card_prob) * 0.95
        })

        # 10. Player To Score in 1st Half
        markets.append({
            'market_type': 'goals_first_half',
            'line': None,
            'fair_prob': p_half
        })

        # 11. Player To Score in 2nd Half
        markets.append({
            'market_type': 'goals_second_half',
            'line': None,
            'fair_prob': p_half
        })

        # 12. Player Total Shots (Over/Under lines)
        for line in [0.5, 1.5, 2.5, 3.5]:
            prob, _ = calculate_over_prob(
                p10_passes=p['shots_p10'], p50_passes=p['shots_p50'], p90_passes=p['shots_p90'],
                p10_minutes=p['min_p10'], p50_minutes=p['min_p50'], p90_minutes=p['min_p90'],
                betting_line=line
            )
            markets.append({
                'market_type': 'shots_total',
                'line': line,
                'fair_prob': prob
            })

        # 13. Player Shots On Target (Over/Under lines)
        for line in [0.5, 1.5, 2.5]:
            prob, _ = calculate_over_prob(
                p10_passes=p['sot_p10'], p50_passes=p['sot_p50'], p90_passes=p['sot_p90'],
                p10_minutes=p['min_p10'], p50_minutes=p['min_p50'], p90_minutes=p['min_p90'],
                betting_line=line
            )
            markets.append({
                'market_type': 'sot_total',
                'line': line,
                'fair_prob': prob
            })

        # 14. Player Offsides Totals
        for line in [0.5, 1.5]:
            # Poisson Over line logic
            prob = poisson_prob_ge(p['lam_offsides'], int(line + 0.5))
            markets.append({
                'market_type': 'offsides_total',
                'line': line,
                'fair_prob': prob
            })

        # Price and place bets
        for mkt in markets:
            over_odds, under_odds = get_current_odds(str(fixture_id), p_name, mkt['market_type'], mkt['line'])
            if over_odds is None:
                continue

            all_outcome_odds = [over_odds, under_odds] if under_odds else [over_odds]
            label = f"{mkt['market_type']}" + (f" line {mkt['line']}" if mkt['line'] else "")

            print(f"    {label.upper()}: Fair prob={mkt['fair_prob']:.3f} | Market over={over_odds} | under={under_odds}")

            bet_id = place_bet(
                fair_prob        = mkt['fair_prob'],
                market_odds      = over_odds,
                all_outcome_odds = all_outcome_odds,
                match_id         = str(fixture_id),
                player_id        = p['player_id'],
                market_type      = mkt['market_type'],
                line             = mkt['line'] or 0.0,
                side             = 'over',
                lineup_drop_at   = lineup_drop_at,
                latency_ms       = latency_ms,
                regime           = regime,
                role_shift_flag  = False
            )

            if bet_id:
                bets_placed.append(bet_id)
                break  # Max 1 bet per player per match to manage overall variance

    elapsed = int((time.time() - start_time) * 1000)
    print(f"\n=== MODEL RUNNER DONE | {len(bets_placed)} bets placed | {elapsed}ms ===")
    return bets_placed
