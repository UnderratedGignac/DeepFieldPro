import lightgbm as lgb
import pandas as pd
import sqlite3
import os
from unidecode import unidecode

print("Building training dataset for all Betarabia props...")
try:
    df = pd.read_csv('C:/Users/Elie/DeepFieldPro/data/world_cup_players_match_logs.csv')
except FileNotFoundError:
    print("Error: world_cup_players_match_logs.csv not found.")
    exit(1)

# Load player database for PPM alignment
try:
    player_db = pd.read_csv('C:/Users/Elie/data/csv/FULL_PLAYER_DATABASE_2026.csv')
    player_db['name_clean'] = player_db['Player Name'].apply(lambda x: unidecode(str(x)).lower().strip())
    player_ppm = player_db.sort_values('season', ascending=False).groupby('name_clean').agg(
        db_ppm = ('PPM', 'first'),
        db_age = ('Age', 'first'),
        db_min_pct = ('Min%', 'first'),
        db_mn_start = ('Mn/Start', 'first'),
        db_mn_mp = ('Mn/MP', 'first'),
    ).reset_index()
    print(f"Loaded PPM stats for {len(player_ppm)} unique players.")
except Exception as e:
    print(f"Warning: Could not load player database: {e}")
    player_ppm = pd.DataFrame()

# Numeric conversions
cols_to_convert = ['min_', 'Performance_Sh', 'Performance_SoT', 'Performance_Crs', 
                   'Performance_TklW', 'Performance_Int', 'Performance_Gls', 'Performance_Ast',
                   'Performance_CrdY', 'Performance_CrdR', 'Performance_Off']
for col in cols_to_convert:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

# Filter: played > 10 minutes, outfield players only
df = df[df['min_'] > 10].copy()
df = df[~df['pos_'].astype(str).str.contains('GK', na=False)].copy()

# Extract opponent from game_ column
def get_opponent(row):
    game = str(row['game_'])
    team = str(row['team_'])
    parts = game.split()
    if len(parts) >= 2:
        matchup = parts[1]
        teams = matchup.split('-')
        if len(teams) == 2:
            h, a = teams[0].strip(), teams[1].strip()
            if h.lower() == team.lower():
                return a
            return h
    return 'Unknown'

df['opponent'] = df.apply(get_opponent, axis=1)

# Rename and build targets
df = df.rename(columns={
    'player_':          'player_name',
    'min_':             'Minutes Played',
    'pos_':             'Position',
    'team_':            'team',
    'Performance_Sh':   'shots',
    'Performance_SoT':  'sot',
    'Performance_Gls':  'goals',
    'Performance_CrdY': 'cards_y',
    'Performance_CrdR': 'cards_r',
    'Performance_Off':  'offsides',
})

df['cards'] = df['cards_y'] + df['cards_r']

df['shots_per_90']    = (df['shots'] / df['Minutes Played']) * 90.0
df['sot_per_90']      = (df['sot'] / df['Minutes Played']) * 90.0
df['goals_per_90']    = (df['goals'] / df['Minutes Played']) * 90.0
df['cards_per_90']    = (df['cards'] / df['Minutes Played']) * 90.0
df['offsides_per_90'] = (df['offsides'] / df['Minutes Played']) * 90.0

# Aligned features
if not player_ppm.empty:
    df['name_clean'] = df['player_name'].apply(lambda x: unidecode(str(x)).lower().strip())
    df = df.merge(player_ppm, on='name_clean', how='left')
    df['PPM'] = df['db_ppm'].fillna(1.0)
    df['Age'] = df['db_age'].fillna(26.0)
    df['Min%'] = df['db_min_pct'].fillna(0.7)
    df['Mn/Start'] = df['db_mn_start'].fillna(75.0)
    df['Mn/MP'] = df['db_mn_mp'].fillna(70.0)
else:
    df['PPM'] = 1.0
    df['Age'] = 26.0
    df['Min%'] = 0.7
    df['Mn/Start'] = 75.0
    df['Mn/MP'] = 70.0

