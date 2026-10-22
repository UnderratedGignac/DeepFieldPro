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
    fetch_kambi_1x2() -> { 'Home vs Away': {home,draw,away,home_team,away_team,start,starts_ts,league,event_id,state} }
    fetch_kambi_ou25() -> { 'Home vs Away': {over,under,home_team,away_team,starts_ts,league} }
    fetch_kambi_btts() -> { 'Home vs Away': {yes,no,home_team,away_team,starts_ts,league} }
Cached (90s for 1X2, 300s for O/U and BTTS).
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


def _is_esports(e):
    """eSports / virtual football: FIFA player names in parens, "Esports"/"Cyber"
    leagues. Not real matches; they would pollute line-shopping."""
    league_l = (e.get("group") or "").lower()
    if any(t in league_l for t in ("esport", "cyber", "battle", "2x4", "2x5", "2x6", "virtual")):
        return True
    home = e.get("homeName") or ""
    return "(" in home and ")" in home


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
        if _is_esports(e):
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
                "event_id": e.get("id"),
                "state": e.get("state"),
            }
    _cache["ts"] = time.time()
    _cache["data"] = out
    return out


# ── Over/Under 2.5 ──────────────────────────────────────────────────────────
# listView only carries the 1X2 ("Full Time") offer, so totals come from the
# per-event betoffer endpoint, which accepts comma-separated event ids.
# Full-time totals are criterion 1001159926 ("Total Goals"); first-half and
# team totals use other criteria. Lines and odds are in thousandths.
# Replies are paged (range: start/size/total, 2000 offers max). Unfiltered, a
# batch holding big matches ran to 8000+ offers and everything past page 1 was
# silently dropped — the senior Bayern and Real Madrid 2.5 lines among them.
# type=6 (Over/Under) keeps a batch near one page; the pager covers the rest.
_BETOFFER_URL = (
    "https://eu-offering-api.kambicdn.com/offering/v2018/ub/betoffer/event/{ids}.json"
    "?lang=en_GB&market=GB&type=6"
)
_OU_CRITERION_ID = 1001159926
_OU_LINE = 2500
_OU_BATCH = 40
_OU_PAGE = 2000
_OU_MAX_PAGES = 10
_OU_TTL = 300
_ou_cache = {"ts": 0.0, "data": {}}


def _fetch_bet_offers(ids_csv):
    """All bet offers for these events, following range pages to the total."""
    offers, start = [], 0
    for _ in range(_OU_MAX_PAGES):
        url = _BETOFFER_URL.format(ids=ids_csv)
        if start:
            url += f"&range_start={start}&range_size={_OU_PAGE}"
        r = requests.get(url, headers=_H, timeout=20)
        if r.status_code != 200:
            break
        j = r.json()
        page = j.get("betOffers") or []
        offers.extend(page)
        rng = j.get("range") or {}
        nxt = rng.get("start", 0) + rng.get("size", len(page))
        if not page or not rng or nxt >= rng.get("total", 0):
            break
        start = nxt
    return offers


def parse_ou25(bet_offers):
    """{eventId: {'over': x, 'under': y}} for the full-time 2.5 total only."""
    out = {}
    for bo in bet_offers or []:
        if (bo.get("criterion") or {}).get("id") != _OU_CRITERION_ID:
            continue
        prices = {}
        for oc in bo.get("outcomes") or []:
            if oc.get("line") != _OU_LINE or oc.get("odds") is None:
                continue
            side = {"OT_OVER": "over", "OT_UNDER": "under"}.get(oc.get("type"))
            if side is None:
                side = str(oc.get("label", "")).lower()
            if side in ("over", "under"):
                prices[side] = round(oc["odds"] / 1000.0, 3)
        if "over" in prices and "under" in prices:
            out[bo.get("eventId")] = prices
    return out


def ou_cache_age_min():
    """Minutes since the current Kambi O/U snapshot was fetched, or None if never."""
    if not _ou_cache.get("ts"):
        return None
    return (time.time() - _ou_cache["ts"]) / 60.0


