"""
sharp_scraper.py - Pinnacle (sharp book) 1X2 odds via the public guest API.
===========================================================================
Pinnacle is the sharpest mainstream book; its line movement is the steam signal
your backtests validated (tools/backtest_market_signals.py). We pull it here to
(a) detect REAL steam (the sharp line moving) and (b) spot when Betarabia is
lagging behind the sharp price (a better-than-close number we can still take).

No account needed: this uses Pinnacle's own guest web-client key. Two bulk calls
(matchups + straight markets) cover all soccer, so it's cheap to poll.

Public function:
    fetch_pinnacle_1x2() -> { "Home vs Away": {home,draw,away, league, starts, matchup_id} }
    decimal odds; None for a missing designation.
"""
import requests

BASE = "https://guest.api.arcadia.pinnacle.com/0.1"
HEADERS = {
    "x-api-key": "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R",
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
}
SOCCER = 29


def _get(path):
    r = requests.get(f"{BASE}{path}", headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.json()


def american_to_decimal(a):
    try:
        a = float(a)
    except (TypeError, ValueError):
        return None
    if a == 0:
        return None
    return round(1 + (a / 100.0 if a > 0 else 100.0 / -a), 4)


def fetch_pinnacle_1x2():
    """Return a dict keyed by 'Home vs Away' -> sharp 1X2 decimal odds + meta."""
    matchups = _get(f"/sports/{SOCCER}/matchups")
    markets = _get(f"/sports/{SOCCER}/markets/straight")

    # Index period-0 moneyline (= 1X2 for soccer) prices by matchup id.
    ml = {}
    for mk in markets:
        if mk.get("type") == "moneyline" and mk.get("period") == 0:
            mid = mk.get("matchupId")
            prices = {}
            for p in (mk.get("prices") or []):
                d = p.get("designation")
                if d:
                    prices[d] = american_to_decimal(p.get("price"))
            if mid is not None:
                ml[mid] = prices

    out = {}
    for m in matchups:
        if m.get("type") != "matchup" or m.get("parent"):
            continue
        parts = m.get("participants") or []
        if len(parts) != 2:
            continue
        home = next((p.get("name") for p in parts if p.get("alignment") == "home"), None)
        away = next((p.get("name") for p in parts if p.get("alignment") == "away"), None)
        if not home or not away:
            home, away = parts[0].get("name"), parts[1].get("name")
        if not home or not away:
            continue
        prices = ml.get(m.get("id"))
        if not prices or prices.get("home") is None or prices.get("away") is None:
            continue
        out[f"{home} vs {away}"] = {
            "home": prices.get("home"),
            "draw": prices.get("draw"),
            "away": prices.get("away"),
            "home_team": home,
            "away_team": away,
            "league": (m.get("league") or {}).get("name"),
            "starts": m.get("startTime"),
            "matchup_id": m.get("id"),
        }
    return out


def fetch_pinnacle_totals(line=2.5):
    """Return 'Home vs Away' -> sharp Over/Under at `line`, de-vigged. Pinnacle's de-vigged
    total-goals probability is the best free PREDICTOR of totals (better than any homegrown
    model — the project's model-on-totals lost). Used as the sharp fair line that soft books
    (Betarabia/Kambi) lag. Full match (period 0) only."""
    matchups = _get(f"/sports/{SOCCER}/matchups")
    markets = _get(f"/sports/{SOCCER}/markets/straight")
    key = f"s;0;ou;{line}"

    tot = {}
    for mk in markets:
        if mk.get("type") == "total" and mk.get("period") == 0 and mk.get("key") == key:
            o = u = None
            for p in (mk.get("prices") or []):
                if p.get("designation") == "over":
                    o = american_to_decimal(p.get("price"))
                elif p.get("designation") == "under":
                    u = american_to_decimal(p.get("price"))
            if o and u:
                io_, iu = 1.0 / o, 1.0 / u
                tot[mk.get("matchupId")] = {
                    "over_odds": o, "under_odds": u,
                    "over_prob": round(io_ / (io_ + iu), 4),
                    "under_prob": round(iu / (io_ + iu), 4),
                }

    out = {}
    for m in matchups:
        if m.get("type") != "matchup" or m.get("parent"):
            continue
        parts = m.get("participants") or []
        if len(parts) != 2:
            continue
        home = next((p.get("name") for p in parts if p.get("alignment") == "home"), None)
        away = next((p.get("name") for p in parts if p.get("alignment") == "away"), None)
        if not (home and away):
            continue
        t = tot.get(m.get("id"))
        if not t:
            continue
        out[f"{home} vs {away}"] = {**t, "line": line, "home_team": home,
                                    "away_team": away, "matchup_id": m.get("id"),
                                    "starts": m.get("startTime"),
                                    "league": (m.get("league") or {}).get("name")}
    return out


if __name__ == "__main__":
    data = fetch_pinnacle_1x2()
    print(f"Pinnacle soccer fixtures with 1X2: {len(data)}")
    for k, v in list(data.items())[:5]:
        print(f"  {k:45s} H={v['home']} D={v['draw']} A={v['away']}  [{v['league']}]")
    tot = fetch_pinnacle_totals()
    print(f"\nPinnacle fixtures with O/U 2.5: {len(tot)}")
    for k, v in list(tot.items())[:5]:
        print(f"  {k:45s} O2.5={v['over_odds']} U2.5={v['under_odds']} "
              f"P(over)={v['over_prob']:.0%}")
