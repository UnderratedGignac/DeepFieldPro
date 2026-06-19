"""
nightly_dc_refit.py -- Rolling 2-season Dixon-Coles refit.
==========================================================
Re-trains the Dixon-Coles model on the most recent 730 days of match data
from data/history.db and atomically replaces models/dixon_coles.json.

The daemon loads models/dixon_coles.json at startup; running this nightly
keeps team strength ratings current without interrupting a running server
(os.replace is atomic on POSIX and near-atomic on Windows NTFS).

Run:
    .venv\\Scripts\\python.exe tools\\nightly_dc_refit.py
"""

import datetime
import json
import os
import sqlite3
import sys
import tempfile

# Make sure src/ is importable from this tools/ location
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.models.dixon_coles import fit_league, MODEL_PATH

DB = os.path.join(os.path.dirname(__file__), "..", "data", "history.db")

# Rolling window: last 730 days (~ 2 full seasons)
WINDOW_DAYS = 730


def parse_date(s):
    """Parse dd/mm/YYYY or dd/mm/YY date string. Returns datetime.date or None."""
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def main():
    cutoff = datetime.date.today() - datetime.timedelta(days=WINDOW_DAYS)
    print(f"Nightly Dixon-Coles refit -- using matches from {cutoff} onwards "
          f"(last {WINDOW_DAYS} days)")
    print()

    # -- Load and filter matches ----------------------------------------------
    if not os.path.exists(DB):
        print(f"[ERROR] history.db not found at {DB}")
        print("        Run tools/ingest_history.py first.")
        sys.exit(1)

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    all_rows = [dict(r) for r in con.execute("SELECT * FROM matches")]
    con.close()

    print(f"  Total rows in history.db : {len(all_rows)}")

    filtered = []
    skipped_parse = 0
    skipped_old = 0
    for r in all_rows:
        d = parse_date(r.get("date", ""))
        if d is None:
            skipped_parse += 1
            continue
        if d < cutoff:
            skipped_old += 1
            continue
        filtered.append({
            "home":    r["home"],
            "away":    r["away"],
            "hg":      r["home_goals"],
            "ag":      r["away_goals"],
            "ordinal": d.toordinal(),
            "league":  r["league"],
        })

    print(f"  Matches in window        : {len(filtered)}")
    if skipped_parse:
        print(f"  Skipped (bad date)       : {skipped_parse}")
    print()

    if not filtered:
        print("[ERROR] No matches fall within the rolling window. "
              "Check history.db date format or run ingest first.")
        sys.exit(1)

    # -- Group by league and fit ----------------------------------------------
    by_league: dict[str, list] = {}
    for r in filtered:
        by_league.setdefault(r["league"], []).append(r)

    leagues = {}
    total_matches_used = 0
    for lg, ms in sorted(by_league.items()):
        params = fit_league(ms)
        if not params:
            print(f"  {lg}: skipped (too few matches/teams for reliable fit)")
            continue
        leagues[lg] = params
        total_matches_used += params["n_matches"]
        teams = params["teams"]
        rank = sorted(teams.items(), key=lambda kv: -kv[1]["att"])
        top = ", ".join(t for t, _ in rank[:3])
        bot = ", ".join(t for t, _ in rank[-3:])
        print(f"  {lg}: {params['n_teams']} teams, {params['n_matches']} matches | "
              f"home_adv={params['home_adv']:.3f} rho={params['rho']:+.3f}")
        print(f"       strongest: {top}  |  weakest: {bot}")

    print()
    if not leagues:
        print("[ERROR] No leagues produced a valid model. "
              "The rolling window may be too short for any league.")
        sys.exit(1)

    # -- Atomic write ---------------------------------------------------------
    model_dir = os.path.dirname(MODEL_PATH)
    os.makedirs(model_dir, exist_ok=True)

    payload = {
        "leagues": leagues,
        "trained_at": datetime.date.today().isoformat(),
        "window_days": WINDOW_DAYS,
        "cutoff_date": cutoff.isoformat(),
    }

    # Write to a temp file in the same directory so os.replace is on the same
    # filesystem (required for atomicity on Windows NTFS).
    fd, tmp_path = tempfile.mkstemp(dir=model_dir, suffix=".tmp",
                                    prefix="dixon_coles_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=1)
        os.replace(tmp_path, MODEL_PATH)
    except Exception:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    rel = os.path.relpath(MODEL_PATH, os.path.join(os.path.dirname(__file__), ".."))
    print(f"Refit complete.")
    print(f"  Leagues refit : {len(leagues)}")
    print(f"  Matches used  : {total_matches_used}")
    print(f"  Window        : {cutoff} to {datetime.date.today()} ({WINDOW_DAYS} days)")
    print(f"  Saved         : {rel}")


if __name__ == "__main__":
    main()
