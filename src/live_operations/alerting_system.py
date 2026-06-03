"""
Alerting System — multi-channel alert dispatcher for kill-switch events,
edge collapse, account restrictions, and infrastructure failures.
"""
import os, sys, logging, datetime, json

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE)
logger = logging.getLogger(__name__)

LOG_PATH = os.path.join(BASE, "data", "alerts.json")

SEVERITY = {"INFO": 0, "WARN": 1, "CRITICAL": 2, "KILL_SWITCH": 3}


def fire_alert(title: str, message: str, severity: str = "WARN", source: str = "system"):
    """
    Fire an alert. Logs to file and stdout.
    In production, this hooks into Slack/email/PagerDuty.
    """
    alert = {
        "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
        "severity": severity,
        "source": source,
        "title": title,
        "message": message,
    }

    # Load existing alerts
    alerts = []
    if os.path.exists(LOG_PATH):
        try:
            alerts = json.load(open(LOG_PATH, encoding="utf-8"))
        except Exception:
            alerts = []

    alerts.append(alert)

    # Keep last 500 alerts
    if len(alerts) > 500:
        alerts = alerts[-500:]

    with open(LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(alerts, f, indent=2)

    level = SEVERITY.get(severity, 0)
    if level >= SEVERITY["CRITICAL"]:
        logger.critical(f"[{severity}] {title}: {message}")
    elif level >= SEVERITY["WARN"]:
        logger.warning(f"[{severity}] {title}: {message}")
    else:
        logger.info(f"[{severity}] {title}: {message}")

    return alert


def get_recent_alerts(n=20):
    if not os.path.exists(LOG_PATH):
        return []
    alerts = json.load(open(LOG_PATH, encoding="utf-8"))
    return alerts[-n:]


# Pre-built alert helpers
def alert_kill_switch(reason):
    return fire_alert("KILL SWITCH ACTIVATED", reason, severity="KILL_SWITCH", source="risk_engine")

def alert_edge_collapse(clv_7d):
    return fire_alert("Edge Collapse Detected", f"7-day CLV = {clv_7d:.2%} (below 0%)", severity="CRITICAL", source="clv_tracker")

def alert_drawdown(daily_loss_pct):
    return fire_alert("Drawdown Breach", f"Daily loss = {daily_loss_pct:.1%} (limit: 5%)", severity="CRITICAL", source="risk_engine")

def alert_account_danger(sportsbook, trust_score):
    return fire_alert("Account Danger", f"{sportsbook} trust score = {trust_score:.0f}/100", severity="WARN", source="account_health")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    fire_alert("System Start", "Alerting system initialized", severity="INFO")
    print("Recent alerts:", get_recent_alerts(5))
