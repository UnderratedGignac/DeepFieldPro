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

    def send_bet_alert(self, home: str, away: str, selection: str, league: str,
                       odds: float, prob: float, ev: float,
                       steam_move: float = 0.0, sharp_move: float = 0.0,
                       bankroll: float = 10.0, kelly_mult: float = 0.25,
                       max_exp: float = 0.05):
        """
        Send a clean, actionable bet recommendation via WhatsApp.
        Formats as: "Team A vs Team B : Team A to win"
        Includes Kelly stake sized for the given bankroll.
        """
        # Human-readable pick label
        sel_l = selection.lower()
        if sel_l == "draw":
            pick_label = "Draw"
        elif sel_l in (home.lower(), "home"):
            pick_label = f"{home} to win"
        elif sel_l in (away.lower(), "away"):
            pick_label = f"{away} to win"
        elif sel_l == "1x":
            pick_label = f"{home} or Draw (1X)"
        elif sel_l == "x2":
            pick_label = f"Draw or {away} (X2)"
        elif sel_l == "12":
            pick_label = f"{home} or {away} (12)"
        elif sel_l == "yes":
            pick_label = "Both Teams To Score - Yes"
        elif sel_l == "no":
            pick_label = "Both Teams To Score - No"
        elif "over" in sel_l or "under" in sel_l:
            pick_label = selection  # e.g. "Over 2.5", "Under 3.0"
        else:
            pick_label = f"{selection} to win"

        # Kelly stake for the provided bankroll
        p = prob / 100.0
        b = odds - 1.0
        if b > 0 and p > 0:
            kf = max(0.0, (p * odds - 1.0) / b) * kelly_mult
            kf = min(kf, max_exp)
        else:
            kf = 0.01
        stake = round(kf * bankroll, 2)
        stake_str = f"${stake:.2f}" if stake >= 0.01 else "<$0.01"

        # Steam / sharp badge
        signals = []
        if steam_move >= 3.0:
            signals.append(f"Steam +{steam_move:.1f}%")
        if sharp_move >= 3.0:
            signals.append(f"Sharp +{sharp_move:.1f}%")
        signal_line = f"\nSignals: {', '.join(signals)}" if signals else ""

        msg = (
            f"*DeepField Best Bet*\n\n"
            f"*{home} vs {away} : {pick_label}*\n\n"
            f"League: {league or 'Unknown'}\n"
            f"Odds: {odds:.2f}\n"
            f"Confidence: {prob:.1f}%\n"
            f"EV: +{ev*100:.1f}%"
            f"{signal_line}\n\n"
            f"*Stake (${bankroll:.0f} bankroll): {stake_str}*\n"
            f"(fractional Kelly x{kelly_mult}, max {max_exp*100:.0f}%)\n\n"
            f"_Research tool — bet responsibly_"
        )
        self._send_whatsapp(msg)

# Singleton instance
notifier = NotificationManager()
