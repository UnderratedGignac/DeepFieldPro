import sqlite3
import json
import datetime
import os

db_path = "data/bet_log.db"
conn = sqlite3.connect(db_path)
cur = conn.cursor()

# Ensure predictions table exists
cur.execute("""
    CREATE TABLE IF NOT EXISTS predictions (
        fixture_id TEXT PRIMARY KEY,
        match_name TEXT,
        league TEXT,
        kickoff TEXT,
        prediction TEXT,
        expected_score TEXT,
        home_prob REAL,
        draw_prob REAL,
        away_prob REAL,
        over_prob REAL,
        under_prob REAL,
        btts_yes_prob REAL,
        btts_no_prob REAL,
        has_lineup INTEGER,
        predicted_at TIMESTAMP,
        extra_json TEXT
    )
""")

# 1. Seed Sweden U21 vs Finland U21 Prediction
sweden_pred_extra = {
    "team_impacts": "Home: 1.45 | Away: 1.15",
    "corners": "Home: 6 | Away: 4",
    "fouls": "Home: 10 | Away: 12",
    "cards": "Home Yellows: 2 | Away Yellows: 2",
    "home_players": [
        {"name": "Hugo Larsson", "rating": 7.2},
        {"name": "Roony Bardghji", "rating": 7.4}
    ],
    "away_players": [
        {"name": "Matias Siltanen", "rating": 6.8},
        {"name": "Juho Talvitie", "rating": 6.9}
    ],
    "detailed_prediction": {
        "home_prob": 45.0,
        "draw_prob": 25.0,
        "away_prob": 30.0,
        "predicted_score": "2 - 1",
        "confidence": 7,
        "home_xg": 1.8,
        "away_xg": 1.2,
        "over_05": 95,
        "over_15": 80,
        "over_25": 55,
        "over_35": 30,
        "under_25": 45,
        "btts_yes": 60,
        "possession_home": 55,
        "possession_away": 45,
        "fouls_home": 10,
        "fouls_away": 12,
        "offsides_home": 2,
        "offsides_away": 1,
        "saves_home": 3,
        "saves_away": 4,
        "clean_sheet_home": 30,
        "clean_sheet_away": 20,
        "corners_total": 10,
        "corners_home": 6,
        "corners_away": 4,
        "corners_over_75": 85,
        "corners_over_85": 70,
        "corners_over_95": 50,
        "corners_over_105": 30,
        "cards_yellow_home": 2,
        "cards_yellow_away": 2,
        "cards_yellow_total": 4,
        "cards_red_total": 0,
        "goalscorers": [
            {"name": "Roony Bardghji", "team": "Sweden U21", "anytime_goal_prob": 25.0, "first_goal_prob": 10.0, "rating": 7.4},
            {"name": "Hugo Larsson", "team": "Sweden U21", "anytime_goal_prob": 22.5, "first_goal_prob": 9.5, "rating": 7.2},
            {"name": "Juho Talvitie", "team": "Finland U21", "anytime_goal_prob": 18.0, "first_goal_prob": 7.5, "rating": 6.9},
            {"name": "Matias Siltanen", "team": "Finland U21", "anytime_goal_prob": 15.0, "first_goal_prob": 6.0, "rating": 6.8}
        ],
        "shots_players": [
            {"name": "Roony Bardghji", "team": "Sweden U21", "exp_shots": 2.5, "exp_sot": 1.2, "rating": 7.4},
            {"name": "Hugo Larsson", "team": "Sweden U21", "exp_shots": 2.2, "exp_sot": 0.8, "rating": 7.2},
            {"name": "Matias Siltanen", "team": "Finland U21", "exp_shots": 1.5, "exp_sot": 0.5, "rating": 6.8}
        ],
        "cards_players": [
            {"name": "Hugo Larsson", "team": "Sweden U21", "yellow_prob": 15.0, "red_prob": 1.0}
        ],
        "value_analysis": {
            "best_result": "Sweden U21 WIN",
            "best_goals": "Over 2.5 Goals",
            "best_cards": "Under 4.5 Cards",
            "best_corners": "Over 9.5 Corners",
            "best_player_prop": "Hugo Larsson Over 1.5 Shots",
            "safest": "Sweden U21 Double Chance (1X)",
            "high_risk_reward": "Sweden U21 WIN & BTTS (Yes)"
        },
        "tactical_summary": "Sweden U21 will look to dominate possession using their strong midfield core anchored by Hugo Larsson, while Finland U21 will seek to counter-attack through Siltanen."
    }
}

