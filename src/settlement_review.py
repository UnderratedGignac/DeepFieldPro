"""
settlement_review.py — manual-review queue for bets settlement cannot grade.

The "never assume a result is correct" policy (see settlement_provenance.py) means
settle_open_bets() must REFUSE to grade a bet when no covered results source has
its fixture. The Uruguay-Tercera-Reserves / Australian-NPL coverage-gap class is
exactly this: no ESPN / TheSportsDB / Flashscore / API-Football / Sofascore feed
carries the match, so any W/L would come from a fuzzy name-collision with a
DIFFERENT fixture (the 2026-07-10 "River Plate Reserves graded L off the wrong
match" bug).

Rather than grade wrong, settlement leaves such a bet OPEN and records it HERE.
That gives an operator a single place to see every unsettleable bet and resolve
it from a verified source (e.g. force-settle a real 4-0 home win) — instead of the
system either silently leaving it OPEN forever (fixtures with no predictions
kickoff never hit the time-based VOID pass) or auto-voiding a genuinely-settleable
result (which under-credits a real win).

One row per bet_id. Idempotent: re-queuing an already-queued UNRESOLVED bet just
refreshes its reason/timestamp; a RESOLVED row is left untouched (the operator's
disposition wins — a re-encountered still-unmapped bet does not silently reopen).
"""

import datetime
import sqlite3

REVIEW_TABLE = "settlement_review"

_CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {REVIEW_TABLE} (
    bet_id       TEXT PRIMARY KEY,
    match_id     TEXT,
    market_type  TEXT,
    league       TEXT,
    reason       TEXT,
    queued_at    TEXT,
    resolved     INTEGER DEFAULT 0,
    resolved_at  TEXT,
    resolution   TEXT
)
"""

_COLUMNS = [
    "bet_id",
    "match_id",
    "market_type",
    "league",
    "reason",
    "queued_at",
    "resolved",
    "resolved_at",
    "resolution",
]


def _utcnow_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def ensure_review_queue(db_path):
    """Idempotently create the review-queue table. Safe on every startup."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(_CREATE_SQL)
        conn.commit()
        return True
    finally:
        conn.close()


def has_review_table(db_path):
    """True if the review-queue table exists (for verification/tests)."""
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (REVIEW_TABLE,),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def queue_for_review_on(
    conn,
    bet_id,
    match_id=None,
    market_type=None,
    reason=None,
    league=None,
    when=None,
):
    """queue_for_review using an ALREADY-OPEN connection; does NOT commit.

    This is the variant the settlement sweep must use: the sweep's own
    connection holds the bet_log write lock mid-transaction, so a second
    connection's INSERT would raise 'database is locked' and the queueing
    would be silently lost (2026-07-12 E2E regression). Joining the caller's
    transaction also makes the queue row atomic with the sweep's commit.
    """
    conn.execute(_CREATE_SQL)
    now = when or _utcnow_iso()
    existing = conn.execute(
        f"SELECT resolved FROM {REVIEW_TABLE} WHERE bet_id=?", (bet_id,)
    ).fetchone()
    if existing is None:
        conn.execute(
            f"INSERT INTO {REVIEW_TABLE} "
            "(bet_id, match_id, market_type, league, reason, queued_at, resolved) "
            "VALUES (?,?,?,?,?,?,0)",
            (bet_id, match_id, market_type, league, reason, now),
        )
    elif not existing[0]:
        conn.execute(
            f"UPDATE {REVIEW_TABLE} SET match_id=?, market_type=?, league=?, "
            "reason=?, queued_at=? WHERE bet_id=?",
            (match_id, market_type, league, reason, now, bet_id),
        )
    # resolved row -> leave untouched


def queue_for_review(
    db_path,
    bet_id,
    match_id=None,
    market_type=None,
    reason=None,
    league=None,
    when=None,
):
    """Record a bet needing manual settlement review (idempotent per bet_id).

    - New bet_id: insert a pending (resolved=0) row.
    - Existing UNRESOLVED bet_id: refresh reason/metadata + queued_at.
    - Existing RESOLVED bet_id: no-op (never silently reopen a resolved bet).

    Self-ensures the table so callers need not pre-create it. Opens its own
    connection — from inside the settlement sweep use queue_for_review_on()
    with the sweep's connection instead (lock safety).
    """
    conn = sqlite3.connect(db_path)
    try:
        queue_for_review_on(
            conn,
            bet_id,
            match_id=match_id,
            market_type=market_type,
            reason=reason,
            league=league,
            when=when,
        )
        conn.commit()
    finally:
        conn.close()


def resolve_review(db_path, bet_id, resolution=None, when=None):
    """Mark a queued bet resolved (e.g. after an operator settles or voids it).

    No-op if the bet_id was never queued. Self-ensures the table.
    """
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(_CREATE_SQL)
        conn.execute(
            f"UPDATE {REVIEW_TABLE} SET resolved=1, resolved_at=?, resolution=? "
            "WHERE bet_id=?",
            (when or _utcnow_iso(), resolution, bet_id),
        )
        conn.commit()
    finally:
        conn.close()


def list_review_queue(db_path, include_resolved=False):
    """Return review-queue rows as dicts (pending first, newest queued first).

    By default only UNRESOLVED rows are returned — the operator's live worklist.
    Returns [] if the table does not exist yet.
    """
    conn = sqlite3.connect(db_path)
    try:
        if not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (REVIEW_TABLE,),
        ).fetchone():
            return []
        sql = f"SELECT {', '.join(_COLUMNS)} FROM {REVIEW_TABLE}"
        if not include_resolved:
            sql += " WHERE resolved=0"
        sql += " ORDER BY queued_at DESC"
        return [dict(zip(_COLUMNS, row)) for row in conn.execute(sql)]
    finally:
        conn.close()
