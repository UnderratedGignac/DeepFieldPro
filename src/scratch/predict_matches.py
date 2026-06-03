from app_config import config

# mypy: ignore-errors
import os
import sqlite3
import pandas as pd
import numpy as np
import lightgbm as lgb
from unidecode import unidecode
from pricing_engine import calculate_over_prob

# Paths
BASE_DIR = config.BASE_DIR
MODEL_DIR = os.path.join(BASE_DIR, "models")
PLAYER_CSV = os.path.join(config.DATA_DIR, "training_dataset.csv")
DB_OPP = os.path.join(BASE_DIR, "data", "opponent_profiles.db")

PASSES_LINES = [30.5, 35.5, 40.5, 45.5, 50.5, 55.5, 60.5]
MIN_EDGE = 0.05  # Look for >5% edge to recommend for live betting

# Load models
models = {
    "start_clf": lgb.Booster(model_file=f"{MODEL_DIR}/minutes_start_classifier.txt"),
    "min_p10": lgb.Booster(model_file=f"{MODEL_DIR}/minutes_p10_regressor.txt"),
    "min_p50": lgb.Booster(model_file=f"{MODEL_DIR}/minutes_p50_regressor.txt"),
    "min_p90": lgb.Booster(model_file=f"{MODEL_DIR}/minutes_p90_regressor.txt"),
    "pass_p10": lgb.Booster(model_file=f"{MODEL_DIR}/passes_p10.txt"),
    "pass_p50": lgb.Booster(model_file=f"{MODEL_DIR}/passes_p50.txt"),
    "pass_p90": lgb.Booster(model_file=f"{MODEL_DIR}/passes_p90.txt"),
}

# Load player database
player_db = pd.read_csv(PLAYER_CSV)
player_db["name_clean"] = player_db["Player Name"].apply(
    lambda x: unidecode(str(x)).lower().strip()
)


def get_player_stats(name):
    clean_name = unidecode(str(name)).lower().strip()
    match = player_db[player_db["name_clean"] == clean_name]
    if match.empty:
        # Fallback to partial match
        match = player_db[
            player_db["name_clean"].str.contains(clean_name[:8], na=False)
        ]
    if match.empty:
        return None
    return match.sort_values("season", ascending=False).iloc[0]


def get_opponent_profile(opponent_team_name):
    if not os.path.exists(DB_OPP):
        return {"ppda": 12.0, "opp_possession_allowed": 50.0}
    conn = sqlite3.connect(DB_OPP)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT ppda, opp_possession_allowed FROM opponent_profiles "
        "WHERE team_name LIKE ? ORDER BY match_week DESC LIMIT 1",
        (f"%{opponent_team_name}%",),
    )
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"ppda": row[0], "opp_possession_allowed": row[1]}
    return {"ppda": 12.0, "opp_possession_allowed": 50.0}


def safe_float(val, default):
    try:
        if isinstance(val, str) and "-" in val:
            return float(val.split("-")[0])
        return float(val)
    except:  # noqa: E722
        return float(default)


def build_features(stats, opp_profile):
    position_map = {"MF": 3, "DF": 2, "FW": 1, "GK": 0, "MF,FW": 2, "DF,MF": 2}
    pos_encoded = position_map.get(str(stats.get("Position", "MF")), 2)

    return {
        "Age": safe_float(stats.get("Age", 25), 25),
        "Position_encoded": pos_encoded,
        "Minutes Played": safe_float(stats.get("Minutes Played", 900), 900),
        "Starts": safe_float(stats.get("Starts", 10), 10),
        "Percentage of Minutes Played": safe_float(stats.get("Min%", 0.7), 0.7),
        "Mn/Start": safe_float(stats.get("Mn/Start", 75), 75),
        "Mn/MP": safe_float(stats.get("Mn/MP", 70), 70),
        "PPM": safe_float(stats.get("PPM", 1.5), 1.5),
        "Crs": safe_float(stats.get("Crs", 1.0), 1.0),
        "Interceptions": safe_float(stats.get("Interceptions", 1.0), 1.0),
        "Tackles Won": safe_float(stats.get("Tackles Won", 1.0), 1.0),
        "Goals Scored While on Pitch": safe_float(stats.get("onG", 35), 35),
        "ppda": safe_float(opp_profile["ppda"], 12.0),
        "opp_possession_allowed": safe_float(
            opp_profile["opp_possession_allowed"], 50.0
        ),
        "sample_weight": 1.0,
    }


