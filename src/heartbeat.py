import time
import requests
import psutil
from alerter import alert_pipeline_failure

def ping_api(url, headers=None, name="API"):
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            return True
        else:
            alert_pipeline_failure(f"{name} Check", f"Status Code: {response.status_code}")
            return False
    except Exception as e:
        alert_pipeline_failure(f"{name} Check", str(e))
        return False

def check_process_alive(process_name):
    # This checks if a python script with process_name is running
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['cmdline'] and process_name in ' '.join(proc.info['cmdline']):
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return False

def monitor():
    print("Heartbeat Monitor started...")
    while True:
        # Example API checks (using public endpoint just as an example)
        # In reality, you'd check your own proxy or exact endpoints if possible
        
        # Check if the odds_feed.py process is running
        # if not check_process_alive("odds_feed.py"):
        #     alert_pipeline_failure("Odds Feed Process", "odds_feed.py is not running.")
            
        # Check if lineup_monitor is running when a match is expected
        # if expected_match and not check_process_alive("lineup_monitor.py"):
        #     alert_pipeline_failure("Lineup Monitor Process", "lineup_monitor.py died.")
            
        time.sleep(60) # check every minute

if __name__ == "__main__":
    monitor()
