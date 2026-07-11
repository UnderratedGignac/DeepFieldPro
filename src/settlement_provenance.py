"""
settlement_provenance.py — "never assume a result is correct" enforcement.

Adds per-bet settlement provenance to bet_log and a DB-level trigger that
REFUSES to mark any bet W/L unless a real scraped result was mapped to it.

Why a trigger (2026-07-11): the settlement forensics found bets graded against
the wrong fixture (U23 vs senior) and a real win recorded as a loss. The fix
is a policy — only settle from a verified scrape, otherwise VOID with a reason
— and this trigger makes the policy unbypassable at the storage layer: no code
path, present or future, can write a W/L without provenance.

NOTE ON THE "TRIGGER THE SCRAPER" IDEA: SQLite triggers cannot make network
calls or launch a scraper — no SQL engine can. The scraping itself is done by
the settlement worker (settle_open_bets), which runs every daemon cycle and,
once a match has ended, looks up the result from the multi-source results
scrapers. This trigger is the *enforcement* half: it guarantees the worker
never records an unverified W/L. Together they deliver "when the match ends,
scrape the result; if it can't be mapped, void it with the reason."

Columns added to bet_log (idempotent):
  settle_source     TEXT     which scraped fixture/source produced the W/L
                             (e.g. 'name-match', 'fid-direct', 'deep-lookup');
                             the "map flag" — NULL until a real result maps.
  result_verified   INTEGER  1 iff the W/L came from a real matched scrape.
  settle_reason     TEXT     the matched fixture, or the VOID reason.
  settle_checked_at TEXT     last settlement attempt (observability).
"""

import sqlite3

PROVENANCE_COLUMNS = {
    "settle_source": "TEXT",
    "result_verified": "INTEGER DEFAULT 0",
    "settle_reason": "TEXT",
    "settle_checked_at": "TEXT",
}

TRIGGER_NAME = "trg_no_unverified_settlement"

# BEFORE UPDATE OF result: only fires on an OPEN -> W/L transition (so re-grades
# and CLV backfills on already-settled rows are never blocked). Requires a
# non-empty settle_source AND result_verified=1, else the write is aborted.
TRIGGER_SQL = f"""
CREATE TRIGGER IF NOT EXISTS {TRIGGER_NAME}
BEFORE UPDATE OF result ON bet_log
WHEN OLD.result = 'OPEN'
     AND NEW.result IN ('W', 'L')
     AND (NEW.settle_source IS NULL
          OR NEW.settle_source = ''
          OR NEW.result_verified IS NOT 1)
BEGIN
    SELECT RAISE(ABORT, 'unverified settlement blocked: W/L requires a mapped scraped result (result_verified=1 + settle_source) - void it with a reason instead');
END;
"""


def ensure_settlement_provenance(db_path):
    """Idempotently add the provenance columns + enforcement trigger to a
    bet_log DB. No-op if the bet_log table doesn't exist yet (the caller
    creates it first). Safe to call on every startup and re-run any number
    of times. Never raises on an already-migrated DB."""
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        existing = {r[1] for r in cur.execute("PRAGMA table_info(bet_log)")}
        if not existing:
            return False  # bet_log not created yet
        for col, decl in PROVENANCE_COLUMNS.items():
            if col not in existing:
                cur.execute(f"ALTER TABLE bet_log ADD COLUMN {col} {decl}")
        cur.execute(TRIGGER_SQL)
        conn.commit()
        return True
    finally:
        conn.close()


def has_trigger(db_path):
    """True if the enforcement trigger is installed (for verification/tests)."""
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='trigger' AND name=?",
            (TRIGGER_NAME,),
        ).fetchone()
        return row is not None
    finally:
        conn.close()
