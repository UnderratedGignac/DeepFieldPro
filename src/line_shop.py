"""
line_shop.py — best 1X2 price across free soft books (Betarabia + Kambi/Unibet).
===============================================================================
The validated line-shopping edge (+1.9% CLV) = take the BEST price across books for a
pick you'd make anyway. With a second keyless soft book (Kambi) we can finally measure
and capture it. This module returns the best available price + which book offered it,
with STRICT matching + a price-ratio sanity guard so a wrong cross-book match can never
inflate a bet (the record was just made honest — keep it that way).

Used as METADATA first (record best_odds/best_book alongside each bet, place as usual),
so the uplift is measured before it's acted on.
"""

import re
import difflib
from src.kambi_scraper import fetch_kambi_1x2

_ALIASES = {
    "cabo verde": "cape verde",
    "cote d ivoire": "ivory coast",
    "korea republic": "south korea",
    "ir iran": "iran",
    "china pr": "china",
    "usa": "united states",
    "czechia": "czech republic",
}
_SIDE = {
    "home": "home",
    "1": "home",
    "draw": "draw",
    "x": "draw",
    "away": "away",
    "2": "away",
}


def _norm(s):
    n = "".join(c for c in (s or "").lower() if c.isalnum() or c == " ")
    n = re.sub(r"\s+", " ", n).strip()
    for a, b in _ALIASES.items():
        n = n.replace(a, b)
    return n


def _side_key(selection):
    s = (selection or "").lower()
    for k, v in _SIDE.items():
        if k in s or f"({k})" in s:
            return v
    return None


def _match(home, away, kambi):
    """Strict cross-book fixture match -> kambi entry, or None."""
    th, ta = _norm(home), _norm(away)
    best, best_score = None, 0.0
    for k, v in kambi.items():
        sh = difflib.SequenceMatcher(None, th, _norm(v["home_team"])).ratio()
        sa = difflib.SequenceMatcher(None, ta, _norm(v["away_team"])).ratio()
        sc = min(sh, sa)
        if sc > best_score:
            best, best_score = v, sc
    return best if best_score >= 0.85 else None  # strict: both teams must match well


def best_1x2(match, selection, betarabia_odds):
    """Return {best_odds, best_book, kambi_odds} for this pick across Betarabia + Kambi.
    Falls back to Betarabia-only when there's no confident cross-book match."""
    out = {"best_odds": betarabia_odds, "best_book": "Betarabia", "kambi_odds": None}
    try:
        parts = (match or "").split(" vs ")
        side = _side_key(selection)
        if len(parts) != 2 or side is None or not betarabia_odds:
            return out
        km = _match(parts[0].strip(), parts[1].strip(), fetch_kambi_1x2())
        if not km:
            return out
        k_odds = km.get(side)
        if not k_odds or k_odds <= 1.0:
            return out
        # Sanity: a Kambi price wildly different from Betarabia signals a wrong match or a
        # stale line — ignore it rather than trust a possibly-bogus better price.
        ratio = k_odds / betarabia_odds
        if ratio < 0.5 or ratio > 2.0:
            return out
        out["kambi_odds"] = round(k_odds, 3)
        if k_odds > betarabia_odds:
            out["best_odds"] = round(k_odds, 3)
            out["best_book"] = "Kambi"
    except Exception:
        pass
    return out


if __name__ == "__main__":
    print(best_1x2("Argentina vs Algeria", "Home (1)", 1.20))
