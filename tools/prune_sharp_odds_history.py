"""One-time reclamation of the unbounded sharp_odds_history table.

Background
----------
src/pinnacle_feed.py appended every polled Pinnacle price every POLL_INTERVAL
(45s) with no dedup and no retention. Over 63 days that produced 64,975,226
rows / 16.6 GB inside data/deepfield_browser_data/completed_fixtures.db —
~1.03M rows/day, ~265 MB/day. Every insert had to touch three indexes at random
offsets across a 16 GB file, which is what kept ~1.7 GB of standby cache hot on
a 16 GB machine.

pinnacle_feed now dedups unchanged prices and purges past
SHARP_ODDS_RETENTION_DAYS each cycle, so growth is bounded going forward. This
script reclaims what already accumulated.

It rebuilds rather than deletes: DELETE of ~51M rows would churn three index
B-trees for hours, whereas a filtered CREATE TABLE ... SELECT is one sequential
scan. The old table is dropped, the new one renamed into place, the indexes are
recreated, and VACUUM reclaims the freed pages.

Usage
-----
    .venv\\Scripts\\python.exe tools\\prune_sharp_odds_history.py --dry-run
    .venv\\Scripts\\python.exe tools\\prune_sharp_odds_history.py
    .venv\\Scripts\\python.exe tools\\prune_sharp_odds_history.py --days 7

Stop the daemon first — this drops and recreates a table the feed writes to.
"""

import argparse
import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DEFAULT_RETENTION_DAYS = 14

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "deepfield_browser_data",
    "completed_fixtures.db",
)

# Exactly the schema pinnacle_feed._ensure_table() creates.
_CREATE_TABLE = """CREATE TABLE sharp_odds_history (
            match_key TEXT, home_team TEXT, away_team TEXT, league TEXT,
            selection TEXT, decimal_odds REAL, devig_prob REAL, ts REAL, starts_ts REAL
        )"""

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_soh_ts ON sharp_odds_history(ts)",
    "CREATE INDEX IF NOT EXISTS idx_soh_teams ON sharp_odds_history(home_team, away_team, selection)",
    (
        "CREATE INDEX IF NOT EXISTS idx_soh_norm ON sharp_odds_history("
        "LOWER(REPLACE(REPLACE(home_team,'.',''),'-',' ')),"
        "LOWER(REPLACE(REPLACE(away_team,'.',''),'-',' ')),"
        "selection)"
    ),
]

_COLUMNS = (
    "match_key, home_team, away_team, league, selection, "
    "decimal_odds, devig_prob, ts, starts_ts"
)


def _size(path):
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def _archive_old_rows(con, archive_path, cutoff, verbose=False):
    """Copy the rows about to be dropped into a sidecar DB. Returns rows written.

    Nothing reads the archive, so it costs disk but no RAM or page cache — the
    point of the prune is to shrink the file the daemon has open, not to throw
    the history away.
    """
    os.makedirs(os.path.dirname(os.path.abspath(archive_path)) or ".", exist_ok=True)
    con.execute("ATTACH DATABASE ? AS arch", (archive_path,))
    try:
        con.execute(
            "CREATE TABLE IF NOT EXISTS arch."
            + _CREATE_TABLE.split("CREATE TABLE ", 1)[1]
        )
        if verbose:
            print(f"[PRUNE] archiving pre-cutoff rows -> {archive_path} ...")
        cur = con.execute(
            f"INSERT INTO arch.sharp_odds_history ({_COLUMNS}) "
            f"SELECT {_COLUMNS} FROM main.sharp_odds_history WHERE ts < ?",
            (cutoff,),
        )
        written = cur.rowcount or 0
        con.commit()
        return written
    finally:
        con.execute("DETACH DATABASE arch")


