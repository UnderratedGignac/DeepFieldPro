"""
redcard_monitor.py — Live WC red card detector.

Research basis (Empirical Economics, Springer, 2017):
  320 WC matches (1998-2014), 84 red cards, Poisson regression.
  Non-sanctioned team goal-scoring rate increases by +124% (exp(0.81)=2.248x)
  after opponent receives a red card.

How it works:
  1. Polls ESPN live scores API every 30s for in-progress WC matches.
  2. Fetches play-by-play events; detects first red card per match.
  3. When a red card fires, computes the updated win probability using the
     +124% goal-rate boost applied to remaining expected goals, and logs an
     informational alert. Purely informational — no market comparison and
     no bet is placed.
  4. Deduplicates per match so each red card only fires one alert.

Alert storage: data/redcard_alerts.json
"""

import os
import json
import time
import math
import threading
import requests
import datetime

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ALERTS_FILE = os.path.join(_ROOT, "data", "redcard_alerts.json")
_ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world"
_UA = {"User-Agent": "Mozilla/5.0 (compatible; DeepFieldPro/1.0)"}

# Red card goal-rate multiplier from peer-reviewed study (exp(0.81))
RED_CARD_GOAL_RATE_MULTIPLIER = 2.248

_alert_lock = threading.Lock()
_fired_keys = set()   # match_id:team to avoid duplicate alerts
_running = False


