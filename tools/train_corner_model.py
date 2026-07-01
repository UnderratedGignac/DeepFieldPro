"""
train_corner_model.py — fit a Poisson corner rate model from historical data
=============================================================================
Uses data/corner_history.db (built by ingest_corner_data.py).

Model: expected_total_corners = league_base + alpha * (home_att - home_def_against)
       Simple team-strength regression calibrated to historical averages.

Saves models/corner_model.json with:
  - league_base: dict[league_code -> avg_corners]
  - team_rates: dict[team -> avg_corners_per_game] (rolling, last 2 seasons)
  - xg_coef: float (corners per xG unit above baseline)

Usage:
  1. Run ingest_corner_data.py first
  2. .venv\\Scripts\\python.exe tools\\train_corner_model.py
"""

import json
import os
import sqlite3

DB = os.path.join(os.path.dirname(__file__), "..", "data", "corner_history.db")
OUT = os.path.join(os.path.dirname(__file__), "..", "models", "corner_model.json")

LEAGUE_LABELS = {
    "E0": "ENG-Premier League",
    "E1": "ENG-Championship",
    "SP1": "ESP-La Liga",
    "I1": "ITA-Serie A",
    "D1": "GER-Bundesliga",
    "F1": "FRA-Ligue 1",
    "N1": "NED-Eredivisie",
    "P1": "POR-Primeira Liga",
    "B1": "BEL-First Division A",
    "SC0": "SCO-Premiership",
    "T1": "TUR-Super Lig",
    "G1": "GRE-Super League",
}


def main():
    if not os.path.exists(DB):
        print(f"ERROR: {DB} not found. Run tools/ingest_corner_data.py first.")
        return

    con = sqlite3.connect(DB)
    cur = con.cursor()

    # Overall stats
    cur.execute("SELECT COUNT(*) FROM corners")
    n_total = cur.fetchone()[0]
    print(f"Total matches with corner data: {n_total}")

    if n_total < 100:
        print(
            "Too few matches to train a reliable model. Run ingest_corner_data.py to download data."
        )
        con.close()
        return

    # 1. League base corner averages (avg total corners per match by league code)
    cur.execute(
        "SELECT league, AVG(total_corners), COUNT(*) FROM corners GROUP BY league ORDER BY COUNT(*) DESC"
    )
    rows = cur.fetchall()
    league_base = {}
    for lg, avg, cnt in rows:
        label = LEAGUE_LABELS.get(lg, lg)
        league_base[label] = round(avg, 2) if avg else 10.5
        league_base[lg] = round(avg, 2) if avg else 10.5
        print(f"  {lg} ({label}): {avg:.2f} avg corners ({cnt} matches)")

    # 2. Team-level home corner rate (how many corners does each team win at home)
    cur.execute(
        """
        SELECT home, AVG(home_corners), COUNT(*) FROM corners
        WHERE season IN (SELECT DISTINCT season FROM corners ORDER BY season DESC LIMIT 2)
        GROUP BY home HAVING COUNT(*) >= 10
    """
    )
    home_rate = {r[0]: round(r[1], 2) for r in cur.fetchall()}

    # 3. Team-level away corner rate
    cur.execute(
        """
        SELECT away, AVG(away_corners), COUNT(*) FROM corners
        WHERE season IN (SELECT DISTINCT season FROM corners ORDER BY season DESC LIMIT 2)
        GROUP BY away HAVING COUNT(*) >= 10
    """
    )
    away_rate = {r[0]: round(r[1], 2) for r in cur.fetchall()}

    # 4. xG coefficient: corners correlate with goals (proxy for attack dominance)
    # Estimate: 1 extra goal scored → how many more corners?
    cur.execute(
        "SELECT home_goals, away_goals, home_corners, away_corners FROM corners WHERE home_corners IS NOT NULL"
    )
    all_rows = cur.fetchall()
    con.close()

    # Simple OLS: corners_h ~ a + b * goals_h
    import math

    n = len(all_rows)
    sx = sum(r[0] for r in all_rows)
    sy = sum(r[2] for r in all_rows)
    sxx = sum(r[0] ** 2 for r in all_rows)
    sxy = sum(r[0] * r[2] for r in all_rows)
    b = (n * sxy - sx * sy) / max(n * sxx - sx**2, 1e-6)
    a = (sy - b * sx) / n
    print(f"\nOLS corners_home ~ goals_home: intercept={a:.2f}, slope={b:.2f}")

    model = {
        "version": "v1",
        "description": "Team + league calibrated corner rate model",
        "league_base": league_base,
        "home_corner_rate": home_rate,
        "away_corner_rate": away_rate,
        "goal_to_corner_coef": round(b, 3),
        "goal_to_corner_intercept": round(a, 3),
        "fallback_total": 10.5,
        "home_adv_factor": 1.07,
    }

    with open(OUT, "w") as f:
        json.dump(model, f, indent=2)

    print(
        f"\nSaved corner model ({len(home_rate)} home teams, {len(away_rate)} away teams)"
    )
    print(f"-> {os.path.relpath(OUT)}")
    print("\nTo use in daemon: the corner rate is loaded automatically from this file.")
    print("Tip: Re-run ingest_corner_data.py + this script each season.")


if __name__ == "__main__":
    main()
