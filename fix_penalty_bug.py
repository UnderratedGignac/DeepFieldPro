import sqlite3
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "bet_log.db")
JSON_PATH = os.path.join(BASE_DIR, "data", "completed_comparisons.json")
BANKROLL_DB = os.path.join(BASE_DIR, "data", "bankroll.db")

def fix_data():
    match_str = "One Knoxville SC vs Chattanooga Red Wolves SC"
    
    # Fix JSON
    if os.path.exists(JSON_PATH):
        with open(JSON_PATH, "r") as f:
            data = json.load(f)
            
        updated = False
        for k, v in data.items():
            if match_str in v.get("match", ""):
                v["score"] = "1 - 1"
                v["home_score"] = 1
                v["away_score"] = 1
                v["winner"] = "DRAW"
                updated = True
                
        if updated:
            with open(JSON_PATH, "w") as f:
                json.dump(data, f, indent=4)
            print("Updated completed_comparisons.json")

    # Fix bet_log.db
    if os.path.exists(DB_PATH):
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        # We need to find the bet that incorrectly won. 
        # The AI bet 'Home (1)' and won because it saw 6-5. 
        # If the result is a draw, 'Home (1)' is a Loss.
        cur.execute("SELECT bet_id, stake, pnl, result FROM bet_log WHERE match_id LIKE ? AND side = 'Home (1)'", (f"%{match_str}%",))
        bet = cur.fetchone()
        
        if bet:
            bet_id, stake, pnl, result = bet
            if result == 'W':
                new_pnl = -stake
                cur.execute("UPDATE bet_log SET result = 'L', pnl = ? WHERE bet_id = ?", (new_pnl, bet_id))
                print(f"Updated bet_log.db for bet {bet_id}. Changed W -> L, PnL from {pnl} to {new_pnl}")
                
                # Also we need to adjust bankroll
                if os.path.exists(BANKROLL_DB):
                    bconn = sqlite3.connect(BANKROLL_DB)
                    bcur = bconn.cursor()
                    # Just deduct the incorrect profit plus the stake loss
                    # Wait, the bankroll is a running total. It's easier to just insert an adjustment entry or fix the last one
                    # Let's insert a correction
                    adjustment = new_pnl - pnl
                    bcur.execute("SELECT current_balance FROM bankroll ORDER BY date DESC LIMIT 1")
                    row = bcur.fetchone()
                    if row:
                        current_bal = row[0]
                        new_bal = current_bal + adjustment
                        bcur.execute("INSERT INTO bankroll (date, starting_balance, current_balance, peak_balance, daily_exposure, daily_pnl, system_status) VALUES (datetime('now'), ?, ?, ?, 0, 0, 'ACTIVE')", (new_bal, new_bal, new_bal))
                        print(f"Adjusted bankroll by {adjustment}. New balance: {new_bal}")
                    bconn.commit()
                    bconn.close()

        conn.commit()
        conn.close()

if __name__ == "__main__":
    fix_data()