def _load_alerts():
    try:
        with open(_ALERTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_alert(alert: dict):
    with _alert_lock:
        alerts = _load_alerts()
        alerts.insert(0, alert)
        alerts = alerts[:200]
        with open(_ALERTS_FILE, "w", encoding="utf-8") as f:
            json.dump(alerts, f, indent=2)


def _espn_live_wc():
    """Return list of live/in-progress WC event dicts from ESPN."""
    try:
        r = requests.get(
            f"{_ESPN_BASE}/scoreboard",
            headers=_UA,
            timeout=8,
        )
        r.raise_for_status()
        data = r.json()
        events = data.get("events", [])
        live = []
        for ev in events:
            status = ev.get("status", {})
            stype = status.get("type", {}).get("name", "")
            if stype in ("STATUS_IN_PROGRESS",):
                live.append(ev)
        return live
    except Exception:
        return []


def _espn_events(event_id: str):
    """Return play-by-play events for a match."""
    try:
        r = requests.get(
            f"{_ESPN_BASE}/summary",
            headers=_UA,
            params={"event": event_id},
            timeout=8,
        )
        r.raise_for_status()
        data = r.json()
        plays = []
        for comp in data.get("competitions", []):
            plays.extend(comp.get("details", []))
        return plays
    except Exception:
        return []


def _find_red_cards(plays: list) -> list:
    """Return list of {team_id, team_name, minute} for red card events."""
    cards = []
    for p in plays:
        ptype = p.get("type", {})
        name = (ptype.get("text") or ptype.get("abbreviation") or "").lower()
        if "red" in name or "straight red" in name or "second yellow" in name:
            minute = p.get("clock", {}).get("displayValue", "?")
            # ESPN: athletesInvolved[0] is the carded player
            athletes = p.get("athletesInvolved", [])
            team = p.get("team", {})
            cards.append({
                "team_id": team.get("id"),
                "team_name": team.get("displayName", "?"),
                "team_abbrev": team.get("abbreviation", "?"),
                "minute": minute,
            })
    return cards


def _remaining_xg(current_minute: int, base_lambda: float) -> float:
    """
    Estimate remaining expected goals for a team given match minute.

    Applies a late-game goal clustering adjustment from PMC9846231 (peer-reviewed):
      22.7% of all WC goals (1966-2018, n=1,881 goals, 732 matches) arrive in
      the 76th-to-final-whistle window. Uniform distribution would expect ~15.8%
      for that window → late-game rate is 22.7/15.8 = 1.44x higher.
    """
    total_minutes = 95  # WC average incl. stoppage
    remaining = max(0.0, total_minutes - current_minute)
    fraction = remaining / total_minutes

    # Late-game clustering bonus: goals cluster after 76' at 1.44x the uniform rate
    # Only apply when a meaningful portion of the remaining time is in the 76'+ window
    LATE_MULTIPLIER = 1.44
    LATE_THRESHOLD = 76
    if current_minute < LATE_THRESHOLD:
        # Portion of remaining time that falls in the 76'+ window
        late_minutes = max(0.0, total_minutes - max(current_minute, LATE_THRESHOLD))
        early_minutes = remaining - late_minutes
        # Weighted xG: early portion at normal rate, late portion at 1.44x
        weighted_lambda = base_lambda * (
            (early_minutes + late_minutes * LATE_MULTIPLIER) / total_minutes
        )
        return weighted_lambda
    else:
        # Already in the late window — apply full multiplier to all remaining time
        return base_lambda * fraction * LATE_MULTIPLIER


def _win_prob_from_xg(xg_a: float, xg_b: float, score_a: int, score_b: int) -> tuple:
    """
    Estimate P(A wins), P(draw), P(B wins) using Poisson with current score.
    Computes P over remaining goals only (xg_a, xg_b = expected goals remaining).
    Returns (p_a_win, p_draw, p_b_win).
    """
    max_goals = 6
    p_a_win = p_draw = p_b_win = 0.0

    def poisson_pmf(lam, k):
        if lam <= 0:
            return 1.0 if k == 0 else 0.0
        return math.exp(-lam) * (lam ** k) / math.factorial(k)

    for ga in range(max_goals + 1):
        for gb in range(max_goals + 1):
            p = poisson_pmf(xg_a, ga) * poisson_pmf(xg_b, gb)
            total_a = score_a + ga
            total_b = score_b + gb
            if total_a > total_b:
                p_a_win += p
            elif total_a == total_b:
                p_draw += p
            else:
                p_b_win += p

    return round(p_a_win, 4), round(p_draw, 4), round(p_b_win, 4)


def _push_alert(msg: str):
    """Fire a push notification via the existing alerting service."""
    try:
        from src.services.alerting import notifier
        notifier.send(msg[:500])
    except Exception:
        pass


def _parse_minute(minute_str: str) -> int:
    """Parse '67'' or '67+2'' into an integer minute."""
    try:
        base = minute_str.replace("'", "").split("+")[0].strip()
        return int(base)
    except Exception:
        return 70  # default to 70 if unparseable


def check_live_matches():
    """Single scan pass: check all live WC matches for red cards."""
    live = _espn_live_wc()
    for ev in live:
        event_id = ev.get("id", "")
        comps = ev.get("competitions", [{}])
        comp = comps[0] if comps else {}

        # Get competitors
        competitors = comp.get("competitors", [])
        home = next((c for c in competitors if c.get("homeAway") == "home"), {})
        away = next((c for c in competitors if c.get("homeAway") == "away"), {})
        home_name = home.get("team", {}).get("displayName", "?")
        away_name = away.get("team", {}).get("displayName", "?")
        home_abbrev = home.get("team", {}).get("abbreviation", "HOM")
        away_abbrev = away.get("team", {}).get("abbreviation", "AWY")
        home_score = int(home.get("score", 0) or 0)
        away_score = int(away.get("score", 0) or 0)
        match_name = f"{home_name} vs {away_name}"

        # Current minute
        status = ev.get("status", {})
        clock_str = status.get("displayClock", "0'")
        current_minute = _parse_minute(clock_str)

        # Get play-by-play
        plays = _espn_events(event_id)
        red_cards = _find_red_cards(plays)

        for card in red_cards:
            carded_abbrev = card["team_abbrev"].upper()
            card_minute = _parse_minute(card["minute"])

            # Non-sanctioned team is the OTHER one
            if carded_abbrev == home_abbrev.upper():
                nonsan_abbrev = away_abbrev
                nonsan_name = away_name
                nonsan_score = away_score
                san_score = home_score
                nonsan_side = "away"
            else:
                nonsan_abbrev = home_abbrev
                nonsan_name = home_name
                nonsan_score = home_score
                san_score = away_score
                nonsan_side = "home"

            alert_key = f"{event_id}:{carded_abbrev}"
            if alert_key in _fired_keys:
                continue

            # Compute expected in-play edge
            # Baseline: WC averages ~2.5 goals/match = ~1.25 per team
            base_lambda_per_team = 1.25
            remaining_base = _remaining_xg(card_minute, base_lambda_per_team)

            # Apply +124% boost to non-sanctioned team's remaining xG
            remaining_nonsan = remaining_base * RED_CARD_GOAL_RATE_MULTIPLIER
            remaining_san = remaining_base * 0.75  # slight reduction for 10-man team

            p_nonsan_win, p_draw, p_san_win = _win_prob_from_xg(
                remaining_nonsan, remaining_san, nonsan_score, san_score
            )

            # Informational only — no market comparison, no bet placed.
            alert = {
                "ts": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
                "match": match_name,
                "event_id": event_id,
                "card_minute": card["minute"],
                "current_minute": clock_str,
                "carded_team": card["team_name"],
                "carded_abbrev": carded_abbrev,
                "non_sanctioned_team": nonsan_name,
                "non_sanctioned_abbrev": nonsan_abbrev,
                "score": f"{home_score}-{away_score}",
                "updated_win_prob": p_nonsan_win,
                "red_card_boost": f"+{round((RED_CARD_GOAL_RATE_MULTIPLIER-1)*100)}% goal rate",
            }

            _fired_keys.add(alert_key)
            _save_alert(alert)

            msg = (
                f"RED CARD ALERT: {match_name} {clock_str} — "
                f"{card['team_name']} down to 10 men. "
                f"{nonsan_name} updated win prob {p_nonsan_win:.0%}"
            )
            print(f"[REDCARD] {msg}")
            _push_alert(msg)


def get_recent_alerts(limit: int = 20) -> list:
    """Return recent red card alerts for the API endpoint."""
    return _load_alerts()[:limit]


def start_monitor(interval: int = 30):
    """Start the red card monitor as a background daemon thread."""
    global _running
    if _running:
        return
    _running = True

    def _loop():
        print("[REDCARD] Monitor started — polling ESPN live WC scores every 30s")
        while _running:
            try:
                check_live_matches()
            except Exception as e:
                print(f"[REDCARD] scan error: {e}")
            time.sleep(interval)

    t = threading.Thread(target=_loop, name="redcard-monitor", daemon=True)
    t.start()


def stop_monitor():
    global _running
    _running = False
