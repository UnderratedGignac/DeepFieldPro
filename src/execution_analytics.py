"""
execution_analytics.py — Phase 2 (Execution Quality) instrumentation for the
StairAI Arena real-money betting path (src/arena_betting.py).

Per-trade execution records + a pre-trade liquidity gate, backed by a new,
additive SQLite database (data/execution_log.db). Nothing here calls
place_order() or changes betting decisions on its own — arena_betting.py
consults liquidity_gate_ok() before sizing/placing a trade and calls
log_signal()/update_fill()/update_settlement() to record what happened.

Design intent (per the master risk-management prompt): every trade must be
measurable. Instrumentation ships before/alongside any behavior change, and a
failure in this module must never crash the betting loop or silently block
all trades — see the fail-open contract on liquidity_gate_ok().
"""

import json
import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "execution_log.db")

# Order-book depth bands checked for the liquidity gate and reported in
# execution records — 0.5%/1%/2%/3% above the reference mid price.
LIQUIDITY_BANDS_PCT = (0.005, 0.01, 0.02, 0.03)


def _connect(db_path=None):
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_execution_log(db_path=None):
    """Create the execution_log table if it doesn't exist. Idempotent."""
    conn = _connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS execution_log (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id            TEXT,
            signal_ts           REAL,
            fixture_id          TEXT,
            match               TEXT,
            outcome             TEXT,
            model_prob          REAL,
            fair_prob           REAL,
            market_mid          REAL,
            best_bid            REAL,
            best_ask            REAL,
            spread              REAL,
            order_type          TEXT,
            requested_size      REAL,
            limit_price         REAL,
            filled_size         REAL,
            fill_price          REAL,
            slippage            REAL,
            execution_delay_sec REAL,
            liquidity_depth     TEXT,
            final_settlement    TEXT,
            ev_at_signal        REAL,
            ev_at_fill          REAL,
            kickoff_ts          REAL
        )
        """
    )
    conn.commit()
    conn.close()


def best_bid_ask(book):
    """
    Extract (best_bid, best_ask) floats from a Polymarket CLOB book response
    (as returned by src.arena_betting.get_order_book()). Returns (None, None)
    if the book is missing or malformed — callers must handle that gracefully
    (fail-open), never crash on it.
    """
    if not isinstance(book, dict):
        return None, None
    try:
        bids = book.get("bids") or []
        asks = book.get("asks") or []
        best_bid = max((float(b["price"]) for b in bids), default=None)
        best_ask = min((float(a["price"]) for a in asks), default=None)
        return best_bid, best_ask
    except (TypeError, ValueError, KeyError):
        return None, None


def compute_liquidity_metrics(book, mid):
    """
    USD notional available on the ASK side (what a buy order fills against)
    within each of LIQUIDITY_BANDS_PCT above the reference mid price.

    Returns {"liq_0.5pct": usd, "liq_1pct": usd, "liq_2pct": usd, "liq_3pct": usd}
    — missing/malformed book or non-positive mid returns all zeros (fail-open
    at the metric level; the gate itself decides what to do with zeros).
    """
    labels = {0.005: "liq_0.5pct", 0.01: "liq_1pct", 0.02: "liq_2pct", 0.03: "liq_3pct"}
    out = {labels[p]: 0.0 for p in LIQUIDITY_BANDS_PCT}
    if not isinstance(book, dict) or not mid or mid <= 0:
        return out
    try:
        asks = book.get("asks") or []
        levels = sorted(
            ((float(a["price"]), float(a["size"])) for a in asks),
            key=lambda x: x[0],
        )
    except (TypeError, ValueError, KeyError):
        return out
    for pct in LIQUIDITY_BANDS_PCT:
        ceiling = mid * (1.0 + pct)
        usd = sum(price * size for price, size in levels if price <= ceiling)
        out[labels[pct]] = round(usd, 2)
    return out


def liquidity_gate_ok(book, mid, desired_usd, required_multiple, band_pct=0.01):
    """
    True if the order book supports `desired_usd` notional within `band_pct`
    of mid, with at least `required_multiple`x headroom (e.g.
    required_multiple=3 means the book must show >= 3x the size we want to
    buy, so we're not trying to consume the whole visible book).

    FAIL-OPEN CONTRACT: if the book is missing/malformed/unreachable, this
    returns (True, {...}) — i.e. does NOT block the trade — because a
    liquidity-API hiccup must never silently halt all betting. The metrics
    dict returned always reports what was actually seen (zeros on failure) so
    the caller can log the fail-open decision instead of it being silent.
    """
    metrics = compute_liquidity_metrics(book, mid)
    band_label = {0.005: "liq_0.5pct", 0.01: "liq_1pct", 0.02: "liq_2pct", 0.03: "liq_3pct"}.get(
        band_pct, "liq_1pct"
    )
    available = metrics.get(band_label, 0.0)
    if not isinstance(book, dict) or not book.get("asks"):
        # No book data at all — fail open, but the caller can see
        # available == 0.0 and know this was a data gap, not a real thin book.
        return True, metrics
    required = (desired_usd or 0.0) * (required_multiple or 1.0)
    return available >= required, metrics


def log_signal(record: dict, db_path=None) -> int:
    """
    Insert one execution record at signal/order-placement time. `record`
    should include whichever of the execution_log columns are known now
    (order_id, signal_ts, fixture_id, match, outcome, model_prob, fair_prob,
    market_mid, best_bid, best_ask, spread, order_type, requested_size,
    limit_price, liquidity_depth (dict — will be JSON-encoded), ev_at_signal,
    kickoff_ts). Fill/settlement fields are filled in later via update_fill()/
    update_settlement(). Returns the new row's id.
    """
    init_execution_log(db_path)
    conn = _connect(db_path)
    liquidity_depth = record.get("liquidity_depth")
    if isinstance(liquidity_depth, dict):
        liquidity_depth = json.dumps(liquidity_depth)
    cur = conn.execute(
        """
        INSERT INTO execution_log
            (order_id, signal_ts, fixture_id, match, outcome, model_prob,
             fair_prob, market_mid, best_bid, best_ask, spread, order_type,
             requested_size, limit_price, liquidity_depth, ev_at_signal, kickoff_ts)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            record.get("order_id"),
            record.get("signal_ts"),
            record.get("fixture_id"),
            record.get("match"),
            record.get("outcome"),
            record.get("model_prob"),
            record.get("fair_prob"),
            record.get("market_mid"),
            record.get("best_bid"),
            record.get("best_ask"),
            record.get("spread"),
            record.get("order_type", "limit"),
            record.get("requested_size"),
            record.get("limit_price"),
            liquidity_depth,
            record.get("ev_at_signal"),
            record.get("kickoff_ts"),
        ),
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id


