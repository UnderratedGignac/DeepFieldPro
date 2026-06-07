"""
DeepFieldPro — Prediction Engine (Module 1 of 3)
=================================================
Generates probability distributions for every player prop market
from the trained LightGBM models using Monte Carlo simulation.

INPUT:  Date (default: today), optional nation codes to filter
OUTPUT: Structured DataFrame of player prop probabilities

No hardcoded values. All predictions driven from:
  - Real match logs (world_cup_players_match_logs_global.csv)
  - Real LightGBM models (models/lgb_*_final.txt)
  - Real live fixtures (API-Football)
"""

import pandas as pd
import numpy as np
import lightgbm as lgb
import requests
import os
import unicodedata
import re
from datetime import date

# stdout encoding is set by the calling script or terminal

# ─── Paths ────────────────────────────────────────────────────────────────────
ROOT         = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR     = os.path.join(ROOT, 'data')
MODEL_DIR    = os.path.join(ROOT, 'models')
GLOBAL_CSV   = os.path.join(DATA_DIR, 'world_cup_players_match_logs_global.csv')

API_KEY     = '4ae9f07e1ae1f775050015c50037a71d'
API_HEADERS = {'x-apisports-key': API_KEY}
API_BASE    = 'https://v3.football.api-sports.io'

# ─── Config ───────────────────────────────────────────────────────────────────
TARGETS      = ['Performance_Gls', 'Performance_Ast', 'Performance_Sh',
                'Performance_SoT', 'Performance_CrdY', 'min_']
NUMERIC_COLS = ['min_', 'Performance_Gls', 'Performance_Ast',
                'Performance_Sh', 'Performance_SoT', 'Performance_CrdY', 'Performance_CrdR']
N_SIMS       = 10_000

# Nation code → API team name mapping (add more as needed)
TEAM_TO_NATION = {
    'Mexico': 'MEX', 'Serbia': 'SRB', 'Hungary': 'HUN', 'Finland': 'FIN',
    'Bulgaria': 'BUL', 'Moldova': 'MDA', 'Slovakia': 'SVK', 'Montenegro': 'MNE',
    'Georgia': 'GEO', 'Argentina': 'ARG', 'France': 'FRA', 'Brazil': 'BRA',
    'England': 'ENG', 'Germany': 'GER', 'Spain': 'ESP', 'Portugal': 'POR',
    'Netherlands': 'NED', 'Italy': 'ITA', 'Belgium': 'BEL', 'Croatia': 'CRO',
    'Uruguay': 'URU', 'Colombia': 'COL', 'Morocco': 'MAR', 'Senegal': 'SEN',
    'Poland': 'POL', 'Switzerland': 'SUI', 'Denmark': 'DEN', 'Japan': 'JPN',
    'South Korea': 'KOR', 'Australia': 'AUS', 'Ecuador': 'ECU', 'USA': 'USA',
    'Canada': 'CAN', 'Wales': 'WAL', 'Scotland': 'SCO', 'Ghana': 'GHA',
    'Nigeria': 'NGA', 'Cameroon': 'CMR', 'Tunisia': 'TUN', 'Algeria': 'ALG',
    'Saudi Arabia': 'KSA', 'Iran': 'IRN', 'Ukraine': 'UKR', 'Peru': 'PER',
    'Paraguay': 'PAR', 'Venezuela': 'VEN', 'Mali': 'MLI',
    'Ivory Coast': "CIV", "Côte d'Ivoire": 'CIV', 'Korea Republic': 'KOR',
}


def normalize(s):
    if not isinstance(s, str): return ''
    s = unicodedata.normalize('NFKD', s.lower().strip())
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'[^a-z\s]', '', s).strip()


def load_dataset():
    """Load dataset and engineer causal rolling features."""
    df = pd.read_csv(GLOBAL_CSV)
    df['Date'] = pd.to_datetime(df['game_'].str[:10], errors='coerce')
    df = df.dropna(subset=['Date', 'player_']).sort_values(['player_', 'Date'])

    for c in NUMERIC_COLS:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0).clip(lower=0)

    g = df.groupby('player_')
    features = []
    for c in NUMERIC_COLS:
        df[f'{c}_roll3']  = g[c].transform(lambda x: x.shift(1).rolling(3,  min_periods=1).mean()).fillna(0)
        df[f'{c}_roll10'] = g[c].transform(lambda x: x.shift(1).rolling(10, min_periods=1).mean()).fillna(0)
        features += [f'{c}_roll3', f'{c}_roll10']
    df['days_since_last_match'] = g['Date'].diff().dt.days.fillna(7).clip(upper=30)
    features.append('days_since_last_match')

    # Latest feature snapshot per player (prediction input)
    latest = df[df['min__roll10'] > 0].groupby('player_').tail(1).copy()
    return latest, features


def load_models():
    """Load all trained LightGBM models from disk."""
    models = {}
    for t in TARGETS:
        path = os.path.join(MODEL_DIR, f'lgb_{t}_final.txt')
        if os.path.exists(path):
            models[t] = lgb.Booster(model_file=path)
        else:
            print(f'  WARNING: Model missing for {t}')
    return models


