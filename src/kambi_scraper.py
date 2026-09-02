"""
kambi_scraper.py — second FREE soft book (Unibet/Kambi) for line-shopping.
==========================================================================
The validated +1.9% CLV line-shopping edge is uncapturable with only ONE soft book
(Betarabia) — there's nothing to shop against. Kambi (Unibet's platform) exposes a
keyless public offering feed (plain requests, no key) with broad coverage and clean
English team names. Taking the BEST price across Betarabia + Kambi per selection is how
that edge becomes bankable.

Feed: eu-offering-api.kambicdn.com/offering/v2018/ub/listView/football.json
  events[].event: id, homeName, awayName, start (ISO), group (league)
  events[].betOffers[] where criterion.label == 'Full Time' == 1X2
  outcomes[]: label '1'/'X'/'2', odds in /1000 (8500 -> 8.50)

Public API:
    fetch_kambi_1x2() -> { 'Home vs Away': {home,draw,away,home_team,away_team,start,starts_ts,league} }
Cached (90s).
"""

import time
import datetime
import requests

_URL = (
    "https://eu-offering-api.kambicdn.com/offering/v2018/ub/listView/football.json"
    "?lang=en_GB&market=GB"
)
_H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/125.0 Safari/537.36",
    "Accept": "application/json",
}
_cache = {"ts": 0.0, "data": {}}
_TTL = 90


def cache_age_min():
    """Minutes since the current Kambi snapshot was fetched, or None if never.

    The bet gate needs to know how old the odds it is about to bet on actually
    are. Kambi's own TTL is 90s, so this is always well inside the 60-minute
    staleness limit — but it must be REPORTED, not assumed: when the Kambi
    branch reported nothing, every Kambi-priced fixture silently inherited the
    previous fixture's staleness and got rejected as stale.
    """
    if not _cache.get("ts"):
        return None
    return (time.time() - _cache["ts"]) / 60.0


def _starts_ts(iso):
    try:
        return datetime.datetime.fromisoformat(
            str(iso).replace("Z", "+00:00")
        ).timestamp()
    except Exception:
        return None


def fetch_kambi_1x2():
    if (time.time() - _cache["ts"]) < _TTL and _cache["data"]:
        return _cache["data"]
    out = {}
    try:
        r = requests.get(_URL, headers=_H, timeout=15)
        if r.status_code != 200:
            return _cache["data"] or {}
        events = r.json().get("events", []) or []
    except Exception as e:
        print(f"[KAMBI] feed error: {e}")
        return _cache["data"] or {}
    for ev in events:
        e = ev.get("event") or {}
        home, away = e.get("homeName"), e.get("awayName")
        if not home or not away:
            continue
        # Skip eSports / virtual football (FIFA player names in parens, "Esports"/"Cyber"
        # leagues) — not real matches, would pollute line-shopping.
        league_l = (e.get("group") or "").lower()
        if any(
            t in league_l
            for t in ("esport", "cyber", "battle", "2x4", "2x5", "2x6", "virtual")
        ):
            continue
        if "(" in home and ")" in home:  # "Real Madrid (player)" = esports
            continue
        prices = {}
        for bo in ev.get("betOffers") or []:
            if (bo.get("criterion") or {}).get("label") != "Full Time":
                continue
            for oc in bo.get("outcomes") or []:
                o = oc.get("odds")
                if o is None:
                    continue
                dec = round(o / 1000.0, 3)
                t = oc.get("type")
                if t == "OT_ONE":
                    prices["home"] = dec
                elif t == "OT_CROSS":
                    prices["draw"] = dec
                elif t == "OT_TWO":
                    prices["away"] = dec
            break
        if "home" in prices and "away" in prices:
            out[f"{home} vs {away}"] = {
                "home": prices.get("home"),
                "draw": prices.get("draw"),
                "away": prices.get("away"),
                "home_team": home,
                "away_team": away,
                "start": e.get("start"),
                "starts_ts": _starts_ts(e.get("start")),
                "league": (e.get("group") or ""),
            }
    _cache["ts"] = time.time()
    _cache["data"] = out
    return out


if __name__ == "__main__":
    import io, sys

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    d = fetch_kambi_1x2()
    print(f"Kambi 1X2 markets: {len(d)}")
    for k, v in list(d.items())[:12]:
        print(f"  {k}: H={v['home']} D={v['draw']} A={v['away']} | {v['league']}")
