"""
ap2_ledger.py — AP2 audit ledger for DeepFieldPro Arena orders.

Every call to place_order() is logged here — whether blocked by the mandate,
blocked by the DEEPFIELD_ARENA_LIVE gate, or successfully placed.  The ledger
is append-only SQLite so no order attempt is ever silently discarded.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Optional

_DB = Path(__file__).parent.parent / "data" / "arena_ledger.db"

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS arena_orders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts              REAL    NOT NULL,          -- unix timestamp of the attempt
    fixture_id      TEXT,
    team_code       TEXT,
    usd_size        REAL,
    limit_price     REAL,
    model_prob      REAL,
    polymarket_mid  REAL,
    edge            REAL,
    mandate_ok      INTEGER NOT NULL DEFAULT 0,  -- 1=passed, 0=blocked
    mandate_reason  TEXT,
    order_id        TEXT,                        -- filled after successful POST
    status          TEXT NOT NULL DEFAULT 'pending',  -- pending|placed|blocked|failed
    error           TEXT
);
"""

# Index on ts for fast daily-spend queries
_IDX_SQL = "CREATE INDEX IF NOT EXISTS ix_arena_orders_ts ON arena_orders(ts);"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB), check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_ledger() -> None:
    """Create the arena_orders table (idempotent)."""
    with _connect() as conn:
        conn.execute(_CREATE_SQL)
        conn.execute(_IDX_SQL)
        conn.commit()


def log_intent(
    fixture_id: str | None,
    team_code: str | None,
    usd_size: float,
    limit_price: float,
    model_prob: float,
    mid: float,
    edge: float,
    mandate_ok: bool,
    mandate_reason: str,
) -> int:
    """
    Record an order attempt BEFORE the Stair AI POST.

    Returns the new row id so the caller can update it once the POST completes.
    status is set to "pending" when the mandate passed, "blocked" otherwise.
    """
    status = "pending" if mandate_ok else "blocked"
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO arena_orders
                (ts, fixture_id, team_code, usd_size, limit_price,
                 model_prob, polymarket_mid, edge,
                 mandate_ok, mandate_reason, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                time.time(),
                str(fixture_id) if fixture_id is not None else None,
                str(team_code) if team_code is not None else None,
                float(usd_size),
                float(limit_price),
                float(model_prob),
                float(mid),
                float(edge),
                1 if mandate_ok else 0,
                str(mandate_reason),
                status,
            ),
        )
        conn.commit()
        return cur.lastrowid


def log_result(
    row_id: int,
    order_id: Optional[str],
    status: str,
    error: Optional[str] = None,
) -> None:
    """
    Update a previously-inserted row with the POST outcome.

    status should be one of: "placed", "failed", "blocked".
    """
    with _connect() as conn:
        conn.execute(
            """
            UPDATE arena_orders
            SET order_id = ?, status = ?, error = ?
            WHERE id = ?
            """,
            (
                order_id,
                status,
                error,
                row_id,
            ),
        )
        conn.commit()


def get_daily_spent(date_str: Optional[str] = None) -> float:
    """
    Return the sum of usd_size for orders that were successfully placed today (UTC).

    'Today' is the UTC calendar date matching date_str (YYYY-MM-DD), or today if None.
    Only rows with mandate_ok=1 AND status='placed' are counted.
    """
    import time as _t

    if date_str is None:
        date_str = _t.strftime("%Y-%m-%d", _t.gmtime())

    # Convert the date string to epoch range in UTC
    import calendar

    struct = _t.strptime(date_str, "%Y-%m-%d")
    day_start = float(calendar.timegm(struct))  # midnight UTC
    day_end = day_start + 86400.0

    with _connect() as conn:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(usd_size), 0.0) AS total
            FROM arena_orders
            WHERE mandate_ok = 1
              AND status = 'placed'
              AND ts >= ?
              AND ts < ?
            """,
            (day_start, day_end),
        ).fetchone()
    return float(row["total"]) if row else 0.0


def get_recent_orders(limit: int = 20) -> list:
    """Return the most recent `limit` orders as a list of dicts (newest first)."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM arena_orders ORDER BY ts DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]