def get_todays_fixtures(target_date: str) -> list[dict]:
    """Fetch fixtures from API-Football for the given date that have DB coverage."""
    r = requests.get(f'{API_BASE}/fixtures', headers=API_HEADERS,
                     params={'date': target_date, 'timezone': 'Asia/Beirut'})
    all_fixtures = r.json().get('response', [])
    output = []
    for fix in all_fixtures:
        home_name = fix['teams']['home']['name']
        away_name = fix['teams']['away']['name']
        home_code = TEAM_TO_NATION.get(home_name)
        away_code = TEAM_TO_NATION.get(away_name)
        if home_code or away_code:
            output.append({
                'fixture_id': fix['fixture']['id'],
                'home':       home_name,
                'away':       away_name,
                'home_code':  home_code,
                'away_code':  away_code,
                'league':     fix['league']['name'],
                'kickoff':    fix['fixture']['date'],
            })
    return output


def simulate_player(row: pd.Series, models: dict, features: list, n_sims: int = N_SIMS) -> dict:
    """
    Run Monte Carlo simulations for a single player row.
    Returns dict of expected values and probabilities for each market.
    """
    X = pd.DataFrame([row[features].fillna(0)])
    result = {'player': row['player_'], 'nation': row.get('nation_', ''), 'pos': row.get('pos_', '')}

    for target in TARGETS:
        if target not in models:
            continue
        exp = max(0.0, float(models[target].predict(X)[0]))
        short = target.replace('Performance_', '').replace('min_', 'min')

        if target == 'min_':
            sims = np.clip(np.random.normal(exp, max(5.0, exp * 0.2), n_sims), 0, 90)
        else:
            sims = np.random.poisson(max(0.001, exp), n_sims)

        result[f'exp_{short}']        = round(exp, 4)
        result[f'p_{short}_over_0_5'] = round(float(np.mean(sims >= 1)),    4)
        result[f'p_{short}_over_1_5'] = round(float(np.mean(sims >= 2)),    4)
        result[f'p_{short}_over_2_5'] = round(float(np.mean(sims >= 3)),    4)
        result[f'ci95_lo_{short}']    = round(float(np.percentile(sims, 2.5)), 2)
        result[f'ci95_hi_{short}']    = round(float(np.percentile(sims, 97.5)), 2)

    # Confidence tier
    exp_gls = result.get('exp_Gls', 0)
    exp_min = result.get('exp_min', 0)
    n_hist = int(row.get('min__roll10', 0) > 10)
    if exp_gls > 0.20 and exp_min > 60 and n_hist:
        result['confidence'] = 'HIGH'
    elif exp_gls > 0.08 or exp_min > 40:
        result['confidence'] = 'MEDIUM'
    else:
        result['confidence'] = 'LOW'

    return result


def run_predictions(target_date: str = None) -> pd.DataFrame:
    """
    Main entry point. Returns a DataFrame of player-level prop probabilities
    for all matches on the given date that have players in our DB.
    """
    if target_date is None:
        target_date = date.today().strftime('%Y-%m-%d')

    print(f'\n{"="*65}')
    print(f'[PREDICTION ENGINE] Running for {target_date}')
    print(f'{"="*65}')

    print('[1] Loading dataset and features...')
    latest_df, features = load_dataset()
    print(f'    {len(latest_df):,} players ready for prediction')

    print('[2] Loading models...')
    models = load_models()
    print(f'    {len(models)} models loaded: {list(models.keys())}')

    print(f'[3] Fetching fixtures for {target_date}...')
    fixtures = get_todays_fixtures(target_date)
    print(f'    {len(fixtures)} matches with potential DB coverage')

    # Build nation→player lookup
    nations_in_db = set(latest_df['nation_'].dropna().str.upper())

    all_rows = []
    for fix in fixtures:
        for team_name, nation_code in [(fix['home'], fix['home_code']),
                                        (fix['away'], fix['away_code'])]:
            if not nation_code or nation_code not in nations_in_db:
                continue
            team_df = latest_df[latest_df['nation_'].str.upper() == nation_code]
            for _, row in team_df.iterrows():
                pred = simulate_player(row, models, features)
                pred['fixture_id'] = fix['fixture_id']
                pred['match']      = f"{fix['home']} vs {fix['away']}"
                pred['team']       = team_name
                pred['nation']     = nation_code
                pred['league']     = fix['league']
                pred['kickoff']    = fix['kickoff']
                all_rows.append(pred)

    if not all_rows:
        print('    No players found for today\'s matches.')
        return pd.DataFrame()

    predictions_df = pd.DataFrame(all_rows)
    print(f'\n[DONE] Generated predictions for {len(predictions_df)} players across {predictions_df["match"].nunique()} matches.')
    return predictions_df


if __name__ == '__main__':
    df = run_predictions()
    if not df.empty:
        out = os.path.join(ROOT, 'data', f'predictions_{date.today()}.csv')
        df.to_csv(out, index=False)
        print(f'\nSaved: {out}')
        print(df[['player', 'match', 'exp_Gls', 'p_Gls_over_0_5', 'exp_Sh', 'confidence']].head(10).to_string())
