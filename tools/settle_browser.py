"""
settle_browser.py
=================
Settles open 1X2 bets that the standard sources (ESPN / TheSportsDB /
Flashscore / Sofascore) couldn't match, using the browser-based score scraper.

Only handles 1X2 market — all other markets (BTTS, O/U, Goalscorer …) are
left OPEN because they need stats beyond a simple home/away score.

Run:
    .venv\\Scripts\\python.exe tools\\settle_browser.py          # settle all open 1X2
    .venv\\Scripts\\python.exe tools\\settle_browser.py --dry     # preview only
"""

import re
import sys
import sqlite3
import argparse
from pathlib import Path

# ── project imports ────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR / "src"))
sys.path.insert(0, str(BASE_DIR / "tools"))

from score_scraper import scrape_score, _teams_and_score_from_title  # noqa: E402

BET_LOG_PATH   = BASE_DIR / "data" / "bet_log.db"
BANKROLL_PATH  = BASE_DIR / "data" / "bankroll.db"


# ── helpers ────────────────────────────────────────────────────────────────

def _open_bets_1x2() -> list[dict]:
    conn = sqlite3.connect(BET_LOG_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT bet_id, match_id, player_id, market_type, side, entry_odds, stake, bet_source "
        "FROM bet_log WHERE result='OPEN' AND market_type='1X2' ORDER BY placed_at"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _strip_selection(s: str) -> str:
    """Remove a trailing bet selection like '(Away (2))' or '(Home (1))' from a string."""
    # Greedy match from first '(' — removes "(Away (2))", "(Home (1))", "(Draw (X))" etc.
    return re.sub(r'\s*\(.*\)\s*$', '', s).strip()


def _parse_teams(player_id: str, match_id: str) -> tuple[str, str]:
    """Extract clean home/away team names, stripping any trailing bet selection."""
    for candidate in [match_id, player_id]:
        src = _strip_selection((candidate or "").strip())
        if " vs " in src:
            h, a = src.split(" vs ", 1)
            return _strip_selection(h), _strip_selection(a)
    return _strip_selection((match_id or "").strip()), ""


def _similarity(a: str, b: str) -> float:
    """Simple token-overlap similarity between two team name strings."""
    a_tok = set(re.sub(r'[^a-z0-9 ]', '', a.lower()).split())
    b_tok = set(re.sub(r'[^a-z0-9 ]', '', b.lower()).split())
    if not a_tok or not b_tok:
        return 0.0
    return len(a_tok & b_tok) / max(len(a_tok), len(b_tok))


def _detect_url_swap(url: str, our_home: str, our_away: str) -> bool:
    """
    Check if a Sofascore URL lists teams in opposite order from our system.
    Sofascore slugs are typically 'home-team-away-team'; if our home appears
    after our away in the slug, the scores need swapping.
    Returns True if scores should be swapped.
    """
    m = re.search(r'/match/([^/?#]+)', url)
    if not m:
        return False
    slug_no_dash = m.group(1).replace('-', '')

    def key(name: str) -> str:
        return re.sub(r'[^a-z0-9]', '', name.lower())[:4]

    h_key = key(our_home)
    a_key = key(our_away)
    if not h_key or not a_key or h_key == a_key:
        return False

    h_pos = slug_no_dash.find(h_key)
    a_pos = slug_no_dash.find(a_key)
    if h_pos < 0 or a_pos < 0 or h_pos == a_pos:
        return False

    return a_pos < h_pos  # away listed before home in URL → teams swapped


def _correct_score_order(
    our_home: str,
    our_away: str,
    raw_home_score: int,
    raw_away_score: int,
    page_title: str,
    source_url: str = "",
) -> tuple[int, int]:
    """
    Sofascore may list teams in the opposite order from our system.
    1) Try to parse team order from the page title (most precise).
    2) Fall back to URL slug order when the title has no embedded score.
    Returns (our_home_score, our_away_score).
    """
    parsed = _teams_and_score_from_title(page_title)
    if parsed:
        page_t1, s1, s2, page_t2 = parsed

        sim_h1 = _similarity(our_home, page_t1)
        sim_h2 = _similarity(our_home, page_t2)
        sim_a1 = _similarity(our_away, page_t1)
        sim_a2 = _similarity(our_away, page_t2)

        score_direct  = sim_h1 + sim_a2
        score_swapped = sim_h2 + sim_a1

        if score_swapped > score_direct + 0.1:
            return s2, s1  # teams were reversed on the scraped page

        return s1, s2

    # Fallback: URL-slug detection (only when title parsing found no teams)
    if source_url and _detect_url_swap(source_url, our_home, our_away):
        return raw_away_score, raw_home_score

    return raw_home_score, raw_away_score


def _grade_1x2(side: str, home_score: int, away_score: int) -> str:
    """Return 'WIN', 'LOSS', or 'VOID'."""
    if home_score > away_score:
        actual = "home"
    elif away_score > home_score:
        actual = "away"
    else:
        actual = "draw"

    side_low = side.lower()
    if actual == "home"  and ("home" in side_low or "(1)" in side_low):
        return "WIN"
    if actual == "away"  and ("away" in side_low or "(2)" in side_low):
        return "WIN"
    if actual == "draw"  and ("draw" in side_low or "(x)" in side_low):
        return "WIN"
    return "LOSS"


def _settle(bet_id: str, result: str, stake: float, odds: float, dry: bool) -> float:
    if result == "WIN":
        payout = round(stake * odds, 4)
        pnl    = round(payout - stake, 4)
    else:
        payout = 0.0
        pnl    = -round(stake, 4)

    if dry:
        return pnl

    # Update bet_log
    conn = sqlite3.connect(BET_LOG_PATH)
    conn.execute(
        "UPDATE bet_log SET result=?, pnl=?, closing_odds=NULL, clv=NULL "
        "WHERE bet_id=?",
        (result, pnl, bet_id),
    )
    conn.commit()
    conn.close()

    # Update bankroll tracker
    from bankroll_tracker import register_settlement
    register_settlement(payout, pnl)

    return pnl


# ── main ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Settle open 1X2 bets via browser scraper")
    parser.add_argument("--dry", action="store_true", help="Preview only — do not write to DB")
    args = parser.parse_args()

    bets = _open_bets_1x2()
    if not bets:
        print("No open 1X2 bets found.")
        return

    print(f"Open 1X2 bets: {len(bets)}  [{'DRY RUN' if args.dry else 'LIVE'}]")

    settled = skipped = not_found = 0

    for bet in bets:
        home, away = _parse_teams(bet["player_id"] or "", bet["match_id"] or "")
        if not away:
            print(f"\nSKIP — cannot parse teams from: {bet['match_id']!r}")
            skipped += 1
            continue

        print(f"\n{'─'*60}")
        print(f"Match  : {home} vs {away}")
        print(f"Bet    : {bet['side']}  @ {bet['entry_odds']}  stake ${bet['stake']:.2f}  [{bet['bet_source']}]")

        result = scrape_score(home, away, headless=True)

        if not result:
            print("Score  : NOT FOUND — leaving OPEN")
            not_found += 1
            continue

        raw_hs = result["home_score"]
        raw_as = result["away_score"]
        page_title = result.get("page_title", "")
        src        = result["source"][:70]

        hs, as_ = _correct_score_order(home, away, raw_hs, raw_as, page_title, src)
        if (hs, as_) != (raw_hs, raw_as):
            print(f"Score  : {raw_hs}-{raw_as} raw -> {hs}-{as_} (teams reversed on page)  (via {src})")
        else:
            print(f"Score  : {hs}-{as_}  (via {src})")

        outcome = _grade_1x2(bet["side"], hs, as_)
        pnl = _settle(bet["bet_id"], outcome, bet["stake"], bet["entry_odds"], args.dry)

        tag = "[DRY]" if args.dry else ""
        print(f"Result : {outcome}  P&L: ${pnl:+.2f}  {tag}")
        settled += 1

    print(f"\n{'='*60}")
    print(f"Done — settled: {settled}  not found: {not_found}  skipped: {skipped}")


if __name__ == "__main__":
    main()
