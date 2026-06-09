import requests
import logging
import json
from datetime import datetime
from src.dfp_config import settings

logger = logging.getLogger(__name__)

class NotificationManager:
    """
    Centralized alerting service for DeepFieldPro.
    Handles critical system errors and execution notifications via webhooks.
    """

    def __init__(self, webhook_url: str = settings.DISCORD_WEBHOOK_URL):
        self.webhook_url = webhook_url

    def _send_payload(self, payload: dict):
        if not self.webhook_url:
            logger.warning("[ALERTING] No webhook URL configured. Alert suppressed.")
            return

        try:
            response = requests.post(self.webhook_url, json=payload, timeout=5)
            response.raise_for_status()
        except Exception as e:
            logger.error(f"[ALERTING] Failed to send notification: {e}")

    def send_critical_error(self, component: str, error_msg: str):
        """Alert on critical infrastructure failure (scraper, DB, circuit breaker)."""
        payload = {
            "embeds": [{
                "title": "🚨 CRITICAL SYSTEM ERROR",
                "color": 15158332, # Red
                "fields": [
                    {"name": "Component", "value": component, "inline": True},
                    {"name": "Timestamp", "value": datetime.utcnow().isoformat(), "inline": True},
                    {"name": "Error Details", "value": f"```\n{error_msg}\n```"}
                ]
            }]
        }
        self._send_payload(payload)

    def send_execution_alert(self, bet_details: dict):
        """Alert when a bet (Live or Shadow) is successfully placed."""
        is_shadow = bet_details.get("status") == "SHADOW"
        title = "💰 SHADOW BET PLACED" if is_shadow else "🔥 LIVE BET EXECUTED"
        color = 3447003 if is_shadow else 3066993 # Blue vs Green

        payload = {
            "embeds": [{
                "title": title,
                "color": color,
                "fields": [
                    {"name": "Match", "value": bet_details.get("match"), "inline": True},
                    {"name": "Market", "value": f"{bet_details.get('market')} - {bet_details.get('side')}", "inline": True},
                    {"name": "Odds", "value": str(bet_details.get("odds")), "inline": True},
                    {"name": "Stake", "value": f"${bet_details.get('stake'):.2f}", "inline": True},
                    {"name": "Edge", "value": f"{bet_details.get('edge', 0)*100:.2f}%", "inline": True},
                    {"name": "Status", "value": bet_details.get("status"), "inline": True}
                ],
                "footer": {"text": f"Bet ID: {bet_details.get('bet_id')}"}
            }]
        }
        self._send_payload(payload)

# Singleton instance
notifier = NotificationManager()
