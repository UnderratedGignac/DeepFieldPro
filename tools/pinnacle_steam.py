"""
pinnacle_steam.py — Sharp-money line-movement detector from Pinnacle odds history.

Betarabia STEAM tracks soft-book price moves (noisy).
Pinnacle STEAM tracks ACTUAL SHARP MONEY moves — smaller moves, much higher signal quality.

When Pinnacle moves toward a team pre-kickoff, that is the professional syndicate
signal. This is the gold-standard indicator used by serious quantitative bettors.

Run: .venv/Scripts/python.exe tools/pinnacle_steam.py
"""

import os
import sqlite3
import time

_COMPLETED_DB = os.path.join(
    os.path.dirname(__file__), "..", "data", "deepfield_browser_data", "completed_fixtures.db"
)


def _norm(name: str) -> str:
    return (name or "").lower().strip().replace(".", "").replace("-", " ")


def pinnacle_steam_moves(home: str, away: str, min_snapshots: int = 2, window_hours: float = 6.0) -> dict:
    """
    Detect Pinnacle line movement for a match pre-kickoff.

    Returns dict:
      {
        "home": move_pct_float,   # prob change: positive = market moved TOWARD home
        "draw": move_pct_float,
        "away": move_pct_float,
        "__meta__": {
          "home": {"earliest_prob": float, "latest_prob": float,
                   "snapshot_count": int, "earliest_ts": float, "latest_ts": float},
          ...
        }
      }

    Returns {} if fewer than min_snapshots exist for any selection, or on error.
    """
    if not os.path.exists(_COMPLETED_DB):
        return {}

    h_norm = _norm(home)
    a_norm = _norm(away)

    try:
        con = sqlite3.connect(_COMPLETED_DB, timeout=5)
        now_ts = time.time()
        window_start = now_ts - window_hours * 3600  # snapshots within last window_hours

        # Fetch pre-kickoff snapshots within the live window (most recent N hours).
        # Exclude Bookings/Corners/specials: Pinnacle stores them as "Team (Bookings)"
        # which also matches LIKE '%team%' and has wildly different home/draw/away probs.
        _EXCL = ("%(bookings)%", "%(corners)%", "%(hits)%", "%(fouls)%", "%(shots)%")
        excl_clause = " AND ".join(
            f"LOWER(home_team) NOT LIKE '{p}'" for p in _EXCL
        )

        rows = con.execute(
            f"""
            SELECT selection, devig_prob, ts, starts_ts
            FROM sharp_odds_history
            WHERE (
                LOWER(REPLACE(REPLACE(home_team,'.',''),'-',' ')) LIKE ?
                AND LOWER(REPLACE(REPLACE(away_team,'.',''),'-',' ')) LIKE ?
            )
            AND {excl_clause}
            AND (starts_ts IS NULL OR ts <= starts_ts + 300)
            AND ts >= ?
            ORDER BY selection, ts ASC
            """,
            (f"%{h_norm}%", f"%{a_norm}%", window_start),
        ).fetchall()

        # If not enough recent snapshots, fall back to ALL available pre-kickoff data
        # so historical data is still usable for analysis (not live detection).
        if not rows or max(len([r for r in rows if r[0] == s]) for s in ("home", "away")) < min_snapshots:
            rows = con.execute(
                f"""
                SELECT selection, devig_prob, ts, starts_ts
                FROM sharp_odds_history
                WHERE (
                    LOWER(REPLACE(REPLACE(home_team,'.',''),'-',' ')) LIKE ?
                    AND LOWER(REPLACE(REPLACE(away_team,'.',''),'-',' ')) LIKE ?
                )
                AND {excl_clause}
                AND (starts_ts IS NULL OR ts <= starts_ts + 300)
                ORDER BY selection, ts ASC
                """,
                (f"%{h_norm}%", f"%{a_norm}%"),
            ).fetchall()

        con.close()
    except Exception:
        return {}

    if not rows:
        return {}

    # Group by selection
    by_sel = {}
    for sel, prob, ts, starts_ts in rows:
        by_sel.setdefault(sel, []).append((ts, prob))

    # Need at least min_snapshots for at least one selection
    if not any(len(v) >= min_snapshots for v in by_sel.values()):
        return {}

    result = {}
    meta = {}

    for sel in ("home", "draw", "away"):
        snaps = by_sel.get(sel, [])
        if len(snaps) < 2:
            result[sel] = 0.0
            meta[sel] = {"snapshot_count": len(snaps), "earliest_prob": None, "latest_prob": None,
                         "earliest_ts": None, "latest_ts": None}
            continue

        earliest_ts, earliest_prob = snaps[0]
        latest_ts, latest_prob = snaps[-1]

        move = latest_prob - earliest_prob  # positive = market moved TOWARD this selection
        result[sel] = round(move, 4)
        meta[sel] = {
            "earliest_prob": round(earliest_prob, 4),
            "latest_prob": round(latest_prob, 4),
            "snapshot_count": len(snaps),
            "earliest_ts": earliest_ts,
            "latest_ts": latest_ts,
        }

    result["__meta__"] = meta
    return result


