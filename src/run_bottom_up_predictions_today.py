import pandas as pd
import numpy as np
import joblib
import requests
import datetime

API_KEY = "4ae9f07e1ae1f775050015c50037a71d"
HEADERS = {"x-apisports-key": API_KEY, "x-apisports-host": "v3.football.api-sports.io"}


def get_todays_fixtures(only_friendlies=False):
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    url = f"https://v3.football.api-sports.io/fixtures?date={today}"
    r = requests.get(url, headers=HEADERS)
    if r.status_code == 200:
        data = r.json()
        if data.get("response"):
            fixtures = data["response"]
            if only_friendlies:
                fixtures = [
                    f
                    for f in fixtures
                    if "Friendlies" in f.get("league", {}).get("name", "")
                ]
            return fixtures
    return []


def get_fixture_lineups(fixture_id):
    url = f"https://v3.football.api-sports.io/fixtures/lineups?fixture={fixture_id}"
    r = requests.get(url, headers=HEADERS)
    if r.status_code == 200:
        data = r.json()
        if data.get("response"):
            return data["response"]
    return []


def load_player_database():
    try:
        df1 = pd.read_csv("data/minor_leagues_2025.csv")
        df2 = pd.read_csv("data/world_cup_players_match_logs.csv")
        df2 = df2.rename(columns={"player_": "player_name", "team_": "team"})
        df = pd.concat([df1, df2], ignore_index=True)
        return df
    except Exception:
        return pd.read_csv("data/minor_leagues_2025.csv")


def get_player_rolling_stats(player_name, df):
    # Match by name loosely
    p_data = df[
        df["player_name"].astype(str).str.contains(player_name, case=False, na=False)
    ]
    if len(p_data) > 0:
        # Take latest rolling avg
        latest = p_data.iloc[-1]
        return {
            "goals_roll": latest.get("goals", 0),
            "assists_roll": latest.get("assists", 0),
            "shots_roll": latest.get("shots", 0),
            "passes_roll": latest.get("passes", 0),
            "rating_roll": latest.get("rating", 6.5),
        }
    else:
        # Unknown player, return league baseline
        return {
            "goals_roll": 0.1,
            "assists_roll": 0.05,
            "shots_roll": 0.5,
            "passes_roll": 15.0,
            "rating_roll": 6.0,
        }


def predict_match(fixture, player_model, match_model, df):
    home_team = fixture["teams"]["home"]["name"]
    away_team = fixture["teams"]["away"]["name"]
    league_name = fixture["league"]["name"]
    fixture_id = fixture["fixture"]["id"]

    # Try to get lineups
    lineups = get_fixture_lineups(fixture_id)
    home_players = []
    away_players = []

    if len(lineups) == 2:
        for p in lineups[0].get("startXI", []):
            home_players.append(p["player"]["name"])
        for p in lineups[1].get("startXI", []):
            away_players.append(p["player"]["name"])
    else:
        # Fallback dummy players if no lineup yet
        home_players = [f"Player {i}" for i in range(1, 12)]
        away_players = [f"Player {i}" for i in range(1, 12)]

    home_impact = 0
    away_impact = 0

    home_player_stats = []
    for p in home_players:
        stats = get_player_rolling_stats(p, df)
        features = pd.DataFrame([stats])
        impact = player_model.predict(features)[0]
        home_impact += impact
        home_player_stats.append({"name": p, "impact": round(impact, 2)})

    away_player_stats = []
    for p in away_players:
        stats = get_player_rolling_stats(p, df)
        features = pd.DataFrame([stats])
        impact = player_model.predict(features)[0]
        away_impact += impact
        away_player_stats.append({"name": p, "impact": round(impact, 2)})

    league_elo_map = {
        "ENG-Premier League": 1800,
        "ENG-Championship": 1550,
        "BRA-Serie A": 1600,
        "ARG-Primera": 1550,
        "MLS": 1500,
        "Saudi Pro League": 1450,
        "World Cup": 1900,
    }

    base_elo = league_elo_map.get(league_name, 1500)
    home_elo = base_elo + (home_impact * 2)  # Form boost
    away_elo = base_elo + (away_impact * 2)

    match_features = pd.DataFrame(
        [
            {
                "team_A_expected_impact": home_impact,
                "team_B_expected_impact": away_impact,
                "impact_diff": home_impact - away_impact,
                "total_expected_impact": home_impact + away_impact,
                "elo_diff": home_elo - away_elo,
                "team_A_elo": home_elo,
                "team_B_elo": away_elo,
            }
        ]
    )

    outcome_pred = match_model.predict(match_features)[0]
    # outcome_pred: 1=Home Win, 0=Away Win, 2=Draw
    if outcome_pred == 1:
        winner = f"{home_team} WIN"
        home_g = np.random.poisson(2.1)
        away_g = np.random.poisson(0.8)
    elif outcome_pred == 0:
        winner = f"{away_team} WIN"
        home_g = np.random.poisson(0.8)
        away_g = np.random.poisson(2.1)
    else:
        winner = "DRAW"
        home_g = np.random.poisson(1.2)
        away_g = np.random.poisson(1.2)
        if home_g != away_g:
            home_g = away_g = max(home_g, away_g)

    # Derived Stats based on impact scaling
    intensity_factor = (home_impact + away_impact) / 10.0
    home_corners = int(np.random.poisson(4.5 + (home_impact * 0.2)))
    away_corners = int(np.random.poisson(4.5 + (away_impact * 0.2)))

    home_fouls = int(np.random.poisson(11.0 + intensity_factor))
    away_fouls = int(np.random.poisson(11.0 + intensity_factor))

    home_yellows = int(np.random.poisson(home_fouls * 0.15))
    away_yellows = int(np.random.poisson(away_fouls * 0.15))

    return {
        "match": f"{home_team} vs {away_team}",
        "league": league_name,
        "prediction": winner,
        "expected_score": f"{home_g} - {away_g}",
        "team_impacts": f"Home: {home_impact:.2f} | Away: {away_impact:.2f}",
        "corners": f"Home: {home_corners} | Away: {away_corners}",
        "fouls": f"Home: {home_fouls} | Away: {away_fouls}",
        "cards": f"Home Yellows: {home_yellows} | Away Yellows: {away_yellows}",
        "home_players": home_player_stats[:3],  # Top 3 for brevity
        "away_players": away_player_stats[:3],
    }


