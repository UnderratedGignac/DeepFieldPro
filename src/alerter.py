import os
import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

# Telegram configuration
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN') # Add to .env
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')     # Add to .env

def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"Mock Alert (Telegram config missing): {message}")
        return
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'Markdown'
    }
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
    except Exception as e:
        print(f"Failed to send Telegram alert: {e}")

def alert_pipeline_failure(component: str, error: str):
    msg = f"[PIPELINE FAILURE] Component: {component} | Error: {error}"
    send_telegram_message(msg)

def alert_bet_placed(bet_id, market, stake, edge_pct):
    msg = f"[BET PLACED] Market: {market} | Stake: ${stake:.2f} | Edge: {edge_pct*100:.1f}% | ID: {bet_id}"
    send_telegram_message(msg)

def alert_daily_limit_hit(current_exposure):
    msg = f"[DAILY LIMIT HIT] Exposure: ${current_exposure:.2f}. System halting further bets today."
    send_telegram_message(msg)

def alert_drawdown_triggered(drawdown_pct):
    msg = f"[DRAWDOWN LIMIT] Drawdown: {drawdown_pct*100:.1f}%. System globally halted."
    send_telegram_message(msg)

def alert_role_shift_detected(player_name, old_role, new_role):
    msg = f"[ROLE SHIFT] Player: {player_name} | Shift: {old_role} -> {new_role}. Adjusting model weights."
    send_telegram_message(msg)

if __name__ == "__main__":
    send_telegram_message("Test Alert: Deep Field Pro Alerter Online.")
