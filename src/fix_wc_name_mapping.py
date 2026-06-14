"""
Advanced WC Player Name Resolver
Uses multi-strategy matching:
1. Exact normalized match
2. Subset token match (FBref name tokens ⊆ legal name tokens)
3. Last-name + first-name-initial match
4. Single distinctive last name match (for mono-name players like Richarlison)
"""

import pandas as pd
import unicodedata
import re
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def normalize_name(name):
    if not isinstance(name, str):
        return ""
    name = name.lower().strip()
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    name = re.sub(r"[^a-z\s]", "", name)
    return re.sub(r"\s+", " ", name).strip()


print("Loading data...")
wc = pd.read_csv("data/worldcup_players.csv")
df_players = pd.read_csv(
    "data/model_ready_features.csv", usecols=["Player"]
).drop_duplicates()
df_players["player_norm"] = df_players["Player"].apply(normalize_name)
df_players_list = list(
    df_players[["Player", "player_norm"]].itertuples(index=False, name=None)
)

wc["player_norm"] = wc["player_name"].apply(normalize_name)

# Build reverse index: last_name -> [df players]
last_name_index = {}
for df_orig, df_norm in df_players_list:
    tokens = df_norm.split()
    if tokens:
        last = tokens[-1]
        last_name_index.setdefault(last, []).append((df_orig, df_norm))


def find_match(wc_name, wc_norm):
    wc_tokens = wc_norm.split()
    if not wc_tokens:
        return None, 0.0

    # Strategy 1: Exact normalized match
    for df_orig, df_norm in df_players_list:
        if wc_norm == df_norm:
            return df_orig, 1.0

    # Strategy 2: All df tokens ⊆ wc tokens (FBref short name contained in legal name)
    best, best_score = None, 0
    for df_orig, df_norm in df_players_list:
        df_tokens = set(df_norm.split())
        wc_set = set(wc_tokens)
        if len(df_tokens) >= 2 and df_tokens.issubset(wc_set):
            score = len(df_tokens) / len(wc_set) + 0.5  # bonus for subset
            if score > best_score:
                best_score, best = score, df_orig

    if best:
        return best, best_score

    # Strategy 3: Last name of WC player matches last name of df player + first initial matches
    for last_token in (
        [wc_tokens[-1], wc_tokens[0]] if len(wc_tokens) > 1 else [wc_tokens[0]]
    ):
        candidates = last_name_index.get(last_token, [])
        for df_orig, df_norm in candidates:
            df_tokens = df_norm.split()
            # Check if first initials match too
            if len(df_tokens) >= 2 and len(wc_tokens) >= 2:
                if df_tokens[0][0] == wc_tokens[0][0]:  # First initial match
                    return df_orig, 0.85
            elif len(df_tokens) == 1 and df_tokens[0] == last_token:
                # Mononym player (e.g., Richarlison in dataset)
                return df_orig, 0.80

    # Strategy 4: Any 2+ token overlap
    for df_orig, df_norm in df_players_list:
        df_set = set(df_norm.split())
        wc_set = set(wc_tokens)
        overlap = df_set & wc_set
        if len(overlap) >= 2:
            score = len(overlap) / max(len(df_set), len(wc_set))
            if score > best_score:
                best_score, best = score, df_orig

    return best, best_score


print(
    f"Running advanced matching for {len(wc)} WC players vs {len(df_players)} dataset players..."
)

results = []
for _, row in wc.iterrows():
    match, score = find_match(row["player_name"], row["player_norm"])
    results.append(
        {
            "player_id": row["player_id"],
            "legal_name": row["player_name"],
            "fbref_name": match,
            "match_score": round(score, 3),
            "nation_code": row.get("nation_code", ""),
            "position": row.get("position", ""),
        }
    )

results_df = pd.DataFrame(results)
matched = results_df[results_df["fbref_name"].notna()]
unmatched = results_df[results_df["fbref_name"].isna()]

print("\n=== ADVANCED MATCHING RESULTS ===")
print(f"  Total WC players:  {len(results_df)}")
print(
    f"  Matched:           {len(matched)} ({round(len(matched)/len(results_df)*100,1)}%)"
)
print(f"  Unmatched:         {len(unmatched)}")

# Save the name mapping file (key reference for all downstream scripts)
results_df.to_csv("data/wc_player_name_mapping.csv", index=False, encoding="utf-8")
print("\nSaved mapping to: data/wc_player_name_mapping.csv")

print(f"\nStill genuinely unmatched ({len(unmatched)}):")
for _, r in unmatched.head(40).iterrows():
    print(f"  [{r['nation_code']}] {r['legal_name']}")