def update_fill(order_id, filled_size, fill_price, fill_observed_at=None, ev_at_fill=None, db_path=None):
    """
    Backfill fill-time fields once an order's status/fill is known (called
    from arena_betting.py's existing order-reconciliation pass).

    `fill_observed_at` is when the caller learned about the fill (defaults to
    now) — NOT necessarily the exact exchange fill timestamp, since the
    StairAI order-status API doesn't expose one; execution_delay_sec is
    therefore computed as `fill_observed_at - signal_ts` (read from the row
    already inserted by log_signal()), an upper-bound proxy on the true fill
    delay, not an exact measurement. Slippage is computed as
    (fill_price - limit_price) / limit_price — positive means we paid MORE
    than our limit implied (adverse), matching the sign convention used
    elsewhere in this project's CLV code.
    """
    init_execution_log(db_path)
    conn = _connect(db_path)
    row = conn.execute(
        "SELECT limit_price, signal_ts FROM execution_log WHERE order_id = ? ORDER BY id DESC LIMIT 1",
        (order_id,),
    ).fetchone()
    slippage = None
    execution_delay_sec = None
    if row:
        if row["limit_price"] and fill_price is not None:
            try:
                slippage = round((float(fill_price) - float(row["limit_price"])) / float(row["limit_price"]), 6)
            except (TypeError, ValueError, ZeroDivisionError):
                slippage = None
        if row["signal_ts"] is not None:
            import time as _time

            observed = fill_observed_at if fill_observed_at is not None else _time.time()
            try:
                execution_delay_sec = round(float(observed) - float(row["signal_ts"]), 3)
            except (TypeError, ValueError):
                execution_delay_sec = None
    conn.execute(
        """
        UPDATE execution_log
        SET filled_size = ?, fill_price = ?, slippage = ?,
            execution_delay_sec = ?, ev_at_fill = ?
        WHERE order_id = ?
        """,
        (filled_size, fill_price, slippage, execution_delay_sec, ev_at_fill, order_id),
    )
    conn.commit()
    conn.close()


