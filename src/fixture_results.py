"""fixture_results.py — durable fixture_id -> final score store.

Why this exists
---------------
settle_open_bets() built its direct-lookup index (_fid_to_score) from one
volatile file: data/todays_dashboard_state.json, rewritten every cycle with
only TODAY's fixtures. Settlement looks back up to 7 days, so the index had
already forgotten the fixture by the time most bets settled. Measured
fid-direct rate by settle lag:

    same day  14.9%   +1 day  5.7%   +2 days  0.0%   +3 days  0.0%

Only 11.8% of verified settles were graded by fixture id. Everything else fell
through to fuzzy team-name matching — the path the 2026-07-12 audit found wrong
on ~29% of externally-checkable grades, and the path the 2026-08-24 analysis
showed carries essentially all of the book's apparent profit (fid-direct is
-19.6% ROI across every strategy; name-match +1.7%; deep-lookup +43.9%).

Namespacing
-----------
fixture_id is not one id space. Across the verified record:

    Sofascore (14-17M)        2451 bets
    Betarabia/Kickertech      522
    synthetic md5 (8-digit)   370
    non-numeric               95
    ESPN (4xxxxxxxx) / other  44

Joining across those namespaces would silently grade a bet off an unrelated
fixture, so rows are keyed by (namespace, fixture_id). load_flat_scores()
provides a bare-id view for legacy bets that predate namespace stamping, and
deliberately omits any id that means different results in two namespaces.

Never raises: settlement must degrade to name-matching, not crash.
"""

import os
import sqlite3
import time

# Known id namespaces. A synthetic id is an md5 of "Home vs Away" minted when a
# source gave us no usable id — stable within that source, meaningless across.
NS_SOFASCORE = "sofascore"
NS_ESPN = "espn"
NS_BETARABIA = "betarabia"
NS_UNKNOWN = "unknown"  # legacy rows / dashboard state with no stamped ns


def synthetic_ns(base):
    """Namespace for a hash-derived id, e.g. synthetic_ns('sofascore')."""
    return f"synthetic:{base}"


FIXTURE_RESULTS_RETENTION_DAYS = 30

# Status values that mean "this is the final score and may grade a bet".
_FINAL_STATUSES = {"ft", "finished", "aet", "pen", "after extra time", "ended"}


def _connect(db_path, readonly=False):
    if readonly and not os.path.exists(db_path):
        return None
    if not readonly and not os.path.isdir(os.path.dirname(os.path.abspath(db_path))):
        return None
    return sqlite3.connect(db_path, timeout=15)


