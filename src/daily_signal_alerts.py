"""
daily_signal_alerts.py — Phone alert system for Betarabia signal picks.

Flow:
  1. Morning prompt (08:00 UTC): ntfy asks user for today's Betarabia balance.
  2. User replies with a number → stored in data/daily_betting_state.json.
  3. Every new TIPSTER_FOREBET pick fires a pick alert with real suggested stake
     sized from that balance (quarter-Kelly from tipster's published confidence).
  4. Evening summary (22:30 UTC): P&L of today's settled picks, net result,
     average return, how much was won/lost. Fires once per day.

Called by: live_predictions_daemon.py (tick every daemon cycle).
"""

import datetime
import json
import os
import sqlite3

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_FILE = os.path.join(BASE, "data", "daily_betting_state.json")
BET_LOG = os.path.join(BASE, "data", "bet_log.db")

# ── ntfy helper ──────────────────────────────────────────────────────────────

def _ntfy(title: str, body: str, priority: str = "high", tags: str = "soccer"):
    try:
        from src.services.alerting import NotificationManager
        NotificationManager()._notify(body, title=title, priority=priority, tags=tags)
    except Exception as e:
        print(f"[ALERTS] ntfy failed: {e}")


# ── state helpers ─────────────────────────────────────────────────────────────

def _load_state() -> dict:
    try:
        return json.load(open(STATE_FILE, encoding="utf-8"))
    except Exception:
        return {}


def _save_state(s: dict):
    json.dump(s, open(STATE_FILE, "w", encoding="utf-8"), indent=2)


def _today() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


def get_betarabia_balance() -> float | None:
    s = _load_state()
    if s.get("date") != _today():
        return None
    return s.get("betarabia_balance")


def store_betarabia_balance(amount: float):
    s = _load_state()
    s["date"] = _today()
    s["betarabia_balance"] = round(float(amount), 2)
    s.setdefault("alerted_bet_ids", [])
    s.setdefault("morning_sent", False)
    s.setdefault("summary_sent", False)
    s["morning_sent"] = True
    _save_state(s)
    print(f"[ALERTS] Betarabia balance stored: ${amount:.2f} for {_today()}")


# ── stake sizing ──────────────────────────────────────────────────────────────

def _real_stake(confidence, odds_val, balance: float) -> float:
    """Quarter-Kelly from user's real balance, clamped to [1% balance, 20% balance] and [$2, $200]."""
    try:
        p = float(confidence) / 100.0
        b = float(odds_val) - 1.0
        if not (0.0 < p < 1.0) or b <= 0:
            return round(max(2.0, balance * 0.02), 2)
        kelly_f = (p * float(odds_val) - 1.0) / b
        if kelly_f <= 0:
            return round(max(2.0, balance * 0.01), 2)
        stake = balance * kelly_f * 0.25
        lo = max(2.0, balance * 0.01)
        hi = min(200.0, balance * 0.20)
        return round(max(lo, min(hi, stake)), 2)
    except (TypeError, ValueError):
        return round(max(2.0, balance * 0.02), 2)


# ── morning prompt ────────────────────────────────────────────────────────────

def maybe_send_morning_prompt():
    """Fire once per UTC day at or after 07:30 UTC to ask for today's balance."""
    s = _load_state()
    today = _today()
    now_utc = datetime.datetime.now(datetime.timezone.utc)

    # Already sent today, or too early
    if s.get("date") == today and s.get("morning_sent"):
        return
    if now_utc.hour < 7 or (now_utc.hour == 7 and now_utc.minute < 30):
        return

    _ntfy(
        title="DeepField - Good morning!",
        body=(
            "What is your Betarabia balance today?\n"
            "Reply with just the number (e.g. 150)\n"
            "I'll size every pick from it automatically."
        ),
        priority="high",
        tags="moneybag",
    )
    s["date"] = today
    s["morning_sent"] = True
    s.setdefault("alerted_bet_ids", [])
    s.setdefault("summary_sent", False)
    _save_state(s)
    print(f"[ALERTS] Morning prompt sent for {today}")


# ── per-pick alert ────────────────────────────────────────────────────────────