# Position encoding
pos_map = {
    'MF': 3, 'CM': 3, 'DM': 3, 'AM': 3, 'LM': 3, 'RM': 3,
    'DF': 2, 'CB': 2, 'LB': 2, 'RB': 2, 'LWB': 2, 'RWB': 2,
    'FW': 1, 'LW': 1, 'RW': 1, 'ST': 1, 'CF': 1, 'SS': 1
}
df['Position_encoded'] = df['Position'].apply(lambda x: pos_map.get(str(x).upper().strip(), 2))

df['Starts'] = (df['Minutes Played'] >= 60).astype(int)
df['Crs']           = df['Performance_Crs']
df['Interceptions'] = df['Performance_Int']
df['Tackles Won']   = df['Performance_TklW']

# Merge opponent profiles
DB_OPP = 'C:/Users/Elie/DeepFieldPro/data/opponent_profiles.db'
df['ppda'] = 12.0
df['opp_possession_allowed'] = 50.0

if os.path.exists(DB_OPP):
    conn = sqlite3.connect(DB_OPP)
    try:
        opp = pd.read_sql_query("SELECT team_name, ppda, opp_possession_allowed FROM opponent_profiles", conn)
        df = df.merge(opp.rename(columns={'team_name': 'opponent'}), on='opponent', how='left', suffixes=('', '_opp'))
        df['ppda'] = df['ppda_opp'].fillna(12.0)
        df['opp_possession_allowed'] = df['opp_possession_allowed_opp'].fillna(50.0)
    except Exception as e:
        print(f"Warning: Opponent DB merge failed: {e}")
    conn.close()

df['sample_weight'] = 1.0

# Features list
FEATURES = [
    'Age',
    'Position_encoded',                       
    'Minutes Played',                 
    'Mn/Start',                       
    'Percentage of Minutes Played',   
    'Crs',                            
    'Interceptions',                  
    'Tackles Won',                    
    'ppda',                           
    'opp_possession_allowed',         
    'sample_weight',                  
]
df['Percentage of Minutes Played'] = df['Min%']
df = df.dropna(subset=FEATURES + ['shots_per_90', 'sot_per_90', 'goals_per_90', 'cards_per_90', 'offsides_per_90'])

X = df[FEATURES].apply(pd.to_numeric, errors='coerce')
weights = df['sample_weight']

os.makedirs('C:/Users/Elie/DeepFieldPro/models', exist_ok=True)

# 1. Train Shots and SOT Models (Quantile)
print("\nTraining SHOTS & SOT models...")
for market, y in [('shots', df['shots_per_90']), ('sot', df['sot_per_90'])]:
    for q in [0.10, 0.50, 0.90]:
        params = {
            'objective': 'quantile',
            'alpha': q,
            'metric': 'quantile',
            'num_leaves': 63,         
            'learning_rate': 0.03,
            'n_estimators': 500,
            'min_child_samples': 15,
            'verbose': -1
        }
        m = lgb.LGBMRegressor(**params)
        m.fit(X, y, sample_weight=weights)
        m.booster_.save_model(f'C:/Users/Elie/DeepFieldPro/models/{market}_p{int(q*100)}.txt')
        print(f"  Trained {market} q={q}")

# 2. Train Goals, Cards, Offsides Mean Models (L2 Regressor)
print("\nTraining GOALS, CARDS, & OFFSIDES mean models...")
for market, y in [('goals', df['goals_per_90']), ('cards', df['cards_per_90']), ('offsides', df['offsides_per_90'])]:
    params = {
        'objective': 'regression',
        'metric': 'rmse',
        'num_leaves': 31,
        'learning_rate': 0.05,
        'n_estimators': 300,
        'verbose': -1
    }
    m = lgb.LGBMRegressor(**params)
    m.fit(X, y, sample_weight=weights)
    m.booster_.save_model(f'C:/Users/Elie/DeepFieldPro/models/{market}_mean.txt')
    print(f"  Trained {market} Mean Model. Avg prediction rate: {m.predict(X.head(1))[0]:.3f} per 90")

print("\n[OK] All Betarabia models successfully trained and saved!")
