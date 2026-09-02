"""
nightly_refresh.py -- Scheduled nightly model refresh (ingest + refit).
======================================================================
Self-contained wrapper intended to be run by a scheduled task (Windows Task
Scheduler / cron) so the Dixon-Coles team ratings never go stale.

Steps:
  1. Determine the current football-data.co.uk season code(s).
  2. Ingest fresh results for those seasons (tools/ingest_history.py).
  3. Refit the Dixon-Coles model on the rolling 730-day window
     (tools/nightly_dc_refit.py).

Each step is best-effort: a partial ingest failure does not abort the refit,
and a failed refit leaves the previous model file untouched (atomic replace).

Run:
    .venv\\Scripts\\python.exe tools\\nightly_refresh.py
"""

import datetime
import subprocess
import sys
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PY = sys.executable


def current_season_codes():
    """Return the football-data.co.uk season codes to ingest.

    European Aug-May leagues: for month >= August the season started this
    calendar year (e.g. Aug 2026 -> '2627'); Jan-Jul belongs to the season
    that started the previous year (e.g. Mar 2027 -> '2627').
    We ingest the current season plus the previous one so the rolling
    730-day refit window always has a full prior season of data.
    """
    today = datetime.date.today()
    yy = today.year % 100
    if today.month >= 8:
        cur = f"{yy:02d}{yy + 1:02d}"
        prev = f"{yy - 1:02d}{yy:02d}"
    else:
        cur = f"{yy - 1:02d}{yy:02d}"
        prev = f"{yy - 2:02d}{yy - 1:02d}"
    return [prev, cur]


def run(args):
    print(f"\n$ {' '.join(args)}")
    proc = subprocess.run(args, cwd=ROOT)
    return proc.returncode


def main():
    print(f"=== nightly_refresh.py @ {datetime.datetime.now():%Y-%m-%d %H:%M:%S} ===")
    seasons = current_season_codes()
    print(f"Season codes to ingest: {seasons}")

    rc_ingest = run([PY, "tools/ingest_history.py", "--seasons", *seasons])
    if rc_ingest != 0:
        print(f"[WARN] ingest_history.py exited {rc_ingest} (continuing to refit)")

    rc_refit = run([PY, "tools/nightly_dc_refit.py"])
    if rc_refit != 0:
        print(f"[ERROR] nightly_dc_refit.py exited {rc_refit}")
        return rc_refit

    print("\n=== nightly_refresh complete ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
