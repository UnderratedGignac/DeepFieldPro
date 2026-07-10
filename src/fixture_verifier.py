"""
fixture_verifier.py — does this fixture actually exist? (phantom detector)
==========================================================================
Some bets get logged against GARBLED Betarabia fixtures that never correspond to a real
match (e.g. "Tindastoll vs Augnablik Under 2.5 @ 4.10" — a stale-odds artifact). No results
source can ever settle them, so they sit OPEN as "awaiting result" forever.

Bug fixed 2026-07-10: this used to rely SOLELY on a Flashscore team-search +
Playwright schedule-page scrape to decide REAL vs PHANTOM. That check has a
narrower/different coverage than the project's actual merged settlement
sources (ESPN/TheSportsDB, Flashscore's own results feed, API-Football,
Sofascore) and produced false positives -- e.g. "Real Oruro vs Universitario
de Vinto" was voided as PHANTOM despite having a clean, exact-match score
available in BOTH ESPN and Flashscore's results feeds. A fixture with a real,
findable score can never be a phantom, regardless of what the separate
schedule-page check finds.

Fix: verify() now accepts an optional `finished_matches` dict (the same
merged-sources dict settle_open_bets() builds — see
src/name_matching.py's best_fixture_match()). If a confident match already
exists there, the verdict is REAL immediately, no Flashscore/Playwright call
needed. Only when finished_matches has nothing (or isn't supplied) does it
fall back to the original search+schedule-page check.

This verifies a fixture against Flashscore, whose SEARCH endpoint is open (unlike Sofascore):
  1. Search both team names — if a team isn't a real Flashscore team, that's a red flag.
  2. Load the home team's results+fixtures page (Playwright) and check whether the away team
     appears in ANY recent/upcoming match. A real fixture leaves a trace on both teams'
     schedules; a phantom leaves none.

Returns a verdict so callers (tools/void_phantoms.py) can decide whether to void.

Public API:
    verify(home, away, finished_matches=None) -> {
        "verdict": "REAL" | "PHANTOM" | "UNKNOWN",
        "home_found": bool, "away_found": bool,
        "opponent_on_schedule": bool, "detail": str,
    }
Network + Playwright heavy — intended for on-demand sweeps, NOT the hot loop.
"""

import requests
import difflib

from src.name_matching import best_fixture_match

_SEARCH = (
    "https://s.livesport.services/api/v2/search/"
    "?q={q}&lang-id=1&project-id=2&project-type-id=1&sport-ids=1&type-ids=1,2,3,4"
)
_HDRS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/125.0 Safari/537.36",
    "Accept": "*/*",
    "Referer": "https://www.flashscore.com/",
}
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def _norm(s):
    return "".join(c for c in (s or "").lower() if c.isalnum() or c == " ").strip()


def _search_team(name):
    """Return the best-matching Flashscore Team entry for `name`, or None."""
    try:
        r = requests.get(
            _SEARCH.format(q=requests.utils.quote(name)), headers=_HDRS, timeout=15
        )
        if r.status_code != 200:
            return None
        items = [it for it in r.json() if it.get("type", {}).get("id") == 2]  # 2 = Team
    except Exception:
        return None
    target = _norm(name)
    best, best_score = None, 0.0
    for it in items:
        sc = difflib.SequenceMatcher(None, target, _norm(it.get("name", ""))).ratio()
        if sc > best_score:
            best, best_score = it, sc
    # Require a reasonable name match so "Tindastoll" doesn't match some unrelated club.
    return best if best and best_score >= 0.6 else None


_ROWS_JS = """() => {
    const out = [];
    document.querySelectorAll('.event__match').forEach(m => {
        const h = m.querySelector('.event__homeParticipant');
        const a = m.querySelector('.event__awayParticipant');
        if (h && a) out.push((h.innerText||'').trim() + ' | ' + (a.innerText||'').trim());
    });
    return out;
}"""


def _opponent_on_schedule(team_url, team_id, opponent_name):
    """Load the team's results + fixtures pages; is `opponent_name` on either?"""
    opp = _norm(opponent_name)
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return None  # Playwright unavailable -> can't confirm
    found = False
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            pg = b.new_page(user_agent=_UA)
            for tab in ("results", "fixtures"):
                try:
                    pg.goto(
                        f"https://www.flashscore.com/team/{team_url}/{team_id}/{tab}/",
                        wait_until="domcontentloaded",
                        timeout=30000,
                    )
                    pg.wait_for_timeout(3500)
                    for row in pg.evaluate(_ROWS_JS):
                        rl = _norm(row)
                        # token-overlap match so "Augnablik" hits "Augnablik Kopavogur"
                        if opp and (
                            opp in rl
                            or any(tok in rl for tok in opp.split() if len(tok) >= 4)
                        ):
                            found = True
                            break
                except Exception:
                    continue
                if found:
                    break
        finally:
            b.close()
    return found


def verify(home, away, finished_matches=None):
    # A fixture with a real, findable score in the merged settlement sources
    # can never be a phantom -- check this FIRST, before the weaker
    # Flashscore-search+schedule-page heuristic below ever runs.
    if finished_matches:
        match = best_fixture_match(home, away, finished_matches)
        if match:
            finished_name, score, _total = match
            return {
                "verdict": "REAL",
                "home_found": True,
                "away_found": True,
                "opponent_on_schedule": True,
                "detail": (
                    f"Confirmed via merged settlement sources: {finished_name!r} "
                    f"= {score} — a real, already-scoreable fixture, never a phantom."
                ),
            }

    h = _search_team(home)
    a = _search_team(away)
    res = {
        "verdict": "UNKNOWN",
        "home_found": bool(h),
        "away_found": bool(a),
        "opponent_on_schedule": False,
        "detail": "",
    }

    if not h and not a:
        res["verdict"] = "PHANTOM"
        res["detail"] = "Neither team exists on Flashscore."
        return res
    if not h or not a:
        missing = home if not h else away
        res["verdict"] = "PHANTOM"
        res["detail"] = f"Team not found on Flashscore: {missing!r}."
        return res

    on = _opponent_on_schedule(h["url"], h["id"], away)
    res["opponent_on_schedule"] = bool(on)
    if on is None:
        res["detail"] = (
            "Both teams exist but schedule could not be loaded (Playwright)."
        )
        res["verdict"] = "UNKNOWN"
    elif on:
        res["verdict"] = "REAL"
        res["detail"] = f"{away!r} appears on {home!r}'s Flashscore schedule."
    else:
        res["verdict"] = "PHANTOM"
        res["detail"] = (
            f"Both teams exist but {away!r} is NOT on {home!r}'s "
            f"results/fixtures — no such match."
        )
    return res


if __name__ == "__main__":
    import sys, json

    if len(sys.argv) >= 3:
        print(
            json.dumps(verify(sys.argv[1], sys.argv[2]), indent=2, ensure_ascii=False)
        )
    else:
        print("usage: python -m src.fixture_verifier <home> <away>")