def get_max_pinnacle_move(home: str, away: str, window_hours: float = 6.0):
    """
    Return (selection, move_pct, meta) for the selection with the largest positive move.
    Returns (None, 0.0, {}) if no movement detected.
    """
    moves = pinnacle_steam_moves(home, away, window_hours=window_hours)
    if not moves:
        return None, 0.0, {}

    best_sel, best_move = None, 0.0
    for sel in ("home", "draw", "away"):
        m = moves.get(sel, 0.0)
        if m > best_move:
            best_move = m
            best_sel = sel

    meta = (moves.get("__meta__") or {}).get(best_sel, {}) if best_sel else {}
    return best_sel, round(best_move * 100.0, 2), meta  # return move as percentage points


def check_pinnacle_steam(home: str, away: str, min_move_pct: float = 2.0, window_hours: float = 6.0):
    """
    Check if any selection has Pinnacle line movement >= min_move_pct percentage points.
    Returns (fired: bool, selection: str | None, move_pct: float).
    """
    sel, move_pct, meta = get_max_pinnacle_move(home, away, window_hours=window_hours)
    fired = sel is not None and move_pct >= min_move_pct
    return fired, sel if fired else None, move_pct


# ─── Standalone analysis ──────────────────────────────────────────────────────

if __name__ == "__main__":
    import datetime

    if not os.path.exists(_COMPLETED_DB):
        print("completed_fixtures.db not found")
        exit(1)

    con = sqlite3.connect(_COMPLETED_DB, timeout=5)

    # How many unique matches have >= 2 snapshots?
    matches_with_data = con.execute(
        """
        SELECT match_key, COUNT(*) as n, MIN(ts) as first_ts, MAX(ts) as last_ts, starts_ts
        FROM sharp_odds_history
        WHERE selection = 'home'
        GROUP BY match_key, starts_ts
        HAVING n >= 2
        ORDER BY n DESC
        LIMIT 20
        """
    ).fetchall()

    total_matches_2plus = con.execute(
        """
        SELECT COUNT(DISTINCT match_key) FROM (
          SELECT match_key FROM sharp_odds_history WHERE selection='home'
          GROUP BY match_key HAVING COUNT(*) >= 2
        )
        """
    ).fetchone()[0]
    con.close()

    print(f"\n=== PINNACLE STEAM DETECTOR ===")
    print(f"Matches with >= 2 snapshots: {total_matches_2plus}")
    print(f"\nTop 10 matches by snapshot count:")
    print(f"{'Match':<45} {'Snaps':>5} {'Span':>8} {'Starts'}")
    print("-" * 75)

    for mk, n, first_ts, last_ts, starts_ts in matches_with_data[:10]:
        span_min = round((last_ts - first_ts) / 60, 1) if last_ts and first_ts else 0
        try:
            starts_dt = datetime.datetime.utcfromtimestamp(starts_ts).strftime("%m-%d %H:%M") if starts_ts else "?"
        except Exception:
            starts_dt = "?"
        print(f"{mk:<45} {n:>5} {span_min:>7.1f}m {starts_dt}")

    print(f"\n=== PINNACLE STEAM CHECK (top 5 matches) ===\n")
    for mk, n, first_ts, last_ts, starts_ts in matches_with_data[:5]:
        parts = mk.split(" vs ", 1)
        if len(parts) != 2:
            continue
        h, a = parts[0].strip(), parts[1].strip()
        moves = pinnacle_steam_moves(h, a, min_snapshots=2)
        if not moves:
            print(f"{mk}: no movement data")
            continue
        print(f"\n{mk}:")
        meta = moves.get("__meta__", {})
        for sel in ("home", "draw", "away"):
            m = moves.get(sel, 0.0)
            sm = meta.get(sel, {})
            snaps = sm.get("snapshot_count", 0)
            ep = sm.get("earliest_prob", 0) or 0
            lp = sm.get("latest_prob", 0) or 0
            arrow = "^" if m > 0 else ("v" if m < 0 else "-")
            print(f"  {sel:5}: {ep:.3f} -> {lp:.3f}  move={m*100:+.2f}pp  {arrow}  [{snaps} snaps]")

    print()
    fired, sel, pct = check_pinnacle_steam(
        matches_with_data[0][0].split(" vs ")[0] if matches_with_data else "Test",
        matches_with_data[0][0].split(" vs ")[1] if matches_with_data else "Match",
        min_move_pct=1.0
    )
    print(f"check_pinnacle_steam(min_move=1%): fired={fired}, sel={sel}, move={pct}%")