def fetch_kambi_ou25():
    """{'Home vs Away': {over, under, home_team, away_team, starts_ts, league}}.

    Pre-match events only: the listView feed also carries in-play events, and
    an in-play price compared with a pre-kickoff fair price is not value.
    """
    if (time.time() - _ou_cache["ts"]) < _OU_TTL and _ou_cache["data"]:
        return _ou_cache["data"]
    now = time.time()
    by_id = {
        row["event_id"]: (key, row)
        for key, row in (fetch_kambi_1x2() or {}).items()
        if row.get("event_id")
        and row.get("state") == "NOT_STARTED"
        and (row.get("starts_ts") or 0) > now
    }
    if not by_id:
        return _ou_cache["data"] or {}
    ids = list(by_id)
    prices = {}
    for i in range(0, len(ids), _OU_BATCH):
        batch = ",".join(str(x) for x in ids[i : i + _OU_BATCH])
        try:
            prices.update(parse_ou25(_fetch_bet_offers(batch)))
        except Exception as e:
            print(f"[KAMBI] O/U batch error: {e}")
    out = {}
    for eid, p in prices.items():
        if eid not in by_id:
            continue
        key, row = by_id[eid]
        out[key] = {
            "over": p["over"],
            "under": p["under"],
            "home_team": row.get("home_team"),
            "away_team": row.get("away_team"),
            "starts_ts": row.get("starts_ts"),
            "league": row.get("league", ""),
        }
    _ou_cache["ts"] = time.time()
    _ou_cache["data"] = out
    return out


# ── Both Teams To Score ─────────────────────────────────────────────────────
# One listView request with category 11942 returns the BTTS offer for every
# listed event (criterion 1001642858, outcomes OT_YES / OT_NO in thousandths).
_BTTS_URL = _URL + "&category=11942"
_BTTS_CRITERION_ID = 1001642858
_BTTS_TTL = 300
_btts_cache = {"ts": 0.0, "data": {}}


def parse_btts(events, now_ts=None):
    """{'Home vs Away': {yes, no, home_team, away_team, starts_ts, league}}.

    Real pre-match events only: in-play prices are not comparable with a
    pre-kickoff fair price, and a suspended side (odds None) is skipped.
    """
    now_ts = time.time() if now_ts is None else now_ts
    out = {}
    for ev in events or []:
        e = ev.get("event") or {}
        home, away = e.get("homeName"), e.get("awayName")
        starts = _starts_ts(e.get("start"))
        if not home or not away or _is_esports(e):
            continue
        if e.get("state") != "NOT_STARTED" or not starts or starts <= now_ts:
            continue
        for bo in ev.get("betOffers") or []:
            if (bo.get("criterion") or {}).get("id") != _BTTS_CRITERION_ID:
                continue
            prices = {}
            for oc in bo.get("outcomes") or []:
                side = {"OT_YES": "yes", "OT_NO": "no"}.get(oc.get("type"))
                if side and oc.get("odds"):
                    prices[side] = round(oc["odds"] / 1000.0, 3)
            if "yes" in prices and "no" in prices:
                out[f"{home} vs {away}"] = {
                    **prices,
                    "home_team": home,
                    "away_team": away,
                    "starts_ts": starts,
                    "league": e.get("group") or "",
                }
            break
    return out


def btts_cache_age_min():
    """Minutes since the current Kambi BTTS snapshot was fetched, or None if never."""
    if not _btts_cache.get("ts"):
        return None
    return (time.time() - _btts_cache["ts"]) / 60.0


def fetch_kambi_btts():
    if (time.time() - _btts_cache["ts"]) < _BTTS_TTL and _btts_cache["data"]:
        return _btts_cache["data"]
    try:
        r = requests.get(_BTTS_URL, headers=_H, timeout=20)
        if r.status_code != 200:
            return _btts_cache["data"] or {}
        out = parse_btts(r.json().get("events"))
    except Exception as e:
        print(f"[KAMBI] BTTS feed error: {e}")
        return _btts_cache["data"] or {}
    _btts_cache["ts"] = time.time()
    _btts_cache["data"] = out
    return out


if __name__ == "__main__":
    import io, sys

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    d = fetch_kambi_1x2()
    print(f"Kambi 1X2 markets: {len(d)}")
    for k, v in list(d.items())[:12]:
        print(f"  {k}: H={v['home']} D={v['draw']} A={v['away']} | {v['league']}")
