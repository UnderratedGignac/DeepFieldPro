import time
import schedule
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from src.services.hourly_hot_bets import run_hourly_hot_bets

def main():
    print("Starting Hourly Hot Bets Notifier Daemon...")
    # Run once immediately
    run_hourly_hot_bets()
    
    # Schedule every 1 hour
    schedule.every(1).hours.do(run_hourly_hot_bets)
    
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    main()
