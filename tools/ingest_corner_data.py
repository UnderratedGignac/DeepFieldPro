"""
ingest_corner_data.py — download historical corner data from football-data.co.uk
=================================================================================
football-data.co.uk CSVs include HC (home corners) and AC (away corners) columns.
This script ingests those into data/corner_history.db so we can train a proper
corner rate model keyed by team and league.

Run: .venv\\Scripts\\python.exe tools\\ingest_corner_data.py
     .venv\\Scripts\\python.exe tools\\ingest_corner_data.py --leagues E0 SP1 --seasons 2324 2425
"""
import argparse
import csv
import io
import os
import sqlite3
import time

import requests

DB = os.path.join(os.path.dirname(__file__), "..", "data", "corner_history.db")
BASE = "https://www.football-data.co.uk/mmz4281"
HDRS = {"User-Agent": "Mozilla/5.0"}

DEFAULT_LEAGUES = ["E0", "E1", "SP1", "I1", "D1", "F1", "N1", "P1", "B1", "SC0", "T1", "G1"]
DEFAULT_SEASONS = ["2122", "2223", "2324", "2425"]


def _fi(row, *keys):
    for k in keys:
        v = row.get(k, "")
        if v not in (None, "", "NA"):
            try:
                return int(float(v))
            except (ValueError, TypeError):
                continue
    return None


def init_db():
    con = sqlite3.connect(DB)
    con.execute("""
        CREATE TABLE IF NOT EXISTS corners (
            date TEXT, league TEXT, season TEXT,
            home TEXT, away TEXT,
            home_goals INTEGER, away_goals INTEGER,
            home_corners INTEGER, away_corners INTEGER,
            total_corners INTEGER,
            UNIQUE(date, league, home, away)
        )""")
    con.commit()
    return con


def ingest(leagues, seasons):
    con = init_db()
    cur = con.cursor()
    total = 0
    skipped = 0
    for season in seasons:
        for lg in leagues:
            url = f"{BASE}/{season}/{lg}.csv"
            try:
                r = requests.get(url, headers=HDRS, timeout=40)
            except Exception as e:
                print(f"  {season}/{lg}: fetch error {type(e).__name__}")
                continue
            if r.status_code != 200 or not r.content:
                print(f"  {season}/{lg}: HTTP {r.status_code} (skip)")
                continue
            rows = list(csv.DictReader(io.StringIO(r.text)))
            n = 0
            for row in rows:
                home, away = row.get("HomeTeam"), row.get("AwayTeam")
                if not home or not away:
                    continue
                hg = _fi(row, "FTHG")
                ag = _fi(row, "FTAG")
                hc = _fi(row, "HC")
                ac = _fi(row, "AC")
                if hg is None or ag is None:
                    continue
                if hc is None or ac is None:
                    skipped += 1
                    continue
                cur.execute(
                    """INSERT INTO corners
                           (date, league, season, home, away, home_goals, away_goals,
                            home_corners, away_corners, total_corners)
                       VALUES (?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(date, league, home, away) DO UPDATE SET
                           home_corners=excluded.home_corners,
                           away_corners=excluded.away_corners,
                           total_corners=excluded.total_corners""",
                    (row.get("Date"), lg, season, home, away, hg, ag, hc, ac, hc + ac),
                )
                n += 1
            con.commit()
            total += n
            print(f"  {season}/{lg}: {n} matches with corners")
            time.sleep(0.3)

    cnt = cur.execute("SELECT COUNT(*) FROM corners").fetchone()[0]
    avg_h = cur.execute("SELECT AVG(home_corners) FROM corners").fetchone()[0]
    avg_t = cur.execute("SELECT AVG(total_corners) FROM corners").fetchone()[0]
    con.close()
    print(f"\nDB: {cnt} matches with corner data | avg home corners {avg_h:.2f} | avg total {avg_t:.2f}")
    print(f"Skipped {skipped} rows (no corner data in CSV)")
    print(f"-> {os.path.relpath(DB)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--leagues", nargs="*", default=DEFAULT_LEAGUES)
    ap.add_argument("--seasons", nargs="*", default=DEFAULT_SEASONS)
    args = ap.parse_args()
    print(f"Ingesting corners: {len(args.leagues)} leagues x {len(args.seasons)} seasons...")
    ingest(args.leagues, args.seasons)


if __name__ == "__main__":
    main()
