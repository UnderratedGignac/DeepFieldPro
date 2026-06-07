"""
World Cup Player Coverage Audit
Performs fuzzy name matching to correctly measure WC player coverage in the dataset.
"""
import pandas as pd
import unicodedata
import re
import sys
import io

# Force UTF-8 output to avoid Windows cp1256 encoding errors
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

def normalize_name(name):
    """Normalize a player name for fuzzy matching."""
    if not isinstance(name, str):
        return ''
    # Lowercase
    name = name.lower().strip()
    # Remove diacritics (accents)
    name = unicodedata.normalize('NFKD', name)
    name = ''.join(c for c in name if not unicodedata.combining(c))
    # Remove special chars, keep spaces and letters
    name = re.sub(r'[^a-z\s]', '', name)
    # Collapse multiple spaces
    name = re.sub(r'\s+', ' ', name).strip()
    return name

def name_token_overlap(a, b):
    """Check if two names share at least 2 tokens (words)."""
    tokens_a = set(normalize_name(a).split())
    tokens_b = set(normalize_name(b).split())
    return len(tokens_a & tokens_b) >= 2

print("Loading data...")
wc = pd.read_csv('data/worldcup_players.csv')
df = pd.read_csv('data/model_ready_features.csv', usecols=['Player'])

wc_names = wc['player_name'].dropna().tolist()
df_names = list(df['Player'].dropna().unique())

# Normalize all names
wc_norm = [(n, normalize_name(n)) for n in wc_names]
df_norm_set = set(normalize_name(n) for n in df_names)
df_norm_list = [(n, normalize_name(n)) for n in df_names]

print(f"\nWC Reference players: {len(wc_norm)}")
print(f"Unique players in dataset: {len(df_names)}")

# Exact match after normalization
exact_matched = []
exact_missing = []
for orig, norm in wc_norm:
    if norm in df_norm_set:
        exact_matched.append(orig)
    else:
        exact_missing.append((orig, norm))

print("\n=== EXACT MATCH (after normalization) ===")
print(f"  Matched: {len(exact_matched)} ({round(len(exact_matched)/len(wc_norm)*100,1)}%)")
print(f"  Missing: {len(exact_missing)}")

# Fuzzy token overlap match for remaining
fuzzy_matched = []
still_missing = []

df_norm_list_normalized = [(n, normalize_name(n)) for n in df_names]

for orig, norm in exact_missing:
    found = False
    for df_orig, df_norm in df_norm_list_normalized:
        tokens_wc = set(norm.split())
        tokens_df = set(df_norm.split())
        overlap = tokens_wc & tokens_df
        # Match if 2+ tokens overlap OR the shorter name is fully contained
        if len(overlap) >= 2 or (len(tokens_wc) == 1 and norm == df_norm):
            fuzzy_matched.append((orig, df_orig))
            found = True
            break
    if not found:
        still_missing.append(orig)

print("\n=== FUZZY TOKEN MATCH (additional) ===")
print(f"  Additional fuzzy matched: {len(fuzzy_matched)}")

total_matched = len(exact_matched) + len(fuzzy_matched)
print("\n=== FINAL COVERAGE ===")
print(f"  Total WC players: {len(wc_norm)}")
print(f"  Total matched: {total_matched} ({round(total_matched/len(wc_norm)*100,1)}%)")
print(f"  Genuinely missing: {len(still_missing)}")

if still_missing:
    print(f"\nPlayers with NO match in dataset ({len(still_missing)}):")
    for p in still_missing[:50]:
        print(f"  - {p}")
    if len(still_missing) > 50:
        print(f"  ... and {len(still_missing)-50} more")

    # Save missing list to file
    with open('data/genuinely_missing_wc_players.txt', 'w', encoding='utf-8') as f:
        for p in still_missing:
            f.write(p + '\n')
    print("\nFull missing list saved to: data/genuinely_missing_wc_players.txt")
