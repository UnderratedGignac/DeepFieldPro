"""
train_dixon_coles.py — fit per-league Dixon-Coles models from data/history.db.
=============================================================================
Saves models/dixon_coles.json (team attack/defense ratings + home_adv + rho per
league). The daemon loads it to produce continuous, team-specific 1X2 probs.

Run:  .venv\\Scripts\\python.exe tools\\train_dixon_coles.py
"""

import datetime
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.models.dixon_coles import fit_league, MODEL_PATH

DB = os.path.join(os.path.dirname(__file__), "..", "data", "history.db")


def parse_ordinal(s):
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.datetime.strptime(s, fmt).toordinal()
        except (ValueError, TypeError):
            continue
    return None


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT * FROM matches")]
    con.close()

    by_league = {}
    for r in rows:
        o = parse_ordinal(r["date"])
        if o is None:
            continue
        by_league.setdefault(r["league"], []).append(
            {
                "home": r["home"],
                "away": r["away"],
                "hg": r["home_goals"],
                "ag": r["away_goals"],
                "ordinal": o,
            }
        )

    leagues = {}
    for lg, ms in sorted(by_league.items()):
        params = fit_league(ms)
        if not params:
            print(f"  {lg}: skipped (too few matches/teams)")
            continue
        leagues[lg] = params
        # sanity: strongest/weakest by attack
        teams = params["teams"]
        rank = sorted(teams.items(), key=lambda kv: -kv[1]["att"])
        top = ", ".join(t for t, _ in rank[:3])
        bot = ", ".join(t for t, _ in rank[-3:])
        print(
            f"  {lg}: {params['n_teams']} teams, {params['n_matches']} matches | "
            f"home_adv={params['home_adv']:.3f} rho={params['rho']:+.3f}"
        )
        print(f"       strongest: {top}  |  weakest: {bot}")

    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    with open(MODEL_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {"leagues": leagues, "trained_at": datetime.date.today().isoformat()},
            f,
            indent=1,
        )
    print(f"\nSaved {len(leagues)} league models -> {os.path.relpath(MODEL_PATH)}")


if __name__ == "__main__":
    main()
