import sqlite3
import numpy as np
from sklearn.calibration import calibration_curve

DB_PATH = 'data/bet_log.db'

def calculate_ece():
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
        print(f"Not enough data for calibration: {len(data)} samples.")
        return

    probs = np.array([row[0] for row in data])
    outcomes = np.array([row[1] for row in data])
    
    prob_true, prob_pred = calibration_curve(outcomes, probs, n_bins=10)
    
    # ECE Calculation
    ece = np.mean(np.abs(prob_true - prob_pred))
    print(f"Expected Calibration Error (ECE) for Player Shots: {ece:.4f}")

if __name__ == "__main__":
    calculate_ece()
