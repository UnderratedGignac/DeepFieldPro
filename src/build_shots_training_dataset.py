"""
build_shots_training_dataset.py
---------------------------------
Builds a clean training dataset for SHOTS and SHOTS ON TARGET (SoT)
using the 25/26 season match logs (49,004 rows).
Integrates real PPM (Passes Per Minute) from the player database to prevent feature mismatch.
"""
import pandas as pd
import sqlite3
import os
from unidecode import unidecode

print("Building training dataset for shots and shots on target...")

try:
    df = pd.read_csv('C:/Users/Elie/DeepFieldPro/data/world_cup_players_match_logs.csv')
except FileNotFoundError:
    print("Error: world_cup_players_match_logs.csv not found.")
    exit(1)

# Load player database for PPM alignment
try:
    player_db = pd.read_csv('C:/Users/Elie/data/csv/FULL_PLAYER_DATABASE_2026.csv')
    player_db['name_clean'] = player_db['Player Name'].apply(lambda x: unidecode(str(x)).lower().strip())
    # Take latest season's PPM and career stats per player
    player_ppm = player_db.sort_values('season', ascending=False).groupby('name_clean').agg(
        db_ppm = ('PPM', 'first'),
        db_age = ('Age', 'first'),
        db_min_pct = ('Min%', 'first'),
        db_mn_start = ('Mn/Start', 'first'),
        db_mn_mp = ('Mn/MP', 'first'),
    ).reset_index()
    print(f"Loaded PPM stats for {len(player_ppm)} unique players.")
except Exception as e:
    print(f"Warning: Could not load player database for PPM alignment: {e}")
    player_ppm = pd.DataFrame()

# Numeric conversions
for col in ['min_', 'Performance_Sh', 'Performance_SoT', 'Performance_Crs', 
            'Performance_TklW', 'Performance_Int', 'Performance_Gls', 'Performance_Ast']:
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

# Rename columns to match standard features
df = df.rename(columns={
    'player_':          'player_name',
    'min_':             'Minutes Played',
    'pos_':             'Position',
    'team_':            'team',
    'Performance_Sh':   'shots',
    'Performance_SoT':  'sot',
    'Performance_Gls':  'Goals Scored While on Pitch',
})

# Targets
df['shots_per_90'] = (df['shots'] / df['Minutes Played']) * 90.0
df['sot_per_90']   = (df['sot'] / df['Minutes Played']) * 90.0

# Player career averages (features)
player_career = df.groupby('player_name').agg(
    career_avg_sh  = ('shots_per_90', 'mean'),
    career_avg_sot = ('sot_per_90', 'mean'),
    career_min     = ('Minutes Played', 'mean'),
    num_matches    = ('game_id_', 'count'),
).reset_index()

df = df.merge(player_career, on='player_name', how='left')

# Join PPM and other aligned features
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
def encode_pos(pos):
    pos = str(pos).upper().strip()
    for key, val in pos_map.items():
        if key in pos:
            return val
    return 2 # default defender/midfielder

df['Position_encoded'] = df['Position'].apply(encode_pos)

df['Starts'] = (df['Minutes Played'] >= 60).astype(int)

# Features
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

# Sample weights
df['sample_weight'] = 1.0

# Save
os.makedirs('C:/Users/Elie/DeepFieldPro/data', exist_ok=True)
df.to_csv('C:/Users/Elie/DeepFieldPro/data/shots_training_dataset.csv', index=False)

print(f"\n[OK] Shots training dataset saved: {df.shape[0]} rows")
print(f"shots_per_90 stats:\n{df['shots_per_90'].describe()}")
print(f"sot_per_90 stats:\n{df['sot_per_90'].describe()}")
