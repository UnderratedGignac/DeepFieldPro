"""
settle_from_sofascore.py — settle stuck OPEN bets from an official Sofascore score.
===================================================================================
For matches too obscure for the free results scraper (ESPN/TheSportsDB) — e.g. Brazilian
Série C/D — paste the Sofascore match URL and this settles the matching OPEN bet(s) using
the real final score. No paid key. Only the whitelisted markets (1X2, Over/Under 2.5,
BTTS) are graded — and ONLY ever from a real score (never fabricated).

Usage:
    # scrape the score from a Sofascore link, auto-match the OPEN bet by team names:
    python tools/settle_from_sofascore.py https://www.sofascore.com/football/match/<slug>/<id>

    # target a specific bet (substring of the bet's match name or its bet_id):
    python tools/settle_from_sofascore.py <sofascore_url> --bet "Manaus"

    # no link available? settle manually from a score you trust:
    python tools/settle_from_sofascore.py --manual "Gremio RR vs Manaus AM" 2 0

Always prints what it WILL do and asks nothing destructive without a match; pass --yes to
skip the confirmation prompt.
"""
import os
import sys
import sqlite3

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
DATA = os.path.join(BASE, "data")

from src.live_predictions_daemon import get_match_score  # reuse the alias-aware matcher


def _grade(market, side, hs, as_):
    """Return True/False/None (None = market not gradable here)."""
    s = (side or "").lower()
    total = hs + as_
    if market == "1X2":
        if "home" in s or s.strip().startswith("1") or "(1)" in s:
            return hs > as_
        if "draw" in s or "(x)" in s or s.strip() == "x":
            return hs == as_
        if "away" in s or "(2)" in s:
            return as_ > hs
    elif market in ("Over/Under 2.5", "Over/Under", "Total Goals"):
        if "over" in s:
            return total > 2.5
        if "under" in s:
            return total < 2.5
    elif market == "BTTS":
        if "yes" in s:
            return hs > 0 and as_ > 0
        if "no" in s:
            return hs == 0 or as_ == 0
    return None


def _find_open_bets(conn, home, away, bet_filter=None):
    rows = conn.execute(
        "SELECT bet_id, match_id, market_type, side, entry_odds, stake "
        "FROM bet_log WHERE result='OPEN'"
    ).fetchall()
    hits = []
    for bid, match_id, market, side, odds, stake in rows:
        if bet_filter:
            if bet_filter.lower() not in (bid or "").lower() and \
               bet_filter.lower() not in (match_id or "").lower():
                continue
        parts = (match_id or "").split(" vs ")
        if len(parts) != 2:
            continue
        bh, ba = parts[0].strip(), parts[1].strip()
        sh = get_match_score(bh, home)
        sa = get_match_score(ba, away)
        if sh >= 0.5 and sa >= 0.5:
            hits.append((bid, match_id, market, side, odds, stake, round(min(sh, sa), 2)))
    return hits


def settle(home, away, hs, as_, bet_filter=None, assume_yes=False):
    print(f"\nResult: {home} {hs}-{as_} {away}  (total {hs + as_})")
    conn = sqlite3.connect(os.path.join(DATA, "bet_log.db"))
    hits = _find_open_bets(conn, home, away, bet_filter)
    if not hits:
        print("  No OPEN bet matches those teams. Nothing to settle.")
        print("  (Tip: pass --bet \"<team substring>\" or check the names.)")
        conn.close()
        return
    print(f"  Matched {len(hits)} OPEN bet(s):")
    graded = []
    for bid, match_id, market, side, odds, stake, conf in hits:
        won = _grade(market, side, hs, as_)
        if won is None:
            print(f"   - {match_id} | {market} {side}: market not gradable (skipped)")
            continue
        pnl = round(stake * (odds - 1) if won else -stake, 2)
        payout = round(stake * odds if won else 0.0, 2)
        graded.append((bid, market, side, won, pnl, payout))
        print(f"   - {match_id} | {market} {side} @ {odds}  ->  "
              f"{'WIN' if won else 'LOSS'} (PnL {pnl:+.2f}) [match {conf}]")
    if not graded:
        conn.close()
        return
    if not assume_yes:
        ans = input("\nSettle these? [y/N] ").strip().lower()
        if ans != "y":
            print("Aborted; nothing changed.")
            conn.close()
            return
    from src.bankroll_tracker import register_settlement
    for bid, market, side, won, pnl, payout in graded:
        conn.execute(
            "UPDATE bet_log SET result=?, pnl=?, closing_odds=COALESCE(closing_odds, entry_odds) "
            "WHERE bet_id=?",
            ("W" if won else "L", pnl, bid),
        )
        register_settlement(payout, pnl)
    conn.commit()
    conn.close()
    print(f"\nSettled {len(graded)} bet(s). Done.")


def main():
    args = sys.argv[1:]
    assume_yes = "--yes" in args
    args = [a for a in args if a != "--yes"]

    if args and args[0] == "--manual":
        # --manual "Home vs Away" hs as
        match = args[1]
        hs, as_ = int(args[2]), int(args[3])
        home, away = [p.strip() for p in match.split(" vs ")]
        settle(home, away, hs, as_, assume_yes=assume_yes)
        return

    if not args:
        print(__doc__)
        return

    url = args[0]
    bet_filter = None
    if "--bet" in args:
        bet_filter = args[args.index("--bet") + 1]

    from src.sofascore_scraper import scrape_match
    print(f"Scraping {url} ...")
    r = scrape_match(url)
    if not r:
        print("  Could not read the match from Sofascore (page blocked or changed).")
        print("  Fall back to: --manual \"Home vs Away\" <hs> <as>")
        return
    if not r["finished"] or r["home_score"] is None:
        print(f"  Match not finished yet ({r['home']} vs {r['away']}). Try again later.")
        return
    settle(r["home"], r["away"], int(r["home_score"]), int(r["away_score"]),
           bet_filter=bet_filter, assume_yes=assume_yes)


if __name__ == "__main__":
    main()
