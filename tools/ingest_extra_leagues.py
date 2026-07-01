"""
ingest_extra_leagues.py
=======================
Expands data/history.db with match data from two sources:

  1. football-data.co.uk "new" format CSVs (free, covers ~25 national leagues)
     URL: https://www.football-data.co.uk/new/{CODE}.csv
     Contains all available seasons in one file per country.

  2. TheSportsDB free API (key=3) — leagues not on football-data.co.uk
     Covers: Iceland, Faroe Islands, Kuwait, Morocco, Peru, Estonia, etc.

After running, retrain:
    .venv\\Scripts\\python.exe tools\\train_dixon_coles.py

Usage:
    .venv\\Scripts\\python.exe tools\\ingest_extra_leagues.py
    .venv\\Scripts\\python.exe tools\\ingest_extra_leagues.py --fdco-only
    .venv\\Scripts\\python.exe tools\\ingest_extra_leagues.py --tsdb-only
    .venv\\Scripts\\python.exe tools\\ingest_extra_leagues.py --list
"""

import argparse
import csv
import io
import json
import os
import sqlite3
import time
from datetime import datetime

import requests

DB = os.path.join(os.path.dirname(__file__), "..", "data", "history.db")
HDRS = {"User-Agent": "Mozilla/5.0 DeepFieldPro/2.0"}
TSDB_BASE = "https://www.thesportsdb.com/api/v1/json/3"

# ── football-data.co.uk "new" format leagues ─────────────────────────────────
# URL: https://www.football-data.co.uk/new/{CODE}.csv
# Column names differ from the mmz4281 format — handled in _parse_fdco_new_row().
FDCO_NEW = [
    ("IRL",  "Irish Premier Division"),
    ("NOR",  "Norwegian Eliteserien"),
    ("SWE",  "Swedish Allsvenskan"),
    ("ROM",  "Romanian Liga 1"),
    ("ARG",  "Argentine Primera Division"),
    ("AUS",  "Australian A-League"),
    ("AUT",  "Austrian Bundesliga"),
    ("BRA",  "Brazilian Serie A"),
    ("CHN",  "Chinese Super League"),
    ("DNK",  "Danish Superliga"),
    ("FIN",  "Finnish Veikkausliiga"),
    ("GRC",  "Greek Super League"),
    ("HUN",  "Hungarian NB I"),
    ("ISR",  "Israeli Premier League"),
    ("JPN",  "Japanese J1 League"),
    ("MEX",  "Mexican Liga MX"),
    ("POL",  "Polish Ekstraklasa"),
    ("RSA",  "South African Premier Division"),
    ("RUS",  "Russian Premier League"),
    ("USA",  "American MLS"),
    ("TUR",  "Turkish Super Lig"),
    ("CZE",  "Czech First League"),
    ("SVK",  "Slovak Super Liga"),
]

# ── TheSportsDB target leagues ────────────────────────────────────────────────
# Each entry: (search_country, search_name_hint, league_code_in_db)
# We search by country to discover the league ID, then pull events.
TSDB_TARGETS = [
    ("Iceland",      "Úrvalsdeild",      "ISL",  "Icelandic Urvalsdeild"),
    ("Faroe Islands","Premier League",   "FAR",  "Faroe Islands Premier League"),
    ("Kuwait",       "Premier League",   "KUW",  "Kuwaiti Premier League"),
    ("Morocco",      "Botola",           "MAR",  "Moroccan Botola Pro"),
    ("Peru",         "Liga 1",           "PER",  "Peruvian Liga 1"),
    ("Estonia",      "Meistriliiga",     "EST",  "Estonian Meistriliiga"),
    ("Norway",       "1. Divisjon",      "NOR2", "Norwegian 1. Divisjon"),
    ("Norway",       "2. Divisjon",      "NOR3", "Norwegian 2. Divisjon"),
    ("Sweden",       "Superettan",       "SWE2", "Swedish Superettan"),
    ("Sweden",       "Division 1",       "SWE3", "Swedish Division 1"),
    ("Ireland",      "First Division",   "IRL2", "Irish First Division"),
    ("Australia",    "National Premier", "AUSE", "Australian National Premier League"),
    ("Kazakhstan",   "Premier League",   "KAZ",  "Kazakhstani Premier League"),
    ("Azerbaijan",   "Premier League",   "AZE",  "Azerbaijani Premier League"),
    ("Mozambique",   "Mocambola",        "MOZ",  "Mozambican Mocambola"),
    ("Qatar",        "Stars League",     "QAT",  "Qatari Stars League"),
    ("Saudi Arabia", "Pro League",       "SAU",  "Saudi Pro League"),
    ("UAE",          "Pro League",       "UAE",  "UAE Pro League"),
]

