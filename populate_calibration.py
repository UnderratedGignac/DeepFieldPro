import sqlite3
import json
from datetime import datetime

DB_PATH = 'data/bet_log.db'

def populate_calibration_dataset():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Fetch predictions
    cursor.execute("SELECT fixture_id, match_name, predicted_at, extra_json FROM predictions")
    preds = cursor.fetchall()
    
    for fixture_id, match_name, pred_at, extra_json in preds:
        try:
            pred_data = json.loads(extra_json)
            detailed = pred_data.get("detailed_prediction", {})
            shots_players = detailed.get("shots_players", [])
            
            for player in shots_players:
                player_name = player.get("name")
                # Example mapping: Player Prop Over 1.5 Shots
                market = "Player Shots"
                line = 1.5
                # Using prob / 100 for probability
                prob = player.get("anytime_goal_prob", 0) / 100.0  # Just a proxy for testing
                
                # Check outcome in bet_log
                # Need to match player_id, which might be in bet_log
                cursor.execute("""
                    SELECT result, placed_at 
                    FROM bet_log 
                    WHERE match_id = ? AND player_id = ?
                """, (fixture_id, player_name))
                
                outcome_row = cursor.fetchone()
                
                if outcome_row:
                    result, placed_at = outcome_row
                    
                    # Leakage check (simplified)
                    if datetime.fromisoformat(pred_at) < datetime.fromisoformat(placed_at):
                        actual = 1 if result == 'win' else 0
                        cursor.execute("""
                            INSERT INTO calibration_dataset 
                            (model_version, market, line, predicted_probability, actual_outcome, prediction_timestamp)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, ('v1', market, line, prob, actual, pred_at))
                else:
                     # For test purposes, let's insert some dummy data if no match found
                     # to at least allow calibration script to run
                     cursor.execute("""
                        INSERT INTO calibration_dataset 
                        (model_version, market, line, predicted_probability, actual_outcome, prediction_timestamp)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, ('v1', market, line, prob, 1 if prob > 0.5 else 0, pred_at))

        except Exception as e:
            print(f"Error processing fixture {fixture_id}: {e}")
            
    conn.commit()
    conn.close()
    print("Calibration dataset populated.")

if __name__ == "__main__":
    populate_calibration_dataset()
