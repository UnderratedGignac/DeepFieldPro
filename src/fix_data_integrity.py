"""
DeepFieldPro - Data Integrity Fix
Fixes unparseable date rows in the global CSV.
"""
import pandas as pd
import sys
import io
import os

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GLOBAL_CSV = os.path.join(ROOT, 'data', 'world_cup_players_match_logs_global.csv')
BACKUP_CSV = os.path.join(ROOT, 'data', 'world_cup_players_match_logs_global.bak.csv')

df = pd.read_csv(GLOBAL_CSV)
print(f"Before: {len(df):,} rows")

# Back up
df.to_csv(BACKUP_CSV, index=False)
print(f"Backup saved: {BACKUP_CSV}")

# Parse dates
df['_date_parsed'] = pd.to_datetime(df['game_'].str[:10], errors='coerce')
bad = df['_date_parsed'].isna()
print(f"Unparseable date rows: {bad.sum()}")
if bad.sum() > 0:
    print("Sample bad rows:")
    print(df[bad][['player_', 'game_', 'game_id_']].head(10).to_string())

# Drop unparseable rows (they are corrupt/API junk rows)
df_clean = df[~bad].drop(columns=['_date_parsed'])
print(f"After cleanup: {len(df_clean):,} rows")

# Also ensure no negative numeric values
numeric_cols = ['min_', 'Performance_Gls', 'Performance_Ast',
                'Performance_Sh', 'Performance_SoT', 'Performance_CrdY', 'Performance_CrdR']
for c in numeric_cols:
    if c in df_clean.columns:
        df_clean[c] = pd.to_numeric(df_clean[c], errors='coerce').fillna(0).clip(lower=0)

# Drop duplicate (game_id_, player_) rows
before_dedup = len(df_clean)
df_clean = df_clean.drop_duplicates(subset=['game_id_', 'player_'], keep='first')
print(f"Deduplication: {before_dedup - len(df_clean)} rows removed")

df_clean.to_csv(GLOBAL_CSV, index=False)
print(f"Clean dataset saved: {len(df_clean):,} rows")
print("Done!")
