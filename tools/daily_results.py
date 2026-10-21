"""
daily_results.py - end-of-day ntfy push: what won, what lost, and the net.
===========================================================================
Covers every paper bet SETTLED since the previous push (bet_log.settle_checked_at,
stamped by settlement), across all strategies, so a late result (Champions
League ~21:00 UTC, Liga MX after midnight) lands in the next push instead of
being missed, and no bet is reported twice. Voids are counted, not won or lost.

The daemon calls maybe_send_daily_results() every cycle; it fires once per UTC
day at or after RESULTS_HOUR_UTC (21:00 UTC = midnight in Lebanon).
READ-ONLY on bet_log. Paper money only.

Run:  .venv\\Scripts\\python.exe tools\\daily_results.py   (last 24h, printed)
"""

import datetime
import json
import os
import sqlite3

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "data", "bet_log.db")
STATE = os.path.join(BASE, "data", "daily_results_state.json")
RESULTS_HOUR_UTC = 21
MAX_LISTED = 12  # per list; ntfy messages are capped at 4 KB


def _parse(ts):
    try:
        d = datetime.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=datetime.timezone.utc)
    except Exception:
        return None


def build_results(db_path=DB, since=None, until=None):
    until = until or datetime.datetime.now(datetime.timezone.utc)
    since = since or until - datetime.timedelta(hours=24)
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    cols = {r[1] for r in con.execute("PRAGMA table_info(bet_log)")}
    pick = ", ".join(c if c in cols else f"NULL AS {c}" for c in (
        "match_id", "market_type", "side", "entry_odds", "stake", "result", "pnl",
        "bet_source", "book", "settle_checked_at"))
    rows = [dict(r) for r in con.execute(
        f"SELECT {pick} FROM bet_log WHERE result IN ('W','L','VOID') AND settle_checked_at >= ?",
        (since.strftime("%Y-%m-%d"),))]
    open_n = con.execute("SELECT COUNT(*) FROM bet_log WHERE result='OPEN'").fetchone()[0]
    con.close()

    done = [r for r in rows if (t := _parse(r["settle_checked_at"])) and since < t <= until]
    won = sorted((r for r in done if r["result"] == "W"), key=lambda r: -(r["pnl"] or 0))
    lost = sorted((r for r in done if r["result"] == "L"), key=lambda r: r["pnl"] or 0)
    by_strategy = {}
    for r in won + lost:
        s = by_strategy.setdefault(r["bet_source"] or "?", {"won": 0, "lost": 0, "net": 0.0})
        s["won" if r["result"] == "W" else "lost"] += 1
        s["net"] += r["pnl"] or 0
    earned = sum(r["pnl"] or 0 for r in won)
    lost_amount = -sum(r["pnl"] or 0 for r in lost)
    staked = sum(r["stake"] or 0 for r in won + lost)
    return {
        "since": since, "until": until, "won": won, "lost": lost,
        "void": sum(1 for r in done if r["result"] == "VOID"), "open": open_n,
        "earned": earned, "lost_amount": lost_amount, "net": earned - lost_amount,
        "staked": staked, "by_strategy": by_strategy,
    }


def _bet_line(mark, r):
    book = f" {r['book']}" if r.get("book") else ""
    return (f"{mark} {r['match_id']} - {r['side']} @{(r['entry_odds'] or 0):.2f}{book} "
            f"{(r['pnl'] or 0):+.2f} ({r['bet_source']})")


def _listing(title, mark, bets):
    out = [f"{title} ({len(bets)}):"]
    out += [_bet_line(mark, r) for r in bets[:MAX_LISTED]]
    if len(bets) > MAX_LISTED:
        out.append(f"  ... +{len(bets) - MAX_LISTED} more")
    return out


def format_results(r):
    n = len(r["won"]) + len(r["lost"])
    lines = [f"Settled since {r['since']:%d %b %H:%M} UTC: {len(r['won'])} won, {len(r['lost'])} lost"]
    if n:
        roi = r["net"] / r["staked"] if r["staked"] else 0.0
        lines.append(
            f"Net {r['net']:+.2f}$ (won +{r['earned']:.2f}$, lost -{r['lost_amount']:.2f}$) "
            f"on {r['staked']:.2f}$ staked, ROI {roi:+.1%}"
        )
        lines += _listing("WON", "✅", r["won"])
        lines += _listing("LOST", "❌", r["lost"])
        lines.append("By strategy: " + " | ".join(
            f"{s} {v['won']}W-{v['lost']}L {v['net']:+.2f}$" for s, v in sorted(r["by_strategy"].items())))
    else:
        lines.append("No bets settled in this window.")
    if r["void"]:
        lines.append(f"Void (stake refunded): {r['void']}")
    lines.append(f"Still open: {r['open']}  |  paper money, no real stakes")
    return "\n".join(lines)


def _ntfy_send(title, body):
    try:
        from src.services.alerting import NotificationManager

        NotificationManager()._notify(body, title=title, priority="default", tags="moneybag")
    except Exception as e:
        print(f"[DAILY RESULTS] ntfy failed: {e}")


def maybe_send_daily_results(now=None, db_path=DB, state_path=STATE, send=_ntfy_send):
    """Push results settled since the last push, once per UTC day after RESULTS_HOUR_UTC."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    if now.hour < RESULTS_HOUR_UTC:
        return False
    day = now.strftime("%Y-%m-%d")
    try:
        with open(state_path, encoding="utf-8") as f:
            state = json.load(f)
    except Exception:
        state = {}
    if state.get("sent_date") == day:
        return False
    since = _parse(state.get("last_until")) or now - datetime.timedelta(hours=24)
    r = build_results(db_path, since=since, until=now)
    send(f"DeepField paper results - {day}: {r['net']:+.2f}$", format_results(r))
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump({"sent_date": day, "last_until": now.isoformat()}, f)
    print(f"[DAILY RESULTS] sent for {day}")
    return True


if __name__ == "__main__":
    print(format_results(build_results()))
