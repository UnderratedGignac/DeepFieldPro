import sqlite3
import numpy as np
import joblib
import os
from sklearn.isotonic import IsotonicRegression

DB_PATH = 'data/bet_log.db'
CALIBRATOR_PATH = 'models/calibrator_player_shots.pkl'

def train_and_save_calibrator():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT predicted_probability, actual_outcome 
        FROM calibration_dataset 
        WHERE market = 'Player Shots'
    """)
    data = cursor.fetchall()
    conn.close()
    
    if len(data) < 100:
        print(f"Insufficient data ({len(data)} samples) to train calibrator.")
        return

    probs = np.array([row[0] for row in data])
    outcomes = np.array([row[1] for row in data])
    
    # Train Isotonic Regression
    # out_of_bounds='clip' ensures probabilities stay in [0, 1]
    iso_reg = IsotonicRegression(out_of_bounds='clip')
    iso_reg.fit(probs, outcomes)
    
    # Save the model
    os.makedirs('models', exist_ok=True)
    joblib.dump(iso_reg, CALIBRATOR_PATH)
    print(f"Calibration model saved to {CALIBRATOR_PATH}")

if __name__ == "__main__":
    train_and_save_calibrator()
