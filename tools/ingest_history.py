"""
ingest_history.py — download historical results + closing odds into data/history.db.
====================================================================================
Source: football-data.co.uk — free CSVs with full-time scores AND closing odds
(Pinnacle PSH/PSD/PSA = the sharpest book; Bet365 B365* as fallback). This is the
training + walk-forward-validation foundation the rest of the model needs.

Creates table `matches`:
    date, league, season, home, away, home_goals, away_goals, result,
    odds_h, odds_d, odds_a,        (1X2 EARLY decimal odds, Pinnacle preferred)
    odds_ch, odds_cd, odds_ca,     (1X2 CLOSING odds, Pinnacle preferred — for CLV)
    odds_maxh, odds_maxd, odds_maxa, (1X2 best EARLY price across books — softest line)
    odds_o25, odds_u25             (Over/Under 2.5 closing odds, Pinnacle preferred)

football-data.co.uk naming: the plain columns (PSH/MaxH/AvgH) are the EARLY odds; the
"C"-infixed ones (PSCH/MaxCH/AvgCH) are the CLOSING odds. CLV = early_price/close_price-1.

Run:  .venv\\Scripts\\python.exe tools\\ingest_history.py
      .venv\\Scripts\\python.exe tools\\ingest_history.py --leagues E0 SP1 --seasons 2324 2425
"""
import argparse
import io
import os
import sqlite3
import time

import requests

DB = os.path.join(os.path.dirname(__file__), "..", "data", "history.db")
BASE = "https://www.football-data.co.uk/mmz4281"
HDRS = {"User-Agent": "Mozilla/5.0"}

# Top leagues with reliable odds coverage.
DEFAULT_LEAGUES = ["E0", "E1", "SP1", "I1", "D1", "F1", "N1", "P1", "B1", "SC0"]
DEFAULT_SEASONS = ["2122", "2223", "2324", "2425"]


def _f(row, *keys):
    """First parseable float among the given CSV columns (closing-odds fallback chain)."""
    for k in keys:
        v = row.get(k, "")
        if v not in (None, "", "NA"):
            try:
                return float(v)
            except ValueError:
                continue
    return None


def init_db():
    con = sqlite3.connect(DB)
    con.execute("""
        CREATE TABLE IF NOT EXISTS matches (
            date TEXT, league TEXT, season TEXT,
            home TEXT, away TEXT,
            home_goals INTEGER, away_goals INTEGER, result TEXT,
            odds_h REAL, odds_d REAL, odds_a REAL,
            odds_ch REAL, odds_cd REAL, odds_ca REAL,
            odds_maxh REAL, odds_maxd REAL, odds_maxa REAL,
            odds_o25 REAL, odds_u25 REAL,
            referee TEXT,
            HY INTEGER, AY INTEGER, HR INTEGER, AR INTEGER,
            UNIQUE(date, league, home, away)
        )""")
    # Migration: add newer columns to a pre-existing DB that lacks them.
    cols = {r[1] for r in con.execute("PRAGMA table_info(matches)")}
    for col, typ in [
        ("odds_ch", "REAL"), ("odds_cd", "REAL"), ("odds_ca", "REAL"),
        ("odds_maxh", "REAL"), ("odds_maxd", "REAL"), ("odds_maxa", "REAL"),
        ("odds_o25", "REAL"), ("odds_u25", "REAL"),
        ("referee", "TEXT"),
        ("HY", "INTEGER"), ("AY", "INTEGER"), ("HR", "INTEGER"), ("AR", "INTEGER"),
    ]:
        if col not in cols:
            con.execute(f"ALTER TABLE matches ADD COLUMN {col} {typ}")
    con.commit()
    return con