TSDB_SEASONS = ["2021-2022", "2022-2023", "2023-2024", "2024-2025"]


# ── DB helpers ────────────────────────────────────────────────────────────────

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
    # Add any columns the existing DB might be missing
    cols = {r[1] for r in con.execute("PRAGMA table_info(matches)")}
    for col, typ in [("odds_ch","REAL"),("odds_cd","REAL"),("odds_ca","REAL"),
                     ("odds_maxh","REAL"),("odds_maxd","REAL"),("odds_maxa","REAL"),
                     ("odds_o25","REAL"),("odds_u25","REAL"),("referee","TEXT"),
                     ("HY","INTEGER"),("AY","INTEGER"),("HR","INTEGER"),("AR","INTEGER")]:
        if col not in cols:
            con.execute(f"ALTER TABLE matches ADD COLUMN {col} {typ}")
    con.commit()
    return con


def upsert(cur, date, league, season, home, away, hg, ag, result,
           oh=None, od=None, oa=None):
    res = "H" if hg > ag else ("A" if ag > hg else "D")
    cur.execute("""
        INSERT INTO matches
            (date, league, season, home, away, home_goals, away_goals, result,
             odds_h, odds_d, odds_a)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(date, league, home, away) DO UPDATE SET
            home_goals=excluded.home_goals,
            away_goals=excluded.away_goals,
            result=excluded.result,
            odds_h=COALESCE(excluded.odds_h, odds_h),
            odds_d=COALESCE(excluded.odds_d, odds_d),
            odds_a=COALESCE(excluded.odds_a, odds_a)
    """, (date, league, season, home, away, hg, ag, res, oh, od, oa))


def _f(row, *keys):
    for k in keys:
        v = row.get(k, "")
        if v not in (None, "", "NA", "N/A"):
            try:
                f = float(v)
                if f > 1.0:
                    return f
            except (ValueError, TypeError):
                continue
    return None


