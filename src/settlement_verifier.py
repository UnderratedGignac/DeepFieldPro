"""Cross-check name-matched settlements against the namespaced fixture result.

WHY THIS EXISTS
---------------
Almost every bet is graded by fuzzy NAME matching rather than by fixture id,
and not because the id is missing. The namespaced result simply arrives after
the bet has already been closed:

    match ends              ~17:20Z
    fast feeds publish      ~17:2xZ   (Flashscore / ESPN / API-Football)
    settlement grades it     17:27Z   -> fid index empty -> name-match wins
    Sofascore fid row lands  18:11Z   -> 44 minutes too late

The fast feeds carry no Sofascore ids, so they can only ever grade by name,
while the one namespaced source rides a 30-minute cache. fid-direct therefore
never gets to grade a promptly-finishing match. The two paths end up covering
different league populations (205 name-match leagues vs 69 fid-direct), which
is why the recorded -19.6% / +45% ROI split between them cannot be read as
grading quality alone — they are not grading the same bets.

Rather than delay settlement (which would slow every grade and still miss the
leagues Sofascore never covers), this turns the lag into a measurement: once
the namespaced result does arrive, re-derive the grade and compare it against
what was recorded. That answers the question the confound note could not —
how often is name-match actually WRONG?

TWO INVARIANTS
--------------
1. It reuses tools.score_lookup._grade_bet, the same grader settlement uses.
   Re-implementing the rules would mean a "disagreement" could be a bug in
   this module rather than a real mis-grade, making the measurement worthless.
2. It is strictly NON-DESTRUCTIVE. It never edits bet_log.result, pnl or
   settle_source. Deciding whether to re-grade off this evidence is a
   separate, human call.
"""

import sqlite3
import time

_TABLE = "settlement_verification"


def ensure_table(bet_db_path):
    """Create the verification ledger. Idempotent."""
    conn = sqlite3.connect(bet_db_path, timeout=10)
    try:
        conn.execute(
            f"""CREATE TABLE IF NOT EXISTS {_TABLE} (
                    bet_id TEXT PRIMARY KEY,
                    verified_at REAL,
                    recorded_result TEXT,
                    recorded_settle_source TEXT,
                    fid_result TEXT,
                    home_score INTEGER,
                    away_score INTEGER,
                    namespace TEXT,
                    fixture_id TEXT,
                    market_type TEXT,
                    side TEXT,
                    agrees INTEGER
                )"""
        )
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_setver_agrees ON {_TABLE}(agrees)"
        )
        conn.commit()
    finally:
        conn.close()


def _candidate_bets(bet_db_path):
    """Settled, name-matched (or deep-looked-up) bets that carry a namespace.

    fid-direct bets are excluded: they were already graded off the namespaced
    id, so re-deriving from the same source proves nothing.
    """
    conn = sqlite3.connect(bet_db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        return [
            dict(r)
            for r in conn.execute(
                """SELECT bet_id, match_id, market_type, side, result,
                          settle_source, fixture_id, fixture_ns
                   FROM bet_log
                   WHERE result IN ('W','L')
                     AND fixture_id IS NOT NULL AND fixture_id != ''
                     AND fixture_ns IS NOT NULL AND fixture_ns != ''
                     AND (settle_source IS NULL OR settle_source != 'fid-direct')"""
            )
        ]
    finally:
        conn.close()


def verify_settlements(bet_db_path, fixture_db_path, days=None):
    """Re-derive each verifiable grade from the namespaced result and compare.

    Returns {checked, agreed, disagreed, ungradeable, skipped_no_result}.
    Never raises and never modifies bet_log.
    """
    from src import fixture_results as _fx
    # Imported here (not at module scope) so the spy in the tests — and any
    # future change to the canonical grader — is always picked up live.
    from tools import score_lookup as _sl

    summary = {
        "checked": 0,
        "agreed": 0,
        "disagreed": 0,
        "ungradeable": 0,
        "skipped_no_result": 0,
    }

    try:
        ensure_table(bet_db_path)
        scores = _fx.load_scores(fixture_db_path, days=days)
        if not scores:
            return summary

        rows = []
        now = time.time()
        for bet in _candidate_bets(bet_db_path):
            ns = str(bet["fixture_ns"])
            fid = str(bet["fixture_id"])
            # Namespaced lookup ONLY. Falling back to a bare id here would
            # re-introduce exactly the cross-namespace collision that
            # fixture_results exists to prevent.
            score = scores.get((ns, fid))
            if score is None:
                summary["skipped_no_result"] += 1
                continue

            home, away = int(score[0]), int(score[1])
            derived = _sl._grade_bet(
                bet["market_type"] or "", bet["side"] or "", home, away
            )
            if derived not in ("W", "L"):
                # 'V' means this grader cannot score that market — unknown,
                # NOT evidence the recorded grade was wrong.
                summary["ungradeable"] += 1
                continue

            agrees = 1 if derived == bet["result"] else 0
            summary["checked"] += 1
            summary["agreed" if agrees else "disagreed"] += 1
            rows.append(
                (
                    bet["bet_id"], now, bet["result"], bet["settle_source"],
                    derived, home, away, ns, fid,
                    bet["market_type"], bet["side"], agrees,
                )
            )

        if rows:
            conn = sqlite3.connect(bet_db_path, timeout=10)
            try:
                conn.executemany(
                    f"""INSERT INTO {_TABLE}
                        (bet_id, verified_at, recorded_result, recorded_settle_source,
                         fid_result, home_score, away_score, namespace, fixture_id,
                         market_type, side, agrees)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                        ON CONFLICT(bet_id) DO UPDATE SET
                            verified_at=excluded.verified_at,
                            recorded_result=excluded.recorded_result,
                            recorded_settle_source=excluded.recorded_settle_source,
                            fid_result=excluded.fid_result,
                            home_score=excluded.home_score,
                            away_score=excluded.away_score,
                            agrees=excluded.agrees""",
                    rows,
                )
                conn.commit()
            finally:
                conn.close()
    except Exception as e:  # never break the settlement cycle over telemetry
        summary["error"] = str(e)
    return summary


def load_disagreements(bet_db_path, limit=500):
    """Bets whose recorded grade conflicts with the namespaced result."""
    try:
        conn = sqlite3.connect(bet_db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            return [
                dict(r)
                for r in conn.execute(
                    f"SELECT * FROM {_TABLE} WHERE agrees=0 "
                    f"ORDER BY verified_at DESC LIMIT ?",
                    (limit,),
                )
            ]
        finally:
            conn.close()
    except Exception:
        return []


def disagreement_rate(bet_db_path):
    """{source: (disagreed, checked, pct)} — how wrong is each grading path?"""
    try:
        conn = sqlite3.connect(bet_db_path, timeout=10)
        try:
            out = {}
            for src, bad, tot in conn.execute(
                f"SELECT COALESCE(recorded_settle_source,'(none)'), "
                f"SUM(1-agrees), COUNT(*) FROM {_TABLE} GROUP BY 1"
            ):
                bad = bad or 0
                out[src] = (bad, tot, round(100.0 * bad / tot, 1) if tot else 0.0)
            return out
        finally:
            conn.close()
    except Exception:
        return {}
