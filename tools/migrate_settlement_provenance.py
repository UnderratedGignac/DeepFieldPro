"""One-shot migration: add settlement-provenance columns + the enforcement
trigger to data/bet_log.db. Idempotent — safe to re-run. See
src/settlement_provenance.py for the schema and the "never assume correct" rule.

Run:  .venv\\Scripts\\python.exe tools\\migrate_settlement_provenance.py
"""
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.settlement_provenance import (  # noqa: E402
    PROVENANCE_COLUMNS,
    ensure_settlement_provenance,
    has_trigger,
)

DB = os.path.join(ROOT, "data", "bet_log.db")


def main():
    if not os.path.exists(DB):
        print(f"bet_log.db not found at {DB}")
        return 1
    before = _cols(DB)
    ok = ensure_settlement_provenance(DB)
    after = _cols(DB)
    added = sorted(set(after) - set(before))
    print(f"migration applied={ok}")
    print(f"columns added: {added or '(none — already present)'}")
    print(f"provenance columns present: {[c for c in PROVENANCE_COLUMNS if c in after]}")
    print(f"enforcement trigger installed: {has_trigger(DB)}")
    # Show how many existing settled rows have no recorded provenance (expected —
    # they were settled before this schema existed; the flag honestly reads 0).
    con = sqlite3.connect(DB)
    n_wl = con.execute("SELECT COUNT(*) FROM bet_log WHERE result IN ('W','L')").fetchone()[0]
    n_unverified = con.execute(
        "SELECT COUNT(*) FROM bet_log WHERE result IN ('W','L') AND (result_verified IS NULL OR result_verified!=1)"
    ).fetchone()[0]
    con.close()
    print(f"existing W/L rows: {n_wl}; of those unverified (pre-migration): {n_unverified}")
    return 0


def _cols(db):
    con = sqlite3.connect(db)
    try:
        return [r[1] for r in con.execute("PRAGMA table_info(bet_log)")]
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