def ensure_fixture_results(db_path):
    """Create the table + index if absent. Idempotent, never raises."""
    try:
        conn = _connect(db_path)
        if conn is None:
            return False
        try:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS fixture_results (
                       namespace  TEXT NOT NULL,
                       fixture_id TEXT NOT NULL,
                       home_score INTEGER NOT NULL,
                       away_score INTEGER NOT NULL,
                       status     TEXT,
                       seen_at    REAL NOT NULL,
                       PRIMARY KEY (namespace, fixture_id)
                   )"""
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_fixres_seen ON fixture_results(seen_at)"
            )
            conn.commit()
            return True
        finally:
            conn.close()
    except Exception:
        return False


def _is_final(status):
    if status is None:
        return True  # caller vouched for it by passing a score with no status
    return str(status).strip().lower() in _FINAL_STATUSES


def record_results(db_path, rows, seen_at=None):
    """Upsert (namespace, fixture_id, home_score, away_score, status) rows.

    Skips rows without an id, without both scores, or whose status is not final.
    A later write for the same key wins, so a corrected score replaces a bad one.
    Returns the number of rows written. Never raises.
    """
    if not rows:
        return 0
    ts = time.time() if seen_at is None else float(seen_at)
    clean = []
    for row in rows:
        try:
            ns, fid, hs, aws, status = row
        except (TypeError, ValueError):
            continue
        if fid is None or hs is None or aws is None:
            continue
        if not _is_final(status):
            continue
        try:
            clean.append((str(ns), str(fid), int(hs), int(aws), status, ts))
        except (TypeError, ValueError):
            continue
    if not clean:
        return 0
    try:
        conn = _connect(db_path)
        if conn is None:
            return 0
        try:
            ensure_fixture_results(db_path)
            conn.executemany(
                "INSERT INTO fixture_results "
                "(namespace, fixture_id, home_score, away_score, status, seen_at) "
                "VALUES (?,?,?,?,?,?) "
                "ON CONFLICT(namespace, fixture_id) DO UPDATE SET "
                "home_score=excluded.home_score, away_score=excluded.away_score, "
                "status=excluded.status, seen_at=excluded.seen_at",
                clean,
            )
            conn.commit()
            return len(clean)
        finally:
            conn.close()
    except Exception:
        return 0


def load_scores(db_path, days=FIXTURE_RESULTS_RETENTION_DAYS):
    """{(namespace, fixture_id): (home_score, away_score)} within *days*.

    days=None returns every row. Never raises; returns {} on any failure.
    """
    try:
        conn = _connect(db_path, readonly=True)
        if conn is None:
            return {}
        try:
            if days is None:
                q = "SELECT namespace, fixture_id, home_score, away_score FROM fixture_results"
                args = ()
            else:
                q = (
                    "SELECT namespace, fixture_id, home_score, away_score "
                    "FROM fixture_results WHERE seen_at >= ?"
                )
                args = (time.time() - float(days) * 86400.0,)
            return {(r[0], r[1]): (r[2], r[3]) for r in conn.execute(q, args)}
        finally:
            conn.close()
    except Exception:
        return {}


def load_flat_scores(db_path, days=FIXTURE_RESULTS_RETENTION_DAYS):
    """{fixture_id: (home, away)} for bets that carry no namespace.

    An id that resolves to DIFFERENT results in two namespaces is ambiguous and
    is omitted — grading off it could pick an unrelated fixture, which is the
    exact class of bug (River Plate Reserves, 2026-07-10) this store exists to
    prevent. Ids that agree across namespaces are kept.
    """
    flat = {}
    ambiguous = set()
    for (_ns, fid), score in load_scores(db_path, days=days).items():
        if fid in ambiguous:
            continue
        prev = flat.get(fid)
        if prev is not None and prev != score:
            del flat[fid]
            ambiguous.add(fid)
            continue
        flat[fid] = score
    return flat


def purge_fixture_results(db_path, days=FIXTURE_RESULTS_RETENTION_DAYS):
    """Drop rows older than *days*. Returns rows removed. Never raises."""
    try:
        conn = _connect(db_path, readonly=True)
        if conn is None:
            return 0
        conn.close()
        conn = _connect(db_path)
        if conn is None:
            return 0
        try:
            cur = conn.execute(
                "DELETE FROM fixture_results WHERE seen_at < ?",
                (time.time() - float(days) * 86400.0,),
            )
            removed = cur.rowcount or 0
            conn.commit()
            return removed
        finally:
            conn.close()
    except Exception:
        return 0


# ─── Harvesters ──────────────────────────────────────────────────────────────
# Turn the daemon's existing in-memory result sources into fixture_results rows.
# Kept here (not in the daemon) so they are unit-testable without running a cycle.


def rows_from_dashboard_state(dash_state):
    """todays_dashboard_state.json entries -> fixture_results rows.

    Each entry carries fixture_id plus fixture.status.short / home_score /
    away_score. The namespace comes from a stamped "fixture_ns" when present
    (bets placed after namespace stamping) and falls back to NS_UNKNOWN, which
    still lets load_flat_scores() serve legacy bare-id bets.
    """
    out = []
    for m in dash_state or []:
        if not isinstance(m, dict):
            continue
        fix = m.get("fixture") or {}
        status = (fix.get("status") or {}).get("short")
        out.append(
            (
                m.get("fixture_ns") or NS_UNKNOWN,
                m.get("fixture_id"),
                fix.get("home_score"),
                fix.get("away_score"),
                status,
            )
        )
    return out


def rows_from_sofascore_events(events_by_date):
    """sofascore_results_scraper.get_events() output -> fixture_results rows.

    This is the source that actually fixes the coverage cliff: it is fetched
    per-date across the whole settlement lookback, not just for today, and its
    ids are native Sofascore ids — the same namespace as ~70% of our bets.
    """
    out = []
    if isinstance(events_by_date, dict):
        buckets = events_by_date.values()
    else:
        buckets = [events_by_date or []]
    for evs in buckets:
        for e in evs or []:
            if not isinstance(e, dict):
                continue
            hs = (e.get("homeScore") or {}).get("current")
            aws = (e.get("awayScore") or {}).get("current")
            out.append(
                (
                    NS_SOFASCORE,
                    e.get("id"),
                    hs,
                    aws,
                    (e.get("status") or {}).get("type"),
                )
            )
    return out