cur.execute("""
    INSERT INTO predictions (
        fixture_id, match_name, league, kickoff, prediction, expected_score,
        home_prob, draw_prob, away_prob, over_prob, under_prob, btts_yes_prob, btts_no_prob,
        has_lineup, predicted_at, extra_json
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(fixture_id) DO UPDATE SET extra_json=excluded.extra_json
""", (
    "16260283", "Sweden U21 vs Finland U21", "International Friendly", "2026-06-05T16:00:00+00:00",
    "Sweden U21 WIN", "2 - 1", 45.0, 25.0, 30.0, 55.0, 45.0, 60.0, 40.0,
    1, datetime.datetime.now().isoformat(), json.dumps(sweden_pred_extra)
))

# 2. Seed AFC Eskilstuna vs Karlbergs BK Prediction
eskilstuna_pred_extra = {
    "team_impacts": "Home: 1.25 | Away: 1.05",
    "corners": "Home: 5 | Away: 5",
    "fouls": "Home: 12 | Away: 11",
    "cards": "Home Yellows: 3 | Away Yellows: 2",
    "home_players": [{"name": "Love Bjornson", "rating": 6.8}],
    "away_players": [{"name": "Kamil Dudek", "rating": 6.5}],
    "detailed_prediction": {
        "home_prob": 40.0,
        "draw_prob": 28.0,
        "away_prob": 32.0,
        "predicted_score": "1 - 1",
        "confidence": 6,
        "home_xg": 1.4,
        "away_xg": 1.1,
        "over_05": 92,
        "over_15": 75,
        "over_25": 48,
        "over_35": 25,
        "under_25": 52,
        "btts_yes": 55,
        "possession_home": 51,
        "possession_away": 49,
        "fouls_home": 12,
        "fouls_away": 11,
        "offsides_home": 1,
        "offsides_away": 2,
        "saves_home": 3,
        "saves_away": 3,
        "clean_sheet_home": 25,
        "clean_sheet_away": 30,
        "corners_total": 10,
        "corners_home": 5,
        "corners_away": 5,
        "corners_over_75": 80,
        "corners_over_85": 65,
        "corners_over_95": 45,
        "corners_over_105": 25,
        "cards_yellow_home": 3,
        "cards_yellow_away": 2,
        "cards_yellow_total": 5,
        "cards_red_total": 0,
        "goalscorers": [
            {"name": "Love Bjornson", "team": "AFC Eskilstuna", "anytime_goal_prob": 20.0, "first_goal_prob": 8.0, "rating": 6.8},
            {"name": "Kamil Dudek", "team": "Karlbergs BK", "anytime_goal_prob": 18.0, "first_goal_prob": 7.0, "rating": 6.5}
        ],
        "shots_players": [
            {"name": "Love Bjornson", "team": "AFC Eskilstuna", "exp_shots": 2.0, "exp_sot": 0.9, "rating": 6.8}
        ],
        "cards_players": [],
        "value_analysis": {
            "best_result": "DRAW",
            "best_goals": "Under 2.5 Goals",
            "best_cards": "Over 4.5 Cards",
            "best_corners": "Under 10.5 Corners",
            "best_player_prop": "Love Bjornson Over 1.5 Shots",
            "safest": "AFC Eskilstuna Double Chance (1X)",
            "high_risk_reward": "DRAW & BTTS (Yes)"
        },
        "tactical_summary": "Both teams are tightly matched in the midtable. Expect a cautious positional affair with heavy emphasis on defensive structures and transitions."
    }
}

cur.execute("""
    INSERT INTO predictions (
        fixture_id, match_name, league, kickoff, prediction, expected_score,
        home_prob, draw_prob, away_prob, over_prob, under_prob, btts_yes_prob, btts_no_prob,
        has_lineup, predicted_at, extra_json
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(fixture_id) DO UPDATE SET extra_json=excluded.extra_json
""", (
    "15458375", "AFC Eskilstuna vs Karlbergs BK", "Ettan, Norra", "2026-06-05T16:00:00+00:00",
    "DRAW", "1 - 1", 40.0, 28.0, 32.0, 48.0, 52.0, 55.0, 45.0,
    1, datetime.datetime.now().isoformat(), json.dumps(eskilstuna_pred_extra)
))

conn.commit()
conn.close()