def ingest(leagues, seasons):
    import csv
    con = init_db()
    cur = con.cursor()
    total = 0
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
                fthg, ftag = row.get("FTHG"), row.get("FTAG")
                if not home or not away or fthg in (None, "") or ftag in (None, ""):
                    continue
                try:
                    hg, ag = int(fthg), int(ftag)
                except ValueError:
                    continue
                oh = _f(row, "PSH", "B365H", "AvgH", "MaxH")   # 1X2 EARLY, Pinnacle preferred
                od = _f(row, "PSD", "B365D", "AvgD", "MaxD")
                oa = _f(row, "PSA", "B365A", "AvgA", "MaxA")
                # 1X2 CLOSING odds (for CLV): Pinnacle-Closing preferred.
                ch = _f(row, "PSCH", "B365CH", "AvgCH", "MaxCH")
                cd = _f(row, "PSCD", "B365CD", "AvgCD", "MaxCD")
                ca = _f(row, "PSCA", "B365CA", "AvgCA", "MaxCA")
                # Best EARLY price across books (softest line you could actually take).
                mxh = _f(row, "MaxH", "B365H", "PSH", "AvgH")
                mxd = _f(row, "MaxD", "B365D", "PSD", "AvgD")
                mxa = _f(row, "MaxA", "B365A", "PSA", "AvgA")
                # Over/Under 2.5 closing odds: Pinnacle-Closing first, then
                # Bet365-Closing / market avg/max, then the non-closing equivalents.
                o25 = _f(row, "PC>2.5", "B365C>2.5", "AvgC>2.5", "MaxC>2.5",
                         "P>2.5", "B365>2.5", "Avg>2.5", "Max>2.5")
                u25 = _f(row, "PC<2.5", "B365C<2.5", "AvgC<2.5", "MaxC<2.5",
                         "P<2.5", "B365<2.5", "Avg<2.5", "Max<2.5")
                # Referee and card columns (football-data.co.uk standard names)
                ref = (row.get("Referee") or "").strip() or None
                def _i(row, *keys):
                    for k in keys:
                        v = row.get(k, "")
                        if v not in (None, "", "NA"):
                            try:
                                return int(float(v))
                            except (ValueError, TypeError):
                                continue
                    return None
                hy = _i(row, "HY")   # home yellows
                ay = _i(row, "AY")   # away yellows
                hr = _i(row, "HR")   # home reds
                ar = _i(row, "AR")   # away reds

                # NAMED columns (not positional): the table may have been built up via
                # ALTER TABLE ADD COLUMN, so physical column order is NOT the CREATE order.
                cur.execute(
                    """INSERT INTO matches
                           (date, league, season, home, away, home_goals, away_goals, result,
                            odds_h, odds_d, odds_a, odds_ch, odds_cd, odds_ca,
                            odds_maxh, odds_maxd, odds_maxa, odds_o25, odds_u25,
                            referee, HY, AY, HR, AR)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(date, league, home, away) DO UPDATE SET
                           odds_h=excluded.odds_h, odds_d=excluded.odds_d, odds_a=excluded.odds_a,
                           odds_ch=excluded.odds_ch, odds_cd=excluded.odds_cd, odds_ca=excluded.odds_ca,
                           odds_maxh=excluded.odds_maxh, odds_maxd=excluded.odds_maxd,
                           odds_maxa=excluded.odds_maxa,
                           odds_o25=excluded.odds_o25, odds_u25=excluded.odds_u25,
                           referee=excluded.referee,
                           HY=excluded.HY, AY=excluded.AY, HR=excluded.HR, AR=excluded.AR""",
                    (row.get("Date"), lg, season, home, away, hg, ag, row.get("FTR"),
                     oh, od, oa, ch, cd, ca, mxh, mxd, mxa, o25, u25,
                     ref, hy, ay, hr, ar),
                )
                n += 1
            con.commit()
            total += n
            print(f"  {season}/{lg}: {n} matches")
            time.sleep(0.3)
    cnt = cur.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    teams = cur.execute("SELECT COUNT(DISTINCT home) FROM matches").fetchone()[0]
    with_odds = cur.execute("SELECT COUNT(*) FROM matches WHERE odds_h IS NOT NULL").fetchone()[0]
    with_close = cur.execute("SELECT COUNT(*) FROM matches WHERE odds_ch IS NOT NULL").fetchone()[0]
    with_ou = cur.execute("SELECT COUNT(*) FROM matches WHERE odds_o25 IS NOT NULL").fetchone()[0]
    con.close()
    print(f"\nDB now holds {cnt} matches | {teams} distinct teams | {with_odds} with 1X2 early odds "
          f"| {with_close} with 1X2 closing odds | {with_ou} with O/U 2.5 odds")
    print(f"-> {os.path.relpath(DB)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--leagues", nargs="*", default=DEFAULT_LEAGUES)
    ap.add_argument("--seasons", nargs="*", default=DEFAULT_SEASONS)
    args = ap.parse_args()
    print(f"Ingesting {len(args.leagues)} leagues x {len(args.seasons)} seasons...")
    ingest(args.leagues, args.seasons)


if __name__ == "__main__":
    main()