def main():
    import sys

    only_friendlies = "--friendlies" in sys.argv

    try:
        player_model = joblib.load("models/player_impact_model.pkl")
        match_model = joblib.load("models/bottom_up_match_model.pkl")
    except Exception as e:
        print("Models not found. Train them first.", e)
        return

    df = load_player_database()
    print("[*] Fetching today's fixtures from API-Football...")
    fixtures = get_todays_fixtures(only_friendlies=only_friendlies)

    if not fixtures:
        print(
            "No fixtures found for today or API limit reached. Mocking a test match..."
        )
        fixtures = [
            {
                "fixture": {"id": 999999},
                "league": {"name": "MLS"},
                "teams": {
                    "home": {"name": "Inter Miami CF"},
                    "away": {"name": "LA Galaxy"},
                },
            }
        ]

    results = []
    for f in fixtures:
        print(
            f"[*] Analyzing {f['teams']['home']['name']} vs {f['teams']['away']['name']}..."
        )
        res = predict_match(f, player_model, match_model, df)
        results.append(res)

    out_text = ""
    out_text += "===========================================\n"
    out_text += " DEEPFIELDPRO BOTTOM-UP MATCH PREDICTIONS\n"
    out_text += "===========================================\n\n"
    for r in results:
        out_text += f"### [{r['league']}] {r['match']}\n"
        out_text += f"- **Predicted Outcome:** {r['prediction']}\n"
        out_text += f"- **Expected Score:** {r['expected_score']}\n"
        out_text += f"- **Team Strengths (Aggregated Impact):** {r['team_impacts']}\n"
        out_text += f"- **Match Stats:** Corners ({r['corners']}) | Fouls ({r['fouls']}) | Cards ({r['cards']})\n"
        out_text += (
            "- **Top Impact Players (Home):** "
            + ", ".join([f"{p['name']} ({p['impact']})" for p in r["home_players"]])
            + "\n"
        )
        out_text += (
            "- **Top Impact Players (Away):** "
            + ", ".join([f"{p['name']} ({p['impact']})" for p in r["away_players"]])
            + "\n\n"
        )
        out_text += "---\n\n"

    with open("data/todays_predictions.md", "w", encoding="utf-8") as f:
        f.write(out_text)
    print("Predictions saved to data/todays_predictions.md")


if __name__ == "__main__":
    main()
