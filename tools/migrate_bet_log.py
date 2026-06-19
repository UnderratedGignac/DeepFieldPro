"""Idempotent migration: add fixture_id + league columns to bet_log (for CLV +
league analytics). Safe to run repeatedly. The clv/closing_odds columns already
exist; this just adds the two missing keys that let us link a bet to its
odds_history (CLV) and its competition (league edge reports)."""

import os
import sqlite3

DB = os.path.join(os.path.dirname(__file__), "..", "data", "bet_log.db")


def main():
    con = sqlite3.connect(DB)
    cur = con.cursor()
    have = {r[1] for r in cur.execute("PRAGMA table_info(bet_log)")}
    for col, decl in (("fixture_id", "TEXT"), ("league", "TEXT")):
        if col not in have:
            cur.execute(f"ALTER TABLE bet_log ADD COLUMN {col} {decl}")
            print(f"added column: {col}")
        else:
            print(f"already present: {col}")
    con.commit()
    con.close()
    print("migration complete.")


if __name__ == "__main__":
    main()