def _norm_date(raw):
    """Normalise various date formats to DD/MM/YYYY for parse_ordinal()."""
    if not raw:
        return None
    raw = raw.strip()
    # Strip time component if present (e.g. "01/08/2024 20:30")
    raw = raw.split(" ")[0].split("T")[0]
    # Try DD/MM/YYYY or DD/MM/YY (football-data.co.uk standard)
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%d/%m/%Y")
        except ValueError:
            pass
    # Try YYYY-MM-DD (ISO, TheSportsDB)
    try:
        return datetime.strptime(raw, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        pass
    # Try MM/DD/YY or MM/DD/YYYY (US)
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            d = datetime.strptime(raw, fmt)
            # Sanity: month ≤ 12, day ≤ 31
            return d.strftime("%d/%m/%Y")
        except ValueError:
            pass
    return None


# ── football-data.co.uk "new" format ─────────────────────────────────────────

def ingest_fdco_new(code, label, con):
    url = f"https://www.football-data.co.uk/new/{code}.csv"
    try:
        r = requests.get(url, headers=HDRS, timeout=40)
    except Exception as e:
        print(f"  [{code}] fetch error: {e}")
        return 0
    if r.status_code != 200 or not r.content.strip():
        print(f"  [{code}] HTTP {r.status_code} — skipped")
        return 0

    cur = con.cursor()
    rows = list(csv.DictReader(io.StringIO(r.text)))
    n = 0
    for row in rows:
        # New format uses HG/AG; some variants use FTHG/FTAG
        home = (row.get("HomeTeam") or row.get("Home") or "").strip()
        away = (row.get("AwayTeam") or row.get("Away") or "").strip()
        hg_raw = row.get("HG") or row.get("FTHG") or row.get("HGS") or ""
        ag_raw = row.get("AG") or row.get("FTAG") or row.get("AGS") or ""
        if not home or not away or hg_raw == "" or ag_raw == "":
            continue
        try:
            hg, ag = int(float(hg_raw)), int(float(ag_raw))
        except (ValueError, TypeError):
            continue

        # Date: new format uses DateTime column
        raw_date = row.get("DateTime") or row.get("Date") or ""
        date = _norm_date(raw_date)
        if not date:
            continue

        # Season from Season column; fall back to extracting from DateTime year
        season = (row.get("Season") or "").strip()
        if not season:
            try:
                yr = datetime.strptime(date, "%d/%m/%Y").year
                season = f"{str(yr-1)[2:]}{str(yr)[2:]}"
            except Exception:
                season = "unknown"

        # Always use the CLI country code as the DB league key so it matches
        # _DC_LEAGUE_MAP exactly. Sub-divisions are separate TheSportsDB targets.
        lg_code = code

        # Odds — new format: MH/MD/MA or BbMxH/BbMxD/BbMxA
        oh = _f(row, "MH", "BbMxH", "BbAvH", "AvgH", "MaxH", "B365H")
        od = _f(row, "MD", "BbMxD", "BbAvD", "AvgD", "MaxD", "B365D")
        oa = _f(row, "MA", "BbMxA", "BbAvA", "AvgA", "MaxA", "B365A")

        try:
            upsert(cur, date, lg_code, season, home, away, hg, ag, None, oh, od, oa)
            n += 1
        except Exception:
            pass

    con.commit()
    return n


# ── TheSportsDB ───────────────────────────────────────────────────────────────

def _tsdb_get(path, params=None, delay=0.5):
    try:
        r = requests.get(f"{TSDB_BASE}/{path}", params=params,
                         headers=HDRS, timeout=30)
        time.sleep(delay)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return {}


def _find_tsdb_league(country, hint):
    """Search TheSportsDB for a soccer league in the given country."""
    data = _tsdb_get("search_all_leagues.php", {"s": "Soccer", "c": country})
    # API returns "countries" (not "countrys")
    leagues = data.get("countries") or data.get("countrys") or []
    if not leagues:
        return None, None
    hint_lower = hint.lower()
    hint_words = hint_lower.split()
    # Prefer division-1 leagues when filtering
    div1 = [lg for lg in leagues if str(lg.get("intDivision", "0")) == "1"]
    pool = div1 if div1 else leagues
    # Keyword match within pool
    for lg in pool:
        name = (lg.get("strLeague") or "").lower()
        if hint_lower in name or any(w in name for w in hint_words):
            return lg.get("idLeague"), lg.get("strLeague")
    # Fallback: first division-1 result
    if pool:
        return pool[0].get("idLeague"), pool[0].get("strLeague")
    return None, None


def ingest_tsdb_league(country, hint, lg_code, label, con):
    league_id, found_name = _find_tsdb_league(country, hint)
    if not league_id:
        print(f"  [{lg_code}] not found on TheSportsDB ({country} / {hint})")
        return 0

    print(f"  [{lg_code}] found: '{found_name}' (id={league_id})")
    cur = con.cursor()
    total = 0

    for season in TSDB_SEASONS:
        data = _tsdb_get("eventsseason.php", {"id": league_id, "s": season})
        events = data.get("events") or []
        n = 0
        for ev in events:
            home = (ev.get("strHomeTeam") or "").strip()
            away = (ev.get("strAwayTeam") or "").strip()
            hg_raw = ev.get("intHomeScore") or ""
            ag_raw = ev.get("intAwayScore") or ""
            raw_date = ev.get("dateEvent") or ""

            if not home or not away or hg_raw in (None, "") or ag_raw in (None, ""):
                continue
            try:
                hg, ag = int(hg_raw), int(ag_raw)
            except (ValueError, TypeError):
                continue
            date = _norm_date(raw_date)
            if not date:
                continue
            # Extract short season label
            short_season = season.replace("-20", "-").replace("20", "")[:4]
            try:
                upsert(cur, date, lg_code, short_season, home, away, hg, ag, None)
                n += 1
            except Exception:
                pass

        if n:
            print(f"    {season}: {n} matches")
            total += n
        time.sleep(0.3)

    con.commit()
    return total


# ── DC_LEAGUE_MAP additions ───────────────────────────────────────────────────

DC_MAP_ADDITIONS = {
    # football-data.co.uk new leagues
    "irish premier division":         "IRL",
    "league of ireland premier":      "IRL",
    "sse airtricity premier":         "IRL",
    "norwegian eliteserien":          "NOR",
    "eliteserien":                    "NOR",
    "tippeligaen":                    "NOR",
    "swedish allsvenskan":            "SWE",
    "allsvenskan":                    "SWE",
    "romanian liga 1":                "ROM",
    "superliga":                      "ROM",
    "liga 1":                         "ROM",
    "liga 1 betano":                  "ROM",
    "argentine primera division":     "ARG",
    "primera division":               "ARG",
    "a-league":                       "AUS",
    "a league":                       "AUS",
    "australian a-league":            "AUS",
    "austrian bundesliga":            "AUT",
    "osterreichische bundesliga":     "AUT",
    "brazilian serie a":              "BRA",
    "serie a brasileirao":            "BRA",
    "chinese super league":           "CHN",
    "danish superliga":               "DNK",
    "superliga":                      "DNK",
    "finnish veikkausliiga":          "FIN",
    "veikkausliiga":                  "FIN",
    "greek super league":             "GRC",
    "super league greece":            "GRC",
    "hungarian nb i":                 "HUN",
    "otp bank liga":                  "HUN",
    "israeli premier league":         "ISR",
    "ligat ha'al":                    "ISR",
    "japanese j1 league":             "JPN",
    "j1 league":                      "JPN",
    "j. league":                      "JPN",
    "mexican liga mx":                "MEX",
    "liga mx":                        "MEX",
    "polish ekstraklasa":             "POL",
    "ekstraklasa":                    "POL",
    "south african premier division": "RSA",
    "dstv premiership":               "RSA",
    "absa premiership":               "RSA",
    "russian premier league":         "RUS",
    "rpl":                            "RUS",
    "american mls":                   "USA",
    "mls":                            "USA",
    "major league soccer":            "USA",
    "turkish super lig":              "TUR",
    "süper lig":                      "TUR",
    "super lig":                      "TUR",
    "czech first league":             "CZE",
    "fortuna liga":                   "CZE",
    "het liga":                       "CZE",
    "czech liga":                     "CZE",
    "slovak super liga":              "SVK",
    # TheSportsDB leagues
    "icelandic urvalsdeild":          "ISL",
    "urvalsdeild":                    "ISL",
    "besta deild karla":              "ISL",
    "faroe islands premier league":   "FAR",
    "faroese premier league":         "FAR",
    "1. deild":                       "FAR",
    "kuwaiti premier league":         "KUW",
    "kuwait premier league":          "KUW",
    "moroccan botola pro":            "MAR",
    "botola pro":                     "MAR",
    "botola maroc":                   "MAR",
    "inwi botola pro":                "MAR",
    "peruvian liga 1":                "PER",
    "liga 1":                         "PER",
    "liga 1 peru":                    "PER",
    "liga 1 movistar":                "PER",
    "estonian meistriliiga":          "EST",
    "meistriliiga":                   "EST",
    "norwegian 1. divisjon":          "NOR2",
    "1. divisjon":                    "NOR2",
    "norwegian 2. divisjon":          "NOR3",
    "2. divisjon":                    "NOR3",
    "3. divisjon":                    "NOR3",
    "swedish superettan":             "SWE2",
    "superettan":                     "SWE2",
    "swedish division 1":             "SWE3",
    "division 2":                     "SWE3",
    "division 1":                     "SWE3",
    "irish first division":           "IRL2",
    "league of ireland first":        "IRL2",
    "sse airtricity first":           "IRL2",
    "national premier league":        "AUSE",
    "npsl":                           "AUSE",
    "npfl":                           "AUSE",
    "kazakhstani premier league":     "KAZ",
    "kpl":                            "KAZ",
    "azerbaijani premier league":     "AZE",
    "azerbaycan premyer liqasi":      "AZE",
    "mozambican mocambola":           "MOZ",
    "mocambola":                      "MOZ",
    "qatari stars league":            "QAT",
    "qatar stars league":             "QAT",
    "saudi pro league":               "SAU",
    "saudi professional league":      "SAU",
    "uae pro league":                 "UAE",
    "arabian gulf league":            "UAE",
    "esiliiga":                       "EST",
    "esiliiga b":                     "EST",
    "primera b metropolitana":        "ARG2",
    "primera b":                      "ARG2",
    "nacional b":                     "ARG2",
    "primera nacional":               "ARG2",
    "queensland premier league":      "AUSE",
    "ffa cup":                        "AUSE",
}


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Ingest extra league data into history.db")
    ap.add_argument("--fdco-only",  action="store_true", help="Only football-data.co.uk")
    ap.add_argument("--tsdb-only",  action="store_true", help="Only TheSportsDB")
    ap.add_argument("--list",       action="store_true", help="List target leagues and exit")
    ap.add_argument("--code",       help="Only ingest this league code (e.g. IRL)")
    args = ap.parse_args()

    if args.list:
        print("football-data.co.uk new-format leagues:")
        for code, label in FDCO_NEW:
            print(f"  {code:6s}  {label}")
        print("\nTheSportsDB targets:")
        for country, hint, code, label in TSDB_TARGETS:
            print(f"  {code:6s}  {label}  ({country})")
        return

    con = init_db()
    print(f"DB: {DB}")
    grand_total = 0

    # ── football-data.co.uk ───────────────────────────────────────────────────
    if not args.tsdb_only:
        print("\n=== football-data.co.uk new-format leagues ===")
        for code, label in FDCO_NEW:
            if args.code and args.code.upper() != code:
                continue
            print(f"  [{code}] {label} ...", end=" ", flush=True)
            n = ingest_fdco_new(code, label, con)
            print(f"{n} rows")
            grand_total += n
            time.sleep(0.5)

    # ── TheSportsDB ───────────────────────────────────────────────────────────
    if not args.fdco_only:
        print("\n=== TheSportsDB leagues ===")
        for country, hint, code, label in TSDB_TARGETS:
            if args.code and args.code.upper() != code:
                continue
            print(f"  [{code}] {label}")
            n = ingest_tsdb_league(country, hint, code, label, con)
            print(f"    → {n} total rows")
            grand_total += n

    con.close()

    print(f"\nDone. {grand_total} rows written to history.db.")
    print("Now retrain the model:")
    print("  .venv\\Scripts\\python.exe tools\\train_dixon_coles.py")
    print()
    print("Then add the league name mappings to _DC_LEAGUE_MAP in")
    print("  src/live_predictions_daemon.py")
    print("(run tools/update_dc_league_map.py to do this automatically)")


if __name__ == "__main__":
    main()
