"""
name_matching.py — fuzzy team/fixture name matching, shared across the
settlement pipeline (src/live_predictions_daemon.py's settle_open_bets())
and the phantom-fixture verifier (src/fixture_verifier.py).

Extracted 2026-07-10 from live_predictions_daemon.py so fixture_verifier.py
(a small, dependency-light module used by manual maintenance tools) doesn't
need to import that 6000+ line daemon module (which loads pandas/numpy/
joblib ML models at import time) just to reuse this pure string-matching
logic. No behavior change — live_predictions_daemon.py re-imports these same
names for backward compatibility with all its existing call sites.

Pure functions only: no network calls, no file I/O, no heavy dependencies
(stdlib re + unicodedata only).
"""

import re
import unicodedata

_TEAM_ALIASES = {
    "cote d ivoire": "ivory coast",
    "cote divoire": "ivory coast",
    "korea republic": "south korea",
    "korea dpr": "north korea",
    "ir iran": "iran",
    "china pr": "china",
    "usa": "united states",
    "czechia": "czech republic",
    "turkiye": "turkey",
    "cabo verde": "cape verde",
    "the gambia": "gambia",
    "congo dr": "dr congo",
    "dr congo": "dr congo",
    "viet nam": "vietnam",
    # Faroese clubs: Betarabia uses the full Faroese name; Flashscore uses the
    # English short-form abbreviation.  Zero token overlap -> must alias before tokenizing.
    "argja boltfelag": "ab argir",  # AB Argir (Argja Boltfelag Argir)
    "argja boltfelag argir": "ab argir",  # full form
    # Icelandic variants seen in Flashscore
    "breidablik": "breidablik",  # already matches; kept for docs
}


def _apply_aliases(n):
    # n is lowercased, accent-stripped, non-alnum collapsed to spaces, single-spaced.
    n = f" {n} "
    for variant, canon in _TEAM_ALIASES.items():
        n = n.replace(f" {variant} ", f" {canon} ")
    return n.strip()


# Age-group / reserve markers are DISTINGUISHING, not noise (fix 2026-07-11):
# a U23 side and its senior twin must never be treated as the same team, or
# the settlement matcher grades U23 bets against senior results (and vice
# versa). _level_signature() extracts a fixture level; get_match_score()
# refuses any cross-level pair. These markers are also stripped from the token
# comparison (see `noise` below) so same-level names still score normally
# (e.g. "River Plate Reserves" vs "River Plate Reserve").
_AGE_RE = re.compile(r"\bu\s*-?\s*(\d{2})\b")          # u23, u-23, u 23
_UNDER_RE = re.compile(r"\bunder\s*-?\s*(\d{2})\b")    # under 23, under-23
_RESERVE_TOKENS = {"reserves", "reserve", "ii"}         # incl. roman-II reserve side
_YOUTH_TOKENS = {"youth", "academy"}