def prune(
    db_path=None,
    days=None,
    dry_run=False,
    vacuum=True,
    verbose=False,
    archive_path=None,
):
    """Drop sharp_odds_history rows older than *days*. Returns a stats dict.

    If *archive_path* is given, the dropped rows are copied there first so the
    prune is reversible.
    """
    db_path = db_path or DB_PATH
    days = DEFAULT_RETENTION_DAYS if days is None else days

    stats = {
        "db": db_path,
        "days": days,
        "rows_before": 0,
        "rows_to_keep": 0,
        "rows_after": 0,
        "rows_removed": 0,
        "rows_archived": 0,
        "archive": archive_path,
        "bytes_before": _size(db_path),
        "bytes_after": 0,
        "vacuumed": False,
        "seconds": 0.0,
    }
    if not os.path.exists(db_path):
        return stats

    t0 = time.time()
    cutoff = time.time() - float(days) * 86400.0

    con = sqlite3.connect(db_path, timeout=120)
    try:
        tables = {
            r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if "sharp_odds_history" not in tables:
            return stats

        stats["rows_before"] = con.execute(
            "SELECT COUNT(*) FROM sharp_odds_history"
        ).fetchone()[0]
        stats["rows_to_keep"] = con.execute(
            "SELECT COUNT(*) FROM sharp_odds_history WHERE ts >= ?", (cutoff,)
        ).fetchone()[0]

        if dry_run:
            stats["rows_after"] = stats["rows_before"]
            stats["rows_removed"] = stats["rows_before"] - stats["rows_to_keep"]
            stats["bytes_after"] = stats["bytes_before"]
            stats["seconds"] = time.time() - t0
            return stats

        if verbose:
            print(
                f"[PRUNE] keeping {stats['rows_to_keep']:,} of "
                f"{stats['rows_before']:,} rows (last {days} days) ..."
            )

        if archive_path:
            stats["rows_archived"] = _archive_old_rows(
                con, archive_path, cutoff, verbose=verbose
            )

        con.execute("DROP TABLE IF EXISTS sharp_odds_history_new")
        con.execute(_CREATE_TABLE.replace("sharp_odds_history", "sharp_odds_history_new"))
        con.execute(
            f"INSERT INTO sharp_odds_history_new ({_COLUMNS}) "
            f"SELECT {_COLUMNS} FROM sharp_odds_history WHERE ts >= ?",
            (cutoff,),
        )
        con.execute("DROP TABLE sharp_odds_history")
        con.execute(
            "ALTER TABLE sharp_odds_history_new RENAME TO sharp_odds_history"
        )
        for ddl in _INDEXES:
            con.execute(ddl)
        con.commit()

        stats["rows_after"] = con.execute(
            "SELECT COUNT(*) FROM sharp_odds_history"
        ).fetchone()[0]
        stats["rows_removed"] = stats["rows_before"] - stats["rows_after"]

        if vacuum:
            if verbose:
                print("[PRUNE] VACUUM (reclaiming freed pages, this takes a while) ...")
            con.isolation_level = None  # VACUUM cannot run inside a transaction
            con.execute("VACUUM")
            stats["vacuumed"] = True
    finally:
        con.close()

    stats["bytes_after"] = _size(db_path)
    stats["seconds"] = time.time() - t0
    return stats


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=DB_PATH)
    ap.add_argument("--days", type=int, default=DEFAULT_RETENTION_DAYS)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-vacuum", action="store_true")
    ap.add_argument(
        "--archive",
        nargs="?",
        const=os.path.join(
            os.path.dirname(DB_PATH), "sharp_odds_history_archive.db"
        ),
        default=None,
        help="copy the dropped rows to this sidecar DB first (default path if bare)",
    )
    a = ap.parse_args()

    s = prune(
        a.db,
        days=a.days,
        dry_run=a.dry_run,
        vacuum=not a.no_vacuum,
        verbose=True,
        archive_path=a.archive,
    )

    gb = 1024 ** 3
    print()
    print(f"  db            : {s['db']}")
    print(f"  retention     : {s['days']} days")
    print(f"  rows before   : {s['rows_before']:,}")
    print(f"  rows after    : {s['rows_after']:,}")
    print(f"  rows removed  : {s['rows_removed']:,}")
    if s["archive"]:
        print(f"  rows archived : {s['rows_archived']:,} -> {s['archive']}")
    print(f"  size before   : {s['bytes_before'] / gb:.2f} GB")
    print(f"  size after    : {s['bytes_after'] / gb:.2f} GB")
    print(f"  reclaimed     : {(s['bytes_before'] - s['bytes_after']) / gb:.2f} GB")
    print(f"  vacuumed      : {s['vacuumed']}")
    print(f"  elapsed       : {s['seconds']:.1f}s")
    if a.dry_run:
        print("\n  (dry run — nothing was changed)")


if __name__ == "__main__":
    main()
