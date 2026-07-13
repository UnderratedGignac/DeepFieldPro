"""audit_bet_timing.py — durable audit: was each bet placed before kickoff?

Answers the question a retroactive investigation (2026-07-13) found impossible
to verify reliably from odds_stream.db alone (it only retains ~3 days of
fixture data, and there's no durable link from an old bet back to its
fixture's kickoff time). bet_log now captures kickoff_time at placement
(tools/migrate_bet_log.py + place_tipster_bets/log_ai_bet/log_steam_bet), so
this becomes a plain SQL comparison instead of forensic archaeology — but
only for bets placed after that column existed. Older bets are reported as
unauditable, never silently assumed clean.

Read-only. Safe to run any time.

Usage:
    .venv\\Scripts\\python.exe tools\\audit_bet_timing.py
"""

import datetime
import os
import sqlite3

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "data", "bet_log.db")


def _parse(ts):
    if not ts:
        return None
    try:
        s = ts.replace("Z", "+00:00")
        dt = datetime.datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def audit_timing(bet_db=DB):
    """Classify every bet_log row by placement-vs-kickoff timing.

    Returns:
        checked: bets with a real, parseable kickoff_time confirmed pre-placement
        missing_kickoff: bets with no kickoff_time recorded (legacy/unauditable)
        unparseable: bets where placed_at or kickoff_time couldn't be parsed
        unknown_time_placeholder: bets whose kickoff_time is a same-day
            00:00:00 date-only placeholder (Kickertech/Betarabia convention,
            same as _fixture_has_started()) -- the real kickoff time is
            unrecorded, so timing can't be proven either way
        violations: list of {bet_id, match_id, bet_source, placed_at,
            kickoff_time, minutes_late} for bets confirmed placed at/after kickoff
    """
    conn = sqlite3.connect(bet_db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT bet_id, match_id, bet_source, placed_at, kickoff_time, result FROM bet_log"
    ).fetchall()
    conn.close()

    checked = 0
    missing_kickoff = 0
    unparseable = 0
    unknown_time_placeholder = 0
    violations = []

    for r in rows:
        if not r["kickoff_time"]:
            missing_kickoff += 1
            continue
        placed = _parse(r["placed_at"])
        kickoff = _parse(r["kickoff_time"])
        if placed is None or kickoff is None:
            unparseable += 1
            continue

        is_midnight_placeholder = (
            kickoff.hour == 0 and kickoff.minute == 0 and kickoff.second == 0
        )
        if is_midnight_placeholder and kickoff.date() >= placed.date():
            # Same-day-or-future placeholder: the real kickoff time is simply
            # unrecorded -- neither clean nor a violation, just unverifiable.
            unknown_time_placeholder += 1
            continue

        checked += 1
        delta_min = (placed - kickoff).total_seconds() / 60.0
        if delta_min >= 0:
            violations.append({
                "bet_id": r["bet_id"],
                "match_id": r["match_id"],
                "bet_source": r["bet_source"],
                "placed_at": r["placed_at"],
                "kickoff_time": r["kickoff_time"],
                "minutes_late": round(delta_min, 1),
            })

    return {
        "checked": checked,
        "missing_kickoff": missing_kickoff,
        "unparseable": unparseable,
        "unknown_time_placeholder": unknown_time_placeholder,
        "violations": violations,
    }


def main():
    result = audit_timing()
    total = (
        result["checked"] + result["missing_kickoff"] + result["unparseable"]
        + result["unknown_time_placeholder"]
    )
    print(f"=== Bet placement-timing audit ({total} total bets) ===")
    print(f"Confirmed pre-kickoff or flagged (real kickoff time known): {result['checked']}")
    print(f"Unauditable — no kickoff_time recorded (legacy, pre-2026-07-13): {result['missing_kickoff']}")
    print(f"Unknown exact time — date-only placeholder, same day: {result['unknown_time_placeholder']}")
    print(f"Unparseable timestamps: {result['unparseable']}")
    print()
    if result["violations"]:
        print(f"!!! {len(result['violations'])} bets placed AT OR AFTER kickoff !!!")
        for v in result["violations"]:
            print(
                f"  {v['bet_id']:24s} {v['match_id'][:35]:35s} src={v['bet_source']:16s} "
                f"{v['minutes_late']:+.1f} min after kickoff"
            )
    else:
        print("No post-kickoff placements found among auditable bets.")
    if result["missing_kickoff"] > 0:
        print()
        print(
            f"NOTE: {result['missing_kickoff']} bets predate kickoff_time capture and "
            "cannot be verified either way — this is a real coverage gap, not a clean bill."
        )


if __name__ == "__main__":
    main()