def _level_signature(name):
    """Return the squad level of a team name: 'uNN' (age group), 'reserve',
    'youth', or 'senior' (default). Pure/among-stdlib; never raises."""
    if not name or not isinstance(name, str):
        return "senior"
    n = name.lower()
    n = "".join(
        c for c in unicodedata.normalize("NFD", n) if unicodedata.category(c) != "Mn"
    )
    n = re.sub(r"[^a-z0-9\s]", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    m = _AGE_RE.search(n) or _UNDER_RE.search(n)
    if m:
        return f"u{m.group(1)}"
    toks = set(n.split())
    if toks & _RESERVE_TOKENS:
        return "reserve"
    if toks & _YOUTH_TOKENS:
        return "youth"
    return "senior"


def get_match_score(name1, name2):
    if not name1 or not name2:
        return 0.0
    if not isinstance(name1, str) or not isinstance(name2, str):
        return 0.0

    # Cross-level pairs (senior vs U23, U21 vs U23, senior vs reserves, ...)
    # are never the same team — settle them separately or not at all.
    if _level_signature(name1) != _level_signature(name2):
        return 0.0

    def get_tokens(name):
        n = name.lower()
        n = "".join(
            c
            for c in unicodedata.normalize("NFD", n)
            if unicodedata.category(c) != "Mn"
        )
        n = re.sub(r"[^a-z0-9\s]", " ", n)
        n = _apply_aliases(re.sub(r"\s+", " ", n).strip())
        noise = {
            "fc",
            "cf",
            "sc",
            "pr",
            "united",
            "city",
            "town",
            "athletic",
            "club",
            "de",
            "fk",
            "afc",
            "sv",
            "sp",
            # Scandinavian / Eastern European suffixes
            "bk",
            "ik",
            "if",
            "sk",
            "aik",
            "ff",
            "bois",
            # Other common suffixes
            "ac",
            "hfc",
            "rfc",
            "utd",
            "jfc",
            # Level markers — DISTINCTION is handled by _level_signature() above;
            # strip them here so same-level names ("Reserves" vs "Reserve",
            # "Gully U23" vs "Gully SC U23") still score on the real name tokens.
            "u23",
            "u21",
            "u20",
            "u19",
            "u18",
            "u17",
            "u16",
            "u15",
            "ii",
            "reserve",
            "reserves",
            "youth",
            "academy",
        }
        return [w for w in n.split() if w and w not in noise]

    t1 = get_tokens(name1)
    t2 = get_tokens(name2)

    if not t1 or not t2:
        return 0.0
    if t1 == t2:
        return 1.0

    s1, s2 = set(t1), set(t2)
    if s1 == s2:
        return 0.95
    if s1.issubset(s2) or s2.issubset(s1):
        return 0.8 + 0.1 * (min(len(s1), len(s2)) / max(len(s1), len(s2)))

    intersection = s1.intersection(s2)
    union = s1.union(s2)
    if intersection:
        jaccard = len(intersection) / len(union)
        return 0.5 + 0.3 * jaccard

    if len(s1) == 1 and len(s2) == 1:
        w1 = list(s1)[0]
        w2 = list(s2)[0]
        if w1 in w2 or w2 in w1:
            return 0.6 * (min(len(w1), len(w2)) / max(len(w1), len(w2)))

    # Substring word matches
    sub_matches = 0
    for w1 in s1:
        for w2 in s2:
            if len(w1) > 3 and len(w2) > 3:
                if w1 in w2 or w2 in w1:
                    sub_matches += 1
    if sub_matches:
        return 0.3 + 0.2 * (sub_matches / max(len(s1), len(s2)))

    return 0.0


def fuzzy_match_teams(name1, name2):
    return get_match_score(name1, name2) >= 0.5


def best_fixture_match(home, away, finished_matches, min_side_score=0.5):
    """
    Find the best-matching entry in `finished_matches` (a {"Home vs Away":
    (home_score, away_score)} dict, as returned by the settlement scrapers)
    for the (home, away) fixture. Tries both name orientations (some feeds
    list the bet's home/away teams swapped).

    Returns (finished_name, (home_score, away_score), combined_score) for
    the best match, oriented so the returned score tuple always matches
    (home, away)'s perspective — or None if no candidate clears
    `min_side_score` on both sides.
    """
    best = None
    for finished_name, score in finished_matches.items():
        try:
            fin_home, fin_away = finished_name.split(" vs ", 1)
        except ValueError:
            continue

        h_score = get_match_score(home, fin_home)
        a_score = get_match_score(away, fin_away)
        if h_score >= min_side_score and a_score >= min_side_score:
            total = h_score + a_score
            if best is None or total > best[2]:
                best = (finished_name, score, total)

        # Reversed orientation: feed lists the two teams swapped vs the query.
        h_rev = get_match_score(home, fin_away)
        a_rev = get_match_score(away, fin_home)
        if h_rev >= min_side_score and a_rev >= min_side_score:
            total_rev = h_rev + a_rev
            if best is None or total_rev > best[2]:
                fin_hs, fin_as = score
                best = (finished_name + " [reversed]", (fin_as, fin_hs), total_rev)

    return best