def alert_new_picks():
    """
    Check bet_log for new TIPSTER_FOREBET bets placed today that haven't been
    alerted yet. Fire one ntfy per pick with the match, side, odds, and the
    real suggested stake from the user's Betarabia balance.
    """
    s = _load_state()
    today = _today()
    balance = s.get("betarabia_balance") if s.get("date") == today else None
    alerted = set(s.get("alerted_bet_ids") or [])

    try:
        conn = sqlite3.connect(BET_LOG)
        rows = conn.execute(
            """SELECT bet_id, match_id, market_type, side, entry_odds, stake, fixture_id
               FROM bet_log
               WHERE bet_source='TIPSTER_FOREBET'
               AND placed_at >= ?
               ORDER BY placed_at ASC""",
            (today + "T00:00:00",),
        ).fetchall()
        conn.close()
    except Exception as e:
        print(f"[ALERTS] bet_log read failed: {e}")
        return

    new_alerts = []
    for bid, match, mtype, side, odds, paper_stake, fid in rows:
        if bid in alerted:
            continue

        # Fetch tipster confidence from the predictions cache if possible
        conf = None
        try:
            from src.tipster_scraper import get_forebet_predictions
            import datetime as _dt
            preds = get_forebet_predictions(_dt.date.today().isoformat()) or []
            for p in preds:
                h = (p.get("home_team") or "").lower()
                a = (p.get("away_team") or "").lower()
                mn = (match or "").lower()
                if h in mn and a in mn:
                    conf = p.get("confidence")
                    break
        except Exception:
            pass

        # Suggested real stake
        if balance and odds:
            real_stake = _real_stake(conf or 55, odds, balance)
            stake_line = f"Suggested stake: ${real_stake:.2f} of your ${balance:.2f}"
        else:
            stake_line = "Reply with your balance to get stake suggestions"

        # Side label
        side_map = {
            "Home (1)": "Home Win",
            "Away (2)": "Away Win",
            "Draw (X)": "Draw",
            "Over 2.5": "Over 2.5 goals",
            "Under 2.5": "Under 2.5 goals",
        }
        side_label = side_map.get(side, side)
        mtype_short = "O/U" if "Over" in mtype else mtype

        conf_str = f" ({conf}% conf)" if conf else ""
        msg = (
            f"{match}\n"
            f"Bet: {side_label} ({mtype_short}){conf_str}\n"
            f"Odds: {odds:.2f}\n"
            f"{stake_line}"
        )

        _ntfy(
            title="DeepField - New Pick",
            body=msg,
            priority="high",
            tags="soccer,moneybag",
        )
        alerted.add(bid)
        new_alerts.append(bid)
        print(f"[ALERTS] Pick alert sent: {match} | {side_label} @ {odds:.2f}")

    if new_alerts:
        s["date"] = today
        s["alerted_bet_ids"] = list(alerted)
        _save_state(s)


# ── evening summary ───────────────────────────────────────────────────────────

def maybe_send_daily_summary():
    """Fire once per day at or after 22:30 UTC with today's settled P&L."""
    s = _load_state()
    today = _today()
    now_utc = datetime.datetime.now(datetime.timezone.utc)

    if s.get("date") == today and s.get("summary_sent"):
        return
    if now_utc.hour < 22 or (now_utc.hour == 22 and now_utc.minute < 30):
        return

    balance = s.get("betarabia_balance") if s.get("date") == today else None

    try:
        conn = sqlite3.connect(BET_LOG)
        rows = conn.execute(
            """SELECT result, stake, pnl, match_id, side FROM bet_log
               WHERE bet_source='TIPSTER_FOREBET'
               AND placed_at >= ?
               AND result IN ('W','L')
               ORDER BY placed_at ASC""",
            (today + "T00:00:00",),
        ).fetchall()
        conn.close()
    except Exception as e:
        print(f"[ALERTS] summary query failed: {e}")
        return

    if not rows:
        # No settled bets today — still send a summary so user knows
        _ntfy(
            title="DeepField - Daily Summary",
            body="No bets settled today.\nAll picks are still open or no matches today.",
            priority="default",
            tags="bar_chart",
        )
        s["date"] = today
        s["summary_sent"] = True
        _save_state(s)
        return

    wins = [(r[1], r[2], r[3], r[4]) for r in rows if r[0] == "W"]
    losses = [(r[1], r[2], r[3], r[4]) for r in rows if r[0] == "L"]
    total_staked = sum(r[1] for r in rows)
    total_pnl = sum(r[2] for r in rows if r[2])
    roi = (total_pnl / total_staked * 100) if total_staked else 0
    avg_ret = (sum((r[2] or 0) / r[1] for r in rows if r[1]) / len(rows) * 100) if rows else 0

    won_str = "\n".join(f"  WIN: {r[3]} ({r[4]})" for r in wins) or "  None"
    lost_str = "\n".join(f"  LOSS: {r[3]} ({r[4]})" for r in losses) or "  None"

    balance_after = f"\nNew balance: ${balance + total_pnl:.2f}" if balance else ""

    body = (
        f"{today} - {len(rows)} settled\n\n"
        f"Won: {len(wins)} | Lost: {len(losses)}\n"
        f"Staked: ${total_staked:.2f}\n"
        f"P&L: {'+'if total_pnl>=0 else ''}${total_pnl:.2f}\n"
        f"ROI today: {roi:+.1f}%\n"
        f"Avg return/bet: {avg_ret:+.1f}%"
        f"{balance_after}\n\n"
        f"WINNERS:\n{won_str}\n\n"
        f"LOSERS:\n{lost_str}"
    )

    _ntfy(
        title=f"DeepField - Daily P&L {'WIN' if total_pnl >= 0 else 'LOSS'}",
        body=body,
        priority="high",
        tags="bar_chart",
    )
    print(f"[ALERTS] Daily summary sent: {len(wins)}W/{len(losses)}L P&L=${total_pnl:.2f}")

    s["date"] = today
    s["summary_sent"] = True
    _save_state(s)