# Define Expected Lineups per team
MATCHES = [
    {
        "home_team": "Croatia",
        "away_team": "Belgium",
        "lineups": {
            "Croatia": [
                "Luka Modric",
                "Mateo Kovacic",
                "Lovro Majer",
                "Mario Pasalic",
                "Andrej Kramaric",
                "Josko Gvardiol",
                "Josip Sutalo",
                "Borna Sosa",
                "Josip Stanisic",
            ],
            "Belgium": [
                "Kevin De Bruyne",
                "Leandro Trossard",
                "Jeremy Doku",
                "Romelu Lukaku",
                "Amadou Onana",
                "Orel Mangala",
                "Timothy Castagne",
                "Wout Faes",
                "Jan Vertonghen",
                "Arthur Theate",
            ],
        },
    },
    {
        "home_team": "Georgia",
        "away_team": "Romania",
        "lineups": {
            "Georgia": [
                "Otar Kiteishvili",
                "Giorgi Kochorashvili",
                "Giorgi Chakvetadze",
                "Budu Zivzivadze",
                "Zuriko Davitashvili",
                "Otar Kakabadze",
                "Solomon Kvirkvelia",
                "Guram Kashia",
                "Lasha Dvali",
                "Levan Shengelia",
            ],
            "Romania": [
                "Dennis Man",
                "Razvan Marin",
                "Nicolae Stanciu",
                "Valentin Mihaila",
                "Denis Dragus",
                "Andrei Ratiu",
                "Radu Dragusin",
                "Andrei Burca",
                "Nicusor Bancu",
                "Marius Marin",
            ],
        },
    },
    {
        "home_team": "Morocco",
        "away_team": "Madagascar",
        "lineups": {
            "Morocco": [
                "Hakim Ziyech",
                "Brahim Diaz",
                "Amine Adli",
                "Youssef En-Nesyri",
                "Achraf Hakimi",
                "Nayef Aguerd",
                "Romain Saiss",
                "Yahia Attiyat Allah",
                "Sofyan Amrabat",
                "Azzedine Ounahi",
            ],
            "Madagascar": [
                "Melvin Adrien",
                "Romain Metanire",
                "Thomas Fontaine",
                "Jeremy Morel",
                "Jerome Mombris",
                "Anicet Abel",
                "Rayan Raveloson",
                "Ibrahim Amada",
                "Lalaina Nomenjanahary",
                "Paulin Voavy",
            ],
        },
    },
    {
        "home_team": "Wales",
        "away_team": "Ghana",
        "lineups": {
            "Wales": [
                "Brennan Johnson",
                "Harry Wilson",
                "Daniel James",
                "Kieffer Moore",
                "Connor Roberts",
                "Chris Mepham",
                "Joe Rodon",
                "Ben Davies",
                "Ethan Ampadu",
                "Jordan James",
            ],
            "Ghana": [
                "Mohammed Kudus",
                "Jordan Ayew",
                "Inaki Williams",
                "Antoine Semenyo",
                "Tariq Lamptey",
                "Daniel Amartey",
                "Alexander Djiku",
                "Gideon Mensah",
                "Thomas Partey",
                "Salis Abdul Samed",
            ],
        },
    },
    {
        "home_team": "Haiti",
        "away_team": "New Zealand",
        "lineups": {
            "Haiti": [
                "Duckens Nazon",
                "Derrick Etienne Jr.",
                "Frantzdy Pierrot",
                "Louicius Don Deedson",
                "Carlens Arcus",
                "Ricardo Ade",
                "Alex Christian",
                "Wilde-Donald Guerrier",
                "Bryan Alceus",
                "Woodensky Pierre",
            ],
            "New Zealand": [
                "Elijah Just",
                "Chris Wood",
                "Ben Waine",
                "Tim Payne",
                "Michael Boxall",
                "Nando Pijnaker",
                "Liberato Cacace",
                "Matthew Garbett",
                "Marko Stamenic",
                "Sarpreet Singh",
            ],
        },
    },
]

# Dumb market baseline parameters
BASELINE_PASSES = {3: 55.0, 2: 48.0, 1: 35.0, 0: 25.0}
MARKET_STD = 18.0

recommendations = []

