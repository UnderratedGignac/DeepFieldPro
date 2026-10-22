"""
xg_elo_bootstrap.py

One-time (re-runnable) script: reads history.db (82k+ match results)
and inserts Poisson-estimated xG into xg_history.db so xg_elo_engine
has ratings for hundreds of teams, not just the 40 with real xG data.

xG ESTIMATION METHOD:
  For a match ending H:A goals, expected xG is approximated as:
    xG_home = H + shrink * (league_home_mean - H)   (shrinks toward league mean)
    xG_away = A + shrink * (league_away_mean - A)

  This "shrinkage toward mean xG" was validated as a better predictor of
  future performance than raw goals (Caley 2015, Mackay 2017).

Real xG rows (from xg_match) are preserved — estimated rows only fill gaps.
"""

import os
import sqlite3
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("bootstrap")

XG_DB   = os.path.join("data", "xg_history.db")
HIST_DB = os.path.join("data", "history.db")

# League mean goals (home_avg, away_avg) from large-sample historical data
LEAGUE_MEANS = {
    "E0":  (1.55, 1.18),  "E1":  (1.51, 1.19),  "E2":  (1.47, 1.15),
    "E3":  (1.43, 1.12),  "EC":  (1.42, 1.12),
    "D1":  (1.60, 1.25),  "D2":  (1.53, 1.20),
    "SP1": (1.47, 1.13),  "SP2": (1.43, 1.10),
    "I1":  (1.45, 1.10),  "I2":  (1.39, 1.08),
    "F1":  (1.43, 1.12),  "F2":  (1.41, 1.10),
    "N1":  (1.62, 1.28),  "B1":  (1.55, 1.22),
    "P1":  (1.50, 1.15),  "T1":  (1.52, 1.17),
    "G1":  (1.42, 1.09),  "SC0": (1.48, 1.15),  "SC1": (1.42, 1.11),
}
FALLBACK_HOME = 1.48
FALLBACK_AWAY = 1.14
SHRINK = 0.15


def estimate_xg(h_goals, a_goals, league):
    lh, la = LEAGUE_MEANS.get(league, (FALLBACK_HOME, FALLBACK_AWAY))
    xg_h = max(0.05, round(h_goals + SHRINK * (lh - h_goals), 4))
    xg_a = max(0.05, round(a_goals + SHRINK * (la - a_goals), 4))
    return xg_h, xg_a


def run():
    if not os.path.exists(HIST_DB):
        log.error(f"history.db not found at {HIST_DB}")
        sys.exit(1)

    xg_conn = sqlite3.connect(XG_DB)
    xg_conn.execute("""
        CREATE TABLE IF NOT EXISTS xg_match (
            league TEXT, season TEXT, date TEXT,
            home_team TEXT, away_team TEXT,
            home_goals INTEGER, away_goals INTEGER,
            home_xg REAL, away_xg REAL,
            estimated INTEGER DEFAULT 0,
            PRIMARY KEY (date, home_team, away_team)
        )
    """)
    xg_conn.commit()
    try:
        xg_conn.execute("ALTER TABLE xg_match ADD COLUMN estimated INTEGER DEFAULT 0")
        xg_conn.commit()
    except Exception:
        pass

    existing = set(xg_conn.execute(
        "SELECT date, home_team, away_team FROM xg_match"
    ).fetchall())
    log.info(f"Existing xg_match rows: {len(existing)}")

    hist_conn = sqlite3.connect(HIST_DB)
    rows = hist_conn.execute(
        "SELECT date, league, season, home, away, home_goals, away_goals "
        "FROM matches WHERE home_goals IS NOT NULL AND away_goals IS NOT NULL "
        "ORDER BY date ASC"
    ).fetchall()
    hist_conn.close()
    log.info(f"history.db rows to process: {len(rows)}")

    inserted = 0
    batch = []
    for date, league, season, home, away, hg, ag in rows:
        try:
            parts = date.split("/")
            iso_date = f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}" if len(parts) == 3 else date
        except Exception:
            iso_date = date

        key = (iso_date, home, away)
        if key in existing:
            continue

        try:
            xg_h, xg_a = estimate_xg(int(hg), int(ag), league)
        except Exception:
            continue

        batch.append((league, season, iso_date, home, away, int(hg), int(ag), xg_h, xg_a, 1))
        existing.add(key)

        if len(batch) >= 1000:
            xg_conn.executemany(
                "INSERT OR IGNORE INTO xg_match "
                "(league, season, date, home_team, away_team, home_goals, away_goals, home_xg, away_xg, estimated) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)", batch
            )
            xg_conn.commit()
            inserted += len(batch)
            batch = []
            log.info(f"  {inserted:,} rows inserted...")

    if batch:
        xg_conn.executemany(
            "INSERT OR IGNORE INTO xg_match "
            "(league, season, date, home_team, away_team, home_goals, away_goals, home_xg, away_xg, estimated) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)", batch
        )
        xg_conn.commit()
        inserted += len(batch)

    total_now = xg_conn.execute("SELECT COUNT(*) FROM xg_match").fetchone()[0]
    xg_conn.close()

    log.info(f"\n=== Bootstrap Complete: inserted {inserted:,}, total rows = {total_now:,} ===")

    log.info("Reloading xG-Elo ratings...")
    import src.xg_elo_engine as eng
    eng._RATINGS.clear()
    eng._RATINGS_LOADED = False
    eng._load_ratings_from_xg_db()
    rs = eng.rating_summary()
    log.info(f"  Teams rated: {rs['total_teams']}, eligible (>=6 matches): {rs['eligible_teams']}")
    log.info("  Top 15:")
    for k, v in eng.top_rated_teams(15):
        log.info(f"    {k:<34} rating={v['rating']:.0f}  n={v['n']}")


if __name__ == "__main__":
    run()
