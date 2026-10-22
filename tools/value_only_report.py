"""
value_only_report.py - is VALUE_ONLY really beating Pinnacle's closing price?
==============================================================================
Realized P&L on a few dozen bets is mostly noise; closing-line value against
Pinnacle's FAIR close (bet_log.pinnacle_fair_clv = entry * the fixture's own
last pre-kickoff de-vigged Pinnacle probability - 1) is the leading indicator.
The raw-close pinnacle_clv keeps Pinnacle's margin and flatters every bet. This report reads
only VALUE_ONLY bets, splits them by market and by bookmaker, and gives the
same verdict as tools/edge_status.py: >= 100 bets with CLV, and CLV > 0 at the
95% lower bound, before real money is even worth discussing.

The daemon calls maybe_send_daily_report() every cycle; it pushes the report
to the phone (ntfy) once per UTC day after SEND_HOUR_UTC and saves it under
reports/. READ-ONLY on bet_log.

Run:  .venv\\Scripts\\python.exe tools\\value_only_report.py
"""

import datetime
import json
import os
import sqlite3
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

from tools import edge_status  # noqa: E402  (same verdict rule as the real-money gate)

DB = os.path.join(BASE, "data", "bet_log.db")
STATE = os.path.join(BASE, "data", "value_only_report_state.json")
REPORTS = os.path.join(BASE, "reports")
SOURCE = "VALUE_ONLY"
SEND_HOUR_UTC = 8


def _group(rows):
    settled = [r for r in rows if r["result"] in ("W", "L")]
    staked = sum(r["stake"] or 0 for r in settled)
    pnl = sum(r["pnl"] or 0 for r in settled)
    clvs = [r["pinnacle_fair_clv"] for r in settled if r["pinnacle_fair_clv"] is not None]
    mean, half = edge_status._mean_ci(clvs)
    return {
        "n": len(rows),
        "settled": len(settled),
        "wins": sum(1 for r in settled if r["result"] == "W"),
        "staked": staked,
        "pnl": pnl,
        "roi": (pnl / staked) if staked else 0.0,
        "clv_n": len(clvs),
        "clv_mean": mean,
        "clv_lo": (mean - half) if clvs else 0.0,
        "clv_hi": (mean + half) if clvs else 0.0,
        "beat_close": (sum(1 for v in clvs if v > 0) / len(clvs)) if clvs else 0.0,
    }


def build_report(db_path=DB, source=SOURCE):
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    cols = {r[1] for r in con.execute("PRAGMA table_info(bet_log)")}
    pick = ", ".join(c if c in cols else f"NULL AS {c}" for c in (
        "market_type", "result", "stake", "pnl", "pinnacle_fair_clv", "book", "placed_at"))
    rows = [dict(r) for r in con.execute(f"SELECT {pick} FROM bet_log WHERE bet_source=?", (source,))]
    con.close()

    report = _group(rows)
    report.update(
        source=source,
        placed=len(rows),
        open=sum(1 for r in rows if r["result"] == "OPEN"),
        void=sum(1 for r in rows if r["result"] == "VOID"),
        by_market={m: _group([r for r in rows if r["market_type"] == m])
                   for m in sorted({r["market_type"] for r in rows if r["market_type"]})},
        by_book={b: _group([r for r in rows if (r["book"] or "unknown") == b])
                 for b in sorted({r["book"] or "unknown" for r in rows})},
    )
    report["verdict"], report["verdict_why"] = edge_status._verdict(
        report["clv_n"], report["clv_mean"], report["clv_lo"])
    return report


def _line(name, g):
    clv = f"CLV {g['clv_mean']:+.1%} (n={g['clv_n']})" if g["clv_n"] else "CLV n/a"
    roi = f"ROI {g['roi']:+.1%}" if g["settled"] else "no results yet"
    return f"  {name}: {g['n']} bets, {g['settled']} settled, {roi}, {clv}"


def format_report(r):
    lines = [
        f"{r['source']} daily report - {datetime.date.today().isoformat()}",
        f"Bets: {r['placed']} placed | {r['settled']} settled, {r['open']} open, {r['void']} void",
    ]
    if r["settled"]:
        lines.append(
            f"Result: {r['wins']}W-{r['settled'] - r['wins']}L, staked ${r['staked']:,.2f}, "
            f"P&L ${r['pnl']:+,.2f}, ROI {r['roi']:+.1%}"
        )
    if r["clv_n"]:
        ci = (f"95% CI {r['clv_lo']:+.1%}..{r['clv_hi']:+.1%}" if r["clv_n"] >= 2 else "CI needs 2+ bets")
        lines.append(
            f"Beat Pinnacle's fair close: avg CLV {r['clv_mean']:+.1%} ({ci}), "
            f"beat it on {r['beat_close']:.0%} of {r['clv_n']} bets"
        )
    else:
        lines.append("Beat Pinnacle's fair close: no settled bets with a Pinnacle close yet")
    lines.append("By market:")
    lines += [_line(m, g) for m, g in r["by_market"].items()]
    lines.append("By book:")
    lines += [_line(b, g) for b, g in r["by_book"].items()]
    lines.append(f"Verdict: {r['verdict']} - {r['verdict_why']}")
    return "\n".join(lines)


def _ntfy_send(title, body):
    try:
        from src.services.alerting import NotificationManager

        NotificationManager()._notify(body, title=title, priority="default", tags="bar_chart")
    except Exception as e:
        print(f"[VALUE_ONLY REPORT] ntfy failed: {e}")


def maybe_send_daily_report(now=None, db_path=DB, state_path=STATE, reports_dir=REPORTS, send=_ntfy_send):
    """Push + save the report once per UTC day at or after SEND_HOUR_UTC. Returns True if sent."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    if now.hour < SEND_HOUR_UTC:
        return False
    day = now.strftime("%Y-%m-%d")
    try:
        with open(state_path, encoding="utf-8") as f:
            state = json.load(f)
    except Exception:
        state = {}
    if state.get("sent_date") == day:
        return False

    text = format_report(build_report(db_path))
    os.makedirs(reports_dir, exist_ok=True)
    with open(os.path.join(reports_dir, f"value_only_{day}.txt"), "w", encoding="utf-8") as f:
        f.write(text + "\n")
    send("DeepField - VALUE_ONLY daily report", text)
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump({"sent_date": day}, f)
    print(f"[VALUE_ONLY REPORT] sent for {day}")
    return True


if __name__ == "__main__":
    print(format_report(build_report()))
