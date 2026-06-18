"""
form_cache.py — Precompute rolling form from history.db for daemon use.

Builds a per-team chronological record so predict_match can fetch:
  - Last 5 home/away form (W/D/L counts, GF/GA)
  - Last 5 H2H between two teams

Call build_cache() once at daemon startup. Then use get_form(team, date, home=True).
Falls back gracefully to None if history.db not found.
"""
import os
import sqlite3
import datetime

_CACHE = {}  # team -> sorted list of (date_ordinal, opponent, is_home, gf, ga, result)
_H2H = {}    # frozenset({home, away}) -> sorted list of (date_ordinal, home_team, hg, ag)
_BUILT = False

DB = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'history.db')


def _parse_date(s):
    for fmt in ('%d/%m/%Y', '%d/%m/%y', '%Y-%m-%d'):
        try:
            return datetime.datetime.strptime(s, fmt).toordinal()
        except (ValueError, TypeError):
            continue
    return 0


def build_cache():
    global _BUILT
    if _BUILT:
        return
    if not os.path.exists(DB):
        _BUILT = True
        return
    try:
        con = sqlite3.connect(DB)
        rows = con.execute(
            'SELECT date, home, away, home_goals, away_goals, result FROM matches'
        ).fetchall()
        con.close()
    except Exception:
        _BUILT = True
        return

    for date_str, home, away, hg, ag, result in rows:
        if hg is None or ag is None or not result:
            continue
        ord_d = _parse_date(date_str)
        h_res = 'W' if result == 'H' else ('D' if result == 'D' else 'L')
        a_res = 'W' if result == 'A' else ('D' if result == 'D' else 'L')
        _CACHE.setdefault(home, []).append((ord_d, away,  True,  hg, ag, h_res))
        _CACHE.setdefault(away, []).append((ord_d, home,  False, ag, hg, a_res))
        key = frozenset({home, away})
        _H2H.setdefault(key, []).append((ord_d, home, hg, ag))

    for team in _CACHE:
        _CACHE[team].sort(key=lambda x: x[0])
    for key in _H2H:
        _H2H[key].sort(key=lambda x: x[0])
    _BUILT = True


def get_form(team: str, before_ordinal: int, home_only: bool = False, n: int = 5) -> dict:
    """Return form stats for team in their last n games before before_ordinal."""
    build_cache()
    records = [r for r in _CACHE.get(team, [])
               if r[0] < before_ordinal and (not home_only or r[2])]
    last_n = records[-n:] if len(records) >= n else records
    w = sum(1 for r in last_n if r[5] == 'W')
    d = sum(1 for r in last_n if r[5] == 'D')
    l = sum(1 for r in last_n if r[5] == 'L')
    gf = sum(r[3] for r in last_n)
    ga = sum(r[4] for r in last_n)
    return {'w5': w, 'd5': d, 'l5': l, 'gf5': gf, 'ga5': ga, 'games': len(last_n)}


def get_h2h(home: str, away: str, before_ordinal: int, n: int = 5) -> dict:
    """Return H2H record for home vs away in their last n meetings before before_ordinal."""
    build_cache()
    key = frozenset({home, away})
    records = [r for r in _H2H.get(key, []) if r[0] < before_ordinal]
    last_n = records[-n:]
    hw = sum(1 for r in last_n if r[1] == home and r[2] > r[3])
    draws = sum(1 for r in last_n if r[2] == r[3])
    aw = sum(1 for r in last_n if r[1] == away and r[3] > r[2])
    return {'home_w5': hw, 'draw5': draws, 'away_w5': aw, 'meetings': len(last_n)}