for m in MATCHES:
    home = m["home_team"]
    away = m["away_team"]
    print(f"\nEvaluating: {home} vs {away}")

    # Process both teams
    for team, players in m["lineups"].items():
        opp_team = away if team == home else home
        opp_profile = get_opponent_profile(opp_team)

        for player_name in players:
            stats = get_player_stats(player_name)
            if stats is None:
                continue

            feats = build_features(stats, opp_profile)

            # Form df for LightGBM
            MINUTES_FEATURES = [
                "Age",
                "Starts",
                "Percentage of Minutes Played",
                "Mn/Start",
                "Mn/MP",
                "PPM",
                "ppda",
                "opp_possession_allowed",
                "sample_weight",
            ]
            PASSES_FEATURES = [
                "Age",
                "Position_encoded",
                "Minutes Played",
                "Mn/Start",
                "Percentage of Minutes Played",
                "Crs",
                "Interceptions",
                "Tackles Won",
                "Goals Scored While on Pitch",
                "ppda",
                "opp_possession_allowed",
                "sample_weight",
            ]

            X_min = pd.DataFrame([feats], columns=MINUTES_FEATURES)
            X_pass = pd.DataFrame([feats], columns=PASSES_FEATURES)

            start_prob = float(models["start_clf"].predict(X_min)[0])
            if start_prob < 0.50:
                continue  # Skip players unlikely to start / play significant minutes

            min_p10 = float(models["min_p10"].predict(X_min)[0])
            min_p50 = float(models["min_p50"].predict(X_min)[0])
            min_p90 = float(models["min_p90"].predict(X_min)[0])

            pass_p10 = float(models["pass_p10"].predict(X_pass)[0])
            pass_p50 = float(models["pass_p50"].predict(X_pass)[0])
            pass_p90 = float(models["pass_p90"].predict(X_pass)[0])

            # Predict for lines
            pos_enc = feats["Position_encoded"]
            market_mean = BASELINE_PASSES.get(pos_enc, 45.0)

            for line in PASSES_LINES:
                # Our fair probability
                our_prob, _ = calculate_over_prob(
                    p10_passes=pass_p10,
                    p50_passes=pass_p50,
                    p90_passes=pass_p90,
                    p10_minutes=min_p10,
                    p50_minutes=min_p50,
                    p90_minutes=min_p90,
                    betting_line=line,
                )

                # Market fair probability (dumb baseline)
                from scipy.stats import norm

                market_fair_prob = float(
                    np.clip(
                        1.0 - norm.cdf(line, loc=market_mean, scale=MARKET_STD),
                        0.01,
                        0.99,
                    )
                )

                # Standard vig-stripped odds implied probability
                market_odds = round(
                    1.0 / (market_fair_prob + 0.025), 2
                )  # Offer with 5% vig split
                market_implied = market_fair_prob

                edge = our_prob - market_implied

                # Sizing bet using fractional Kelly
                b = market_odds - 1.0
                if b > 0:
                    kelly_full = (our_prob * b - (1.0 - our_prob)) / b
                    stake = kelly_full * 0.25 * 10000.0  # $10k bankroll, 0.25 Kelly
                else:
                    stake = 0

                if edge >= MIN_EDGE and stake > 0:
                    recommendations.append(
                        {
                            "match": f"{home} vs {away}",
                            "player": player_name,
                            "line": line,
                            "our_prob": our_prob,
                            "market_odds": market_odds,
                            "market_implied": market_implied,
                            "edge": edge,
                            "stake": stake,
                            "exp_passes": pass_p50,
                        }
                    )

# Print Recommendations
print("\n" + "=" * 70)
print("             DEEPFIELD PRO RECOMMENDED HIGH-EDGE BETS")
print("=" * 70)
if not recommendations:
    print("No high-edge bets detected matching safety criteria.")
else:
    df_recs = pd.DataFrame(recommendations).sort_values("edge", ascending=False)
    for idx, r in df_recs.iterrows():
        print(f"Match:       {r['match']}")
        print(f"Player:      {r['player']} (Expected passes/90: {r['exp_passes']:.1f})")
        print(f"Bet:         Over {r['line']} Passes @ {r['market_odds']}")
        print(
            f"Model Prob:  {r['our_prob']*100:.1f}% | Market Implied: {r['market_implied']*100:.1f}%"
        )
        print(f"True Edge:   {r['edge']*100:+.1f}%")
        print(f"Rec Stake:   ${r['stake']:.2f} (on a $10,000 bankroll)")
        print("-" * 50)
