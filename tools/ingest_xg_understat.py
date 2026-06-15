"""
ingest_xg_understat.py — free historical xG into data/xg_history.db (foundation for #7).
=======================================================================================
The one xG idea aligned with the validated edges (roadmap #7): soft books overprice teams
whose recent RESULTS outran their xG; backing the regression is an early-price inefficiency.
This ingests REAL historical xG from Understat via the soccerdata package (keyless, tls-client
— raw requests.get is Cloudflare-stripped and returns null xG, so we MUST use soccerdata).

Writes a standalone data/xg_history.db (does NOT touch the live betting DBs). The backtest
(tools/backtest_xg_regression.py) is the next step and must clear a monotone-positive
selectivity sweep before any belief — same bar the goals-DC model failed.

Usage:
    python tools/ingest_xg_understat.py                 # default: a few top leagues, recent seasons
    python tools/ingest_xg_understat.py ENG-Premier\\ League 2024
"""
import os
import sys
import sqlite3
import warnings

warnings.filterwarnings("ignore")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "data", "xg_history.db")

DEFAULT_LEAGUES = ["ENG-Premier League", "ESP-La Liga", "GER-Bundesliga",
                   "ITA-Serie A", "FRA-Ligue 1"]
DEFAULT_SEASONS = ["2122", "2223", "2324", "2425"]


def _init(con):
    con.execute("""CREATE TABLE IF NOT EXISTS xg_match (
        league TEXT, season TEXT, date TEXT,
        home_team TEXT, away_team TEXT,
        home_goals REAL, away_goals REAL, home_xg REAL, away_xg REAL,
        PRIMARY KEY (season, date, home_team, away_team))""")


def ingest(leagues, seasons):
    import soccerdata as sd
    con = sqlite3.connect(DB)
    _init(con)
    total = 0
    for lg in leagues:
        try:
            sch = sd.Understat(leagues=lg, seasons=seasons).read_schedule()
        except Exception as e:
            print(f"[{lg}] read failed: {e}")
            continue
        done = sch[sch["is_result"] == True] if "is_result" in sch.columns else sch
        # Hard guard: if EVERY xG is null, Understat was Cloudflare-stripped — fail loudly
        # rather than silently writing useless null-xG rows.
        if len(done) and done["home_xg"].notna().sum() == 0:
            raise SystemExit(f"[{lg}] ALL xG null — Understat access is broken (stripped). Aborting.")
        n = 0
        for (_, season, _), r in done.iterrows():
            if r.get("home_xg") is None:
                continue
            con.execute(
                "INSERT OR REPLACE INTO xg_match VALUES (?,?,?,?,?,?,?,?,?)",
                (lg, str(season), str(r["date"]), r["home_team"], r["away_team"],
                 r.get("home_goals"), r.get("away_goals"), r.get("home_xg"), r.get("away_xg")))
            n += 1
        con.commit()
        print(f"[{lg}] ingested {n} matches with xG")
        total += n
    print(f"\nTotal: {total} matches with xG in {DB}")
    print("rows now:", con.execute("SELECT COUNT(*) FROM xg_match").fetchone()[0])
    con.close()


if __name__ == "__main__":
    args = sys.argv[1:]
    if args:
        ingest([args[0]], [args[1]] if len(args) > 1 else DEFAULT_SEASONS)
    else:
        ingest(DEFAULT_LEAGUES, DEFAULT_SEASONS)
