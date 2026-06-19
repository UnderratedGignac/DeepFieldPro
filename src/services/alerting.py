import json
import logging
import os
import urllib.parse
from datetime import datetime

import requests

from src.dfp_config import settings

logger = logging.getLogger(__name__)

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")
_STATE_FILE = os.path.join(_DATA_DIR, "todays_dashboard_state.json")

# Track last sent top-pick key to avoid identical spam each cycle
_last_sent_pick = None


def _read_ntfy_topic() -> str | None:
    """Read NTFY_TOPIC from settings or .env directly (works on daemon threads)."""
    topic = getattr(settings, "NTFY_TOPIC", None) or os.getenv("NTFY_TOPIC")
    if topic:
        return topic.strip()
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
    try:
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                if line.startswith("NTFY_TOPIC="):
                    val = line.split("=", 1)[1].strip()
                    return val if val else None
    except OSError:
        pass
    return None


class NotificationManager:
    """
    Centralized alerting service for DeepFieldPro.
    Primary channel: ntfy.sh (free, no account, native lock-screen push).
    Fallback channel: WhatsApp via CallMeBot (when quota is available).
    """

    def __init__(
        self,
        discord_url: str = settings.DISCORD_WEBHOOK_URL,
        wa_phone: str = settings.WHATSAPP_PHONE,
        wa_key: str = settings.WHATSAPP_API_KEY,
        ntfy_topic: str = None,
    ):
        self.discord_url = discord_url
        if wa_phone and not wa_phone.startswith("+"):
            wa_phone = "+" + wa_phone
        self.wa_phone = wa_phone
        self.wa_key = wa_key
        self.ntfy_topic = ntfy_topic or _read_ntfy_topic()

    # ------------------------------------------------------------------
    # ntfy.sh (primary — free, instant, no quota)
    # ------------------------------------------------------------------
    def _send_ntfy(
        self,
        message: str,
        title: str = "DeepField",
        priority: str = "high",
        tags: str = "soccer",
    ) -> bool:
        """Send a push notification via ntfy.sh to the phone's lock screen."""
        topic = self.ntfy_topic
        if not topic:
            logger.warning("[NTFY] NTFY_TOPIC not configured — skipping push")
            return False
        try:
            url = f"https://ntfy.sh/{topic}"
            headers = {
                "Title": title,
                "Priority": priority,
                "Tags": tags,
                "Content-Type": "text/plain; charset=utf-8",
            }
            resp = requests.post(
                url, data=message.encode("utf-8"), headers=headers, timeout=10
            )
            if resp.status_code in (200, 201, 204):
                logger.info(f"[NTFY] Push sent OK (topic={topic})")
                return True
            logger.error(f"[NTFY] HTTP {resp.status_code}: {resp.text[:200]}")
            return False
        except Exception as e:
            logger.error(f"[NTFY] Failed: {e}")
            return False

    # ------------------------------------------------------------------
    # WhatsApp via CallMeBot (fallback — quota-limited free tier)
    # ------------------------------------------------------------------
    def _send_whatsapp(self, message: str) -> bool:
        """Send via CallMeBot WhatsApp. Returns True on success."""
        if not self.wa_phone or not self.wa_key:
            logger.warning("[WA] WhatsApp not configured")
            return False
        try:
            encoded_msg = urllib.parse.quote(message)
            url = (
                f"https://api.callmebot.com/whatsapp.php"
                f"?phone={self.wa_phone}&text={encoded_msg}&apikey={self.wa_key}"
            )
            resp = requests.get(url, timeout=15)
            body = resp.text or ""
            if resp.status_code != 200:
                logger.error(f"[WA] HTTP {resp.status_code}: {body[:200]}")
                return False
            if "0 messages left" in body or "0</b> messages left" in body:
                logger.warning(
                    f"[WA] Quota exhausted — subscribe at https://callmebot.com/{self.wa_phone.lstrip('+')}"
                )
                return False
            if "Message to:" in body or "Message queued" in body:
                logger.info("[WA] Sent OK")
                return True
            logger.warning(f"[WA] Unexpected response: {body[:200]}")
            return False
        except Exception as e:
            logger.error(f"[WA] Failed: {e}")
            return False

    # ------------------------------------------------------------------
    # Unified send — ntfy first, WhatsApp fallback
    # ------------------------------------------------------------------
    def _notify(
        self,
        message: str,
        title: str = "DeepField",
        priority: str = "high",
        tags: str = "soccer",
    ) -> bool:
        sent = self._send_ntfy(message, title=title, priority=priority, tags=tags)
        if not sent:
            sent = self._send_whatsapp(message)
        return sent

    # ------------------------------------------------------------------
    # Discord
    # ------------------------------------------------------------------
    def _send_discord(self, payload: dict):
        if not self.discord_url:
            return
        try:
            requests.post(self.discord_url, json=payload, timeout=5).raise_for_status()
        except Exception as e:
            logger.error(f"[DISCORD] Failed: {e}")

    # ------------------------------------------------------------------
    # Public alert methods
    # ------------------------------------------------------------------
    def send_critical_error(self, component: str, error_msg: str):
        self._send_discord(
            {
                "embeds": [
                    {
                        "title": "CRITICAL SYSTEM ERROR",
                        "color": 15158332,
                        "fields": [
                            {"name": "Component", "value": component, "inline": True},
                            {
                                "name": "Timestamp",
                                "value": datetime.utcnow().isoformat(),
                                "inline": True,
                            },
                            {
                                "name": "Error Details",
                                "value": f"```\n{error_msg}\n```",
                            },
                        ],
                    }
                ]
            }
        )
        self._notify(
            f"Component: {component}\nError: {error_msg}",
            title="DeepField CRITICAL ERROR",
            priority="urgent",
            tags="warning,rotating_light",
        )

    def send_execution_alert(self, bet_details: dict):
        is_shadow = bet_details.get("status") == "SHADOW"
        title = "SHADOW BET" if is_shadow else "LIVE BET EXECUTED"
        color = 3447003 if is_shadow else 3066993
        self._send_discord(
            {
                "embeds": [
                    {
                        "title": title,
                        "color": color,
                        "fields": [
                            {
                                "name": "Match",
                                "value": bet_details.get("match"),
                                "inline": True,
                            },
                            {
                                "name": "Market",
                                "value": f"{bet_details.get('market')} - {bet_details.get('side')}",
                                "inline": True,
                            },
                            {
                                "name": "Odds",
                                "value": str(bet_details.get("odds")),
                                "inline": True,
                            },
                            {
                                "name": "Stake",
                                "value": f"${bet_details.get('stake'):.2f}",
                                "inline": True,
                            },
                            {
                                "name": "Edge",
                                "value": f"{bet_details.get('edge', 0)*100:.2f}%",
                                "inline": True,
                            },
                        ],
                        "footer": {"text": f"Bet ID: {bet_details.get('bet_id')}"},
                    }
                ]
            }
        )
        msg = (
            f"Match: {bet_details.get('match')}\n"
            f"Pick: {bet_details.get('market')} - {bet_details.get('side')}\n"
            f"Odds: {bet_details.get('odds')}\n"
            f"Stake: ${bet_details.get('stake'):.2f}\n"
            f"Edge: {bet_details.get('edge', 0)*100:.2f}%"
        )
        self._notify(msg, title=f"DeepField {title}", tags="money_with_wings")

    def send_general_alert(self, title: str, message: str):
        self._send_discord(
            {"embeds": [{"title": title, "description": message, "color": 15844367}]}
        )
        self._notify(message, title=title)

    def send_bet_alert(
        self,
        home: str,
        away: str,
        selection: str,
        league: str,
        odds: float,
        prob: float,
        ev: float,
        steam_move: float = 0.0,
        sharp_move: float = 0.0,
        bankroll: float = 10.0,
        kelly_mult: float = 0.25,
        max_exp: float = 0.05,
    ):
        sel_l = selection.lower()
        if sel_l == "draw":
            pick_label = "Draw"
        elif sel_l in (home.lower(), "home"):
            pick_label = f"{home} to win"
        elif sel_l in (away.lower(), "away"):
            pick_label = f"{away} to win"
        elif sel_l == "1x":
            pick_label = f"{home} or Draw"
        elif sel_l == "x2":
            pick_label = f"Draw or {away}"
        elif sel_l == "12":
            pick_label = f"{home} or {away}"
        elif sel_l == "yes":
            pick_label = "BTTS Yes"
        elif sel_l == "no":
            pick_label = "BTTS No"
        elif "over" in sel_l or "under" in sel_l:
            pick_label = selection
        else:
            pick_label = f"{selection} to win"

        p = prob / 100.0
        b = odds - 1.0
        if b > 0 and p > 0:
            kf = max(0.0, (p * odds - 1.0) / b) * kelly_mult
            kf = min(kf, max_exp)
        else:
            kf = 0.01
        stake = round(kf * bankroll, 2)

        signals = []
        if steam_move >= 3.0:
            signals.append(f"Steam +{steam_move:.1f}%")
        if sharp_move >= 3.0:
            signals.append(f"Sharp +{sharp_move:.1f}%")

        msg = (
            f"{home} vs {away}\n"
            f"Pick: {pick_label}\n"
            f"League: {league or 'Unknown'}\n"
            f"Odds: {odds:.2f} | Conf: {prob:.1f}% | EV: +{ev*100:.1f}%\n"
        )
        if signals:
            msg += f"Signals: {', '.join(signals)}\n"
        msg += f"Stake (${bankroll:.0f} bankroll): ${stake:.2f}"
        self._notify(
            msg, title="DeepField Best Bet", tags="chart_with_upwards_trend,soccer"
        )

    def send_hot_picks(self, bankroll: float = 10.0, state_file: str = None) -> bool:
        """
        Read todays_dashboard_state.json, find top 3 picks by EV (1X2, EV > 0, no draws),
        calculate quarter-Kelly stake for the given bankroll, and push one notification.
        Skips if the best pick hasn't changed since last send (avoids spam).
        """
        global _last_sent_pick
        path = state_file or _STATE_FILE
        try:
            with open(path, encoding="utf-8") as f:
                state = json.load(f)
        except Exception as e:
            logger.warning(f"[HOT_PICKS] Could not read state file: {e}")
            return False

        picks = []
        for item in state:
            match = item.get("match", "")
            league = item.get("league", "Unknown")
            status = item.get("status_code", "")
            if status not in ("NS", "TBD", ""):
                continue
            pred = item.get("prediction") or {}
            markets = pred.get("markets") or {}
            for sel in markets.get("1X2") or []:
                ev = sel.get("ev") or sel.get("ev_best") or 0.0
                prob = sel.get("prob", 0.0)
                odds = sel.get("best_odds") or sel.get("odds") or 0.0
                selection = sel.get("selection", "")
                if ev <= 0 or prob <= 0 or odds <= 1.0:
                    continue
                if "draw" in selection.lower() or "(x)" in selection.lower():
                    continue
                p = prob / 100.0
                b = odds - 1.0
                kf = max(0.0, (p * odds - 1.0) / b) if b > 0 else 0.0
                stake = round(min(kf * 0.25 * bankroll, bankroll * 0.25), 2)
                stake = max(stake, 0.25)
                picks.append(
                    {
                        "match": match,
                        "league": league,
                        "selection": selection,
                        "odds": odds,
                        "prob": prob,
                        "ev": ev,
                        "stake": stake,
                    }
                )

        if not picks:
            logger.info("[HOT_PICKS] No qualifying picks — notification skipped")
            return False

        picks.sort(key=lambda x: x["ev"], reverse=True)
        top = picks[:3]

        best_key = f"{top[0]['match']}|{top[0]['selection']}"
        if best_key == _last_sent_pick:
            logger.info("[HOT_PICKS] Top pick unchanged — notification skipped")
            return False
        _last_sent_pick = best_key

        today_str = datetime.now().strftime("%Y-%m-%d")
        lines = [f"Hot Bets - {today_str}\n"]
        total_stake = 0.0
        for i, p in enumerate(top, 1):
            sel = p["selection"]
            if "(1)" in sel or "home" in sel.lower():
                parts = p["match"].split(" vs ")
                label = parts[0].strip() + " to win" if parts else sel
            elif "(2)" in sel or "away" in sel.lower():
                parts = p["match"].split(" vs ")
                label = parts[-1].strip() + " to win" if parts else sel
            else:
                label = sel
            lines.append(
                f"#{i} {p['match']} : {label}\n"
                f"Odds {p['odds']:.2f} | Conf {p['prob']:.0f}% | EV +{p['ev']*100:.1f}%\n"
                f"Stake (${bankroll:.0f}): ${p['stake']:.2f}\n"
            )
            total_stake += p["stake"]
        lines.append(f"Total: ${total_stake:.2f} exposure")

        msg = "\n".join(lines)
        return self._notify(
            msg,
            title="DeepField Hot Bets",
            priority="high",
            tags="chart_with_upwards_trend,soccer",
        )


# Singleton instance
notifier = NotificationManager()