# 3. Create completed comparisons JSON file
completed_comparisons = {
    "16260283": {
        "fixture_id": 16260283,
        "match": "Sweden U21 vs Finland U21",
        "league": "International Friendly",
        "status": "FT",
        "score": "1 - 3",
        "home_score": 1,
        "away_score": 3,
        "winner": "Finland U21 WIN",
        "goals": [
            {"player": "Neo Jönsson", "team": "Sweden U21", "minute": 2},
            {"player": "Otso Liimatta", "team": "Finland U21", "minute": 23},
            {"player": "Julius Körkkö", "team": "Finland U21", "minute": 54},
            {"player": "Matias Siltanen", "team": "Finland U21", "minute": 67}
        ],
        "possession_home": 56,
        "possession_away": 44,
        "corners_home": 8,
        "corners_away": 5,
        "corners_total": 13,
        "fouls_home": 10,
        "fouls_away": 12,
        "cards_yellow_home": 2,
        "cards_yellow_away": 3,
        "cards_yellow_total": 5,
        "cards_red_total": 0,
        "shots_home": 12,
        "shots_away": 9,
        "shots_on_target_home": 5,
        "shots_on_target_away": 6,
        "player_stats": [
            {"name": "Neo Jönsson", "team": "Sweden U21", "goals": 1, "shots": 3, "shots_on_target": 2},
            {"name": "Otso Liimatta", "team": "Finland U21", "goals": 1, "shots": 2, "shots_on_target": 1},
            {"name": "Julius Körkkö", "team": "Finland U21", "goals": 1, "shots": 1, "shots_on_target": 1},
            {"name": "Matias Siltanen", "team": "Finland U21", "goals": 1, "shots": 2, "shots_on_target": 2}
        ]
    },
    "15458375": {
        "fixture_id": 15458375,
        "match": "AFC Eskilstuna vs Karlbergs BK",
        "league": "Ettan, Norra",
        "status": "FT",
        "score": "1 - 1",
        "home_score": 1,
        "away_score": 1,
        "winner": "DRAW",
        "goals": [
            {"player": "Love Bjornson", "team": "AFC Eskilstuna", "minute": 14},
            {"player": "Kamil Dudek", "team": "Karlbergs BK", "minute": 62}
        ],
        "possession_home": 49,
        "possession_away": 51,
        "corners_home": 4,
        "corners_away": 6,
        "corners_total": 10,
        "fouls_home": 13,
        "fouls_away": 11,
        "cards_yellow_home": 3,
        "cards_yellow_away": 2,
        "cards_yellow_total": 5,
        "cards_red_total": 0,
        "shots_home": 8,
        "shots_away": 10,
        "shots_on_target_home": 3,
        "shots_on_target_away": 4,
        "player_stats": [
            {"name": "Love Bjornson", "team": "AFC Eskilstuna", "goals": 1, "shots": 2, "shots_on_target": 2},
            {"name": "Kamil Dudek", "team": "Karlbergs BK", "goals": 1, "shots": 3, "shots_on_target": 1}
        ]
    }
}

with open("data/completed_comparisons.json", "w", encoding="utf-8") as f:
    json.dump(completed_comparisons, f, indent=4)

# 4. Inject into todays_dashboard_state.json so they appear in UI state as finished
dashboard_state_path = "data/todays_dashboard_state.json"
if os.path.exists(dashboard_state_path):
    with open(dashboard_state_path, "r", encoding="utf-8") as f:
        dashboard_data = json.load(f)
        
    # Remove duplicates
    dashboard_data = [m for m in dashboard_data if m["fixture_id"] not in [16260283, 15458375]]
    
    # Append U21 match
    dashboard_data.append({
        "fixture_id": 16260283,
        "match": "Sweden U21 vs Finland U21",
        "league": "International Friendly",
        "kickoff": "2026-06-05T16:00:00+00:00",
        "status_code": "FT",
        "has_lineup": True,
        "prediction": {
            "fixture_id": 16260283,
            "match": "Sweden U21 vs Finland U21",
            "league": "International Friendly",
            "kickoff": "2026-06-05T16:00:00+00:00",
            "prediction": "Sweden U21 WIN",
            "expected_score": "2 - 1",
            "has_lineup": True,
            **sweden_pred_extra
        },
        "prematch_markets": None
    })
    
    # Append Eskilstuna match
    dashboard_data.append({
        "fixture_id": 15458375,
        "match": "AFC Eskilstuna vs Karlbergs BK",
        "league": "Ettan, Norra",
        "kickoff": "2026-06-05T16:00:00+00:00",
        "status_code": "FT",
        "has_lineup": True,
        "prediction": {
            "fixture_id": 15458375,
            "match": "AFC Eskilstuna vs Karlbergs BK",
            "league": "Ettan, Norra",
            "kickoff": "2026-06-05T16:00:00+00:00",
            "prediction": "DRAW",
            "expected_score": "1 - 1",
            "has_lineup": True,
            **eskilstuna_pred_extra
        },
        "prematch_markets": None
    })
    
    with open(dashboard_state_path, "w", encoding="utf-8") as f:
        json.dump(dashboard_data, f, indent=4)
        
print("Seed script completed successfully! Predictions seeded and todays_dashboard_state updated.")
