import requests
import logging
import json
import urllib.parse
from datetime import datetime
from src.dfp_config import settings

logger = logging.getLogger(__name__)

class NotificationManager:
    """
    Centralized alerting service for DeepFieldPro.
    Handles critical system errors and execution notifications via Discord and WhatsApp.
    """

    def __init__(self, discord_url: str = settings.DISCORD_WEBHOOK_URL, wa_phone: str = settings.WHATSAPP_PHONE, wa_key: str = settings.WHATSAPP_API_KEY):
        self.discord_url = discord_url
        self.wa_phone = wa_phone
        self.wa_key = wa_key

    def _send_discord(self, payload: dict):
        if not self.discord_url:
            return
        try:
            response = requests.post(self.discord_url, json=payload, timeout=5)
            response.raise_for_status()
        except Exception as e:
            logger.error(f"[ALERTING] Discord failed: {e}")

    def _send_whatsapp(self, message: str):
        if not self.wa_phone or not self.wa_key:
            return
        try:
            encoded_msg = urllib.parse.quote(message)
            url = f"https://api.callmebot.com/whatsapp.php?phone={self.wa_phone}&text={encoded_msg}&apikey={self.wa_key}"
            response = requests.get(url, timeout=10)
            if response.status_code != 200:
                logger.error(f"[ALERTING] WhatsApp failed: {response.text}")
        except Exception as e:
            logger.error(f"[ALERTING] WhatsApp failed: {e}")

    def send_critical_error(self, component: str, error_msg: str):
        """Alert on critical infrastructure failure."""
        # Discord
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
        self._send_discord(payload)
        
        # WhatsApp
        wa_msg = f"*🚨 DeepField CRITICAL ERROR*\n\n*Component:* {component}\n*Error:* {error_msg}\n\n_System Halt Recommended_"
        self._send_whatsapp(wa_msg)

    def send_execution_alert(self, bet_details: dict):
        """Alert when a bet is successfully placed."""
        is_shadow = bet_details.get("status") == "SHADOW"
        title = "💰 SHADOW BET PLACED" if is_shadow else "🔥 LIVE BET EXECUTED"
        color = 3447003 if is_shadow else 3066993

        # Discord
        payload = {
            "embeds": [{
                "title": title,
                "color": color,
                "fields": [
                    {"name": "Match", "value": bet_details.get("match"), "inline": True},
                    {"name": "Market", "value": f"{bet_details.get('market')} - {bet_details.get('side')}", "inline": True},
                    {"name": "Odds", "value": str(bet_details.get("odds")), "inline": True},
                    {"name": "Stake", "value": f"${bet_details.get('stake'):.2f}", "inline": True},
                    {"name": "Edge", "value": f"{bet_details.get('edge', 0)*100:.2f}%", "inline": True}
                ],
                "footer": {"text": f"Bet ID: {bet_details.get('bet_id')}"}
            }]
        }
        self._send_discord(payload)
        
        # WhatsApp
        emoji = "💰" if is_shadow else "🔥"
        status_txt = "SHADOW" if is_shadow else "LIVE"
        wa_msg = (
            f"*{emoji} DeepField {status_txt} BET*\n\n"
            f"*Match:* {bet_details.get('match')}\n"
            f"*Pick:* {bet_details.get('market')} - {bet_details.get('side')}\n"
            f"*Odds:* {bet_details.get('odds')}\n"
            f"*Stake:* ${bet_details.get('stake'):.2f}\n"
            f"*Edge:* {bet_details.get('edge', 0)*100:.2f}%\n\n"
            f"_Targeting High Value Gradient_"
        )
        self._send_whatsapp(wa_msg)

    def send_general_alert(self, title: str, message: str):
        """Generic alert for audits, news, etc."""
        self._send_discord({"embeds": [{"title": title, "description": message, "color": 15844367}]})
        self._send_whatsapp(f"*🔔 {title}*\n\n{message}")

# Singleton instance
notifier = NotificationManager()
