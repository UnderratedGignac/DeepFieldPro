import sqlite3, os

DB_BETLOG = os.path.join("data", "bet_log.db")

def upgrade_schema():
    conn = sqlite3.connect(DB_BETLOG)
    cursor = conn.cursor()
    
    # 1. Add model_version to bet_log
    try:
        cursor.execute("ALTER TABLE bet_log ADD COLUMN model_version TEXT")
    except sqlite3.OperationalError:
        print("Column 'model_version' already exists in 'bet_log'.")
        
    # 2. Add model_version to predictions
    try:
        cursor.execute("ALTER TABLE predictions ADD COLUMN model_version TEXT")
    except sqlite3.OperationalError:
        print("Column 'model_version' already exists in 'predictions'.")

    # 3. Create calibration_dataset
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS calibration_dataset (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        model_version TEXT,
        market TEXT,
        line REAL,
        predicted_probability REAL,
        actual_outcome INTEGER,
        prediction_timestamp TIMESTAMP,
        outcome_timestamp TIMESTAMP
    );
    """)
    
    conn.commit()
    conn.close()
    print("Schema updated successfully.")

if __name__ == "__main__":
    upgrade_schema()
