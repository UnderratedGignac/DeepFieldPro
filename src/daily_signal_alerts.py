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

def _pick_confidence(match: str) -> float | None:
    """Look up the tipster's published confidence for this match, if cached."""
    try:
        from src.tipster_scraper import get_forebet_predictions
        import datetime as _dt
        preds = get_forebet_predictions(_dt.date.today().isoformat()) or []
        for p in preds:
            h = (p.get("home_team") or "").lower()
            a = (p.get("away_team") or "").lower()
            mn = (match or "").lower()
            if h in mn and a in mn:
                return p.get("confidence")
    except Exception:
        pass
    return None


def _claim_alert(conn, bet_id: str) -> bool:
    """Atomically claim the right to alert this bet. INSERT OR IGNORE into a
    PRIMARY KEY table means exactly ONE process ever wins, even if two
    daemons run this concurrently — the twin-daemon race that made the old
    JSON-list dedup double-send (and re-send everything when the state file
    was lost) can't happen against the DB."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS user_alerts (bet_id TEXT PRIMARY KEY, sent_at TEXT)"
    )
    cur = conn.execute(
        "INSERT OR IGNORE INTO user_alerts (bet_id, sent_at) VALUES (?, ?)",
        (bet_id, datetime.datetime.now(datetime.timezone.utc).isoformat()),
    )
    conn.commit()
    return cur.rowcount > 0


def alert_new_picks():
    """
    Check bet_log for new TIPSTER_FOREBET bets placed today that haven't been
    alerted yet. Fire ONE ntfy per pick — ever — with the match, side, odds,
    and a real suggested stake sized from the user's persistent tracked
    balance (src.user_bankroll). The suggestion is auto-deducted from the
    tracked balance so the next pick is sized from what's actually left;
    the user corrects the balance anytime by replying with a number.
    """
    from src import user_bankroll

    today = _today()

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
    except Exception as e:
        print(f"[ALERTS] bet_log read failed: {e}")
        return

    for bid, match, mtype, side, odds, paper_stake, fid in rows:
        try:
            if not _claim_alert(conn, bid):
                continue
        except Exception as e:
            print(f"[ALERTS] dedup claim failed for {bid}: {e}")
            continue

        conf = _pick_confidence(match)
        balance = user_bankroll.get_balance()

        # Suggested real stake from the user's tracked balance
        real_stake = None
        if balance is None or not odds:
            stake_line = "Reply with your balance (just a number) to get stake suggestions"
        elif balance <= 0:
            stake_line = (
                "Balance is $0 — no stake suggested.\n"
                "Reply with your current balance to resume suggestions."
            )
        else:
            real_stake = _real_stake(conf or 55, odds, balance)
            stake_line = (
                f"Suggested stake: ${real_stake:.2f} of your ${balance:.2f}\n"
                f"(balance auto-updates; reply with a number anytime to correct it)"
            )

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
        if real_stake:
            user_bankroll.deduct(real_stake, note=f"suggested stake for {bid}")
        print(f"[ALERTS] Pick alert sent: {match} | {side_label} @ {odds:.2f}")

    conn.close()


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
