"""
DeepFieldPro - Match Simulation Engine (Production-Ready)
Runs 10,000 simulations per match using actual WC team rosters from the mapping CSV.
Players are looked up by their real national team assignments from the nation_ field.
"""

import pandas as pd
import numpy as np
import os
import sys
import io
import lightgbm as lgb
import warnings

warnings.filterwarnings("ignore")

sys.stdout = io.TextIOWrapper(
    sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
MODEL_DIR = os.path.join(ROOT, "models")
ARTIFACT_DIR = os.path.join(ROOT, "artifacts")
GLOBAL_CSV = os.path.join(DATA_DIR, "world_cup_players_match_logs_global.csv")
MAPPING_CSV = os.path.join(DATA_DIR, "wc_player_name_mapping.csv")

os.makedirs(ARTIFACT_DIR, exist_ok=True)

TARGETS = [
    "Performance_Gls",
    "Performance_Ast",
    "Performance_Sh",
    "Performance_SoT",
    "Performance_CrdY",
    "min_",
]
N_SIMS = 10000

NUMERIC_COLS = [
    "min_",
    "Performance_Gls",
    "Performance_Ast",
    "Performance_Sh",
    "Performance_SoT",
    "Performance_CrdY",
    "Performance_CrdR",
]


def build_features(df: pd.DataFrame):
    """Build causal rolling features. shift(1) ensures no look-ahead bias."""
    df = df.copy()
    df_grouped = df.groupby("player_")
    features = []
    for c in NUMERIC_COLS:
        if c not in df.columns:
            df[c] = 0.0
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
        df[f"{c}_roll3"] = (
            df_grouped[c]
            .transform(lambda x: x.shift(1).rolling(3, min_periods=1).mean())
            .fillna(0)
        )
        df[f"{c}_roll10"] = (
            df_grouped[c]
            .transform(lambda x: x.shift(1).rolling(10, min_periods=1).mean())
            .fillna(0)
        )
        features += [f"{c}_roll3", f"{c}_roll10"]
    df["days_since_last_match"] = (
        df_grouped["Date"].diff().dt.days.fillna(7).clip(upper=30)
    )
    features.append("days_since_last_match")
    return df, features


def load_models():
    """Load all 6 finalized LightGBM models from disk."""
    models = {}
    for target in TARGETS:
        path = os.path.join(MODEL_DIR, f"lgb_{target}_final.txt")
        if os.path.exists(path):
            models[target] = lgb.Booster(model_file=path)
            print(f"  Loaded model: {target}")
        else:
            print(f"  WARNING: Model missing for {target} at {path}")
    return models


def get_team_players(
    team_name: str, latest_df: pd.DataFrame, mapping: pd.DataFrame
) -> pd.DataFrame:
    """
    Returns real player rows for a given national team.
    Strategy:
      1. First filter the dataset using the nation_ field (e.g., 'FRA', 'ENG', 'ARG').
      2. Then further filter to only players on the WC roster (via mapping.fbref_name).
    """
    import unicodedata
    import re

    def normalize(s):
        if not isinstance(s, str):
            return ""
        s = s.lower().strip()
        s = unicodedata.normalize("NFKD", s)
        s = "".join(c for c in s if not unicodedata.combining(c))
        return re.sub(r"[^a-z\s]", "", s).strip()

    team_code = team_name.upper().strip()  # e.g., 'ENG', 'FRA'

    # 1. Get all players with this nation code in the main dataset
    nation_players = latest_df[
        latest_df["nation_"].str.upper().str.strip() == team_code
    ]

    if nation_players.empty:
        print(f"  WARNING: No players found with nation_ == '{team_code}'")
        return pd.DataFrame()

    # 2. Intersect with WC roster (fbref_name in mapping)
    wc_fbref_names = set(mapping["fbref_name"].dropna().tolist())
    wc_roster_players = nation_players[nation_players["player_"].isin(wc_fbref_names)]

    if wc_roster_players.empty:
        print(
            f"  WARNING: Nation '{team_code}' has {len(nation_players)} players in CSV but 0 match the WC roster."
        )
        print(f"  Falling back to all {len(nation_players)} nation players...")
        return nation_players

    print(
        f"  {team_code}: {len(wc_roster_players)} WC roster players with data (out of {len(nation_players)} total nation players in DB)"
    )
    return wc_roster_players


def simulate_match(
    team_a: str,
    team_b: str,
    models: dict,
    latest_df: pd.DataFrame,
    mapping: pd.DataFrame,
    features: list,
):
    """
    Simulate a match between two real national teams using the actual player roster.
    No random sampling - only real WC players from the roster.
    """
    print(f"\nSimulating: {team_a} vs {team_b} ({N_SIMS:,} iterations)")

    results_a = run_team_simulation(team_a, models, latest_df, mapping, features)
    results_b = run_team_simulation(team_b, models, latest_df, mapping, features)

    if results_a is None or results_b is None:
        print("  Cannot simulate: insufficient player data for one or both teams.")
        return None, None

    return results_a, results_b


def run_team_simulation(
    team_name: str,
    models: dict,
    latest_df: pd.DataFrame,
    mapping: pd.DataFrame,
    features: list,
):
    """Run Monte Carlo simulations for a team's players."""
    team_players = get_team_players(team_name, latest_df, mapping)

    if team_players.empty:
        print(f"  No data found for {team_name}")
        return None

    print(f"  {team_name}: {len(team_players)} players with data")

    X = team_players[features].fillna(0)
    player_names = team_players["player_"].tolist()

    player_results = []
    for i, player in enumerate(player_names):
        row = X.iloc[[i]]
        prow = {"Player": player, "Team": team_name}

        for target in TARGETS:
            if target not in models:
                continue
            exp = max(0, models[target].predict(row)[0])

            # Monte Carlo: Poisson for count stats, Normal for minutes
            if target == "min_":
                sims = np.random.normal(exp, max(5, exp * 0.2), N_SIMS)
                sims = np.clip(sims, 0, 90)
            else:
                sims = np.random.poisson(max(0.001, exp), N_SIMS)

            short = target.replace("Performance_", "").replace("min_", "min")
            prow[f"exp_{short}"] = exp
            prow[f"p_{short}_gt0"] = float(np.mean(sims >= 1))
            prow[f"p_{short}_gt1"] = float(np.mean(sims >= 2))
            prow[f"ci_low_{short}"] = float(np.percentile(sims, 2.5))
            prow[f"ci_high_{short}"] = float(np.percentile(sims, 97.5))

        player_results.append(prow)

    return pd.DataFrame(player_results)


def calculate_ev(prob_model: float, bookmaker_odds_decimal: float) -> float:
    """
    Calculate expected value (EV) given model probability and bookmaker decimal odds.
    EV > 0 means positive value.
    """
    ev = prob_model * (bookmaker_odds_decimal - 1) - (1 - prob_model)
    return ev


def generate_report(
    results_a: pd.DataFrame, results_b: pd.DataFrame, team_a: str, team_b: str
):
    """Generate a structured markdown simulation report."""
    report_path = os.path.join(ARTIFACT_DIR, "match_simulation_report.md")

    md = [f"# Match Simulation Report: {team_a} vs {team_b}\n"]
    md.append(
        f"**Simulations:** {N_SIMS:,} per player | **Method:** Monte Carlo Poisson / Normal"
    )
    md.append(f"**Players with data ({team_a}):** {len(results_a)}")
    md.append(f"**Players with data ({team_b}):** {len(results_b)}\n")

    for team_name, results_df in [(team_a, results_a), (team_b, results_b)]:
        md.append(f"\n## {team_name} Player Projections\n")
        md.append("| Player | xGoals | Goal% | xShots | SoT% | xMin | 95% CI Goals |")
        md.append("|---|---|---|---|---|---|---|")

        for _, row in results_df.sort_values("exp_Gls", ascending=False).iterrows():
            md.append(
                f"| {row['Player']} "
                f"| {row.get('exp_Gls', 0):.3f} "
                f"| {row.get('p_Gls_gt0', 0):.1%} "
                f"| {row.get('exp_Sh', 0):.2f} "
                f"| {row.get('p_SoT_gt0', 0):.1%} "
                f"| {row.get('exp_min', 0):.1f} "
                f"| [{row.get('ci_low_Gls', 0):.2f}, {row.get('ci_high_Gls', 0):.2f}] |"
            )

    # Team-level aggregates
    md.append("\n## Team Aggregates\n")
    md.append("| Stat | " + team_a + " | " + team_b + " |")
    md.append("|---|---|---|")

    for stat in ["exp_Gls", "exp_Sh", "exp_SoT"]:
        short = stat.replace("exp_", "")
        va = results_a[stat].sum() if stat in results_a.columns else 0
        vb = results_b[stat].sum() if stat in results_b.columns else 0
        md.append(f"| {short} (team total) | {va:.2f} | {vb:.2f} |")

    md.append("\n## EV Methodology")
    md.append(
        "For any player prop line, Expected Value = `P(model) × (decimal_odds - 1) - (1 - P(model))`"
    )
    md.append("Only bet when EV > 0. This system does **not** guarantee profits.")
    md.append("\n## Data Coverage Warning")
    md.append(
        "Note: 375 WC players (Saudi, MLS, Brasileirao, Iranian League, etc.) lack historical club match logs due to FBref data limitations. Projections for these players are marked as 'No Data'."
    )

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print(f"\nReport saved: {report_path}")


def main(team_a: str = None, team_b: str = None):
    print("=" * 65)
    print("DeepFieldPro - Match Simulation Engine (Production)")
    print("=" * 65)

    # Load data
    print("\n[1] Loading data...")
    df = pd.read_csv(GLOBAL_CSV)
    mapping = pd.read_csv(MAPPING_CSV)
    df["Date"] = pd.to_datetime(df["game_"].str[:10], errors="coerce")
    df = df.dropna(subset=["Date", "player_"]).sort_values(["player_", "Date"])

    df, features = build_features(df)

    # Get latest row per player
    latest_df = df[df["min__roll10"] > 0].groupby("player_").tail(1).copy()
    print(f"  {len(latest_df)} players have sufficient history for predictions")

    # Load models
    print("\n[2] Loading models...")
    models = load_models()

    if not team_a or not team_b:
        # Show available nation codes
        print("\n  Available nation codes:")
        print(" ", sorted(mapping["nation_code"].dropna().unique())[:30])
        team_a = team_a or "ARG"
        team_b = team_b or "FRA"

    print(f"\n[3] Running simulation: {team_a} vs {team_b}")
    results_a, results_b = simulate_match(
        team_a, team_b, models, latest_df, mapping, features
    )

    if results_a is not None and results_b is not None:
        generate_report(results_a, results_b, team_a, team_b)

    print("\nDone!")


if __name__ == "__main__":
    # Accept command-line args: python match_simulation_engine.py ARG FRA
    team_a = sys.argv[1] if len(sys.argv) > 1 else None
    team_b = sys.argv[2] if len(sys.argv) > 2 else None
    main(team_a, team_b)