def update_settlement(order_id, final_settlement, db_path=None):
    init_execution_log(db_path)
    conn = _connect(db_path)
    conn.execute(
        "UPDATE execution_log SET final_settlement = ? WHERE order_id = ?",
        (final_settlement, order_id),
    )
    conn.commit()
    conn.close()


def slippage_report(db_path=None):
    """
    Slippage summary over all filled orders in the execution log: overall
    average/median/worst, plus breakdowns by liquidity bucket (using the
    liq_1pct band recorded at signal time), by market (fixture_id), and by
    time-to-kickoff bucket at signal time. Returns an empty-but-valid
    structure (not an error) when there are zero filled rows yet — this is
    expected early in the tournament and must not be treated as a failure.
    """
    init_execution_log(db_path)
    conn = _connect(db_path)
    rows = conn.execute(
        "SELECT * FROM execution_log WHERE slippage IS NOT NULL"
    ).fetchall()
    conn.close()

    if not rows:
        return {
            "n": 0,
            "avg_slippage": None,
            "median_slippage": None,
            "worst_slippage": None,
            "by_liquidity_bucket": {},
            "by_market": {},
            "by_time_to_kickoff": {},
        }

    slips = sorted(r["slippage"] for r in rows)
    n = len(slips)
    median = slips[n // 2] if n % 2 else (slips[n // 2 - 1] + slips[n // 2]) / 2.0

    def _bucket_liquidity(row):
        try:
            depth = json.loads(row["liquidity_depth"] or "{}")
            liq = depth.get("liq_1pct", 0.0)
        except (TypeError, ValueError):
            liq = 0.0
        if liq >= 500:
            return "deep (>=$500)"
        if liq >= 100:
            return "medium ($100-500)"
        return "thin (<$100)"

    def _bucket_kickoff(row):
        try:
            hrs = (row["kickoff_ts"] - row["signal_ts"]) / 3600.0
        except (TypeError, ZeroDivisionError):
            return "unknown"
        if hrs < 1:
            return "<1h to kickoff"
        if hrs < 6:
            return "1-6h to kickoff"
        if hrs < 24:
            return "6-24h to kickoff"
        return ">24h to kickoff"

    def _agg(group_key_fn):
        buckets = {}
        for r in rows:
            k = group_key_fn(r)
            buckets.setdefault(k, []).append(r["slippage"])
        return {
            k: {"n": len(v), "avg_slippage": round(sum(v) / len(v), 6)}
            for k, v in buckets.items()
        }

    return {
        "n": n,
        "avg_slippage": round(sum(slips) / n, 6),
        "median_slippage": round(median, 6),
        "worst_slippage": round(max(slips, key=abs), 6),
        "by_liquidity_bucket": _agg(_bucket_liquidity),
        "by_market": _agg(lambda r: r["fixture_id"]),
        "by_time_to_kickoff": _agg(_bucket_kickoff),
    }
